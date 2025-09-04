import re
import sys
import os
import struct
from common import *
from extract_TXT import searchLine, ParseVar, dealLastCtrl, initParseVar
from helper_text import generateBytes



# ---------------- Group: BIN -------------------
def parseImp(content, listCtrl, dealOnce):
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
		if var.checkLast:
			var.lastCtrl = dealLastCtrl(var.lastCtrl, ctrls, contentIndex)

# -----------------------------------
def replaceOnceImp(content, lCtrl, lTrans):
	#print(lCtrl)
	#print(lTrans)
	num = len(lCtrl)
	for i in range(num):
		# 位置
		ctrl = lCtrl[i]
		contentIndex, start, end = ctrl['pos']
		if contentIndex < 0: continue #不写回
		transData = generateBytes(lTrans[i], end - start, ExVar.NewEncodeName)
		if transData == None:
			return False
		#写入new
		diff = len(transData) - (end - start)
		preData = content[contentIndex][:start]
		if ExVar.preLen and ExVar.preLenFix:
			if diff != 0 and 'preLen' in ctrl:
				#需要修正
				preData = bytearray(preData)
				length = diff // ExVar.preLenScale + ctrl['preLen'][0]
				lenPos = ctrl['preLen'][1]
				preData[lenPos:lenPos+ExVar.preLen] = length.to_bytes(ExVar.preLen, 'little')
		strNew = preData + transData + content[contentIndex][end:]
		content[contentIndex] = strNew
		if ExVar.addrFixer:
			if diff != 0:
				#需要修正
				addrStart = ExVar.addrList[contentIndex] + start
				ExVar.addrFixer.fix(addrStart, diff)
	return True