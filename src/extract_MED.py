import re
from common import *
from extract_BIN import replaceOnceImp as replaceOnceImpBIN
from extract_BIN import parseImp as parseImpBIN

insertContent = {}

# ---------------- Engine: MED -------------------
def parseImp(content, listCtrl, dealOnce):
	parseImpBIN(content, listCtrl, dealOnce)

# -----------------------------------
def replaceOnceImp(content, lCtrl, lTrans):
	return replaceOnceImpBIN(content, lCtrl, lTrans)
	
def replaceEndImp(content):
	totalLen = 0
	for i in range(len(content)):
		totalLen += len(content[i]) + 1
	totalLen -= 1 #末尾没有\0
	headSec = insertContent[0]
	totalLen += len(headSec) - 0x10
	headSec[0:4] = int2bytes(totalLen, 4)
	
# -----------------------------------
def readFileDataImp(fileOld, contentSeparate):
	data = fileOld.read()
	skip = int.from_bytes(data[4:8], byteorder='little') + int.from_bytes(data[10:12], byteorder='little')*2 + 0x10
	#print('skip start', skip)
	if skip >= len(data):
		#print('skip is too big')
		return [], {}
	#if isShiftJis(data[skip], data[skip+1]) == False:
		#print('not start with shift-jis')
	realData = data[skip:]
	content = re.split(contentSeparate, realData)
	insertContent.clear()
	insertContent[0] = bytearray(data[0:skip])
	return content, insertContent
