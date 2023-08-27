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
			ExVar.transDic[msgOrig] = msgTrans

#自动重新分割
#TODO
def splitToTransDicAuto(orig, trans):
	listMsgOrig = re.split(sep, orig)
	listMsgTrans = redistributeTrans(orig, trans)
	for j in range(len(listMsgOrig)):
		msgOrig = listMsgOrig[j]
		msgTrans = listMsgTrans[j]
		ExVar.transDic[msgOrig] = msgTrans

#重新分割
def redistributeTrans(orig:str, trans:str):
	#分割原文
	origList = re.split(sep, orig)
	trans = re.sub(sep, '', trans)
	transList = []
	start = 0
	for index in range(len(origList) - 1):
		#单行处理
		orig = origList[index]
		end = start + len(orig) #最大长度为原文长度
		pos = end
		for i in range(1, searchCount, 1):
			#单个字符扫描
			pos = end - i
			if pos < start:
				#扫描失败
				pos = end
				break
			ret = re.match(symbolPattern, trans[pos])
			if ret:
				pos += 1
				break
		transList[index] = trans[start:pos]
		start = pos
	#最后一行保留所有
	transList[-1] = trans[start:]
	return origList, transList





