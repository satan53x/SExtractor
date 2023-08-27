import re
from common import *
from extract_BIN import replaceOnceImp as replaceOnceImpBIN
from extract_TXT import searchLine, ParseVar, GetRegList

OldEncodeName = 'cp932'
NewEncodeName = 'gbk'

# ---------------- Engine: NekoSDK -------------------
def parseImp(content, listCtrl, dealOnce):
	if not content[0][0:18] == b'NEKOSDK_ADVSCRIPT2':
		print('\033[33m文本头部不是NEKOSDK_ADVSCRIPT2\033[0m', ExVar.filename)
		return
	var = ParseVar()
	var.listIndex = 0
	var.listCtrl = listCtrl
	var.dealOnce = dealOnce
	var.OldEncodeName = OldEncodeName
	var.lineData = content[0]
	#print(len(content))
	searchBytes = '[テキスト表示]'.encode(OldEncodeName)
	ExVar.startline = 1
	pos = 18
	while True:
		pos = var.lineData.find(searchBytes, pos)
		if pos < 0: break
		#跳过
		length = int.from_bytes(var.lineData[pos-4:pos], byteorder='little')
		#print(length)
		pos += length
		#名字
		pos = readText(var, pos, 0)
		#对话或旁白
		pos = readText(var, pos, 1)

# textType: 0名字 1对话或旁白
def readText(var:ParseVar, pos, textType):
	length = int.from_bytes(var.lineData[pos:pos+4], byteorder='little')
	pos += 4
	startAll = pos
	pos += length
	endAll = pos - 1 #不包含末尾的\0
	textAll = var.lineData[startAll:endAll].decode(OldEncodeName)
	if textType == 0:
		#名字
		if textAll == '': return pos
		#0行数，1起始字符下标（包含），2结束字符下标（不包含）
		ctrl = {'pos':[0, startAll, endAll]}
		ctrl['isName'] = True
		if var.dealOnce(textAll, var.listIndex):
			var.listIndex += 1
			var.listCtrl.append(ctrl)
	else:
		#对话或旁白
		start = startAll
		end = startAll
		lastCtrl = None
		it = re.finditer(rb'\r\n', var.lineData[startAll:endAll])
		for r in it:
			end = r.start() + startAll
			text = var.lineData[start:end].decode(OldEncodeName)
			#0行数，1起始字符下标（包含），2结束字符下标（不包含）
			ctrl = {'pos':[0, start, end]}
			ctrl['unfinish'] = True
			if var.dealOnce(text, var.listIndex):
				var.listIndex += 1
				var.listCtrl.append(ctrl)
				lastCtrl = ctrl
			start = end + 2
		if start < endAll:
			end = endAll
			text = var.lineData[start:end].decode(OldEncodeName)
			#0行数，1起始字符下标（包含），2结束字符下标（不包含）
			ctrl = {'pos':[0, start, end]}
			if var.dealOnce(text, var.listIndex):
				var.listIndex += 1
				var.listCtrl.append(ctrl)
		elif lastCtrl:
			del lastCtrl['unfinish']
	return pos

# -----------------------------------
def replaceOnceImp(content, lCtrl, lTrans):
	return replaceOnceImpBIN(content, lCtrl, lTrans)