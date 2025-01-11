import re
import pandas as pd
from common import *
from extract_TXT import ParseVar, searchLine, initParseVar, dealLastCtrl
from extract_TXT import replaceOnceImp as replaceOnceImpTXT
from helper_text import getBytes

separate = ''
validCols = []
nameCols = []
writeOffset = 0

# ---------------- Group: CSV/TSV -------------------
def parseImp(content, listCtrl, dealOnce):
	var = ParseVar(listCtrl, dealOnce)
	initParseVar(var)
	if ExVar.pureText:
		parseText(content, var)
	else:
		parse(content, var)
	
def parse(content, var:ParseVar):
	ExVar.pureText = 1
	for contentIndex, row in content.iterrows():
		for colIndex in validCols:
			var.lineData = row.iloc[colIndex]
			if pd.isnull(var.lineData):
				var.lineData = ''
			else:
				var.lineData = str(var.lineData)
			var.contentIndex = [contentIndex, colIndex]
			ctrls = searchLine(var)
			if colIndex in nameCols and ctrls and ctrls[0]:
				ctrls[0]['name'] = True
			if var.checkLast:
				var.lastCtrl = dealLastCtrl(var.lastCtrl, ctrls, contentIndex)
	ExVar.pureText = 0

def parseText(content, var:ParseVar):
	for contentIndex in range(len(content)):
		if contentIndex < ExVar.startline: continue 
		var.lineData = content[contentIndex][:-1] #不检查末尾换行
		var.contentIndex = contentIndex
		ctrls = searchLine(var)
		if ctrls == None or len(ctrls) > 0:
			#已匹配
			continue
		#按列处理
		start = 0
		col = 0
		ret = re.finditer(separate, content[contentIndex])
		for r in ret:
			end = r.start()
			if start < end and col in validCols:
				#有效行
				text = var.lineData[start:end]
				if var.postSkip and var.postSkip.search(text):
					start = r.end()
					col += 1
					continue
				ctrl = {'pos':[contentIndex, start, end]}
				if col in nameCols or text in var.nameList: #强制检查名字
					ctrl['name'] = True #名字标记
				if var.dealOnce(text, ctrl):
					var.listCtrl.append(ctrl)
			start = r.end()
			col += 1

# -----------------------------------
def replaceOnceImp(content, lCtrl, lTrans):
	if ExVar.pureText:
		return replaceOnceImpTXT(content, lCtrl, lTrans)
	#处理CSV
	num = len(lCtrl)
	for i in range(num):
		# 位置
		ctrl = lCtrl[i]
		posData = ctrl['pos']
		contentIndex, colIndex = posData[0]
		start = posData[1]
		end = posData[2]
		trans = lTrans[i]
		if ExVar.subsJis:
			transData = getBytes(trans, ExVar.NewEncodeName)
			trans = transData.decode(ExVar.JisEncodeName)
		#写入new
		strOld = content.iat[contentIndex, colIndex + writeOffset]
		if writeOffset != 0:
			if pd.isnull(strOld):
				content.iat[contentIndex, colIndex + writeOffset] = content.iat[contentIndex, colIndex]
				strOld = content.iat[contentIndex, colIndex + writeOffset]
		strNew = strOld[:start] + trans + strOld[end:]
		#print(strNew)
		content.iat[contentIndex, colIndex + writeOffset] = strNew
	return True

def replaceEndImp(content):
	if ExVar.pureText: return content
	#需要改变外部content
	if ExVar.extraData == 'nohead':
		data = content.to_csv(index=False, header=None, sep=separate)
	else:
		data = content.to_csv(index=False, sep=separate)
	ExVar.newline = ''
	ExVar.content = [data]

	
# -----------------------------------
import csv
def init(fileOld):
	global writeOffset
	global separate
	separate = ExVar.contentSeparate.encode().decode('unicode_escape')
	writeOffset = int(ExVar.writeOffset)
	if ExVar.extraData == 'nohead':
		content = pd.read_csv(fileOld, header=None, sep=separate, quoting=csv.QUOTE_MINIMAL)
		contentNames = None
		row = content.iloc[0]
		colMax = len(row)
	else:
		content = pd.read_csv(fileOld, sep=separate, quoting=csv.QUOTE_MINIMAL)
		contentNames = content.columns.tolist()
		colMax = len(contentNames)
	setValid(contentNames, colMax)
	return content

def initText(content):
	#分隔符
	global separate
	separate = f'[{ExVar.contentSeparate}\\n]'
	if ExVar.extraData == 'nohead':
		contentNames = None
	else:
		head = content[0].lstrip('#')
		contentNames = re.split(separate, head)
	setValid(contentNames)

def setValid(contentNames, colMax=9999):
	#有效列
	validCols.clear()
	nameCols.clear()
	if not ExVar.extractKey: return validCols
	if not contentNames or ExVar.extraData == 'useIndex':
		#按列索引
		valid = ExVar.extractKey.split(',')
		for s in valid:
			if s.startswith('name'):
				i = int(s[4:])
				nameCols.append(i)
			else:
				i = int(s)
			if i < colMax:
				validCols.append(i)
	else:
		#按列名
		valid = ExVar.extractKey
		for col, name in enumerate(contentNames):
			if re.search(valid, name):
				validCols.append(col)

def readFileDataImp(fileOld, contentSeparate):
	if ExVar.pureText:
		#TXT模式
		content = fileOld.readlines()
		initText(content)
	else:
		content = init(fileOld)
	return content, {}


