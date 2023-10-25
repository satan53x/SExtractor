import re
from common import *
from extract_BIN import replaceOnceImp as replaceOnceImpBIN
from extract_BIN import parseImp as parseImpBIN
from extract_TXT import GetRegList, ParseVar, searchLine

XorKey = b'\x2B\xC5\x2A\x3D'

headerList = []
insertContent = {}

# ---------------- Engine: MoonHir -------------------
def parseImp(content, listCtrl, dealOnce):
	return parseImpBIN(content, listCtrl, dealOnce)

# -----------------------------------
def replaceOnceImp(content, lCtrl, lTrans):
	return replaceOnceImpBIN(content, lCtrl, lTrans)

def replaceEndImp(content:list):
	totalLen = 0
	for contentIndex in range(len(content)):
		lineData = content[contentIndex]
		header = headerList[contentIndex]
		if header['segType'] == 0x08:
			#文本
			diffLen = len(lineData) - header['textLen']
			header['textLen'] += diffLen
			header['segLen'] += diffLen
			bs = bytearray()
			bs.extend(int2bytes(header['roleLen']))
			bs.extend(int2bytes(header['textLen']))
			if header['roleLen'] > 0:
				bs.extend(header['role'])
			#加密
			lineData = xorBytes(lineData, XorKey)
			bs.extend(lineData)
		else:
			bs = b''
		content[contentIndex] = int2bytes(header['segType']) + int2bytes(header['segLen']) + header['pre'] + bs
		totalLen += len(content[contentIndex])
	#修正总长度
	insertContent[0][-4:] = int2bytes(totalLen)

# -----------------------------------
def readFileDataImp(fileOld, contentSeprate):
	data = fileOld.read()
	#文本为第一区块
	pos = 0x4C
	insertContent.clear()
	insertContent[0] = bytearray(data[0:pos])
	content = []
	headerList.clear()
	while pos < len(data):
		segType = readInt(data, pos)
		pos += 4
		segLen =  readInt(data, pos)
		pos += 4
		header = {'segType':segType, 'segLen':segLen}
		if segType == 0x08:
			#文本
			header['pre'] = data[pos:pos+0x0C]
			pos += 0x0C
			roleLen = readInt(data, pos)
			header['roleLen'] = roleLen
			pos += 4
			textLen = readInt(data, pos)
			header['textLen'] = textLen
			pos += 4
			#角色
			if roleLen > 0:
				bs = data[pos:pos+roleLen]
				header['role'] = bs
				pos += roleLen
			#文本
			bs = data[pos:pos+textLen]
			pos += textLen
			#文本解密
			bs = xorBytes(bs, XorKey)
			content.append(bs)
		else:
			header['pre'] = data[pos:pos+segLen]
			pos += segLen
			content.append(b'')
		headerList.append(header)
	return content, insertContent