import re
import sys
import os
import struct
from common import *

# ---------------- Group: Artemis pfs -------------------
def parseImp(content, listCtrl, dealOnce):
	listIndex = 0
	dealText = False
	serialCount = 0 #连续计数
	for contentIndex in range(len(content)):
		if contentIndex < 1: continue #起始跳过行数
		lineData = content[contentIndex]
		if lineData.isspace():
			continue
		#每行
		#print('>>> Line ' + str(contentIndex), ': ', lineData)
		if dealText == False:
			if re.match(r'\s*\[\d+\]', lineData):
				dealText = True
				serialCount = 0
			continue
		if re.match(r'\s*{\s*$', lineData) :continue
		if re.match(r'\s*},\s*$', lineData):
			serialCount += 1
			if serialCount >= 2:
				dealText = False
			continue
		else:
			serialCount = 0
		#处理文本
		start = 0
		end = 0
		if re.match(r'\s*name=', lineData) or re.match(r'\s*"', lineData): #名字和对话
			ret = re.search(r'".+?"', lineData)
			if ret:
				start = ret.start() + 1
				end = ret.end() - 1
			else: continue
		elif re.match(r'\s*{"rt2"}', lineData): #换行
			listCtrl[-1]["notEnd"] = True #换行标记
			continue
		else:
			continue
		#print(lineData, start, len(lineData))
		text = lineData[start:end]
		#0行数，1起始字符下标（包含），2结束字符下标（不包含）
		ctrl = {'pos':[contentIndex, start, end]}
		if re.match(r'\s*name=', lineData):
			ctrl["isName"] = True #名字标记
		#print(ctrl)
		ret = dealOnce(text, listIndex)
		if ret: #成功
			listIndex += 1
			listCtrl.append(ctrl)
			#break #测试

# ---------------- Group: Artemis pfs -------------------
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