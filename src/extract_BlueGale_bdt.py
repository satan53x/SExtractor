import re
import struct
from common import *
from extract_BIN import replaceOnceImp as replaceOnceImpBIN
from extract_BIN import parseImp as parseImpBIN
from extract_TXT import ParseVar, initParseVar, searchLine, dealLastCtrl

exportIndex = True
MaxIndex = 0xFA0

# ---------------- Engine: BlueGale bdt -------------------
def parseImp(content, listCtrl, dealOnce):
	parseImpBIN(content, listCtrl, dealOnce)

# -----------------------------------
def replaceOnceImp(content, lCtrl, lTrans):
	return replaceOnceImpBIN(content, lCtrl, lTrans)


def replaceEndImp(content):
	separate = ExVar.contentSeparate.decode('unicode_escape').encode('latin-1')
	subPattern = re.compile(rb'^\t*[$%](.*)$')
	indexList = []
	data = bytearray()
	for i, lineData in enumerate(content):
		#索引
		m = subPattern.search(lineData)
		if m:
			name = m.group(1)
			offset = len(data) + m.start(1) - 1
			indexList.append((name, offset))
		#数据
		data.extend(lineData)
		if i < len(content)-1:
			data.extend(separate)
	if ExVar.decrypt & 2 == 2:
		data = decrypt(data) #加密
	content.clear()
	content.append(data)
	#输出索引
	if exportIndex:
		data = bytearray()
		empty = b'\x00' * 16
		for i in range(MaxIndex):
			if i < len(indexList):
				name, offset = indexList[i]
				if i+1 < len(indexList):
					offsetNex = indexList[i+1][1]
					length = offsetNex - offset
				else:
					length = 0
				bs = struct.pack('<8sII', name, offset, length)
				data.extend(bs)
			else:
				data.extend(empty)
		#导出文件
		filepath = os.path.join(ExVar.workpath, 'new', 'indexwww.dat')
		fileNew = open(filepath, 'wb')
		fileNew.write(data)
		fileNew.close()

# -----------------------------------
def readFileDataImp(fileOld, contentSeparate):
	global exportIndex
	exportIndex = False
	if ExVar.extraData:
		lst = ExVar.extraData.split(',')
		exportIndex = 'exportIndex' in lst
	data = bytearray(fileOld.read())
	if ExVar.decrypt & 1 == 1:
		data = decrypt(data)
	content = re.split(contentSeparate, data)
	return content, {}

#解密/加密
def decrypt(data:bytearray):
	for i in range(len(data)):
		data[i] ^= 0xFF
	return data