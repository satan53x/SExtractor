import re
import sys
import os
import struct
from common import *
from extract_TXT import ParseVar, GetRegList, searchLine
from extract_TXT import replaceOnceImp as replaceOnceTxt

# ---------------- Group: JSON -------------------
def parseImp(content, listCtrl, dealOnce):
	var = ParseVar()
	var.listIndex = 0
	var.listCtrl = listCtrl
	var.dealOnce = dealOnce
	#print(len(content))
	regDic = GetG('Var').regDic
	var.regList = GetRegList(regDic.items(), None)
	for contentIndex in range(len(content)):
		#if contentIndex < 1: continue 
		lineData = content[contentIndex][:-1] #不检查末尾换行
		# 每行
		#print('>>> Line ' + str(contentIndex), ': ', lineData)
		if lineData == '': continue #空白行
		if re.match(r'\s*[\[\]\{\}]', lineData): continue #括号
		# 确认需要匹配的数据段
		if re.search(r'" *: *"', lineData): #键值对
			ret = re.search(r': *"(.*)"[ ,]*$', lineData)
		else: #字符串
			ret = re.search(r'"(.*)"[ ,]*$', lineData)
		#ret = re.search(r'"([^:]*)"[ ,]*$', lineData)
		if ret:
			var.searchStart = ret.start(1)
			var.searchEnd = ret.end(1)
			# value为空则复制key到value
			# if value == '':
			# 	key = ret.group(1)
			# 	strNew = content[contentIndex][:var.searchStart] + key + content[contentIndex][var.searchEnd:]
			# 	content[contentIndex] = strNew
			# 	lineData = content[contentIndex][:-1]
			# 	var.searchEnd += len(key)
		else:
			print('\033[33m值查找失败, 请检查Json格式\033[0m', lineData)
			continue
		# 查询
		var.contentIndex = contentIndex
		var.lineData = lineData
		searchLine(var)

# -----------------------------------
def replaceOnceImp(content, lCtrl, lTrans):
	replaceOnceTxt(content, lCtrl, lTrans)