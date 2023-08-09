import re
import sys
import os
import struct
from common import *
from extract_TXT import searchLine, ParseVar, GetRegList, dealLastCtrl

OldEncodeName = 'cp932'
NewEncodeName = 'gbk'

# ---------------- Group: BIN -------------------
def parseImp(content, listCtrl, dealOnce):
	checkLast = GetG('Var').structure.startswith('para')
	var = ParseVar(listCtrl, dealOnce)
	var.OldEncodeName = OldEncodeName
	regDic = GetG('Var').regDic
	var.regList = GetRegList(regDic.items(), OldEncodeName)
	lastCtrl = None
	for contentIndex in range(len(content)):
		if contentIndex < GetG('Var').startline: continue 
		var.lineData = content[contentIndex]
		# 每行
		#print('>>> Line ' + str(contentIndex), ': ', var.lineData)
		var.contentIndex = contentIndex
		ctrls = searchLine(var)
		if checkLast:
			lastCtrl = dealLastCtrl(lastCtrl, ctrls)

# -----------------------------------
def replaceOnceImp(content, lCtrl, lTrans):
	#print(lCtrl)
	#print(lTrans)
	num = len(lCtrl)
	for i in range(num):
		# 位置
		ctrl = lCtrl[i]
		posData = ctrl['pos']
		contentIndex = posData[0]
		start = posData[1]
		end = posData[2]
		transData = generateBytes(lTrans[i], end - start, NewEncodeName)
		if transData == None:
			return False
		#写入new
		strNew = content[contentIndex][:start] + transData + content[contentIndex][end:]
		content[contentIndex] = strNew
	return True