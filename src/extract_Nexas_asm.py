import json
import re
from common import *
from extract_TXT import ParseVar, searchLine, initParseVar, dealLastCtrl
from extract_TXT import replaceOnceImp as replaceOnceImpTXT

checkList = {}
baseIndex = 0

def initExtra():
	global checkList, baseIndex
	checkList = json.loads(ExVar.extraData)
	baseIndex = 0
	for r in checkList:
		if "?P<name>" in r:
			break
		baseIndex += 1
	for i, r in enumerate(checkList):
		checkList[i] = re.compile(r)

# ---------------- Group: Nexas asm -------------------
def parseImp(content, listCtrl, dealOnce):
	initExtra()
	var = ParseVar(listCtrl, dealOnce)
	initParseVar(var)
	for contentIndex in range(len(content)):
		if contentIndex < ExVar.startline: continue 
		var.lineData = content[contentIndex]
		# 每行
		var.contentIndex = contentIndex
		ctrls = searchLine(var)
		if ctrls and len(ctrls) > 0:
			ctrl = ctrls[0]
			#校验名字
			if 'name' in ctrl:
				#检查前后
				checkIndex = ctrl['pos'][0]
				for i, r in enumerate(checkList):
					nowLine = content[checkIndex + i - baseIndex]
					if not r.search(nowLine):
						del ctrl['name']
						break
		if var.checkLast:
			var.lastCtrl = dealLastCtrl(var.lastCtrl, ctrls, contentIndex)

# -----------------------------------
def replaceOnceImp(content, lCtrl, lTrans):
	return replaceOnceImpTXT(content, lCtrl, lTrans)
