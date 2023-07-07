import re
import sys
import os
import struct
from common import *

OldEncodeName = 'cp932'
NewEncodeName = 'gbk'

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
					text = lineData[start:end].decode(OldEncodeName)
					ctrl = {'pos':[contentIndex, start, end]}
					ctrl['isName'] = True #名字标记
					#print(ctrl)
					if dealOnce(text, listIndex):
						listIndex += 1
						listCtrl.append(ctrl)
			continue
		#处理对话
		else:
			if re.match(rb'[<\n]', lineData):
				dealText = 0
				if "notEnd" in listCtrl[-1]:
					del listCtrl[-1]["notEnd"]
				continue
			dealText = 2
			#print(lineData, start, len(lineData))
			start = 0
			end = len(lineData)
			ret = re.search(rb'<', lineData)
			if ret:
				end = ret.start()
			text = lineData[start:end].decode(OldEncodeName)
			#0行数，1起始字符下标（包含），2结束字符下标（不包含）
			ctrl = {'pos':[contentIndex, start, end]}
			ctrl["notEnd"] = True
			#print(ctrl)
			if dealOnce(text, listIndex):
				listIndex += 1
				listCtrl.append(ctrl)

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
		transData = lTrans[i].encode(NewEncodeName)
		# 检查长度
		lenOrig = end - start
		lenTrans = len(transData)
		#print(contentIndex, start, end)
		count = lenOrig - lenTrans
		#print('Diff', count)
		#写入new
		strNew = content[contentIndex][:start] + transData + content[contentIndex][end:]
		content[contentIndex] = strNew
		return True