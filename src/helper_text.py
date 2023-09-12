import re
from common import *

__all__ = ['splitToTransDic', 'splitToTransDicAuto']

sep = '\r\n'
sepLen = 2
symbolPattern = '[\\u3000-\\u303F\\uFF00-\\uFF65\\u2000-\\u206F]'
searchCount = 10

#固定分割
def splitToTransDic(orig, trans):
	if trans == '': return #整体译文为空则不处理
	if ExVar.splitIndexArray:
		#重新分割
		splitToTransDicAuto(orig, trans) 
		return
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
	#分割原文
	scale = len(trans) / len(orig)
	origList = re.split(sep, orig)
	transList = re.split(sep, trans)
	if len(origList) == len(transList):
		#个数相同则不需要进行重新分割
		return origList, transList
	newTrans = re.sub(sep, '', trans)
	transList = []
	start = 0
	max = len(newTrans)
	for index in range(len(origList) - 1):
		#单行处理
		orig = origList[index]
		end = start + round(len(orig)*scale) #初始搜索位置
		if end > max:
			end = max
		pos = end
		for i in ExVar.splitIndexArray:
			#单个字符扫描
			pos = end + i
			if pos < start or pos >= max:
				#扫描失败
				pos = end
				#printWarning('建议手动修正分割:', trans.replace('\r\n', '\\r\\n'))
				break
			ret = re.match(symbolPattern, newTrans[pos])
			if ret:
				pos += 1
				break
		text = newTrans[start:pos] or '　'
		transList.append(text)
		start = pos
	#最后一行保留所有
	text = newTrans[start:] or '　'
	transList.append(text)
	return origList, transList





