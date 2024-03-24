import re
import sys
import os
import struct
from common import *
from extract_TXT import searchLine, ParseVar, dealLastCtrl, initParseVar
from helper_text import generateBytes



# ---------------- Group: BIN -------------------
def parseImp(content, listCtrl, dealOnce):
	lastCtrl = None
	checkLast = ExVar.structure.startswith('para')
	var = ParseVar(listCtrl, dealOnce)
	var.OldEncodeName = ExVar.OldEncodeName
	initParseVar(var)
	for contentIndex in range(len(content)):
		if contentIndex < ExVar.startline: continue 
		var.lineData = content[contentIndex]
		# 每行
		#print('>>> Line ' + str(contentIndex), ': ', var.lineData)
		var.contentIndex = contentIndex
		ctrls = searchLine(var)
		if checkLast:
			lastCtrl = dealLastCtrl(lastCtrl, ctrls, contentIndex)

# -----------------------------------
def replaceOnceImp(content, lCtrl, lTrans):
	#print(lCtrl)
	#print(lTrans)
	num = len(lCtrl)
	for i in range(num):
		# 位置
		ctrl = lCtrl[i]
		contentIndex, start, end = ctrl['pos']
		transData = generateBytes(lTrans[i], end - start, ExVar.NewEncodeName)
		if transData == None:
			return False
		#写入new
		strNew = content[contentIndex][:start] + transData + content[contentIndex][end:]
		content[contentIndex] = strNew
	return True