import os
import re
from common import *
from extract_TXT import ParseVar, initParseVar, searchLine
from helper_text import generateBytes

XorTable = b'\xFF'
StartLine = 1
MagicNumberLen = 4

fixLength = True #修正索引长度
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
	var.OldEncodeName = ExVar.OldEncodeName
	initParseVar(var)
	for contentIndex in range(len(content)):
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
		if var.regList == []:
			text = text.decode(ExVar.OldEncodeName)
			ctrl = {'pos':[contentIndex, start, end]}
			if textType == 2: #名字类型
				ctrl['isName'] = True
			if dealOnce(text, contentIndex): 
				listCtrl.append(ctrl)
		else:
			var.lineData = text
			var.searchStart = start
			var.searchEnd = end
			var.contentIndex = contentIndex
			ctrls = searchLine(var)
			if textType == 2: #名字类型
				ctrls[0]['isName'] = True
			lastCtrl = ctrls[-1]
			if lastCtrl and 'unfinish' in lastCtrl:
				del lastCtrl['unfinish']

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
		strNew = lineData[:start] + transData + lineData[end:]
		content[contentIndex] = strNew

	return True

# -----------------------------------
def replaceEndImp(content:list):
	#遍历
	ariBuffer = bytearray(b'\0\0\0\0') #ARI头部长度4，文本个数
	addr = MagicNumberLen + 4
	ariCount = 1 #好像ari头部本身也算一个count
	for contentIndex in range(len(headerList)):
		textType, length = headerList[contentIndex]
		#还原控制段
		prefix = int2bytes(textType) + int2bytes(length)
		content[contentIndex] = prefix + content[contentIndex]
		#索引
		if textType == 0 or MagicNumberLen > 0:
			#为ari添加索引
			ariCount += 1
			ariBuffer.extend(int2bytes(addr))
		#下一个地址
		addr += 8 + length #字符串header长度为8字节
	#写入arc包长
	b = int2bytes(addr, 4)
	ExVar.insertContent[0][MagicNumberLen:MagicNumberLen+4] = b
	#修正ari头部
	ariBuffer[0:4] = int2bytes(ariCount)
	if MagicNumberLen > 0 and fixLength:
		#ari包含在arc中
		ExVar.insertContent[len(content)] = ariBuffer[4:] #不需要个数
	if exportAri:
		if MagicNumberLen > 0:
			print('此版本ARC已包含ARI')
		else:
			#导出ari
			filepath = os.path.join(ExVar.workpath, 'new', 'TBLSTR.ARI')
			fileNew = open(filepath, 'wb')
			fileNew.write(ariBuffer)
			fileNew.close()

# -----------------------------------
def readFileDataImp(fileOld, contentSeprate):
	data = fileOld.read()
	global MagicNumberLen
	if data[0:4] == 'UF01'.encode('ascii'):
		MagicNumberLen = 4
	else:
		MagicNumberLen = 0
	pos = MagicNumberLen
	strMaxAddr = readInt(data, pos) #字符区最大位置
	content = []
	insertContent = {
		0: bytearray(data[0:pos+4]) #header
	}
	headerList.clear()
	pos += 4 
	while pos < strMaxAddr:
		textType = readInt(data, pos)
		pos += 4
		length = readInt(data, pos)
		pos += 4
		end = pos + length
		headerList.append([textType, length])
		content.append(data[pos:end])
		pos = end
	if MagicNumberLen > 0:
		insertContent[len(content)] = data[strMaxAddr:] #ari索引区
	return content, insertContent
