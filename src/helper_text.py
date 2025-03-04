import math
import os
import re
import time
from common import *

__all__ = ['splitToTransDic', 'splitToTransDicAuto', 
		'generateJisList', 'generateTunnelJis', 'generateTunnelJisMap',
		'generateSubsDic', 'generateSubsJis', 'generateSubsConfig',
		'writeSubsConfig',
		'replaceValue', 'replaceValueRE', 'replaceValueFull', 
		'keepFirstTrans',
		'getBytes', #'OldEncodeName',
		'keepBytes', 'TextConfig'
]

#inner text config
TextConfig = {
	'orig_fix': {
		'RealLive': {
			' +': '' #删除fix填充的空格
		},
		'Silky_map': {
			'<001A0014>': '\n' #换行字节
		}
	},
	'trans_fix': {
		'RealLive': {
			'<n>': '<230003C900000000>' #还原换行字节
		},
		'Silky_map': {
			'\n': '<001A0014>' #还原换行字节
		}
	}
}

#OldEncodeName = 'cp932'
BytePadding = ord(' ') #字节补齐，默认为英文空格
#----------------------------------------------------------
def getBytes(text, NewEncodeName):
	transData = None
	if ExVar.tunnelJis: #JIS隧道
		transData, _ = generateTunnelJis(text)
	elif ExVar.subsJis: #JIS替换
		transData, _ = generateSubsJis(text)
	else:
		try:
			transData, _ = encodeText(text, NewEncodeName)
		except Exception as ex:
			print(ex)
			return None
	return transData

def getBytesMax(text, NewEncodeName, maxLen):
	transData = None
	cutoffLen = 0
	if ExVar.tunnelJis: #JIS隧道
		transData, cutoffLen = generateTunnelJis(text, maxLen)
	elif ExVar.subsJis: #JIS替换
		transData, cutoffLen = generateSubsJis(text, maxLen)
	else:
		try:
			transData, cutoffLen = encodeText(text, NewEncodeName, maxLen)
		except Exception as ex:
			print(ex)
			return None, 0
	totalLen = len(transData)
	if cutoffLen > 0: #截断
		transData = transData[0:cutoffLen]
	return transData, maxLen - totalLen

#----------------------------------------------------------
#编码生成目标长度的字节数组，会截断和填充字节
def generateBytes(text, lenOrig, NewEncodeName):
	if ExVar.cutoff == False:
		transData = getBytes(text, NewEncodeName)
		return transData
	# 检查长度
	transData, diff = getBytesMax(text, NewEncodeName, lenOrig)
	if transData == None: return transData
	#print('Diff', diff) 
	#diff为预计最终差值，即原文字节长度减去不截断时的译文字节长度
	if diff < 0:
		dic = ExVar.cutoffDic
		if text not in dic:
			if ExVar.cutoffCopy:
				dic[text] = [text, diff]
			else:
				dic[text] = ['', diff]
		elif dic[text][0] != '':
			#从cutoff字典读取
			oldText = text
			text = dic[oldText][0]
			transData, diff = getBytesMax(text, NewEncodeName, lenOrig)
			dic[oldText][1] = diff #刷新长度
		if diff < 0:
			#进行了截断
			printWarning('译文长度超出原文，部分截断', text)
	lost = lenOrig - len(transData) #lost为截断后实际差值
	if lost < 0:
		printError('截断后仍然超长')
		return None
	if lost > 0:
		# 右边补足空格
		#print(transData)
		padLen = len(ExVar.padding)
		empty = bytearray(lost)
		end = 0
		for start in range(0, lost-padLen+1, padLen): #填充padding
			end = start + padLen
			empty[start:end] = ExVar.padding
		for start in range(end, lost): #剩余填充英文空格
			empty[start] = BytePadding
		transData += empty
	return transData

#----------------------------------------------------------
#保留字节
def keepBytes(data, reg):
	newdata = bytearray()
	iter = re.finditer(reg, data)
	preEnd = 0
	for match in iter:
		start = match.start()
		if start > preEnd:
			newdata.extend(data[preEnd:start])
		end = start + len(match.group())
		text:bytes = data[start:end]
		text = text.hex().upper()
		newdata.extend(f'<{text}>'.encode('ascii'))
		preEnd = end
	if preEnd == 0:
		return data
	if preEnd < len(data):
		newdata.extend(data[preEnd:])
	return newdata

#encode
def encodeText(text, NewEncodeName, maxLen=0):
	if ExVar.keepBytes or ExVar.cutoff:
		cutoffLen = 0
		data = bytearray()
		pos = 0
		while pos < len(text):
			bs, pos = encodeChar(text, NewEncodeName, pos)
			data.extend(bs)
			if maxLen > 0 and len(data) > maxLen and cutoffLen == 0:
				cutoffLen = len(data) - len(bs)
		return data, cutoffLen
	return text.encode(NewEncodeName), 0

