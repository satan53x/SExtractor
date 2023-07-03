import re
import sys
import os
import struct
from common import *

# ---------------- Group: Kirikiri -------------------
def parseImp(content, listCtrl, dealOnce):
	listIndex = 0
	#print(len(content))
	for contentIndex in range(len(content) - 1):
		if contentIndex < 1: continue 
		#if contentIndex > 41: break #测试 
		lineData = content[contentIndex]
		start = 0
		end = 0
		#每行
		#print('>>> Line ' + str(contentIndex), ': ', lineData)
		if lineData.isspace(): continue #空白行
		if re.match(r'[;\*]', lineData): continue #注释行
		if re.match(r'\[\w', lineData): continue #控制行
		tmpDic = {}
		#名字
		iter = re.finditer(r'\[【.+】', lineData)
		for r in iter:
			start = r.start() + 2
			end = r.end() - 1
			text = lineData[start:end]
			#0行数，1起始字符下标（包含），2结束字符下标（不包含）
			ctrl = {'pos':[contentIndex, start, end]}
			ctrl["isName"] = True #名字标记
			tmpDic[start] = [text, ctrl]
			#print(text)
		ret = re.match(r'\[【.+】[^[]*?\]', lineData)
		findStart = 0
		if ret:
			findStart = ret.end()
		#对话
		iter = re.finditer(r'[^\[a-zA-Z0-9\]\\]+', lineData[findStart:-1])
		for r in iter:
			start = findStart + r.start()
			end = findStart + r.end()
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

# ---------------- Group:  -------------------
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