import math
import re
from common import *

__all__ = ['splitToTransDic', 'splitToTransDicAuto']

#sep = '\r\n'
sepLen = 2
symbolPattern = '[\\u3000-\\u303F\\uFF00-\\uFF65\\u2000-\\u206F]'
searchCount = 10

#固定分割
def splitToTransDic(orig, trans):
	if trans == '': return #整体译文为空则不处理
	if ExVar.splitAuto:
		#重新分割
		splitToTransDicAuto(orig, trans) 
		return
	sep = ExVar.splitParaSep
	listMsgOrig = re.split(sep, orig)
	listMsgTrans = re.split(sep, trans)
	for j in range(len(listMsgOrig)):
		msgOrig = listMsgOrig[j]
		msgTrans = '　'
		if j<len(listMsgTrans) and listMsgTrans[j] != '':
			msgTrans = listMsgTrans[j]
		if  msgOrig not in ExVar.transDic or \
			ExVar.transDic[msgOrig] == '' or \
			ExVar.transDic[msgOrig] == '　' or \
			ExVar.transDic[msgOrig] == ' ':
			if len(msgTrans) > ExVar.maxCountPerLine:
				printWarning('译文长度存疑', msgTrans)
			ExVar.transDic[msgOrig] = msgTrans

#自动重新分割
def splitToTransDicAuto(orig, trans):
	listMsgOrig, listMsgTrans = redistributeTrans(orig, trans)
	for j in range(len(listMsgOrig)):
		msgOrig = listMsgOrig[j]
		msgTrans = listMsgTrans[j]
		if len(msgTrans) > ExVar.maxCountPerLine:
			printWarning('译文长度存疑', msgTrans)
		ExVar.transDic[msgOrig] = msgTrans

#重新分割
def redistributeTrans(orig:str, trans:str):
	sep = ExVar.splitParaSep
	#分割原文
	origList = re.split(sep, orig)
	newTrans = re.sub(sep, '', trans)
	if len(origList) == 1:
		return origList, [newTrans]
	# transList = re.split(sep, trans)
	# if len(origList) == len(transList):
	# 	return origList, transList
	#查询译文符号
	transSymbolList = []
	matches = re.finditer(symbolPattern, newTrans)
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
			transList.append('　')
		else:
			transList.append(newTrans[start:end])
		start = end
	return origList, transList





