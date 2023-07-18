import re
from common import *

OldEncodeName = 'cp932'
NewEncodeName = 'gbk'

# ---------------- Engine: MED -------------------
def parseImp(content, listCtrl, dealOnce):
	listIndex = 0
	#print(len(content))
	for contentIndex in range(len(content)):
		#if contentIndex < 1: continue 
		lineData = content[contentIndex]
		#每行
		#print('>>> Line ' + str(contentIndex), ': ', lineData)
		if lineData == b'': continue #空白行
		if re.match(rb'[#a-zA-Z0-9;:@\-\*_?\{\}\]]', lineData): continue #无数据行
		if re.match(rb'\[[=,0-9]', lineData): continue
		start = 0
		end = len(lineData)
		ctrl = {}
		if re.search(rb'\\N', lineData): #本行结束
			#print('start')
			pass
		elif re.match(r'【.*】'.encode('cp932'), lineData): #名字
			start += 2
			end -= 2
			ctrl['isName'] = True #名字标记
		else: #对话
			if re.search(r'[^。）』】？」！]$'.encode('cp932'), lineData):
				ctrl['unfinish'] = True
		text = lineData[start:end].decode(OldEncodeName)
		ctrl['pos'] = [contentIndex, start, end]
		#print(ctrl)
		if dealOnce(text, listIndex):
			listIndex += 1
			listCtrl.append(ctrl)
	#结束处理 删除从最后一行开始的unfinish
	pos = listIndex - 1
	while pos >= 0:
		ctrl = listCtrl[pos]
		if 'isName' in ctrl: break
		if 'unfinish' not in ctrl: break
		del listCtrl[pos]['unfinish']
		pos -= 1
		print('删除从该文件最后一行开始的unfinish控制段', ctrl, GetG('FileName'))

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
		transData = generateBytes(lTrans[i], end - start, NewEncodeName)
		if transData == None:
			return False
		#写入new
		strNew = content[contentIndex][:start] + transData + content[contentIndex][end:]
		content[contentIndex] = strNew
		return True
	
# -----------------------------------
def readFileDataImp(fileOld, contentSeprate):
	data = fileOld.read()
	skip = int.from_bytes(data[4:8], byteorder='little') + int.from_bytes(data[10:12], byteorder='little')*2 + 0x10
	#print('skip start', skip)
	if skip >= len(data):
		#print('skip is too big')
		return [], []
	#if isShiftJis(data[skip], data[skip+1]) == False:
		#print('not start with shift-jis')
	realData = data[skip:]
	content = realData.split(contentSeprate)
	insertContent = { 0 : data[0:skip] }
	return content, insertContent