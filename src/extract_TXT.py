import re
import sys
import os
import struct
from common import *

# ---------------- Group: Kirikiri -------------------
def parseImp(content, listCtrl, dealOnce):
	listIndex = 0
	#print(len(content))
	regDic = GetG('RegDic')
	skipList = []
	searchList = []
	for key, value in regDic.items():
		if key.startswith('skip'):
			skipList.append(value)
		elif key.startswith('search'):
			searchList.append(value)
	for contentIndex in range(len(content)):
		if contentIndex < 1: continue 
		lineData = content[contentIndex][:-1] #不检查末尾换行
		# 每行
		#print('>>> Line ' + str(contentIndex), ': ', lineData)
		if lineData == '': continue #空白行
		# 跳过
		matched = False
		for value in skipList:
			if re.search(value, lineData):
				matched = True
				break
		if matched : continue
		tmpDic = {}
		# 搜索
		for value in searchList:
			iter = re.finditer(value, lineData) 
			for r in iter:
				#print(r.groups())
				i = 0
				for key in r.groupdict().keys():
					i += 1
					if r.group(i) == None: continue
					start = r.start(i)
					end = r.end(i)
					text = lineData[start:end]
					#0行数，1起始字符下标（包含），2结束字符下标（不包含）
					ctrl = {'pos':[contentIndex, start, end]}
					tmpDic[start] = [text, ctrl]
					if key.startswith('name'):
						ctrl['isName'] = True #名字标记
					elif key.startswith('unfinish'):
						ctrl['unfinish'] = True
					matched = True
			if matched : break #已匹配则停止搜索
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