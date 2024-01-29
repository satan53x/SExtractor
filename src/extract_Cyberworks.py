import re
from common import *
from extract_TXT import searchLine, ParseVar, dealLastCtrl, initParseVar
from extract_BIN import replaceOnceImp as replaceOnceImpBIN
from extract_BIN import parseImp as parseImpBIN

headerList = []

def initExtra():
	#默认编码
	if ExVar.extraData.startswith('readJIS'): return
	ExVar.OldEncodeName = 'utf-16-le'
	ExVar.NewEncodeName = 'utf-16-le'
	ExVar.pureText = True #强制使用纯文本模式，不然正则pattern编码会有问题

# ---------------- Engine: Cyberworks CSystem -------------------
def parseImp(content, listCtrl, dealOnce):	
	parseImpBIN(content, listCtrl, dealOnce)

# -----------------------------------
def replaceOnceImp(content, lCtrl, lTrans):
	replaceOnceImpBIN(content, lCtrl, lTrans)

def replaceEndImp(content):
	for contentIndex in range(len(content)):
		lineData = content[contentIndex]
		header = headerList[contentIndex]
		data = bytearray(b'\0\0\0\0') #长度占位
		if header['type'] == 'S': #文本
			#pre
			data.extend(header['pre'])
			#文本的字节长度
			textLen = len(lineData)
			bs = int2bytes(textLen)
			data.extend(bs)
			#xor密钥
			if textLen < 0x100:
				xorKey = bs[0:1]
			else:
				xorKey = None
				printWarningGreen('文本长度超过0x100', ExVar.filename, lineData)
			#文本加密
			bs = xorBytes(lineData, xorKey)
			data.extend(bs)
		elif header['type'] == 'T': #文本
			#pre
			data.extend(header['pre'])
			#文本的Unicode长度
			textLen = len(lineData)//2
			bs = int2bytes(textLen)
			data.extend(bs)
			#xor密钥
			xorKey = bs[0:2]
			#文本加密
			bs = xorBytes(lineData, xorKey)
			data.extend(bs)
		#post
		if 'post' in header:
			data.extend(header['post'])
		#设置长度
		length = len(data) - 4
		data[0:4] = int2bytes(length)
		#还原结构
		content[contentIndex] = data
	
# -----------------------------------
def readFileDataImp(fileOld, contentSeparate):
	initExtra()
	#读取
	data = fileOld.read()
	pos = 0
	content = []
	headerList.clear()
	while pos < len(data):
		length = readInt(data, pos)
		if length == 0:
			break
		pos += 4
		end = pos + length
		header = {}
		if data[pos] == 0x53: #文本S
			header['type'] = 'S'
			#pre
			pre = bytearray(data[pos:pos+1])
			header['pre'] = pre
			pos += 1
			#文本的字节长度
			textLen = readInt(data, pos)
			header['textLen'] = textLen
			#xor密钥
			if textLen < 0x100:
				xorKey = data[pos:pos+1]
			else:
				xorKey = None
				printWarningGreen('文本长度超过0x100', ExVar.filename, pos)
			pos += 4
			#文本解密
			bs = data[pos:pos+textLen] #字节长度
			bs = xorBytes(bs, xorKey)
			content.append(bs)
			pos += textLen
			#post
			if pos < end:
				post = data[pos:end]
				header['post'] = post
		elif data[pos] == 0x54: #文本T
			header['type'] = 'T'
			#pre
			pre = bytearray(data[pos:pos+5])
			header['pre'] = pre
			pos += 5
			#xor密钥
			xorKey = data[pos:pos+2]
			#文本的Unicode长度
			textLen = readInt(data, pos)
			header['textLen'] = textLen
			pos += 4
			#文本解密
			bs = data[pos:pos+textLen*2] #Unicode长度
			bs = xorBytes(bs, xorKey)
			content.append(bs)
			pos += textLen*2
			#post
			if pos < end:
				post = data[pos:end]
				header['post'] = post
		else:
			header['type'] = 'M'
			post = bytearray(data[pos:pos+length])
			header['post'] = post
			content.append(b'')
		#缓存头部
		headerList.append(header)
		pos = end
	#尾部非文本数据
	if pos < len(data):
		insertContent = {
			len(content): data[pos:]
		}
	else:
		insertContent = {}
	return content, insertContent