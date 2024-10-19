import json
import re
from common import *
from helper_text import generateBytes
from extract_TXT import ParseVar, initParseVar, searchLine

headerList = []
content = []
insertContent = {}
addrFixer = None

writeCompress = True
fixJumpNormal = True
curConfig = None
fileType = 0
jumpCount = 0
TextSeq = 0
SelectSeq = 2
JumpSeq = 4
JumpNormalSeq = 6
JumpConditionSeq = 8

def initExtra():
	#写入是否压缩
	global writeCompress, fixNormalJump
	lst = ExVar.extraData.split(',')
	writeCompress = 'compress' in lst
	fixJumpNormal = 'fixJump' in lst
	if not fixJumpNormal:
		curConfig[JumpNormalSeq] = []
		curConfig[JumpConditionSeq] = []
	#类型控制
	if ExVar.ctrlStr:
		lst = eval(ExVar.ctrlStr)
		for i, cs in enumerate(lst):
			if cs == None: continue
			#修改控制字节
			newCs = []
			start = 0
			if len(cs) > 0:
				if cs[0] == None:
					#保留原始，即追加
					newCs = curConfig[i * 2]
					start = 1
			for j in range(start, len(cs)):
				if cs[j] not in newCs:
					newCs.append(cs[j])
			curConfig[i * 2] = newCs
				
def getSep():
	separate = bytearray(rb'[')
	for i in range(0, len(curConfig), 2):
		for j in curConfig[i]:
			bs = f'\\x{j:02X}'.encode('ASCII')
			separate.extend(bs)
	separate.extend(rb']\0\0\0')
	return bytes(separate)

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
	#打印
	if ExVar.isStart == 3:
		printInfo(f'Jump Count: {jumpCount}')

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
		#修正地址
		origLen  = end - start
		diff = len(transData) - origLen
		if diff != 0:
			addrStart = headerList[contentIndex]['addr'][lineIndex]
			addrFixer.fix(addrStart, diff)
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
				if i < len(header['pre']):
					bs.extend(header['pre'][i])
				if not header['hasText']:
					#跳转
					continue
				bs.extend(int2bytes(length))
				bs.extend(lineData)
		else:
			bs = header['pre'] + content[contentIndex]
		data.extend(bs)
	#修正跳转地址
	addrFixer.apply(data)
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
def readFileDataImp(fileOld, contentSeparate):
	global addrFixer, fileType, jumpCount, curConfig
	if ExVar.isStart == 1:
		jumpCount = 0
	addrFixer = AddrFixer()
	data = fileOld.read()
	#文件头 
	sig = readInt(data, 0)
	if isinstance(ExVar.version, str):
		fileType = int(ExVar.version, 0)
	else:
		fileType = ExVar.version
	if fileType == 0:
		if sig < 0x10:
			fileType = 1
		else:
			fileType = 10
	if fileType < 10:
		pos = 0x10
	else:
		pos = 0xC
	curConfig = config[fileType]
	comLen = readInt(data, pos)
	pos += 4
	uncomLen = readInt(data, pos)
	pos += 4
	insertContent.clear()
	insertContent[0] = bytearray(data[0:pos])
	initExtra()
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
	separate = getSep()
	pattern = re.compile(separate)
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
		pre = bytes(data[pos:pos+4])
		pos += 4
		lineData = None
		for i in range(0, len(curConfig), 2):
			if segType in curConfig[i]:
				deal = curConfig[i+1]
				header = {
					'segType':segType, 
					'pre':[bytearray(pre)],
					'hasText':False,
				}
				lineData, newPos = deal(data, pos, header)
				if lineData:
					break
		if lineData == None:
			continue
		pos = newPos
		start = pos
		content.append(lineData)
		headerList.append(header)
	return content, insertContent

#名字和对话
def dealText(data, pos, header):
	header['pre'][0].extend(data[pos:pos+4]) #序号
	pos += 4
	header['addr'] = []
	lineData = []
	#名字
	header['name'] = 0
	nameLen = readInt(data, pos)
	if nameLen < 0 or nameLen > 0x40:
		return None, 0
	pos += 4
	header['addr'].append(pos)
	lineData.append(data[pos:pos+nameLen])
	pos += nameLen
	#消息
	msgLen = readInt(data, pos)
	pos += 4
	header['addr'].append(pos)
	lineData.append(data[pos:pos+msgLen])
	pos += msgLen
	if pos >= len(data) or msgLen > 0x200:
		return None, 0
	#检查
	dig = readInt(data, pos)
	if dig != 0:
		return None, 0
	return lineData, pos

#选项
def dealSel(data, pos, header):
	count = readInt(data, pos) #选项个数
	if count < 2 or count > 5:
		return None, 0
	header['pre'][0].extend(data[pos:pos+8]) #个数和0A
	pos += 8
	header['addr'] = []
	lineData = []
	for i in range(count):
		if fileType == 11 and i > 0:
			header['pre'].append(data[pos:pos+4])
			pos += 4
		#选项
		msgLen = readInt(data, pos)
		if msgLen <= 0 or msgLen >= 0x200:
			return None, 0
		pos += 4
		header['addr'].append(pos)
		lineData.append(data[pos:pos+msgLen])
		pos += msgLen
	#选项后的0A,0A
	#pos += (3+count) * 4
	return lineData, pos

