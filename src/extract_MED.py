import re
from common import *
from extract_BIN import replaceOnceImp as replaceOnceImpBIN
from extract_BIN import parseImp as parseImpBIN

# ---------------- Engine: MED -------------------
def parseImp(content, listCtrl, dealOnce):
	parseImpBIN(content, listCtrl, dealOnce)

# -----------------------------------
def replaceOnceImp(content, lCtrl, lTrans):
	return replaceOnceImpBIN(content, lCtrl, lTrans)
	
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
	insertContent = { 0 : data[0:skip] }
	return content, insertContent
