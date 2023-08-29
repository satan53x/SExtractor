import json
import os
import re
from common import *
from extract_TXT import ParseVar, searchLine, initParseVar
from extract_TXT import replaceOnceImp as replaceOnceImpTXT

seprate = ''

def initExtra(content):
	#分隔符
	global seprate
	seprate = f'[{ExVar.contentSeprate}\\n]'
	#有效列
	validCols = []
	nameCols = []
	if not ExVar.extraData: return validCols
	if ExVar.structure == 'nohead':
		#按列索引
		valid = ExVar.extraData.split(',')
		for s in valid:
			if s.startswith('name'):
				i = int(s[4:])
				nameCols.append(i)
			else:
				i = int(s)
			validCols.append(i)
	else:
		#按列名
		valid = ExVar.extraData
		head = content[0].lstrip('#')
		contentNames = re.split(seprate, head)
		for col, name in enumerate(contentNames):
			if re.search(valid, name):
				validCols.append(col)
	return validCols, nameCols

# ---------------- Group: CSV/TSV -------------------
def parseImp(content, listCtrl, dealOnce):
	var = ParseVar(listCtrl, dealOnce)
	initParseVar(var)
	validCols, nameCols = initExtra(content)
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
		ret = re.finditer(seprate, content[contentIndex])
		for r in ret:
			end = r.start()
			if start < end and col in validCols:
				#有效行
				text = var.lineData[start:end]
				if var.postSkip and re.search(var.postSkip, text):
					start = r.end()
					col += 1
					continue
				ctrl = {'pos':[contentIndex, start, end]}
				if col in nameCols or text in var.nameList: #强制检查名字
					ctrl['isName'] = True #名字标记
				if dealOnce(text, contentIndex):
					listCtrl.append(ctrl)
			start = r.end()
			col += 1

# -----------------------------------
def replaceOnceImp(content, lCtrl, lTrans):
	replaceOnceImpTXT(content, lCtrl, lTrans)