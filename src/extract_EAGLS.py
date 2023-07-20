import re
from common import *
import extract_BIN

OldEncodeName = 'cp932'
NewEncodeName = 'gbk'

# ---------------- Engine: EAGLS -------------------
def parseImp(content, listCtrl, dealOnce):
	listIndex = 0
	#print(len(content))
	for contentIndex in range(len(content)):
		if contentIndex < 1: continue 
		lineData = content[contentIndex]
		start = 0
		end = 0
		#每行
		#print('>>> Line ' + str(contentIndex), ': ', lineData)
		#if lineData.isspace(): continue #空白行
		if re.match(rb'[#&]', lineData) == None:
			if re.match(rb'52', lineData):
				#提取选择项
				ret = re.finditer(rb'"_SelStr\d*?","([^"]+?)"', lineData)
				for r in ret:
					#print(r.group(1).decode(OldEncodeName))
					start = r.start(1)
					end = r.end(1)
					text = lineData[start:end].decode(OldEncodeName)
					#0行数，1起始字符下标（包含），2结束字符下标（不包含）
					ctrl = {'pos':[contentIndex, start, end]}
					if dealOnce(text, listIndex):
						listIndex += 1
						listCtrl.append(ctrl)
			continue
		tmpDic = {}
		#对话
		iter = re.finditer(rb'"[^a-zA-Z0-9_,\)&][^"]+"', lineData)
		for r in iter:
			start = r.start() + 1
			end = r.end() - 1
			text = lineData[start:end].decode(OldEncodeName)
			#0行数，1起始字符下标（包含），2结束字符下标（不包含）
			ctrl = {'pos':[contentIndex, start, end]}
			tmpDic[start] = [text, ctrl]
		#名字
		iter = re.finditer(rb'#[^=&]*', lineData)
		for r in iter:
			start = r.start() + 1
			end = r.end()
			text = lineData[start:end].decode(OldEncodeName)
			#0行数，1起始字符下标（包含），2结束字符下标（不包含）
			ctrl = {'pos':[contentIndex, start, end]}
			ctrl['isName'] = True #名字标记
			tmpDic[start] = [text, ctrl]
		#按文本中顺序处理
		for key in sorted(tmpDic.keys()):
			value = tmpDic[key]
			if dealOnce(value[0], listIndex):
				listIndex += 1
				listCtrl.append(value[1])

# -----------------------------------
def replaceOnceImp(content, lCtrl, lTrans):
	extract_BIN.replaceOnceImp(content, lCtrl, lTrans)