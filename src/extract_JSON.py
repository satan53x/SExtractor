import re
import sys
import os
import struct
from common import *
from extract_TXT import ParseVar, GetRegList, searchLine

copyKeyToValue = True

# ---------------- Group: JSON -------------------
def parseImp(content, listCtrl, dealOnce):
	var = ParseVar()
	var.listIndex = 0
	var.listCtrl = listCtrl
	var.dealOnce = dealOnce
	#print(len(content))
	GetG('Var').indent = 2
	regDic = GetG('Var').regDic
	var.regList = GetRegList(regDic.items(), None)
	if isinstance(content, dict):
		#字典: 子项为字符串key:value
		if copyKeyToValue:
			#复制key到value
			for key, value in content.items():
				if value == '':
					content[key] = key
		index = -1
		for i, value in content.items():
			index += 1
			if index < GetG('Var').startline: continue 
			lineData = value
			if lineData == '': continue #空白行
			var.contentIndex = [i, None]
			var.lineData = lineData
			searchLine(var)
	else:
		#列表
		if isinstance(content[0], dict):
			#子项为字典
			for i in range(len(content)):
				if i < GetG('Var').startline: continue 
				for j, value in content[i].items():
					lineData = value
					if lineData == '': continue #空白行
					var.contentIndex = [i, j]
					var.lineData = lineData
					searchLine(var)
		elif isinstance(content[0], str):
			#子项为字符串
			for i in range(len(content)):
				if i < GetG('Var').startline: continue
				lineData = content[i]
				if lineData == '': continue #空白行
				var.contentIndex = [i, None]
				var.lineData = lineData
				searchLine(var)

# -----------------------------------
def replaceOnceImp(content, lCtrl, lTrans):
	num = len(lCtrl)
	for index in range(num):
		# 位置
		ctrl = lCtrl[index]
		posData = ctrl['pos']
		contentIndex = posData[0]
		start = posData[1]
		end = posData[2]
		trans = lTrans[index]
		#写入new
		i = contentIndex[0]
		j = contentIndex[1]
		if j == None:
			#一层
			strOld = content[i]
			strNew = strOld[:start] + trans + strOld[end:]
			content[i] = strNew
		else:
			#两层
			strOld = content[i][j]
			strNew = strOld[:start] + trans + strOld[end:]
			content[i][j] = strNew
			


