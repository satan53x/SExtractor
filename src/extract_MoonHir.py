import re
from common import *
from extract_BIN import replaceOnceImp as replaceOnceImpBIN
from extract_BIN import parseImp as parseImpBIN
from extract_TXT import GetRegList, ParseVar, searchLine

OldEncodeName = 'cp932'
NewEncodeName = 'gbk'

# ---------------- Engine: MoonHir -------------------
def parseImp(content, listCtrl, dealOnce):
	return parseImpBIN(content, listCtrl, dealOnce)

# -----------------------------------
def replaceOnceImp(content, lCtrl, lTrans):
	return replaceOnceImpBIN(content, lCtrl, lTrans)

# -----------------------------------
def readFileDataImp(fileOld, contentSeprate):
	data = fileOld.read()
	#文本为第一区块
	start = readInt(data, 8)
	size = readInt(data, 12)
	end = start + size
	if end > len(data):
		print('error: 区块结束超过了文件末尾')
		return [], {}
	realData = data[start:end]
	content = re.split(contentSeprate, realData)
	insertContent = { 
		0 : data[0:start],
		len(content) : data[end:]
	}
	return content, insertContent