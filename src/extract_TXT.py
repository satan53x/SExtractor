import re
import sys
import os
import struct
from common import *

class ParseVar():
	contentIndex = 0
	lineData = None
	searchStart = 0
	searchEnd = -1
	listIndex = 0 #准备弃用
	listCtrl = None
	dealOnce = None
	regList = []
	nameList = []
	OldEncodeName = None

	def __init__(self, listCtrl=None, dealOnce=None):
		self.listCtrl = listCtrl
		self.dealOnce = dealOnce

# -----------------------------------
def searchLine(var:ParseVar):
	if var.searchStart > 0:
		searchData = var.lineData[var.searchStart:var.searchEnd]
	else:
		searchData = var.lineData
	ctrls = []
	for regItem in var.regList:
		regType = regItem[1]
		value = regItem[0]
		if regType == 'skip':
			# 跳过
			if re.search(value, searchData): #已匹配则停止
				return None #skip则返回None
		else:
			# 搜索
			tmpDic = {}
			matched = False
			iter = re.finditer(value, searchData) 
			for r in iter:
				#print(r.groups())
				for i in range(1, len(r.groups())+1):
					if r.group(i) == None: continue
					start = r.start(i) + var.searchStart
					end = r.end(i) + var.searchStart
					if var.OldEncodeName: # bin
						text = var.lineData[start:end].decode(var.OldEncodeName)
					else: # txt
						text = var.lineData[start:end]
					#0行数，1起始字符下标（包含），2结束字符下标（不包含）
					ctrl = {'pos':[var.contentIndex, start, end]}
					tmpDic[start] = [text, ctrl]
					#检查命名
					key = None
					for name, index in r.re.groupindex.items():
						if i == index: key = name
					if text in var.nameList: #强制检查名字
						ctrl['isName'] = True #名字标记
					elif not key:
						pass
					elif key.startswith('name'):
						ctrl['isName'] = True #名字标记
					elif key.startswith('unfinish'):
						ctrl['unfinish'] = True
					matched = True
			if matched :
				#按文本中顺序处理
				for key in sorted(tmpDic.keys()):
					value = tmpDic[key]
					if var.dealOnce(value[0], var.contentIndex):
						var.listCtrl.append(value[1])
						ctrls.append(value[1])
				break #已匹配则停止
	return ctrls

def GetRegList(items, OldEncodeName):
	lst = []
	for key, value in items:
		if OldEncodeName:
			value = value.encode(OldEncodeName)
		if re.search('skip', key):
			lst.append([value, 'skip'])
		elif re.search('search', key):
			lst.append([value, 'search'])
	return lst

# ---------------- Group: TXT -------------------
def parseImp(content, listCtrl, dealOnce):
	if GetG('Var').structure.startswith('para'):
		return parseImpParagraph(content, listCtrl, dealOnce)
	var = ParseVar(listCtrl, dealOnce)
	#print(len(content))
	regDic = GetG('Var').regDic
	var.nameList = GetG('Var').nameList
	var.regList = GetRegList(regDic.items(), None)
	for contentIndex in range(len(content)):
		if contentIndex < GetG('Var').startline: continue 
		lineData = content[contentIndex][:-1] #不检查末尾换行
		# 每行
		#print('>>> Line ' + str(contentIndex), ': ', lineData)
		if lineData == '': continue #空白行
		var.contentIndex = contentIndex
		var.lineData = lineData
		searchLine(var)

# ---------------- Group: TXT -------------------
#特殊格式，按skip划分段落
def parseImpParagraph(content, listCtrl, dealOnce):
	var = ParseVar(listCtrl, dealOnce)
	var.nameList = GetG('Var').nameList
	regList = GetRegList(GetG('Var').regDic.items(), None)
	regSkip = []
	regName = []
	regMsg = []
	for item in regList:
		if item[1] == 'skip':
			regSkip.append(item)
		elif '?P<name' in item[0]:
			regName.append(item)
		else:
			regMsg.append(item)
	lastCtrl = None
	for contentIndex in range(len(content)):
		var.lineData = content[contentIndex][:-1] #不检查末尾换行
		var.contentIndex = contentIndex
		#检查skip
		var.regList = regSkip
		if searchLine(var) == None:
			#skip匹配成功
			if lastCtrl and 'unfinish' in lastCtrl: del lastCtrl['unfinish']
			lastCtrl = None
			continue
		#检查名字
		var.regList = regName
		ctrls = searchLine(var)
		if len(ctrls) > 0:
			#名字匹配成功
			if lastCtrl and 'unfinish' in lastCtrl: del lastCtrl['unfinish']
			lastCtrl = None
			continue
		var.regList = regMsg
		ctrls = searchLine(var)
		if len(ctrls) > 0:
			lastCtrl = ctrls[0]

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