import re
from common import *
from extract_BIN import replaceOnceImp as replaceOnceImpBIN
from extract_BIN import parseImp as parseImpBIN
from extract_TXT import GetRegList, ParseVar, dealLastCtrl, initParseVar, searchLine

OldEncodeName = 'cp932'
NewEncodeName = 'gbk'
XorTable = b'\xFF'

# ---------------- Engine: Kaguya TBLSTR -------------------
def parseImp(content, listCtrl, dealOnce):
	var = ParseVar(listCtrl, dealOnce)
	var.OldEncodeName = OldEncodeName
	initParseVar(var)
	for contentIndex in range(len(content)):
		if contentIndex < 1: continue #第一行为总长
		var.lineData:str = content[contentIndex]
		# 每行
		textType = readInt(var.lineData, 0)
		start = 8
		end = len(var.lineData)
		index = var.lineData.find(b'\x00', start)
		if index > 0:
			end = index
		#解密
		text = xorBytes(var.lineData[start:end], XorTable)
		text = text.decode(OldEncodeName)
		ctrl = {'pos':[contentIndex, start, end]}
		if textType == 2: #名字类型
			ctrl['isName'] = True
		if dealOnce(text, contentIndex): 
			listCtrl.append(ctrl)
				

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
		transData = generateBytes(lTrans[i], end - start, NewEncodeName)
		if transData == None:
			return False
		transData = xorBytes(transData, XorTable)
		#写入new
		strNew = content[contentIndex][:start] + transData + content[contentIndex][end:]
		content[contentIndex] = strNew
	return True

# -----------------------------------
def readFileDataImp(fileOld, contentSeprate):
	data = fileOld.read()
	arcLength = readInt(data, 0)
	content = []
	content.append(data[0:4])
	pos = 4
	while pos < arcLength:
		start = pos
		pos += 4
		length = readInt(data, pos)
		pos += 4
		end = pos + length
		content.append(data[start:end])
		pos = end
	return content, []