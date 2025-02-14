from collections import OrderedDict
import re
from common import *
from helper_text import generateBytes, getBytes, keepBytes

#OldEncodeName = 'cp932' #仅用于TXT模式截断和JIS替换
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
	checkLast = False
	lastCtrl = None
	intervalFlag = None #区间保持标记

	def __init__(self, listCtrl=None, dealOnce=None):
		self.listCtrl = listCtrl
		self.dealOnce = dealOnce

# -----------------------------------
longText = False
pureTextDataRel = [] #纯文本模式下，字符index对应的字节结束位置
def GetPos(var:ParseVar, searchData:str, r:re.Match[str], i):
	start = r.start(i)
	end = r.end(i)
	if var.OldEncodeName and ExVar.pureText:
		#bin的纯文本模式
		if not longText:
			#短文本
			lengthPre = len(searchData[0:start].encode(var.OldEncodeName))
			lengthText = len(searchData[start:end].encode(var.OldEncodeName))
			start = lengthPre
			end = lengthPre + lengthText
		else:
			if len(pureTextDataRel) < end:
				#计算字符字节对应关系
				for i in range(len(pureTextDataRel), end):
					if i == 0:
						pos = 0
					else:
						pos = pureTextDataRel[i-1]
					pos += len(searchData[i].encode(var.OldEncodeName))
					pureTextDataRel.append(pos)
			#从字符位置转为字节位置
			start = 0 if start==0 else pureTextDataRel[start-1]
			end = 0 if end==0 else pureTextDataRel[end-1]
	start += var.searchStart
	end += var.searchStart
	return start, end
# -----------------------------------
def searchLine(var:ParseVar):
	if var.searchEnd >= 0:
		searchData = var.lineData[var.searchStart:var.searchEnd]
	else:
		searchData = var.lineData
	if var.OldEncodeName and ExVar.pureText:
		#bin的纯文本模式
		searchData = searchData.decode(var.OldEncodeName)
		global longText
		longText = len(searchData) > 0x400
		pureTextDataRel.clear()
	ctrls = []
	for regItem in var.regList:
		regType = regItem[1]
		pattern:re.Pattern = regItem[0]
		if regType == 'skip':
			# 跳过
			if pattern.search(searchData): #已匹配则停止
				if not ExVar.skipIgnoreUnfinish:
					var.intervalFlag = None
				return None #skip则返回None
		else:
			# 搜索
			tmpDic = OrderedDict()
			matched = False
			iter = pattern.finditer(searchData) 
			for r in iter:
				#print(r.groups())
				for i in range(1, len(r.groups())+1):
					if r.group(i) == None: continue
					start, end = GetPos(var, searchData, r, i)
					data = var.lineData[start:end]
					if var.OldEncodeName: # bin
						try:
							if ExVar.keepBytes:
								data = keepBytes(data, ExVar.keepBytes)
							if var.checkJIS != None:
								ret = checkJIS(data, var.checkJIS)
								if not ret:
									continue
							text = data.decode(var.OldEncodeName)
						except Exception as ex:
							if var.ignoreDecodeError:
								continue
							else:
								raise
					else: # txt
						text = data
					#匹配后跳过
					if var.postSkip:
						if var.postSkip.search(text):
							#print('postSkip', text)
							continue
					#0行数，1起始字符下标（包含），2结束字符下标（不包含）
					ctrl = {'pos':[var.contentIndex, start, end]}
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
						elif key == 'skip':
							continue
						else:
							keys = [key]
						for key in keys:
							if key.startswith('pre'):
								if 'flags' not in ctrl:
									ctrl['flags'] = []
								ctrl['flags'].append(key)
							elif key.startswith('type_'):
								ctrl['type'] = key[5:]
							elif key.startswith('start_'):
								var.intervalFlag = key[6:]
							elif key.startswith('end_'):
								var.intervalFlag = None
							else: #name, unfinish
								ctrl[key] = True #标记
					if var.intervalFlag:
						ctrl[var.intervalFlag] = True
					matched = True
					tmpDic[start] = [text, ctrl]
			if matched :
				#按文本中顺序处理
				for key, value in tmpDic.items():
					if var.dealOnce(value[0], value[1]):
						var.listCtrl.append(value[1])
						ctrls.append(value[1])
				break #已匹配则停止
	return ctrls

def GetRegList(items, OldEncodeName):
	lst = []
	for key, value in items:
		if OldEncodeName and ExVar.pureText == False:
			if OldEncodeName.lower().startswith('utf-16'):
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
			if not ExVar.nameKeepCtrl:
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
	var.checkLast = ExVar.structure.startswith('para')
	var.lastCtrl = None
	var.intervalFlag = None

# ---------------- Group: TXT -------------------
def parseImp(content, listCtrl, dealOnce):
	var = ParseVar(listCtrl, dealOnce)
	initParseVar(var)
	for contentIndex in range(len(content)):
		if contentIndex < ExVar.startline: continue 
		var.lineData = content[contentIndex][:-1] #不检查末尾换行
		#print('>>> Line ' + str(contentIndex), ': ', var.lineData)
		var.contentIndex = contentIndex
		ctrls = searchLine(var)
		if var.checkLast:
			var.lastCtrl = dealLastCtrl(var.lastCtrl, ctrls, contentIndex)
	#文末处理
	if var.lastCtrl and 'unfinish' in var.lastCtrl:
		del var.lastCtrl['unfinish'] #段落结束

# -----------------------------------
def replaceOnceImp(content, lCtrl, lTrans):
	num = len(lCtrl)
	for i in range(num):
		# 位置
		ctrl = lCtrl[i]
		contentIndex, start, end = ctrl['pos']
		trans = lTrans[i]
		#处理trans
		trans = dealTransLine(trans, content[contentIndex][start:end])
		#写入new
		strNew = content[contentIndex][:start] + trans + content[contentIndex][end:]
		#print(strNew)
		content[contentIndex] = strNew
	return True

def dealTransLine(trans, orig):
	if ExVar.subsJis:
		transData = getBytes(trans, ExVar.JisEncodeName)
		trans = transData.decode(ExVar.JisEncodeName)
	elif ExVar.cutoff:
		origData = orig.encode(ExVar.JisEncodeName)
		transData = generateBytes(trans, len(origData), NewEncodeName)
		if transData == None:
			return False
		trans = transData.decode(NewEncodeName)
	return trans
