import json
import re
from common import *
from extract_TXT import searchLine, ParseVar, dealLastCtrl, initParseVar
from extract_BIN import replaceOnceImp as replaceOnceImpBIN
from extract_BIN import parseImp as parseImpBIN

XorTable = b'\xFF'

def initExtra():
	pass

# ---------------- Engine: Kaguya message.dat -------------------
def parseImp(content, listCtrl, dealOnce):	
	var = ParseVar(listCtrl, dealOnce)
	var.OldEncodeName = ExVar.OldEncodeName
	initParseVar(var)
	for contentIndex in range(len(content)):
		if contentIndex < ExVar.startline: continue 
		var.lineData = content[contentIndex]
		var.contentIndex = contentIndex
		col = -1 #列的索引
		start = 0
		end = 0
		count = 0 #每行内容数量，当为选项时则为0
		ret = re.finditer(b'\0', var.lineData)
		for r in ret:
			col += 1
			end = r.start()
			if col == 0:
				count = var.lineData[end + 1]
				if start < end:
					#有内容：名字或选项
					ctrl = {'pos':[var.contentIndex, start, end]}
					if count > 0:
						#名字
						ctrl['name'] = True
					text = var.lineData[start:end].decode(var.OldEncodeName)
					if var.dealOnce(text, var.contentIndex):
						var.listCtrl.append(ctrl)
				if count <= 0:
					#选项
					break
				start = end + 2
			else:
				if start < end:
					var.searchStart = start
					var.searchEnd = end
					searchLine(var)
				start = end + 1
		#每行结束
		if 'unfinish' in listCtrl[-1]:
			del listCtrl[-1]['unfinish']

# -----------------------------------
def replaceOnceImp(content, lCtrl, lTrans):
	replaceOnceImpBIN(content, lCtrl, lTrans)

def replaceEndImp(content):
	for contentIndex in range(len(content)):
		lineData = content[contentIndex]
		#设置长度
		length = len(lineData)
		data = int2bytes(length)
		#设置内容
		bs = xorBytes(lineData, XorTable)
		data += bs
		#还原结构
		content[contentIndex] = data
	
# -----------------------------------
Signature = b'[SCR-MESSAGE]'
def readFileDataImp(fileOld, contentSeparate):
	initExtra()
	#读取
	data = fileOld.read()
	pos = 0
	content = []
	insertContent = {}
	#Signature
	bs = data[pos:pos+len(Signature)]
	pos += len(Signature)
	if bs != Signature:
		printError('Signature不符合', bs)
		return content, insertContent
	#版本
	bs2 = bytearray(data[pos:pos+4])
	pos += 4
	offset = 1
	if bs2[3] >= 0x34:
		printError('版本不符合', bs2)
		return content, insertContent
	elif bs2[3] >= 3:
		offset = 2
	bs2.extend(data[pos:pos+offset])
	pos += offset
	insertContent[0] = bs + bs2
	#global XorTable
	#XorTable = bs2[4]
	#读取内容
	while pos < len(data):
		length = readInt(data, pos)
		if length == 0:
			break
		pos += 4
		end = pos + length
		bs = data[pos:end]
		bs = xorBytes(bs, XorTable)
		content.append(bs)
		pos = end
	#尾部非文本数据
	if pos < len(data):
		insertContent[len(content)] = data[pos:]
	return content, insertContent