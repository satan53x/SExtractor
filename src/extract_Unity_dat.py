import re
from common import *
from extract_BIN import replaceOnceImp as replaceOnceImpBIN
from extract_BIN import parseImp as parseImpBIN

infoList = []
fixLength = True
alignBytes = True

def initExtra():
	if not ExVar.binEncodeValid:
		encode = 'utf-8'
		printInfo('启用默认文本编码:', encode)
		ExVar.OldEncodeName = encode
		ExVar.NewEncodeName = encode
	global fixLength, alignBytes
	if ExVar.extraData:
		lst = ExVar.extraData.split(',')
		fixLength = 'fixLength' in lst
		alignBytes = 'alignBytes' in lst

# ---------------- Engine: Unity mono -------------------
def parseImp(content, listCtrl, dealOnce):
	parseImpBIN(content, listCtrl, dealOnce)

# -----------------------------------
def replaceOnceImp(content, lCtrl, lTrans):
	return replaceOnceImpBIN(content, lCtrl, lTrans)

def replaceEndImp(content):
	data = bytearray()
	for i in range(len(content)):
		lineData = content[i]
		info = infoList[i]
		if i < len(content) - 1: #最后一个lineData始终为空
			nextInfo = infoList[i + 1]
			#修正长度
			if fixLength:
				oldLen = info['oldLen']
				newLen = len(lineData)
				if newLen != oldLen:
					#长度有变化
					info['pre'][-4:] = newLen.to_bytes(4, byteorder='little')
					if alignBytes:
						#修正对齐字节
						oldRemain = (4 - oldLen % 4) % 4
						newRemain = (4 - newLen % 4) % 4
						if newRemain > oldRemain:
							#添加
							nextInfo['pre'] = b'\x00'*(newRemain - oldRemain) + nextInfo['pre']
						elif newRemain < oldRemain:
							#删除
							nextInfo['pre'] = nextInfo['pre'][oldRemain-newRemain:]
		data.extend(info['pre'])
		data.extend(lineData)
	content.clear()
	content.append(data)


def readFileDataImp(fileOld, contentSeparate):
	initExtra()
	data = fileOld.read()
	content = []
	infoList.clear()
	pattern = re.compile(contentSeparate)
	oldPos = 0
	pos = 0
	while pos < len(data):
		m = pattern.search(data, pos)
		if m is None:
			break
		pos = m.start()
		length = int.from_bytes(data[pos-4:pos], byteorder='little')
		textLen = m.end() - m.start()
		if length != textLen:
			pos = m.end()
			continue
		#分块
		info = {'oldLen':textLen, 'pre':b''}
		if oldPos < pos:
			info['pre'] = bytearray(data[oldPos:pos])
		infoList.append(info)
		content.append(data[pos:m.end()])
		pos = m.end()
		oldPos = pos
	#结尾
	info = {'oldLen':0, 'pre':b''}
	info['pre'] = bytearray(data[oldPos:len(data)])
	infoList.append(info)
	content.append(b'')
	return content, {}