#encode one
#返回值:
#	1成功; -1字节还原
keepBytesSearch = re.compile(r'<[0-9a-zA-Z]+?>')
def encodeChar(text, NewEncodeName, pos):
	wchar = text[pos]
	if ExVar.keepBytes:
		if wchar == '<':
			#字节还原
			match = keepBytesSearch.match(text, pos=pos)
			if match:
				pos = match.end()
				bs = bytes.fromhex(match.group()[1:-1])
				return bs, pos
	bs = wchar.encode(NewEncodeName)
	pos += 1
	return bs, pos

#----------------------------------------------------------
#sep = '\r\n'
#sepLen = 2
#symbolPattern = '[\\u3000-\\u303F\\uFF00-\\uFF65\\u2000-\\u206F]'
#searchCount = 10

#固定分割
def splitToTransDic(orig, trans):
	if orig == '': return #整体原文为空则不处理
	#if trans == '': return #整体译文为空则不处理
	if ExVar.preReplace:
		#分割前替换
		if 'replace_before_split' in ExVar.textConf:
			replaceDic = ExVar.textConf['replace_before_split']
			for old, new in replaceDic.items():
				trans = re.sub(old, new, trans)
	if ExVar.splitAuto:
		#重新分割
		splitToTransDicAuto(orig, trans) 
		return
	sepRegex = ExVar.splitParaSepRegex
	listMsgOrig = re.split(sepRegex, orig)
	listMsgTrans = re.split(sepRegex, trans)
	if len(listMsgTrans) > len(listMsgOrig):
		#合并末尾多余行数
		i = len(listMsgOrig) - 1
		listMsgTrans[i] = ''.join(listMsgTrans[i:])
		for j in range(len(listMsgTrans)-1, i, -1):
			listMsgTrans.pop(j)
	for j in range(len(listMsgOrig)):
		msgOrig = listMsgOrig[j]
		if trans == '': #整体为空则不需要补齐
			msgTrans = ''
		else:
			msgTrans = ExVar.addSpace
			if j<len(listMsgTrans):
				msgTrans = listMsgTrans[j]
		if msgOrig not in ExVar.transDic:
			ExVar.transDic[msgOrig] = []
		ExVar.transDic[msgOrig].append(msgTrans)
		if len(msgTrans) > ExVar.maxCountPerLine:
			printWarning('长度超过设置阈值', msgTrans)

#自动重新分割
def splitToTransDicAuto(orig, trans):
	listMsgOrig, listMsgTrans = redistributeTrans(orig, trans)
	if ExVar.joinAfterSplit:
		#重新分割，但是再合并
		sep = ExVar.splitParaSep
		#orig = sep.join(listMsgOrig) #再合并不影响orig
		trans = sep.join(listMsgTrans)
		if orig not in ExVar.transDic:
			ExVar.transDic[orig] = []
		ExVar.transDic[orig].append(trans)
		return
	for j in range(len(listMsgOrig)):
		msgOrig = listMsgOrig[j]
		msgTrans = listMsgTrans[j]
		if len(msgTrans) > ExVar.maxCountPerLine:
			printWarning('长度超过设置阈值', msgTrans)
		if msgOrig not in ExVar.transDic:
			ExVar.transDic[msgOrig] = []
		ExVar.transDic[msgOrig].append(msgTrans)

