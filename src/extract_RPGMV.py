import re
import sys
import os
import struct
import traceback
from common import *
from extract_TXT import ParseVar, GetRegList, searchLine

extractItemName = True

# ---------------- Group: RPGMV -------------------
def dealList(var, pages, i):
	for j in range(len(pages)):
		page = pages[j]
		if page == None: continue
		if extractItemName and 'name' in page and page['name']:
			var.lineData = page['name']
			var.contentIndex = [i, j, -1, -1]
			ctrl = {'pos':[var.contentIndex, 0, -1]}
			if var.dealOnce(var.lineData, var.listIndex):
				var.listIndex += 1
				var.listCtrl.append(ctrl)
		lastMessageCtrl = None
		if 'list' not in page: continue
		for k in range(len(page['list'])):
			item = page['list'][k]
			if item['code'] == 401:
				#普通文本
				var.lineData = item['parameters'][0]
				var.contentIndex = [i, j, k, -1]
				ctrls = searchLine(var)
				if len(ctrls) == 0: #未捕捉到，一般为空字符串
					continue 
				elif 'isName' not in ctrls[0]:
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
			
def parseImp(content, listCtrl, dealOnce):
	var = ParseVar()
	var.listIndex = 0
	var.listCtrl = listCtrl
	var.dealOnce = dealOnce
	#print(len(content))
	GetG('Var').indent = 0
	regDic = GetG('Var').regDic
	var.regList = GetRegList(regDic.items(), None)
	extractName = GetG('Var').extractName
	global extractItemName
	if re.search(extractName, GetG('Var').filename):
		extractItemName = True
	else:
		extractItemName = False
	#文件类型
	pages = None
	if isinstance(content, list):
		#单page
		pages = content
	else:
		events = content['events']
	# 处理
	i = -1
	try:
		if pages:
			dealList(var, pages, -1)
		else:
			for i in range(len(events)):
				event = events[i]
				if event == None: continue
				if extractItemName and 'name' in event and event['name']:
					var.lineData = events[i]['name']
					var.contentIndex = [i, -1, -1, -1]
					ctrl = {'pos':[var.contentIndex, 0, -1]}
					if var.dealOnce(var.lineData, var.listIndex):
						var.listIndex += 1
						var.listCtrl.append(ctrl)
				pages = event['pages']
				dealList(var, pages, i)
	except Exception as ex:
		print('\033[33m值查找失败, 请检查Json格式\033[0m', i)
		#print(ex)
		traceback.print_exc()
		return 2

# -----------------------------------
def replaceOnceImp(content, lCtrl, lTrans):
	pages = None
	if isinstance(content, list):
		#单page
		pages = content
	else:
		events = content['events']
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
		l = contentIndex[3]
		if j < 0:
			# event['name']
			strOld = events[i]['name']
			strNew = strOld[:start] + trans + strOld[end:]
			events[i]['name'] = strNew
			continue
		if not pages:
			pages = events[i]['pages']
		if k < 0:
			# page['name']
			strOld = pages[i]['name']
			strNew = strOld[:start] + trans + strOld[end:]
			pages[i]['name'] = strNew
			continue
		if l < 0:
			strOld = pages[j]['list'][k]['parameters'][0]
			strNew = strOld[:start] + trans + strOld[end:]
			pages[j]['list'][k]['parameters'][0] = strNew
		else:
			strOld = pages[j]['list'][k]['parameters'][0][l]
			strNew = strOld[:start] + trans + strOld[end:]
			pages[j]['list'][k]['parameters'][0][l] = strNew
	return True