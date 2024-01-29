import re
from common import *
from extract_BIN import replaceOnceImp as replaceOnceImpBIN
from extract_TXT import searchLine, ParseVar, GetRegList

OldEncodeName = 'cp932'
NewEncodeName = 'gbk'

# ---------------- Engine: Custom -------------------
# content按配置中contentSeparate分割
def parseImp(content, listCtrl, dealOnce):
	for contentIndex in range(len(content)):
		lineData = content[contentIndex]
		# TODO 在这附近修改
		start = 0
		end = len(lineData)
		# TODO
		text = lineData[start:end].decode(OldEncodeName)
		# 0行数，1起始字符下标（包含），2结束字符下标（不包含）
		ctrl = {'pos':[contentIndex, start, end]}
		#ctrl['name'] = True #名字
		#ctrl['unfinish'] = True #段落未完结
		if dealOnce(text): listCtrl.append(ctrl)

# -----------------------------------
def replaceOnceImp(content, lCtrl, lTrans):
	return replaceOnceImpBIN(content, lCtrl, lTrans)