#重新分割
def redistributeTrans(orig:str, trans:str):
	sepRegex = ExVar.splitParaSepRegex
	#分割原文
	origList = re.split(sepRegex, orig)
	newTrans = re.sub(sepRegex, '', trans)
	if len(origList) == 1:
		return origList, [newTrans]
	if ExVar.ignoreSameLineCount or ExVar.ignoreNotMaxCount:
		transList = re.split(sepRegex, trans)
		#行数一致则忽略
		if ExVar.ignoreSameLineCount and len(origList) == len(transList):
			return origList, transList
		#不超长则忽略
		if ExVar.ignoreNotMaxCount and len(origList) >= len(transList):
			if not any(len(t) > ExVar.maxCountPerLine for t in transList):
				for i in range(len(origList)):
					if i >= len(transList):
						transList.append(ExVar.addSpace)
					elif transList[i] == '':
						transList[i] = ExVar.addSpace
				return origList, transList
	if ExVar.fixedMaxPerLine:
		#固定长度
		lineLen = ExVar.maxCountPerLine
		transList = [newTrans[i:i+lineLen] for i in range(0, len(newTrans), lineLen)]
		if len(transList) > len(origList):
			#合并末尾多余行数
			i = len(origList) - 1
			transList[i] = ''.join(transList[i:])
			for j in range(len(transList)-1, i, -1):
				transList.pop(j)
		else:
			for i in range(len(transList), len(origList)):
				transList.append(ExVar.addSpace)
		return origList, transList
	#查询译文符号
	transSymbolList = []
	matches = re.finditer(ExVar.symbolPattern, newTrans)
	for match in matches:
		transSymbolList.append(match.end()) #右区间，不包含
	#找出最接近的下标
	transSepList = []
	if len(transSymbolList) <= len(origList):
		#符号数量不大于原文行数
		for index in range(len(origList)):
			if index < len(transSymbolList):
				transSepList.append(transSymbolList[index])
			else:
				transSepList.append(len(newTrans))
	else:
		#符号数量大于原文行数
		scale = len(trans) / len(orig)
		origSepList = []
		length = 0
		for seq in range(len(origList) - 1):
			length += len(origList[seq])
			pos = math.floor(length * scale)
			origSepList.append(pos)
		#查找
		transIndexList = []
		for j, pos in enumerate(origSepList):
			index = findNearestIndex(transSymbolList, pos)
			if j>0 and index <= transIndexList[j-1]:
				index = transIndexList[j-1] + 1
			transIndexList.append(index)
		transIndexList.append(len(transSymbolList)-1)
		#修正尾部重复
		for j in range(len(transIndexList) - 2, -1, -1):
			if transIndexList[j] >= transIndexList[j+1]:
				transIndexList[j] = transIndexList[j+1] - 1
			else:
				break
		#分配
		for index in transIndexList:
			transSepList.append(transSymbolList[index])
	#分割译文
	transList = []
	start = 0
	for end in transSepList:
		if start == end:
			transList.append(ExVar.addSpace)
			#printWarningGreen('添加空行', trans)
		else:
			transList.append(newTrans[start:end])
		start = end
	return origList, transList

# ------------------------------------------------------------
tunnelJisList = []
tunnelUnicodeList = []
lowBytesToAvoid = [ ord('\t'), ord('\n'), ord('\r'), ord(' '), ord(',') ]
#生成VNT的Jis表
def generateJisList():
	tunnelUnicodeList.clear()
	global tunnelJisList
	if tunnelJisList != []: return
	lst = list(range(0x81, 0xA0)) + list(range(0xE0, 0xFE))
	for i in lst:
		for j in range(0x01, 0x40):
			if j in lowBytesToAvoid: continue
			tunnelJisList.append(i.to_bytes(1, byteorder='little') + j.to_bytes(1, byteorder='little'))

#插入VNT的字符表，生成JIS编码文本
def generateTunnelJis(text, maxLen=0):
	data = bytearray()
	cutoffLen = 0
	pos = 0
	while pos < len(text):
		try:
			b, pos = encodeChar(text, ExVar.JisEncodeName, pos)
		except Exception as ex:
			wchar = text[pos]
			pos += 1
			if wchar in tunnelUnicodeList:
				#已存在
				index = tunnelUnicodeList.index(wchar)
			else:
				#新增
				index = len(tunnelUnicodeList)
				tunnelUnicodeList.append(wchar)
			#获取转换字符
			b = tunnelJisList[index]
		#导出
		data.extend(b)
		if maxLen > 0 and cutoffLen == 0:
			if len(data) < maxLen:
				pass
			elif len(data) == maxLen:
				cutoffLen = maxLen
			else:
				cutoffLen = len(data) - len(b)
	if cutoffLen == len(data):
		cutoffLen = 0
	return data, cutoffLen

def generateTunnelJisMap(filepath=''):
	data = bytearray()
	for wchar in tunnelUnicodeList:
		bs = wchar.encode('utf-16-le')
		data.extend(bs)
	if filepath != None:
		if filepath == '':
			filepath = os.path.join(ExVar.workpath, 'ctrl', 'sjis_ext.bin')
		fileOutput = open(filepath, 'wb')
		fileOutput.write(data)
		fileOutput.close()
		printWarningGreen('在ctrl文件夹下生成了sjis_ext.bin')
	#subs配置
	readSubsConfig()
	subsConfig['tunnel_decoder']['mapping'] = ''.join(tunnelUnicodeList)
	subsConfig['tunnel_decoder']['enable'] = True
	writeSubsConfig()
	return data

