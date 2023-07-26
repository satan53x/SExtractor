import re
import sys
import os
import struct
from common import *
from extract_TXT import ParseVar, GetRegList, searchLine

# ---------------- Group: RPGMV -------------------
def parseImp(content, listCtrl, dealOnce):
	var = ParseVar()
	var.listIndex = 0
	var.listCtrl = listCtrl
	var.dealOnce = dealOnce
	#print(len(content))
	regDic = GetG('Var').regDic
	var.regList = GetRegList(regDic.items(), None)
	if isinstance(content, dict):
		#字典
		if 'events' not in content: 
			print('\033[33m字典不含events, 请检查格式\033[0m', GetG('Var').filename)
			return 1
		events = content['events']
	else:
		events = content
	#列表
	for i in range(len(events)):
		try:
			if events[i] == None: continue
			pages = events[i]['pages']
			for j in range(len(pages)):
				lst = pages[j]['list']
				lastMessageCtrl = None
				for k in range(len(lst)):
					item = lst[k]
					if item['code'] == 401:
						#普通文本
						var.lineData = item['parameters'][0]
						var.contentIndex = [i, j, k]
						ctrls = searchLine(var)
						if 'isName' not in ctrls[0]:
							#对话
							for ctrl in ctrls:
								ctrl['unfinish'] = True
							lastMessageCtrl = ctrls[-1]
							continue
					else:
						# 不是普通文本则段落结束
						if item['code'] == 102:
							#选项
							parameter = item['parameters'][0]
							for l in range(len(parameter)):
								var.lineData = parameter[l]
								var.contentIndex = [i, j, k, l]
								searchLine(var)
					if lastMessageCtrl:
						del lastMessageCtrl['unfinish']
						lastMessageCtrl = None
		except Exception as ex:
			print('\033[33m值查找失败, 请检查Json格式\033[0m', i)
			print(ex)
			return 2

# -----------------------------------
def replaceOnceImp(content, lCtrl, lTrans):
	if isinstance(content, dict):
		#字典
		if 'events' not in content: return False
		events = content['events']
	else:
		events = content
	#print(lCtrl)
	#print(lTrans)
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
		k = contentIndex[2]
		if len(contentIndex) == 3:
			strOld = events[i]['pages'][j]['list'][k]['parameters'][0]
			strNew = strOld[:start] + trans + strOld[end:]
			events[i]['pages'][j]['list'][k]['parameters'][0] = strNew
		else:
			l = contentIndex[3]
			strOld = events[i]['pages'][j]['list'][k]['parameters'][0][l]
			strNew = strOld[:start] + trans + strOld[end:]
			events[i]['pages'][j]['list'][k]['parameters'][0][l] = strNew
		return True