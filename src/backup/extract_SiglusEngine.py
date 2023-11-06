import re
from common import *

# ---------------- Group: SiglusEngine -------------------
def parseImp(content, listCtrl, dealOnce):
	listIndex = 0
	nameList = ExVar.nameList
	for contentIndex in range(len(content)):
		#if contentIndex < 0: continue #起始跳过行数
		lineData = content[contentIndex]
		#每行
		#print('>>> Line ' + str(contentIndex), ': ', lineData)
		ret = re.match(r'●\d+●', lineData)
		if ret:
			#print(ret)
			start = ret.end()
			end = len(lineData) - 1
			text = lineData[start:end]
			#0行数，1起始字符下标（包含），2结束字符下标（不包含）
			ctrl = {'pos':[contentIndex, start, end]}
			if text in nameList:
				ctrl['name'] = True #名字标记
			#print(ctrl)
			if dealOnce(text, listIndex):
				listIndex += 1
				listCtrl.append(ctrl)

# -----------------------------------
def replaceOnceImp(content, lCtrl, lTrans):
	#print(lCtrl)
	#print(lTrans)
	num = len(lCtrl)
	for i in range(num):
		# 位置
		ctrl = lCtrl[i]
		posData = ctrl['pos']
		contentIndex = posData[0]
		start = posData[1]
		end = posData[2]
		trans = lTrans[i]
		#写入new
		strNew = content[contentIndex][:start] + trans + content[contentIndex][end:]
		#print(strNew)
		content[contentIndex] = strNew
		return True