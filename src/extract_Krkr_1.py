import re
import sys
import os
import struct
from common import *

from extract_TXT import ParseVar, searchLine, initParseVar
from extract_TXT import replaceOnceImp as replaceOnceImpTXT

# ---------------- Group: Krkr 1 -------------------
def parseImp(content, listCtrl, dealOnce):
	listR = GetG('Var').extraData.split(',')
	if listR[0] == '':
		listR[0] = 'r' #默认的[r]换行标志，表示段落未结束
	var = ParseVar(listCtrl, dealOnce)
	initParseVar(var)
	for contentIndex in range(len(content)):
		if contentIndex < GetG('Var').startline: continue 
		var.lineData = content[contentIndex][:-1] #忽略换行
		# 每行
		var.contentIndex = contentIndex
		ctrls = searchLine(var)
		if ctrls == None: continue #skip
		if len(ctrls) > 0: continue #已匹配到
		#print(var.lineData)
		#搜索
		ctrl = None
		endWithR = False
		iter = re.finditer(r'[^\[\]]+', var.lineData)
		for r in iter:
			endWithR = False
			text = r.group()
			if re.match(r'[A-Za-z]', text):
				#控制段
				if text in listR:
					endWithR = True
				continue
			start = r.start()
			end = r.end()
			ctrl = {'pos':[contentIndex, start, end]}
			ctrl['unfinish'] = True
			if dealOnce(text, contentIndex):
				listCtrl.append(ctrl)
		if not endWithR:
			if ctrl and 'unfinish' in ctrl:
				del ctrl['unfinish'] #段落结束

# -----------------------------------
def replaceOnceImp(content, lCtrl, lTrans):
	return replaceOnceImpTXT(content, lCtrl, lTrans)
