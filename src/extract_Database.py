import json
import os
import re
from common import *
from extract_TXT import ParseVar, searchLine, initParseVar
from extract_TXT import replaceOnceImp as replaceOnceImpTXT

def initExtra(firstLine):
	validCol = []
	if not ExVar.extraData: return validCol
	data = json.loads(ExVar.extraData)
	#检查首行
	if 'name' in data:
		validNameList = data['name']
		contentNames = firstLine.split('\t')
		for col, name in enumerate(contentNames):
			if name in validNameList:
				validCol.append(col)
	if 'col' in data:
		for colStr in data['col']:
			col = int(colStr)
			validCol.append(col)
	return validCol

# ---------------- Group: Database -------------------
def parseImp(content, listCtrl, dealOnce):
	var = ParseVar(listCtrl, dealOnce)
	initParseVar(var)
	validCol = initExtra(content[0][:-1])
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
		ret = re.finditer('[\t\n]', content[contentIndex])
		for r in ret:
			end = r.start()
			if start < end and col in validCol:
				#有效行
				text = var.lineData[start:end]
				if var.postSkip and re.search(var.postSkip, text):
					start = r.end()
					col += 1
					continue
				ctrl = {'pos':[contentIndex, start, end]}
				if text in var.nameList: #强制检查名字
					ctrl['isName'] = True #名字标记
				if dealOnce(text, contentIndex):
					listCtrl.append(ctrl)
			start = r.end()
			col += 1

# -----------------------------------
def replaceOnceImp(content, lCtrl, lTrans):
	replaceOnceImpTXT(content, lCtrl, lTrans)

