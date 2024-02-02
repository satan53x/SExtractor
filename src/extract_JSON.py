from common import *
from extract_TXT import ParseVar, GetRegList, searchLine, initParseVar

copyKeyToValue = True

# ---------------- Group: JSON -------------------
def parseImp(content, listCtrl, dealOnce):
	if content == []: return
	var = ParseVar(listCtrl, dealOnce)
	initParseVar(var)
	#print(len(content))
	ExVar.indent = 2
	if isinstance(content, dict):
		#字典: 子项为字符串key:value
		if copyKeyToValue:
			#复制key到value
			for key, value in content.items():
				if value == '':
					content[key] = key
		index = -1
		for i, value in content.items():
			index += 1
			if index < ExVar.startline: continue 
			lineData = value
			if lineData == '': continue #空白行
			var.contentIndex = [i, None]
			var.lineData = lineData
			searchLine(var)
	else:
		#列表
		if isinstance(content[0], dict):
			#子项为字典
			for i in range(len(content)):
				if i < ExVar.startline: continue 
				for j, value in content[i].items(): #j可以是key值
					lineData = value
					if lineData == '': continue #空白行
					var.contentIndex = [i, j]
					var.lineData = lineData
					ctrls = searchLine(var)
					if ExVar.keepFormat and ctrls and len(ctrls) > 0:
						#保持格式
						ctrl = ctrls[-1]
						if j == 'name':
							ctrl['name'] = True
						elif j == 'message':
							if 'unfinish' in ctrl:
								del ctrl['unfinish']
		elif isinstance(content[0], str):
			#子项为字符串
			for i in range(len(content)):
				if i < ExVar.startline: continue
				lineData = content[i]
				if lineData == '': continue #空白行
				var.contentIndex = [i, None]
				var.lineData = lineData
				searchLine(var)

# -----------------------------------
def replaceOnceImp(content, lCtrl, lTrans):
	num = len(lCtrl)
	for index in range(num):
		# 位置
		ctrl = lCtrl[index]
		contentIndex, start, end = ctrl['pos']
		trans = lTrans[index]
		#写入new
		i = contentIndex[0]
		j = contentIndex[1]
		if j == None:
			#一层
			strOld = content[i]
			strNew = strOld[:start] + trans + strOld[end:]
			content[i] = strNew
		else:
			#两层
			strOld = content[i][j]
			strNew = strOld[:start] + trans + strOld[end:]
			content[i][j] = strNew
			


