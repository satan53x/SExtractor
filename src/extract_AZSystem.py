import re
from common import *
from extract_TXT import searchLine, ParseVar, dealLastCtrl, initParseVar
from extract_BIN import replaceOnceImp as replaceOnceImpBIN
from extract_BIN import parseImp as parseImpBIN
from helper_text import generateBytes

# ---------------- Engine: AZSystem Encrypt Isaac -------------------
def parseImp(content, listCtrl, dealOnce):	
	parseImpBIN(content, listCtrl, dealOnce)

# -----------------------------------
def replaceOnceImp(content, lCtrl, lTrans):
	num = len(lCtrl)
	for i in range(num):
		# 位置
		ctrl = lCtrl[i]
		posData = ctrl['pos']
		contentIndex = posData[0]
		start = posData[1]
		end = posData[2]
		transData = generateBytes(lTrans[i], end - start, ExVar.NewEncodeName)
		if transData == None:
			return False
		#写入new
		strNew = content[contentIndex][:start] + transData + content[contentIndex][end:]
		content[contentIndex] = bytearray(strNew)
		#修正长度
		diff = end - start - len(transData)
		content[contentIndex][start - 2] += diff 
	return True
	

	