#名字和对话：sig 0
def dealText0(data, pos, header):
	header['pre'][0].extend(data[pos:pos+0x11]) #序号
	pos += 0x11
	header['addr'] = []
	lineData = []
	#名字
	header['name'] = 0
	nameLen = readInt(data, pos)
	if nameLen < 0 or nameLen > 0x40:
		return None, 0
	pos += 4
	header['addr'].append(pos)
	lineData.append(data[pos:pos+nameLen])
	pos += nameLen
	#消息
	header['pre'].append(data[pos:pos+5]) #空
	pos += 5
	msgLen = readInt(data, pos)
	pos += 4
	header['addr'].append(pos)
	lineData.append(data[pos:pos+msgLen])
	pos += msgLen
	header['hasText'] = True
	return lineData, pos

#选项：sig 0
def dealSel0(data, pos, header):
	header['pre'][0].extend(data[pos:pos+0x8]) #未知
	pos += 0x8
	count = readInt(data, pos) #选项个数
	if count < 2 or count > 5:
		return None, 0
	header['pre'][0].extend(data[pos:pos+0x15]) #个数和00
	pos += 0x15
	header['addr'] = []
	lineData = []
	for i in range(count):
		#选项
		if i > 0:
			header['pre'].append(data[pos:pos+5]) #空
			pos += 5
		msgLen = readInt(data, pos)
		if msgLen <= 0 or msgLen >= 0x100:
			return None, 0
		pos += 4
		header['addr'].append(pos)
		lineData.append(data[pos:pos+msgLen])
		pos += msgLen
	header['hasText'] = True
	return lineData, pos

JumpPostBytes = b'\x01\x00\x00\x00'
#跳转（分支）：sig 0
def dealJump0(data, pos, header):
	bs = data[pos:pos+len(JumpPostBytes)]
	if bs != JumpPostBytes:
		return None, 0
	header['pre'][0].extend(data[pos:pos+0x14]) #未知
	pos += 0x14
	count = readInt(data, pos) #跳转个数
	if count < 2 or count > 15:
		return None, 0
	header['pre'][0].extend(data[pos:pos+0x4]) #个数
	pos += 0x4
	lineData = []
	for i in range(count):
		#跳转
		if i > 0:
			header['pre'].append(data[pos:pos+0x28]) #固定长度
			pos += 0x28
		#添加监听
		realAddr, end, jumpStr = checkJump(data, pos)
		if realAddr < 0:
			return None, 0
		addrFixer.listen(pos, realAddr)
		lineData.append(b'')
		printDebug('分支跳转：', i, hex(pos), jumpStr.decode('ascii'))
		global jumpCount
		jumpCount += 1
	return lineData, pos

#跳转（普通）：sig 0
def dealJumpNormal0(data, pos, header):
	realAddr, end, jumpStr = checkJump(data, pos)
	if realAddr < 0:
		return None, 0
	lineData = []
	addrFixer.listen(pos, realAddr)
	lineData.append(b'')
	printDebug('普通跳转：', hex(pos), jumpStr.decode('ascii'))
	global jumpCount
	jumpCount += 1
	header['pre'][0].extend(data[pos:end])
	pos = end
	return lineData, pos

def dealJumpCondition0(data, pos, header):
	bs = data[pos:pos+len(JumpPostBytes)]
	if bs != JumpPostBytes:
		return None, 0
	header['pre'][0].extend(data[pos:pos+0x24]) #未知
	pos += 0x24
	#跳转地址
	realAddr, end, jumpStr = checkJump(data, pos)
	if realAddr < 0:
		return None, 0
	lineData = []
	addrFixer.listen(pos, realAddr)
	lineData.append(b'')
	printDebug('条件跳转：', hex(pos), jumpStr.decode('ascii'))
	global jumpCount
	jumpCount += 1
	header['pre'][0].extend(data[pos:end])
	pos = end
	return lineData, pos

patZero = re.compile(b'\x00')
patAscii = re.compile(b'^[A-Za-z0-9_]{1,32}$')
def checkJump(data, pos):
	realAddr = readInt(data, pos)
	pos += 4
	if realAddr >= len(data) or realAddr == 0:
		return -1, 0, b''
	m = patZero.search(data, pos)
	if m:
		jumpStr = data[pos:m.start()]
		if patAscii.search(jumpStr):
			return realAddr, m.start(), jumpStr
	return -2, 0, b''

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

# -----------------------------------
config = {
	1: [
		[0x3F], dealText0, 
		[0x15,0x1A], dealSel0, 
		[0x16,0x17], dealJump0,
		[0x14,0x15], dealJumpNormal0,
		[0x18,0x19], dealJumpCondition0,
	],
	10: [
		[0x11], dealText, 
		[0x14], dealSel, 
		[], dealJump0, #TODO跳转
		[], dealJumpNormal0, #TODO跳转
		[], dealJumpCondition0, #TODO跳转
	],
	11: [
		[0x11], dealText, 
		[0x14], dealSel, 
		[], dealJump0, #TODO跳转
		[], dealJumpNormal0, #TODO跳转
		[], dealJumpCondition0, #TODO跳转
	], 
}
