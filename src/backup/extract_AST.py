import re
import sys
import os
import struct
from common import *
from extract_BIN import replaceOnceImp as replaceOnceImpBIN


# ---------------- Group: AST -------------------
def parseImp(content, listCtrl, dealOnce):
	listIndex = 0
	dealText = 0 # 0不处理 1已读WINDOW 尝试处理 2已进行处理至少一行
	for contentIndex in range(len(content)):
		if contentIndex < 1: continue #起始跳过行数
		lineData = content[contentIndex]
		#每行
		#print('>>> Line ' + str(contentIndex), ': ', lineData)
		if dealText == 1:
			if re.match(rb'<', lineData):
				dealText = 0 #废弃上一个window
		if dealText == 0:
			if re.match(rb'[;\n]', lineData): continue#注释行
			if re.match(rb'<WINDOW', lineData): #名字行
				dealText = 1
				ret = re.search(rb'NAME=".*?"', lineData)
				if ret:
					start = ret.start() + 6
					end = ret.end() - 1
					text = lineData[start:end].decode(ExVar.OldEncodeName)
					ctrl = {'pos':[contentIndex, start, end]}
					ctrl['name'] = True #名字标记
					#print(ctrl)
					if dealOnce(text, listIndex):
						listIndex += 1
						listCtrl.append(ctrl)
			continue
		#处理对话
		else:
			if re.match(rb'[<\n]', lineData):
				dealText = 0
				if 'unfinish' in listCtrl[-1]:
					del listCtrl[-1]['unfinish']
				continue
			dealText = 2
			#print(lineData, start, len(lineData))
			start = 0
			end = len(lineData)
			ret = re.search(rb'<', lineData)
			if ret:
				end = ret.start()
			text = lineData[start:end].decode(ExVar.OldEncodeName)
			#0行数，1起始字符下标（包含），2结束字符下标（不包含）
			ctrl = {'pos':[contentIndex, start, end]}
			ctrl['unfinish'] = True
			#print(ctrl)
			if dealOnce(text, listIndex):
				listIndex += 1
				listCtrl.append(ctrl)

# -----------------------------------
def replaceOnceImp(content, lCtrl, lTrans):
	return replaceOnceImpBIN(content, lCtrl, lTrans)