import re
import sys
import os
import struct
from common import *

# ---------------- Group: AST -------------------
def parseImp(content, listCtrl, dealOnce):
	listIndex = 0
	dealText = 0 # 0不处理 1已读名字 尝试处理 2已进行处理至少一行
	ctrl = None
	text = ''
	start = 0
	end = 0
	for contentIndex in range(len(content)):
		if contentIndex < 1: continue #起始跳过行数
		lineData = content[contentIndex]
		#每行
		#print('>>> Line ' + str(contentIndex), ': ', lineData)
		if re.match(r'[/\*#]', lineData): continue#注释行
		if dealText == 1:
			if re.match(r'[\[\n]', lineData):
				dealText = 0 #废弃上一个名字
			elif ctrl:
				if dealOnce(text, listIndex): #保存名字
					listIndex += 1
					listCtrl.append(ctrl)
		if dealText == 0:
			dealText = 1
			if lineData == '\n':
				ctrl = None
				continue
			ret = re.match(r'\[.*?[ \]]', lineData)
			if ret: #控制行 先假设为名字行
				ret2 = re.search(r'表示=".*?"', lineData)
				if ret2:
					start = ret2.start() + 4
					end = ret2.end() - 1
					#print('表示=', lineData)
				else:
					start = ret.start() + 1
					end = ret.end() - 1
				text = lineData[start:end]
				ctrl = {'pos':[contentIndex, start, end]}
				ctrl["isName"] = True #名字标记
				#print(ctrl)
			continue
		#处理对话
		if lineData == '\n':
			ctrl = None
			dealText = 1
			if "notEnd" in listCtrl[-1]:
				del listCtrl[-1]["notEnd"]
			continue
		dealText = 2
		#print(lineData, start, len(lineData))
		start = 0
		end = len(lineData) - 1
		text = lineData[start:end]
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
		trans = lTrans[i]
		#写入new
		strNew = content[contentIndex][:start] + trans + content[contentIndex][end:]
		#print(strNew)
		content[contentIndex] = strNew
		return True