import os
import re
from common import *
from extract_BIN import replaceOnceImp as replaceOnceImpBIN
from extract_BIN import parseImp as parseImpBIN
from extract_TXT import GetRegList, ParseVar, dealLastCtrl, initParseVar, searchLine

OldEncodeName = 'cp932'
NewEncodeName = 'gbk'
XorTable = b'\xFF'
StartLine = 1
ArcHeaderLen = 4

fixLength = False #修正索引长度
exportAri = False #导出索引文件ari
headerList = []

def initExtra():
	global fixLength
	global exportAri
	lst = ExVar.extraData.split(',')
	fixLength = 'fixLength' in lst
	exportAri = 'exportAri' in lst

# ---------------- Engine: Kaguya TBLSTR -------------------
def parseImp(content, listCtrl, dealOnce):
	initExtra()
	var = ParseVar(listCtrl, dealOnce)
	var.OldEncodeName = OldEncodeName
	initParseVar(var)
	for contentIndex in range(len(content)):
		if contentIndex < StartLine: continue #第一行为总长
		textType, length = headerList[contentIndex]
		lineData = content[contentIndex]
		# 每行
		start = 0
		end = length
		index = lineData.find(b'\x00')
		if index > 0:
			end = index
		#解密
		text = xorBytes(lineData[start:end], XorTable)
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
		#加密
		transData = xorBytes(transData, XorTable)
		textType, length = headerList[contentIndex]
		lineData = content[contentIndex]
		#修正长度
		if fixLength:
			lenOrig = end - start
			length += len(transData) - lenOrig
			headerList[contentIndex][1] = length
		#写入new
		strNew = b''
		strNew += int2bytes(textType)
		strNew += int2bytes(length)
		strNew += lineData[:start] + transData + lineData[end:]
		content[contentIndex] = strNew

	return True

# -----------------------------------
def replaceEndImp(content):
	if not fixLength: return
	#遍历
	ariBuffer = bytearray(b'\0\0\0\0') #ARI头部长度4，文本个数
	addr = ArcHeaderLen
	ariCount = 1 #好像ari头部本身也算一个count
	for contentIndex in range(1, len(headerList)):
		textType, length = headerList[contentIndex]
		if exportAri:
			if textType == 0:
				#为ari添加文本索引
				ariCount += 1
				ariBuffer.extend(int2bytes(addr))
		#下一个地址
		addr += 8 + length #字符串header长度为8字节
	#写入arc包长
	b = int2bytes(addr, ArcHeaderLen)
	content[0][0:ArcHeaderLen] = b
	#导出ari
	if exportAri:
		#修正ari头部
		ariBuffer[0:4] = int2bytes(ariCount)
		#导出
		filepath = os.path.join(ExVar.workpath, 'new', 'TBLSTR.ARI')
		fileNew = open(filepath, 'wb')
		fileNew.write(ariBuffer)
		fileNew.close()

# -----------------------------------
def readFileDataImp(fileOld, contentSeprate):
	data = fileOld.read()
	totalLen = readInt(data, 0)
	content = []
	headerList.clear()
	headerList.append([])
	content.append(bytearray(data[0:ArcHeaderLen]))
	pos = ArcHeaderLen
	while pos < totalLen:
		textType = readInt(data, pos)
		pos += 4
		length = readInt(data, pos)
		pos += 4
		end = pos + length
		headerList.append([textType, length])
		content.append(data[pos:end])
		pos = end
	return content, {}