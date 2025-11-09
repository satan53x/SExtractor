import re
from common import *

from extract_TXT import ParseVar, searchLine, initParseVar, GetRegList
from extract_TXT import replaceOnceImp as replaceOnceImpTXT

def initExtra():
	endStr = ExVar.endStr
	ctrlStr = ExVar.ctrlStr
	sepStr = ExVar.sepStr
	mergeStr = ExVar.mergeStr
	extractKey = ExVar.extractKey
	if not endStr:
		endStr = 'np'
	if not endStr.startswith('^'):
		endStr = '^' + endStr + '$'
	if not ctrlStr:
		ctrlStr = '^[A-Za-z]'
	if not sepStr:
		sepList = ['[', ']']
	elif isinstance(sepStr, str):
		sepList = sepStr.split(',')
	if mergeStr: #可以为None
		mergeStr = re.compile(mergeStr)
	if not extractKey:
		extractKey = '^(?P<unfinish>[\\S\\s]+)$'
	regList = GetRegList({
		'10_search': extractKey
	}.items())
	return re.compile(endStr), re.compile(ctrlStr), mergeStr, sepList, regList

# ---------------- Group: Krkr Split -------------------
def parseImp(content, listCtrl, dealOnce):
	endStr, ctrlStr, mergeStr, sepList, inlineRegList = initExtra()
	addSep = ExVar.extraData == 'addSep'
	var = ParseVar(listCtrl, dealOnce)
	initParseVar(var)
	regList = var.regList
	for contentIndex in range(len(content)):
		if contentIndex < ExVar.startline: continue 
		# 每行
		var.lineData = content[contentIndex]
		var.contentIndex = contentIndex
		var.searchStart = 0
		var.searchEnd = -1
		var.regList = regList #原始正则
		ctrls = searchLine(var)
		if ctrls == None or len(ctrls) > 0:
			#要求段落结束后一定有skip
			if var.lastCtrl and 'unfinish' in var.lastCtrl:
				del var.lastCtrl['unfinish'] 
			var.lastCtrl = None
			continue
		#print(var.lineData)
		#搜索
		matches = findNested(var.lineData, open_char=sepList[0], close_char=sepList[1], add_outer=True, add_sep=addSep, check_inner=mergeStr)
		for start, end in matches:
			text = var.lineData[start:end]
			if endStr.search(text):
				if var.lastCtrl and 'unfinish' in var.lastCtrl:
					del var.lastCtrl['unfinish'] 
				var.lastCtrl = None
				continue
			if ctrlStr.search(text):
				continue
			var.searchStart = start
			var.searchEnd = end
			var.regList = inlineRegList #内部正则
			ctrls = searchLine(var)
			if ctrls and len(ctrls) > 0:
				var.lastCtrl = ctrls[-1]

# -----------------------------------
def replaceOnceImp(content, lCtrl, lTrans):
	return replaceOnceImpTXT(content, lCtrl, lTrans)

def findNested(text, open_char='[', close_char=']', add_outer=False, add_sep=False, check_inner=None):
	start = 0
	count = 0
	pre = 0
	pos = 0
	skip_next = False
	results = []
	for pos, char in enumerate(text):
		if char == open_char:
			if count == 0:
				if check_inner and check_inner.search(text[pos+1:]):
					skip_next = True #不进行加入
				else:
					start = pos
					if add_outer and pre < pos:
						results.append((pre, pos))
						pre = pos
			count += 1
		elif char == close_char:
			count -= 1
			if count == 0:
				if skip_next:
					skip_next = False
				else:
					if add_sep:
						results.append((start, pos + 1))
					else:
						results.append((start + 1, pos))
					pre = pos + 1
	if add_outer and pre < pos:
		results.append((pre, pos + 1))
		pre = pos + 1
	return results