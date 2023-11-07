import re
from common import *
from helper_text import generateBytes
from extract_TXT import ParseVar, initParseVar, searchLine

headerList = []
content = []
insertContent = {}

writeCompress = True
def initExtra():
	global writeCompress
	lst = ExVar.extraData.split(',')
	writeCompress = 'compress' in lst

# ---------------- Engine: CScript -------------------
def parseImp(content, listCtrl, dealOnce):
	var = ParseVar(listCtrl, dealOnce)
	var.OldEncodeName = ExVar.OldEncodeName
	initParseVar(var)
	for contentIndex in range(len(content)):
		header = headerList[contentIndex]
		if 'segType' in header:
			for i, lineData in enumerate(content[contentIndex]):
				if len(lineData) == 0: continue
				var.lineData = lineData
				var.contentIndex = [contentIndex, i]
				ctrls = searchLine(var)
				if 'name' in header and header['name'] == i:
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
		posData = ctrl['pos']
		contentIndex, lineIndex = posData[0]
		start = posData[1]
		end = posData[2]
		transData = generateBytes(lTrans[i], end - start, ExVar.NewEncodeName)
		if transData == None:
			return False
		#写入new
		strNew = content[contentIndex][lineIndex][:start] + transData + content[contentIndex][lineIndex][end:]
		content[contentIndex][lineIndex] = strNew
	return True

def replaceEndImp(content:list):
	data = bytearray()
	for contentIndex in range(len(content)):
		header = headerList[contentIndex]
		if 'segType' in header:
			#修正长度
			bs = bytearray()
			for i, lineData in enumerate(content[contentIndex]):
				length = len(lineData)
				bs.extend(int2bytes(length))
				bs.extend(lineData)
		else:
			bs = content[contentIndex]
		bs = header['pre'] + bs
		data.extend(bs)
	#压缩
	uncomLen = len(data)
	if writeCompress:
		data = compress(data)
		comLen = len(data)
	else:
		#不压缩
		comLen = int.from_bytes(insertContent[0][-8:-4], byteorder='little')
	content.clear()
	content.append(data)
	#修正头部
	insertContent[0][-8:-4] = int2bytes(comLen)
	insertContent[0][-4:] = int2bytes(uncomLen)

# -----------------------------------
def readFileDataImp(fileOld, contentSeprate):
	initExtra()
	data = fileOld.read()
	#文件头
	comLen = readInt(data, 0xC)
	uncomLen = readInt(data, 0x10)
	pos = 0x14
	insertContent.clear()
	insertContent[0] = bytearray(data[0:pos])
	#解压
	if len(data) - pos == comLen:
		data = uncompress(data[pos:pos+comLen], uncomLen)
	else:
		printWarningGreen('压缩长度与头部定义不同，不进行解压')
		data = data[pos:]
	if uncomLen != len(data):
		printWarning('解压长度与头部定义不同', uncomLen, len(data))
	#处理
	pos = 0
	content.clear()
	headerList.clear()
	pattern = re.compile(contentSeprate)
	start = 0
	while True:
		#查找
		ret = pattern.search(data, pos)
		if not ret: 
			pos = len(data) #结束
		else:
			pos = ret.start()
		if start < pos:
			#前置剩余字节
			headerList.append({'pre':data[start:pos]})
			content.append(b'')
			start = pos
		if pos >= len(data):
			break
		#检查文本
		segType = readInt(data, pos)
		header = {'segType':segType, 'pre':bytearray(data[pos:pos+4])}
		pos += 4
		if segType == 0x11:
			lineData, newPos = dealText(data, pos, header)
		elif segType == 0x14:
			lineData, newPos = dealSel(data, pos, header)
		else:
			printError('错误类型', segType)
		if lineData == None:
			continue
		pos = newPos
		start = pos
		content.append(lineData)
		headerList.append(header)
	return content, insertContent

#处理名字和对话
def dealText(data, pos, header):
	header['pre'].extend(data[pos:pos+4]) #序号
	pos += 4
	lineData = []
	#名字
	header['name'] = 0
	nameLen = readInt(data, pos)
	if nameLen < 0 or nameLen > 0x100:
		return None, 0
	pos += 4
	lineData.append(data[pos:pos+nameLen])
	pos += nameLen
	#消息
	msgLen = readInt(data, pos)
	pos += 4
	lineData.append(data[pos:pos+msgLen])
	pos += msgLen
	#检查
	dig = readInt(data, pos)
	if dig != 0:
		return None, 0
	return lineData, pos

#处理选项
def dealSel(data, pos, header):
	count = readInt(data, pos) #选项个数
	if count < 2 or count > 4:
		return None, 0
	header['pre'].extend(data[pos:pos+8]) #个数和0A
	pos += 8
	lineData = []
	for i in range(count):
		#选项
		msgLen = readInt(data, pos)
		if msgLen < 0 or msgLen > 0x400:
			return None, 0
		pos += 4
		lineData.append(data[pos:pos+msgLen])
		pos += msgLen
	#选项后的0A,0A
	#pos += (3+count) * 4
	return lineData, pos

# -----------------------------------
from libs.lzss import lzss_s
def uncompress(com, uncomSize=0):
	if uncomSize == 0: uncomSize = len(com)*8 #尽量大
	uncom = bytearray(uncomSize) 
	realsize = lzss_s.decompress(uncom, com)
	return uncom[0:realsize]

def compress(uncom):
	com = bytearray(uncom)
	realsize = lzss_s.compress(com, uncom)
	return com[0:realsize]
