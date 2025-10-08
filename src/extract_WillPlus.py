import re
from common import *
from extract_BIN import replaceOnceImp as replaceOnceImpBIN
from extract_TXT import searchLine, ParseVar, GetRegList

# ---------------- Engine: WillPlus -------------------
def parseImp(content, listCtrl, dealOnce):
	var = ParseVar(listCtrl, dealOnce)
	var.OldEncodeName = ExVar.OldEncodeName
	#print(len(content))
	regLists = [None, None]
	regLists[0] = GetRegList({
		'10_search': '^[^\0](?P<name>.*?)\0'
	}.items(), var.OldEncodeName)
	regLists[1] = GetRegList({
		'10_search': '^%[A-Z0-9]+(.*?)%[A-Z0-9]+%K',
		'11_search': '^(.*?)%K',
	}.items(), var.OldEncodeName)
	ExVar.startline = 1
	textType = -1
	for contentIndex in range(len(content)):
		if contentIndex < ExVar.startline: continue 
		lineData = content[contentIndex]
		# 每行
		#print('>>> Line ' + str(contentIndex), ': ', lineData)
		if  textType < 0:
			if lineData == b'%L':
				textType = 0
			elif lineData == b'char\0':
				textType = 1
			elif lineData == b'\x01\x0F' or lineData == b'\x00\x0F':
				textType = 2
			else:
				print('Not found textType')
			continue
		elif textType == 0 or textType == 1:
			#名字或对话
			var.contentIndex = contentIndex
			var.lineData = lineData
			var.regList = regLists[textType]
			searchLine(var)
		elif textType == 2:
			#textType = -1 #测试
			#continue #测试
			#选项
			count = lineData[0] #选项个数
			if count >= 6 or count == 0: 
				#printDebug('选项个数过滤', ExVar.filename)
				textType = -1
				continue #选项个数不能超过
			start = 1
			for i in range(count):
				start += 2
				ret = re.search(b'\0', lineData[start:])
				if ret == None:
					printError('select: Not found \\0')
					break
				elif isShiftJis(lineData[start], lineData[start+1]) == 0:
					printError('选项开头不是日文')
					break
				end = start + ret.start()
				text = lineData[start:end].decode(ExVar.OldEncodeName)
				#0行数，1起始字符下标（包含），2结束字符下标（不包含）
				ctrl = {'pos':[contentIndex, start, end]}
				#print(ctrl)
				if dealOnce(text, ctrl):
					var.listCtrl.append(ctrl)
				start = end + 5
				ret = re.search(b'\0', lineData[start:]) #跳过下一句
				if ret == None:
					print('select: Not found second \\0')
					break
				end = start + ret.start()
				start = end + 1
		else:
			print('Error textType')
		textType = -1

# -----------------------------------
def replaceOnceImp(content, lCtrl, lTrans):
	return replaceOnceImpBIN(content, lCtrl, lTrans)