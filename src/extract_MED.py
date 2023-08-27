import re
from common import *
from extract_BIN import replaceOnceImp as replaceOnceImpBIN

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
		elif re.match(r'【.*】'.encode(OldEncodeName), lineData): #名字
			start += 2
			end -= 2
			ctrl['isName'] = True #名字标记
		else: #对话
			if re.search(r'[^。）』】？」！]$', lineData.decode(OldEncodeName)):
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
		print('删除从该文件最后一行开始的unfinish控制段', ctrl, ExVar.filename)

# -----------------------------------
def replaceOnceImp(content, lCtrl, lTrans):
	return replaceOnceImpBIN(content, lCtrl, lTrans)
	
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
	content = re.split(contentSeprate, realData)
	insertContent = { 0 : data[0:skip] }
	return content, insertContent
