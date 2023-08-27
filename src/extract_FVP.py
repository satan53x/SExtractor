import re
from common import *
from extract_BIN import replaceOnceImp as replaceOnceImpBIN
from extract_TXT import searchLine, ParseVar, GetRegList

OldEncodeName = 'cp932'
NewEncodeName = 'gbk'

nameDic = {}
nameEnd = 0
msgStart = 0
unfinishBytes = 0

def initExtra():
	global nameEnd
	global msgStart
	global unfinishBytes
	lst = ExVar.extraData.split(',')
	nameEnd = int(lst[0], 16)
	msgStart = int(lst[1], 16)
	unfinishBytes = bytes.fromhex(lst[2])

# ---------------- Engine: FVP -------------------
def parseImp(content, listCtrl, dealOnce):
	initExtra()
	lineData = content[0]
	addrEnd = int.from_bytes(lineData[0:4], byteorder='little')
	offsetDic = {
		5: [0x02, 0x06, 0x07, 0x0A, 0x0D],
		3: [0x01, 0x03, 0x0B, 0x0F, 0x11, 0x15, 0x17],
		2: [0x0C, 0x10, 0x12, 0x16, 0x18],
		1: [0x04, 0x05, 0x08, 0x09, 0x13, 0x14, 0x19, 0x1A, \
			0x1B, 0x1C, 0x1D, 0x1E, 0x1F, 0x20, 0x21, 0x22, \
			0x23, 0x24, 0x25, 0x26, 0x27]
	}
	#regSkip = rb'^[A-Za-z]'
	var = ParseVar(listCtrl, dealOnce)
	var.lineData = lineData
	nameDic.clear()
	pos = 4
	while pos < addrEnd:
		key = lineData[pos]
		if key == 0x0E:
			#字符串
			count = lineData[pos+1]
			start = pos + 2
			end = start + count - 1 #去掉末尾\0
			pos = end + 1
			if count == 1: continue
			if end > nameEnd and start < msgStart: continue #跳过
			text = lineData[start:end]
			#if re.match(regSkip, text): continue
			text = text.decode(OldEncodeName)
			#0行数，1起始字符下标（包含），2结束字符下标（不包含）
			ctrl = {'pos':[0, start, end]}
			if end <= nameEnd: #名字
				if text.startswith('【'):
					nameDic[pos] = text[1:-1] #名字去掉【】，仅辅助不会导入
				else:
					nameDic[pos] = text
			elif start >= msgStart: #对话或旁白
				var.searchStart = start - 2
				name = searchName(var)
				if name:
					#额外增加不写回的名字
					ctrlName = {'pos':[0, -1, -1]}
					ctrlName['isName'] = True
					if dealOnce(name, start):
						listCtrl.append(ctrlName)
				var.searchStart = end + 1
				if checkUnfinish(var):
					ctrl['unfinish'] = True
					pass
			if dealOnce(text, start): 
				listCtrl.append(ctrl)
			continue
		#其他指令
		matched = False
		for offset, insList in offsetDic.items():
			if key in insList:
				pos += offset
				matched = True
				break
		if not matched:
			print('\033[31m错误指令编号\033[0m')
			return False
	
# -----------------------------------
#获取msg对应的名字
def searchName(var:ParseVar):	
	pos = var.searchStart - 5
	if var.lineData[pos] != 0x02: return None
	funcAddr = int.from_bytes(var.lineData[pos+1:pos+5], byteorder='little') # call func
	if funcAddr < nameEnd:
		lst = list(nameDic.keys())
		i = findInsertIndex(lst, funcAddr)
		if i >= len(lst) or lst[i] > nameEnd:
			print('searchName', '未找到名字', var.searchStart)
			return None
		pos -= 2
		name = nameDic[lst[i]]
		if var.lineData[pos] == 0x08:
			if name.startswith('？') :
				name = nameDic[lst[i+1]]
			return name
		elif var.lineData[pos] == 0x19:
			return name
		else:
			print('searchName', '未知指令', var.searchStart)
			return None

#检查msg是否是段落结束行
def checkUnfinish(var:ParseVar):
	pos = var.searchStart
	bs = var.lineData[pos:pos+len(unfinishBytes)]
	if bs == unfinishBytes:
		return True
	else:
		return False

# -----------------------------------
def replaceOnceImp(content, lCtrl, lTrans):
	#print(lCtrl)
	#print(lTrans)
	num = len(lCtrl)
	for i in range(num):
		# 位置
		ctrl = lCtrl[i]
		posData = ctrl['pos']
		contentIndex = posData[0]
		start = posData[1]
		end = posData[2]
		if start < 0: continue #不写回
		transData = generateBytes(lTrans[i], end - start, NewEncodeName)
		if transData == None:
			return False
		#写入new
		if ExVar.cutoff:
			mv = memoryview(content[contentIndex])
			mv[start:end] = transData
		else:
			strNew = content[contentIndex][:start] + transData + content[contentIndex][end:]
			content[contentIndex] = strNew
	return True