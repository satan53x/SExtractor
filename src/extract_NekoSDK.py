import re
from common import *
from extract_BIN import replaceOnceImp as replaceOnceImpBIN
from extract_TXT import searchLine, ParseVar, initParseVar
from helper_text import generateBytes

# ---------------- Engine: NekoSDK -------------------
def parseImp(content, listCtrl, dealOnce):
	if not content[0][0:18] == b'NEKOSDK_ADVSCRIPT2':
		printError('文本头部不是NEKOSDK_ADVSCRIPT2', ExVar.filename)
		return
	var = ParseVar(listCtrl, dealOnce)
	var.OldEncodeName = ExVar.OldEncodeName
	initParseVar(var)
	for contentIndex in range(len(content)):
		if contentIndex < 1: continue 
		var.lineData = content[contentIndex]
		pos = 0
		length = readInt(var.lineData, pos)
		pos += 4 + length
		#名字
		length = readInt(var.lineData, pos) #有结束符\0
		pos += 4
		if length > 1:
			#有名字
			end = pos + length - 1
			text = var.lineData[pos:end].decode(ExVar.OldEncodeName)
			ctrl = {'pos':[contentIndex, pos, end]}
			ctrl['isName'] = True
			if var.dealOnce(text, contentIndex): listCtrl.append(ctrl)
		pos += length
		#对话/旁边
		length = readInt(var.lineData, pos) #有结束符\0
		pos += 4
		end = pos + length - 1
		text = var.lineData[pos:end].decode(ExVar.OldEncodeName)
		ctrl = {'pos':[contentIndex, pos, end]}
		if var.dealOnce(text, contentIndex): listCtrl.append(ctrl)

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
		if transData == None: return False
		#修正长度
		before = bytearray(content[contentIndex][:start])
		before[start-4:start] = int2bytes(len(transData) + 1)
		#写入new
		strNew = before + transData + content[contentIndex][end:]
		content[contentIndex] = strNew
	return True

# -----------------------------------
def readFileDataImp(fileOld, contentSeprate):
	data = fileOld.read()
	content = []
	start = 0
	pat = rb'\x5B\x83\x65\x83\x4C\x83\x58\x83\x67\x95\x5C\x8E\xA6\x5D'
	iter = re.finditer(pat, data)
	for r in iter:
		end = r.start() - 4 #长度
		content.append(data[start:end])
		start = end
	end = len(data)
	content.append(data[start:end])
	return content, {}