import re
from common import *
from extract_TXT import replaceOnceImp as replaceOnceImpTXT
from extract_TXT import parseImp as parseImpTXT
import zlib

header = {'data':b''}
infoList = []
fixLength = True

def initExtra():
	if not ExVar.binEncodeValid:
		encode = 'utf-8'
		printInfo('启用默认文本编码:', encode)
		ExVar.OldEncodeName = encode
		ExVar.NewEncodeName = encode

# ---------------- Engine: GxEngine V3 mwb -------------------
def parseImp(content, listCtrl, dealOnce):
	parseImpTXT(content, listCtrl, dealOnce)

# -----------------------------------
def replaceOnceImp(content, lCtrl, lTrans):
	return replaceOnceImpTXT(content, lCtrl, lTrans)

def replaceEndImp(content):
	data = bytearray()
	for i in range(len(content)):
		lineData = content[i].encode(ExVar.NewEncodeName)
		info = infoList[i]
		if i < len(content) - 1: #最后一个lineData始终为空
			#修正长度
			if fixLength:
				oldLen = info['oldLen']
				newLen = len(lineData)
				if newLen != oldLen:
					#长度有变化
					info['pre'][-4:] = newLen.to_bytes(4, 'big')
		data.extend(info['pre'])
		data.extend(lineData)
	#压缩
	uncomSize = comSize = len(data)
	if ExVar.encrypt:
		data = zlib.compress(data)
		comSize = len(data)
	header['data'][-4:] = comSize.to_bytes(4, 'little')
	header['data'][-8:-4] = uncomSize.to_bytes(4, 'little')
	content.clear()
	content.append(header['data'])
	content.append(data)


def readFileDataImp(fileOld, contentSeparate):
	initExtra()
	data = fileOld.read()
	#解压
	header['data'] = bytearray(data[:0x1C])
	data = data[0x1C:]
	comSize = int.from_bytes(header['data'][-4:], byteorder='little')
	uncomSize = int.from_bytes(header['data'][-8:-4], byteorder='little')
	if uncomSize != comSize:
		printTip('进行解压:', ExVar.filename)
		data = zlib.decompress(data)
	#内容
	content = []
	infoList.clear()
	pattern = re.compile(contentSeparate)
	oldPos = 0
	pos = 0
	while pos < len(data):
		m = pattern.search(data, pos)
		if m is None:
			break
		pos = m.end()
		length = int.from_bytes(data[pos-4:pos], byteorder='big')
		end = pos+length
		bs = data[pos:end]
		try:
			text = bs.decode(ExVar.OldEncodeName)
		except:
			printDebug('Decode失败:', hex(pos))
			continue
		#分块
		info = {'oldLen':length, 'pre':b''}
		if oldPos < pos:
			info['pre'] = bytearray(data[oldPos:pos])
		infoList.append(info)
		content.append(text)
		pos = end
		oldPos = pos
	#结尾
	info = {'oldLen':0, 'pre':b''}
	info['pre'] = bytearray(data[oldPos:len(data)])
	infoList.append(info)
	content.append('')
	return content, {}
