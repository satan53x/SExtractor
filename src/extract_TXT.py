import re
import sys
import os
import struct
from common import *
from helper_text import generateBytes, getBytes

OldEncodeName = 'cp932' #仅用于TXT模式截断和JIS替换
NewEncodeName = 'gbk' #仅用于TXT模式截断

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
	ignoreDecodeError = False
	postSkip = None
	checkJIS = None

	def __init__(self, listCtrl=None, dealOnce=None):
		self.listCtrl = listCtrl
		self.dealOnce = dealOnce

# -----------------------------------
def GetPos(var:ParseVar, searchData:str, r:re.Match[str], i):
	start = r.start(i)
	end = r.end(i)
	if var.OldEncodeName and ExVar.pureText:
		#bin的纯文本模式
		#从字符位置转为字节位置
		lengthPre = len(searchData[0:start].encode(var.OldEncodeName))
		lengthText = len(searchData[start:end].encode(var.OldEncodeName))
		start = lengthPre
		end = lengthPre + lengthText
	start += var.searchStart
	end += var.searchStart
	return start, end
# -----------------------------------
def searchLine(var:ParseVar):
	if var.searchStart > 0:
		searchData = var.lineData[var.searchStart:var.searchEnd]
	else:
		searchData = var.lineData
	if var.OldEncodeName and ExVar.pureText:
		#bin的纯文本模式
		searchData = searchData.decode(var.OldEncodeName)
	ctrls = []
	for regItem in var.regList:
		regType = regItem[1]
		pattern:re.Pattern = regItem[0]
		if regType == 'skip':
			# 跳过
			if pattern.search(searchData): #已匹配则停止
				return None #skip则返回None
		else:
			# 搜索
			tmpDic = {}
			matched = False
			iter = pattern.finditer(searchData) 
			for r in iter:
				#print(r.groups())
				for i in range(1, len(r.groups())+1):
					if r.group(i) == None: continue
					start, end = GetPos(var, searchData, r, i)
					if var.OldEncodeName: # bin
						try:
							if var.checkJIS != None:
								ret = checkJIS(var.lineData[start:end], var.checkJIS)
								if not ret:
									continue
							text = var.lineData[start:end].decode(var.OldEncodeName)
						except Exception as ex:
							if var.ignoreDecodeError:
								continue
							else:
								raise
					else: # txt
						text = var.lineData[start:end]
					#匹配后跳过
					if var.postSkip:
						if var.postSkip.search(text):
							#print('postSkip', text)
							continue
					#0行数，1起始字符下标（包含），2结束字符下标（不包含）
					ctrl = {'pos':[var.contentIndex, start, end]}
					tmpDic[start] = [text, ctrl]
					#检查命名
					key = None
					for name, index in r.re.groupindex.items():
						if i == index: key = name
					if text in var.nameList: #强制检查名字
						ctrl['name'] = True #名字标记
					elif not key:
						pass
					else:
						key = key.rstrip('0123456789')
						if 'AND' in key:
							keys = key.split('AND')
						else:
							keys = [key]
						for key in keys:
							if key == 'name' or key == 'unfinish':
								ctrl[key] = True #标记
							else:
								if 'flags' not in ctrl:
									ctrl['flags'] = []
								ctrl['flags'].append(key)
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
		if OldEncodeName and ExVar.pureText == False:
			if OldEncodeName.startswith('UTF-16'):
				value = value.encode('latin-1') #utf-16不兼容ascii，不能用于BIN正则
			else:
				value = value.encode(OldEncodeName)
		if re.search('skip', key):
			lst.append([re.compile(value), 'skip'])
		elif re.search('search', key):
			lst.append([re.compile(value), 'search'])
	return lst

def dealLastCtrl(lastCtrl, ctrls, contentIndex=-1):
	flags = []
	ctrl = None
	if ctrls == None: #skip匹配
		if not ExVar.skipIgnoreUnfinish:
			flags.append('predel_unfinish')
		if ExVar.skipIgnoreCtrl:
			ctrl = lastCtrl
	elif len(ctrls) == 0:
		ctrl = lastCtrl
	else:
		ctrl = ctrls[-1]
		if 'flags' in ctrl:
			flags.extend(ctrl['flags'])
		if 'name' in ctrl: #name匹配
			flags.append('predel_unfinish')
			ctrl = None
	#处理flags
	for flag in flags:
		if lastCtrl:
			if flag.startswith('pre_'):
				key = flag[4:]
				lastCtrl[key] = True #添加
			elif flag.startswith('predel_'):
				key = flag[7:]
				if key in lastCtrl:
					del lastCtrl[key] #删除
	return ctrl

def initParseVar(var:ParseVar, regDic=None):
	if regDic == None:
		regDic = ExVar.regDic
	var.nameList = ExVar.nameList
	var.regList = GetRegList(regDic.items(), var.OldEncodeName)
	var.ignoreDecodeError = ExVar.ignoreDecodeError
	if ExVar.postSkip:
		var.postSkip = re.compile(ExVar.postSkip)
	if ExVar.checkJIS:
		var.checkJIS = ExVar.checkJIS
		if var.OldEncodeName:
			var.checkJIS = var.checkJIS.encode(var.OldEncodeName)
		var.checkJIS = re.compile(var.checkJIS)

# ---------------- Group: TXT -------------------
def parseImp(content, listCtrl, dealOnce):
	checkLast = ExVar.structure.startswith('para')
	var = ParseVar(listCtrl, dealOnce)
	initParseVar(var)
	lastCtrl = None
	for contentIndex in range(len(content)):
		if contentIndex < ExVar.startline: continue 
		var.lineData = content[contentIndex][:-1] #不检查末尾换行
		#print('>>> Line ' + str(contentIndex), ': ', var.lineData)
		var.contentIndex = contentIndex
		ctrls = searchLine(var)
		if checkLast:
			lastCtrl = dealLastCtrl(lastCtrl, ctrls, contentIndex)
	#文末处理
	if lastCtrl and 'unfinish' in lastCtrl:
		del lastCtrl['unfinish'] #段落结束

# -----------------------------------
def replaceOnceImp(content, lCtrl, lTrans):
	num = len(lCtrl)
	for i in range(num):
		# 位置
		ctrl = lCtrl[i]
		contentIndex, start, end = ctrl['pos']
		trans = lTrans[i]
		if ExVar.subsJis:
			transData = getBytes(trans, ExVar.NewEncodeName)
			trans = transData.decode(OldEncodeName)
		elif ExVar.cutoff:
			origData = content[contentIndex][start:end].encode(OldEncodeName)
			transData = generateBytes(trans, len(origData), NewEncodeName)
			if transData == None:
				return False
			trans = transData.decode(NewEncodeName)
		#写入new
		strNew = content[contentIndex][:start] + trans + content[contentIndex][end:]
		#print(strNew)
		content[contentIndex] = strNew
	return True
