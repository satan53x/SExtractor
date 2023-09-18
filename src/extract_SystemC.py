import re
from common import *
from extract_BIN import replaceOnceImp as replaceOnceImpBIN
from extract_TXT import searchLine, ParseVar, GetRegList


# ---------------- Engine: SystemC -------------------
def parseImp(content, listCtrl, dealOnce):
	var = ParseVar(listCtrl, dealOnce)
	var.OldEncodeName = ExVar.OldEncodeName
	lastCtrl = None
	regSkip = [rb'^[A-Za-z/\*]', rb'^$']
	regName = [ [r'^(?P<name>.+?)　（'.encode(ExVar.OldEncodeName), 'search'] ]
	regMessage = [ [r'^(?P<unfinish>.+)$'.encode(ExVar.OldEncodeName), 'search'] ]
	for contentIndex in range(len(content)):
		var.lineData = content[contentIndex]
		if any(re.match(pattern, var.lineData) for pattern in regSkip):
			if lastCtrl and 'unfinish' in lastCtrl:
				del lastCtrl['unfinish']
			lastCtrl = None
			continue
		var.contentIndex = contentIndex
		ctrls = []
		if lastCtrl == None:
			#前一行不是message时才检查名字
			var.regList = regName
			ctrls = searchLine(var)
		if len(ctrls) == 0:
			var.regList = regMessage
			ctrls = searchLine(var)
		if len(ctrls) > 0:
			lastCtrl = ctrls[0]

# -----------------------------------
def replaceOnceImp(content, lCtrl, lTrans):
	return replaceOnceImpBIN(content, lCtrl, lTrans)