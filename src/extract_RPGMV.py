import re
import sys
import os
import struct
import traceback
from common import *
from extract_TXT import ParseVar, GetRegList, searchLine, initParseVar

extractItemName = True

# ---------------- Group: RPGMV -------------------
#处理通用pages
def dealPages(var, pages, i):
	for j in range(len(pages)):
		page = pages[j]
		if page == None: continue
		if extractItemName and 'name' in page and page['name']:
			var.lineData = page['name']
			var.contentIndex = [i, j, -1, -1]
			searchLine(var)
		lastMessageCtrl = None
		if 'list' not in page: continue
		for k in range(len(page['list'])):
			item = page['list'][k]
			if item['code'] == 401:
				#普通文本
				var.lineData = item['parameters'][0]
				var.contentIndex = [i, j, k, -1]
				ctrls = searchLine(var)
				if ctrls == None:
					pass
				elif len(ctrls) == 0: #未捕捉到，一般为空字符串
					continue 
				elif 'name' not in ctrls[0]:
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
# -----------------------------------
#处理System.json
SystemPathList = [
	{
		'type': 'str',
		'path': ['gameTitle']
	},
	{
		'type': 'list',
		'path': ['switches']
	},
	{
		'type': 'list',
		'path': ['variables']
	},
	{
		'type': 'list',
		'path': ['terms', 'commands']
	},
	{
		'type': 'dict',
		'path': ['terms', 'messages']
	}
]
def setTarget(content, nodeList, replace=None):
	target = content
	for i, node in enumerate(nodeList):
		if replace and i == len(nodeList) - 1:
			#替换
			target[node] = replace
		target = target[node]
	return target

def dealPathStr(var:ParseVar, content, pathList):
	for item in pathList:
		nodeList = item['path']
		target = setTarget(content, nodeList)
		if item['type'] == 'str':
			#字符串
			var.lineData = target
			var.contentIndex = list(nodeList)
			searchLine(var)
		elif item['type'] == 'list':
			#列表
			for i, value in enumerate(target):
				if value == None: continue
				var.lineData = value
				var.contentIndex = list(nodeList)
				var.contentIndex.append(i)
				searchLine(var)
		elif item['type'] == 'dict':
			#列表
			for key, value in target.items():
				if value == None: continue
				var.lineData = value
				var.contentIndex = list(nodeList)
				var.contentIndex.append(key)
				searchLine(var)

# -----------------------------------
#解析
def parseImp(content, listCtrl, dealOnce):
	var = ParseVar(listCtrl, dealOnce)
	initParseVar(var)
	#print(len(content))
	ExVar.indent = 0
	extractName = ExVar.extractName
	global extractItemName
	if re.search(extractName, ExVar.filename):
		extractItemName = True
	else:
		extractItemName = False
	#System.json
	if ExVar.filename == 'System':
		dealPathStr(var, content, SystemPathList)
		return
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
			dealPages(var, pages, -1)
		else:
			for i in range(len(events)):
				event = events[i]
				if event == None: continue
				if extractItemName and 'name' in event and event['name']:
					var.lineData = events[i]['name']
					var.contentIndex = [i, -1, -1, -1]
					searchLine(var)
				pages = event['pages']
				dealPages(var, pages, i)
	except Exception as ex:
		print('\033[33m值查找失败, 请检查Json格式\033[0m', i)
		#print(ex)
		traceback.print_exc()
		return 2

# -----------------------------------
def replaceOnceImp(content, lCtrl, lTrans):
	pages = None
	nodeList = None
	if ExVar.filename == 'System':
		nodeList = []
	elif isinstance(content, list):
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
		#按nodeList写入
		if nodeList != None:
			nodeList = contentIndex
			setTarget(content, nodeList, trans)
		else:
			#按pages写入
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