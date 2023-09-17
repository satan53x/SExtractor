import re
from common import *
from extract_TXT_Paragraph import replaceOnceImp as replaceOnceImpTXT
from extract_TXT_Paragraph import parseImp as parseImpTXT

# ---------------- Engine: Unity 1 -------------------
def parseImp(content:list, listCtrl, dealOnce):
	for contentIndex in range(len(content)):
		lineData = content[contentIndex]
		if contentIndex < 1: continue
		if contentIndex == len(content) - 1:
			#处理结束行，分离行尾\0
			ret = re.search(b'\0+$', lineData)
			if ret:
				lineData = lineData[0:ret.start()]
		content[contentIndex] = lineData.decode('utf-8') + '\n' #bin转txt
	parseImpTXT(content, listCtrl, dealOnce)

# -----------------------------------
def replaceOnceImp(content, lCtrl, lTrans):
	return replaceOnceImpTXT(content, lCtrl, lTrans)

def replaceEndImp(content):
	totalLen = 0
	for contentIndex in range(len(content)):
		lineData = content[contentIndex][0:-1]
		if contentIndex >= ExVar.startline:
			content[contentIndex] = lineData.encode('utf-8')
		totalLen += len(content[contentIndex]) + 2
	totalLen -= 2 #最后一行不添加分隔符\r\n
	#重写长度
	data = bytearray(content[0])
	pos = 0
	nameLen = readInt(data, pos)
	remain =  nameLen % 4
	if remain > 0:
		nameLen = nameLen - remain + 4
	pos += 4 + nameLen
	data[pos:pos+4] = int2bytes(totalLen - pos - 4)
	content[0] = data
	#文件末尾补\0
	remain = totalLen % 4
	if remain > 0:
		for i in range(4 - remain):
			content[-1] += b'\0'
