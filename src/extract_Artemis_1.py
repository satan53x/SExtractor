import re
import sys
import os
import struct
from common import *

# ---------------- Group: AST -------------------
def parseImp(content, listCtrl, dealOnce):
	listIndex = 0
	prelineIsText = False
	for contentIndex in range(len(content)):
		if contentIndex < 1: continue #起始跳过行数
		lineData = content[contentIndex]
		#每行
		#print('>>> Line ' + str(contentIndex), ': ', lineData)
		#非对话
		if re.match(r'[/\*#\n\[]', lineData):
			prelineIsText = False
			ret = re.match(r'\[.*?[ \]]', lineData)
			if ret:
				start = ret.start() + 1
				end = ret.end() - 1
				text = lineData[start:end]
				if re.match(r'[&a-zA-Z]', text): continue
				#这些是需要排除的特殊名字
				if text.startswith('背景') or \
					text.startswith('画面') or \
					text.startswith('オープニングムービー') or \
					text.startswith('イベントCG') or \
					text.startswith('スタッフロール'): 
					continue
				#处理真名
				ret2 = re.search(r'表示=".*?"', lineData)
				if ret2:
					start = ret2.start() + 4
					end = ret2.end() - 1
					#print('表示=', lineData)
					text = lineData[start:end]
				#0行数，1起始字符下标（包含），2结束字符下标（不包含）
				ctrl = {'pos':[contentIndex, start, end]}
				ctrl['isName'] = True #名字标记
				if dealOnce(text, listIndex):
					listIndex += 1
					listCtrl.append(ctrl)
			continue
		#对话
		if prelineIsText:
			listCtrl[-1]['notEnd'] = True
		prelineIsText = True
		start = 0
		end = len(lineData) - 1
		ret = re.search(r'\[', lineData)
		if ret:
			end = ret.start()
		text = lineData[start:end]
		#0行数，1起始字符下标（包含），2结束字符下标（不包含）
		ctrl = {'pos':[contentIndex, start, end]}
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