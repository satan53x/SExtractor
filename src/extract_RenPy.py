from common import *
from extract_TXT import parseImp as parseImpTXT
from extract_TXT import replaceOnceImp as replaceOnceImpTXT

# ---------------- Group: RenPy -------------------
def parseImp(content, listCtrl, dealOnce):
	#处理复制
	checkCopy = ExVar.extraData
	if checkCopy:
		for contentIndex in range(len(content)):
			if contentIndex < ExVar.startline: continue 
			line = content[contentIndex]
			if re.search(checkCopy, line):
				preline = content[contentIndex-1]
				if re.match('\\s*# ?', preline):
					preline = re.sub('(\\s*)# ?', '\\1', preline)
					content[contentIndex] = preline
				elif re.match('\\s*old', preline):
					preline = re.sub('(\\s*)old', '\\1new', preline)
					content[contentIndex] = preline
				else:
					printWarningGreen('强制复制', preline)
					content[contentIndex] = str(preline)
	parseImpTXT(content, listCtrl, dealOnce)

# -----------------------------------
def replaceOnceImp(content, lCtrl, lTrans):
	replaceOnceImpTXT(content, lCtrl, lTrans)