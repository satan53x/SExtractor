import re
import sys
import os
import struct
from common import *

# ---------------- Group: Kirikiri -------------------
def parseImp(content, listCtrl, dealOnce):
	listIndex = 0
	#print(len(content))
	for contentIndex in range(len(content)):
		if contentIndex < 1: continue 
		lineData = content[contentIndex]
		start = 0
		end = 0
		#每行
		#print('>>> Line ' + str(contentIndex), ': ', lineData)
		if lineData.isspace(): continue #空白行
		if re.match(r'[;\*]', lineData): continue #注释行
		tmpDic = {}
		ctrl = {}
		text = ''
		#控制段
		iter = re.finditer(r'\[.*?\]', lineData)
		for rBrackets in iter:
			#[]前有文本
			if start < rBrackets.start():
				end = rBrackets.start()
				text = lineData[start:end]
				#0行数，1起始字符下标（包含），2结束字符下标（不包含）
				ctrl = {'pos':[contentIndex, start, end]}
				tmpDic[start] = [text, ctrl]
				#print("[]前有文本", ctrl, text)
			#[]中有文本
			bracketsData = lineData[rBrackets.start():rBrackets.end()]
			if re.match(r'\[name', bracketsData):
				#名字
				rName = re.search(r'text=".*"', bracketsData)
				if rName:
					start = rBrackets.start() + rName.start() + 6
					end = rBrackets.start() + rName.end() - 1
					text = lineData[start:end]
					#0行数，1起始字符下标（包含），2结束字符下标（不包含）
					ctrl = {'pos':[contentIndex, start, end]}
					ctrl['isName'] = True #名字标记
					tmpDic[start] = [text, ctrl]
			elif bracketsData == '[r]':
				ctrl['unfinish'] = True
				#print('有[r]换行', ctrl, text)
			start = rBrackets.end()
		#行末有文本
		if start < len(lineData) - 1:
			end = len(lineData) - 1
			text = lineData[start:end]
			#0行数，1起始字符下标（包含），2结束字符下标（不包含）
			ctrl = {'pos':[contentIndex, start, end]}
			tmpDic[start] = [text, ctrl]
		#按文本中顺序处理
		for key in sorted(tmpDic.keys()):
			value = tmpDic[key]
			if dealOnce(value[0], listIndex):
				listIndex += 1
				listCtrl.append(value[1])

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