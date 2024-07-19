import re
from common import *
from extract_TXT import searchLine, ParseVar, dealLastCtrl, initParseVar
from extract_BIN import replaceOnceImp as replaceOnceImpBIN
from extract_BIN import parseImp as parseImpBIN
from helper_text import generateBytes

headerList = []

class Config():
	@classmethod
	def init0(self) -> 'Config':
		self.MessageSig = b'\x1F\x00\x00\x00\x00\x00'
		self.SelectSig = b'[\x1D\x11\x1C]\x00\x00\x00\x00\x00'
		self.JumpSig = b'[\x04\x05\x0A\x0D]\x00'
		return self
	
	@classmethod
	def init1(self) -> 'Config':
		self.MessageSig = b'\x1B\x00\x00\x00\x00\x00'
		self.SelectSig = b'[\x16]\x00\x00\x00\x00\x00'
		self.JumpSig = b'[\x04\x05\x0A\x0D]\x00'
		return self

# ---------------- Engine: AZSystem Encrypt Isaac -------------------
def parseImp(content, listCtrl, dealOnce):	
	var = ParseVar(listCtrl, dealOnce)
	var.OldEncodeName = ExVar.OldEncodeName
	initParseVar(var)
	for contentIndex in range(len(content)):
		var.lineData:str = content[contentIndex]
		if re.match(Config.MessageSig, var.lineData):
			#对话
			var.contentIndex = contentIndex
			pos = 10
			#首行为名字
			ret, length, var.searchStart, var.searchEnd = readText(var.lineData, pos)
			pos += length
			ctrls = searchLine(var)
			if ctrls and len(ctrls) > 0:
				ctrls[0]['name'] = True
			#第二行为文本
			ret, length, var.searchStart, var.searchEnd = readText(var.lineData, pos)
			pos += length
			ctrls = searchLine(var)
		elif re.match(Config.SelectSig, var.lineData):
			#选项
			var.contentIndex = contentIndex
			pos = 10
			while pos < len(var.lineData):
				ret, length, var.searchStart, var.searchEnd = readText(var.lineData, pos)
				pos += length
				if ret < 0: break
				elif ret > 0: continue
				ctrls = searchLine(var)
		#elif re.match(b'[\x04\x05\x0A\x0D\x02\x08]\x00', var.lineData):
		elif re.match(Config.JumpSig, var.lineData):
			#跳转
			var.contentIndex = contentIndex
			pos = 2
			jumpAddr = readInt(var.lineData, pos, 4)
			if jumpAddr < 0x80:
				continue
			if jumpAddr > headerList[-1]['addr']:
				printWarning('跳转地址异常', ExVar.filename, headerList[contentIndex]['addr'])
				continue
			#添加关联
			tagertIndex = -1
			for index, header in enumerate(headerList):
				if jumpAddr == header['addr']:
					tagertIndex = index
					break
			if tagertIndex < 0:
				printWarning('跳转地址无对应', ExVar.filename, headerList[contentIndex]['addr'])
				continue
			headerList[contentIndex]['ref'] = tagertIndex

def readText(data, pos):
	ret = -1
	length, start, end = 0, 0, 0
	if data[pos+1] == 0x07:
		#文本
		length = data[pos]
		start = pos+2
		end = pos + length - 1 #不包含末尾的\0
		ret = 0
	elif data[pos+1] in (0x06, 0x1C, 0x05, 0x04):
		#跳过控制
		length = data[pos]
		ret = 1
	else:
		pass
	return ret, length, start, end

# -----------------------------------
def replaceOnceImp(content, lCtrl, lTrans):
	for i in range(len(lCtrl)):
		# 位置
		ctrl = lCtrl[i]
		contentIndex, start, end = ctrl['pos']
		transData = generateBytes(lTrans[i], end - start, ExVar.NewEncodeName)
		if transData == None:
			return False
		#写入new
		strNew = content[contentIndex][:start] + transData + content[contentIndex][end:]
		content[contentIndex] = bytearray(strNew)
		#修正文本长度
		diff = end - start - len(transData)
		newLen = content[contentIndex][start - 2] - diff
		if newLen > 0xFF:
			printError('文本长度异常', ExVar.filename, lTrans[i])
		content[contentIndex][start - 2] = newLen 
	return True
	
def replaceEndImp(content):
	pos = 0
	for contentIndex in range(len(content)):
		#添加长度
		lineData = content[contentIndex]
		length = len(lineData) + 2
		bs = int2bytes(length, 2)
		content[contentIndex] = bytearray(bs + lineData)
		#修正地址
		headerList[contentIndex]['addr'] = pos
		pos += length
	for contentIndex in range(len(content)):
		lineData = content[contentIndex]
		header = headerList[contentIndex]
		if 'ref' in header:
			#修正跳转
			jumpAddr = headerList[header['ref']]['addr']
			lineData[4:8] = int2bytes(jumpAddr, 4)

# -----------------------------------
def readFileDataImp(fileOld, contentSeparate):
	if ExVar.extraData == 'type1':
		Config.init1()
	else:
		Config.init0()
	data = fileOld.read()
	pos = 0x10 #文件头部长度
	insertContent = {
		0: data[0:pos]
	}
	content = []
	headerList.clear()
	while pos < len(data):
		#按长度读取
		header = { 'addr': pos-0x10 }
		headerList.append(header)
		cmdLen = readInt(data, pos, 2)
		if cmdLen == 0:
			printError('命令长度为0，结构不匹配', ExVar.filename, pos)
			content.clear()
			break
		content.append(data[pos+2: pos+cmdLen])
		pos += cmdLen
	return content, insertContent


