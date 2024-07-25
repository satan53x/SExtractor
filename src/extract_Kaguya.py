import os
import re
from common import *
from extract_TXT import ParseVar, initParseVar, searchLine
from helper_text import generateBytes

XorTable = b'\xFF'

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
		textType, length, id = headerList[contentIndex]
		lineData = content[contentIndex]
		# 每行
		start = 0
		end = length
		index = lineData.find(manager.endStr)
		if index > 0:
			end = index
		#解密
		text = xorBytes(lineData[start:end], XorTable)
		if var.regList == []:
			text = text.decode(ExVar.OldEncodeName)
			ctrl = {'pos':[contentIndex, start, end]}
			if textType == 2: #名字类型
				ctrl['name'] = True
			if dealOnce(text, ctrl): 
				listCtrl.append(ctrl)
		else:
			var.lineData = text
			var.searchStart = start
			var.searchEnd = end
			var.contentIndex = contentIndex
			ctrls = searchLine(var)
			if ctrls:
				if textType == 2: #名字类型
					ctrls[0]['name'] = True
				lastCtrl = ctrls[-1]
				if lastCtrl and 'unfinish' in lastCtrl:
					del lastCtrl['unfinish']

# -----------------------------------
def replaceOnceImp(content, lCtrl, lTrans):
	num = len(lCtrl)
	for i in range(num):
		# 位置
		ctrl = lCtrl[i]
		contentIndex, start, end = ctrl['pos']
		transData = generateBytes(lTrans[i], end - start, ExVar.NewEncodeName)
		if transData == None:
			return False
		#加密
		transData = xorBytes(transData, XorTable)
		textType, length, id = headerList[contentIndex]
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
	addr = manager.arcHeaderLen
	ariCount = 1 #好像ari头部本身也算一个count
	for contentIndex in range(len(headerList)):
		textType, length, id = headerList[contentIndex]
		#还原控制段
		if manager.arcType == 2:
			prefix = int2bytes(id) + int2bytes(length, 2)
		else:
			prefix = int2bytes(textType) + int2bytes(length)
		content[contentIndex] = prefix + content[contentIndex]
		#索引
		if textType == 0 or manager.arcType == 1:
			#为ari添加索引
			ariCount += 1
			ariBuffer.extend(int2bytes(addr))
		#下一个地址
		addr += manager.headerLen + length #字符串header长度为8字节
	#写入arc包长
	if manager.arcType != 2:
		bs = int2bytes(addr, 4)
		ExVar.insertContent[0][manager.magicNumberLen:manager.magicNumberLen+4] = bs
	#修正ari头部
	ariBuffer[0:4] = int2bytes(ariCount)
	if fixLength:
		if manager.arcType == 1:
			#ari包含在arc中
			ExVar.insertContent[len(content)] = ariBuffer[4:] #不需要个数
	if exportAri:
		if manager.arcType == 1:
			printInfo('此版本ARC已包含ARI')
		elif manager.arcType == 2:
			printInfo('此版本没有ARI')
		else:
			#导出ari文件
			filepath = os.path.join(ExVar.workpath, 'new', 'TBLSTR.ARI')
			fileNew = open(filepath, 'wb')
			fileNew.write(ariBuffer)
			fileNew.close()

# -----------------------------------
def readFileDataImp(fileOld, contentSeparate):
	data = fileOld.read()
	manager.init(data)
	pos = manager.arcHeaderLen
	content = []
	insertContent = {
		0: bytearray(data[0:pos]) #header
	}
	headerList.clear()
	while pos < manager.strMaxAddr:
		if manager.arcType == 2:
			id = readInt(data, pos)
			pos += 4
			length = readInt(data, pos, 2)
			pos += 2
			headerList.append([0, length, id]) #没有字符串类型区别
		else:
			textType = readInt(data, pos)
			pos += 4
			length = readInt(data, pos)
			pos += 4
			headerList.append([textType, length, 0])
		end = pos + length
		content.append(data[pos:end])
		pos = end
	if manager.arcType == 1:
		insertContent[len(content)] = data[manager.strMaxAddr:] #ari索引区
	return content, insertContent

class Manager():
	def init(self, data):
		#类型
		if data[0:4] == 'UF01'.encode('ascii'):
			self.arcType = 1
			self.magicNumberLen = 4
		elif data[0:8] == '[STRTBL]'.encode('ascii'):
			self.arcType = 2
			self.magicNumberLen = 8
		else:
			self.arcType = 0
			self.magicNumberLen = 0
		#字符区最大位置
		if self.arcType == 2:
			self.arcHeaderLen = self.magicNumberLen + 8 #4字符串个数+4未知字节
			self.strMaxAddr = len(data) - self.arcHeaderLen
			self.headerLen = 6 #每个字符串前的控制长度
			self.endStr = bytes(xorBytes(b'\x00', XorTable))
		else:
			self.arcHeaderLen = self.magicNumberLen + 4 #4字符区地址
			self.strMaxAddr = readInt(data, self.magicNumberLen) 
			self.headerLen = 8
			self.endStr = b'\x00'

manager = Manager()