# ------------------------------------------------------------
import json
subsDic = {} #预设字典，默认来自GalTransl_DumpInjector项目
subsDicValues = [] #预设字典的Value列表，即替换后的字符列表
subsJPList = [] #jp
subsCNList = [] #cn
subsRemainList = [] #剩余的cn
subsRepeatList = [] #和替换后字符重复的原始译文字符
subsConfig = {}

def generateSubsDic():
	subsJPList.clear()
	subsCNList.clear()
	subsRemainList.clear()
	subsRepeatList.clear()
	global subsDic, subsDicValues
	if subsDic != {}: return
	filepath = os.path.join('src', 'subs_cn_jp.json')
	fileOld = open(filepath, 'r', encoding='utf-8')
	subsDic = json.load(fileOld)
	subsDicValues = set(subsDic.values()) #集合提高效率
	printInfo('读入subs字典：', os.path.basename(filepath))

#生成替换后的JIS编码文本
def generateSubsJis(text, maxLen=0):
	data = bytearray()
	cutoffLen = 0
	pos = 0
	while pos < len(text):
		wchar = text[pos]
		if wchar in subsDicValues:
			#原始字符和替换后字符重复
			subsRepeatList.append(wchar)
		try:
			#b = wchar.encode(OldEncodeName)
			#pos += 1
			b, pos = encodeChar(text, ExVar.JisEncodeName, pos)
		except Exception as ex:
			pos += 1
			if wchar in subsDic:
				#存在预设
				if wchar not in subsCNList:
					#未加入列表
					subsJPList.append(subsDic[wchar])
					subsCNList.append(wchar)
				b = subsDic[wchar].encode(ExVar.JisEncodeName)
			else:
				#不存在预设
				subsRemainList.append(wchar)
				#wcharList.append(wchar)
				printError('JIS替换字典不存在字符：', wchar)
				b = '　'.encode(ExVar.JisEncodeName)
		#导出
		data.extend(b)
		if maxLen > 0 and cutoffLen == 0:
			if len(data) < maxLen:
				pass
			elif len(data) == maxLen:
				cutoffLen = maxLen
			else:
				cutoffLen = len(data) - len(b)
	if cutoffLen == len(data):
		cutoffLen = 0
	return data, cutoffLen
	
#生成配置文件
def generateSubsConfig():
	readSubsConfig()
	subs = subsConfig['character_substitution']
	subs['source_characters'] = ''.join(subsJPList)
	subs['target_characters'] = ''.join(subsCNList)
	subs['enable'] = True
	if subsRemainList != []:
		lst = list(set(subsRemainList))
		subs['remain'] = lst
		printError('译文存在替换字典未匹配字符，请进行修正；详见uif_config.json中remain：\n', ''.join(lst))
	elif 'remain' in subs:
		del subs['remain']
	lst = list(set(subsRepeatList))
	if '―' in lst: #不处理
		lst.remove('―')
	if lst != []:
		subs['repeat'] = lst
		printError('原始译文含有替换后字符，如果使用字体请进行修正，如果使用hook则无需修正；详见uif_config.json中repeat：（常用汉字修正请留言https://github.com/satan53x/SExtractor/issues/74）\n', ''.join(lst))
	elif 'repeat' in subs:
		del subs['repeat']
	writeSubsConfig()

def readSubsConfig():
	global subsConfig
	filepath = os.path.join('src', 'uif_config.json')
	fileOld = open(filepath, 'r', encoding='utf-8')
	subsConfig = json.load(fileOld)
	fileOld.close()

def writeSubsConfig(filepath=''):
	if filepath == '':
		filepath = os.path.join(ExVar.workpath, 'ctrl', 'uif_config.json')
	fileOutput = open(filepath, 'w', encoding='utf-8')
	json.dump(subsConfig, fileOutput, ensure_ascii=False, indent=2)
	fileOutput.close()
	printWarningGreen('在ctrl文件夹下生成了uif_config.json')
	
# ------------------------------------------------------------
def replaceValue(transDic, replaceDic):
	for orig, trans in transDic.items():
		for old, new in replaceDic.items():
			for i, t in enumerate(trans):
				trans[i] = t.replace(old, new)

def replaceValueRE(transDic, replaceDic):
	for orig, trans in transDic.items():
		for old, new in replaceDic.items():
			for i, t in enumerate(trans):
				trans[i] = re.sub(old, new, t)	

def replaceValueFull(transDic, replaceDic):
	for orig, trans in transDic.items():
		for old, new in replaceDic.items():
			for i, t in enumerate(trans):
				if t == old:
					trans[i] = new

#只保留第一个，用于输出
def keepFirstTrans(transDic):
	if not isinstance(transDic, dict):
		return transDic
	newDic = {}
	for orig, trans in transDic.items():
		newDic[orig] = trans[0]
	return newDic