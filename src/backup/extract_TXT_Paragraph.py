import re
import sys
import os
import struct
from common import *
from extract_TXT import ParseVar, searchLine, initParseVar, dealLastCtrl
from extract_TXT import replaceOnceImp as replaceOnceImpTXT

def initExtra():
	msgPattern = ExVar.extraData
	return msgPattern

# ---------------- Group: TXT Paragraph -------------------
def parseImp(content, listCtrl, dealOnce):
	msgPattern = initExtra()
	checkLast = True
	var = ParseVar(listCtrl, dealOnce)
	initParseVar(var)
	lastCtrl = None
	for contentIndex in range(len(content)):
		if contentIndex < ExVar.startline: continue 
		var.lineData = content[contentIndex][:-1] #不检查末尾换行
		var.contentIndex = contentIndex
		ctrls = searchLine(var)
		if checkLast:
			lastCtrl = dealLastCtrl(lastCtrl, ctrls, contentIndex)
		#处理对话
		if ctrls and len(ctrls) > 0 and msgPattern != '':
			ctrl = ctrls[0]
			start = ctrl['pos'][1]
			end = ctrl['pos'][2]
			text = var.lineData[start:end]
			if re.search(msgPattern, text):
				ctrl['isMsg'] = True
				index = len(listCtrl) - 1 - len(ctrls)
				if index >= 0 and 'isMsg' not in listCtrl[index]:
					listCtrl[index]['name'] = True
	#文末处理
	if lastCtrl and 'unfinish' in lastCtrl:
		del lastCtrl['unfinish'] #段落结束

# -----------------------------------
def replaceOnceImp(content, lCtrl, lTrans):
	return replaceOnceImpTXT(content, lCtrl, lTrans)
