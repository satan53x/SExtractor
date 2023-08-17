import re
from common import *

__all__ = ['initTextVar', 'splitToTransDic']

var = None

def initTextVar(v):
	global var
	var = v

def splitToTransDic(orig, trans):
	listMsgOrig = re.split('\r\n', orig)
	listMsgTrans = re.split('\r\n', trans)
	for j in range(len(listMsgOrig)):
		msgOrig = listMsgOrig[j]
		msgTrans = '　'
		if j<len(listMsgTrans) and listMsgTrans[j] != '':
			msgTrans = listMsgTrans[j]
		if  msgOrig not in var.transDic or \
			var.transDic[msgOrig] == '' or \
			var.transDic[msgOrig] == '　' or \
			var.transDic[msgOrig] == ' ':
			var.transDic[msgOrig] = msgTrans




