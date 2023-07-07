import re
import sys
import os
import struct
from common import *

# ---------------- Group: RenPy -------------------
def parseImp(content, listCtrl, dealOnce):
	listIndex = 0
	#print(len(content))
	for contentIndex in range(len(content)):
		if contentIndex < 1: continue 
		lineData = content[contentIndex]
		start = 0
		end = 0
		searchStart = 0
		#每行
		#print('>>> Line ' + str(contentIndex), ': ', lineData)
		if re.match(r' ', lineData) == False: continue #非数据行
		tmpDic = {}
		retName = re.match(r'    [^ ]+? "', lineData)
		if retName: #含名字
			start = retName.start() + 4
			end = retName.end() - 2
			text = lineData[start:end]
			if text == 'voice' or text == 'old': continue
			if text != 'new':
				#0行数，1起始字符下标（包含），2结束字符下标（不包含）
				ctrl = {'pos':[contentIndex, start, end]}
				ctrl['isName'] = True #名字标记
				if dealOnce(text, listIndex):
					listIndex += 1
					listCtrl.append(ctrl)
			searchStart = end
		retMsg = re.search(r'".*"', lineData[searchStart:])
		if retMsg: #对话
			start = searchStart + retMsg.start() + 1
			end = searchStart + retMsg.end() - 1
			text = lineData[start:end]
			searchStart = start
			iter = re.finditer(r'[^\{\}]+', text) #按{}分割查找
			for r in iter:
				if re.match(r'[a-zA-Z0-9/]', r.group()): continue #控制字
				start = searchStart + r.start()
				end = searchStart + r.end()
				text = lineData[start:end]
				searchStart2 = start
				iter2 = re.finditer(r'[^\\n]+', text) #按\n分割查找
				for r2 in iter2:
					start = searchStart2 + r2.start()
					end = searchStart2 + r2.end()
					text = lineData[start:end]
					#0行数，1起始字符下标（包含），2结束字符下标（不包含）
					ctrl = {'pos':[contentIndex, start, end]}
					ctrl['notEnd'] = True
					if dealOnce(text, listIndex):
						listIndex += 1
						listCtrl.append(ctrl)
			if 'notEnd' in listCtrl[-1]:
				del listCtrl[-1]['notEnd']

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