import re
import sys
import os
import struct
from common import *
import extract_TXT

# ---------------- Group: JSON -------------------
def parseImp(content, listCtrl, dealOnce):
	listIndex = 0
	#print(len(content))
	regDic = GetG('Var').regDic
	skipList = []
	searchList = []
	for key, value in regDic.items():
		if key.startswith('skip'):
			skipList.append(value)
		elif key.startswith('search'):
			searchList.append(value)
	for contentIndex in range(len(content)):
		#if contentIndex < 1: continue 
		lineData = content[contentIndex][:-1] #不检查末尾换行
		# 每行
		#print('>>> Line ' + str(contentIndex), ': ', lineData)
		if lineData == '': continue #空白行
		if re.match(r'\s*[\[\]\{\}]', lineData): continue #括号
		# 确认需要匹配的数据段
		searchData = None
		ret = re.match(r'\s*"(.+?)":\s*"(.*?)"', lineData)
		if ret:
			value = ret.group(2)
			searchStart = ret.start(2)
			searchEnd = ret.end(2)
			# value为空则复制key到value
			if value == '':
				key = ret.group(1)
				strNew = content[contentIndex][:searchStart] + key + content[contentIndex][searchEnd:]
				content[contentIndex] = strNew
				lineData = content[contentIndex][:-1]
				searchEnd += len(key)
				searchData = key
			else:
				searchData = value
		else:
			print('\033[33m查找键值对失败\033[0m', lineData)
			continue
		# 跳过
		matched = False
		for value in skipList:
			if re.search(value, searchData):
				matched = True
				break
		if matched : continue
		tmpDic = {}
		# 搜索
		for value in searchList:
			iter = re.finditer(value, searchData) 
			for r in iter:
				#print(r.groups())
				i = 0
				for key in r.groupdict().keys():
					i += 1
					if r.group(i) == None: continue
					start = r.start(i) + searchStart
					end = r.end(i) + searchStart
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
	extract_TXT.replaceOnceImp(content, lCtrl, lTrans)