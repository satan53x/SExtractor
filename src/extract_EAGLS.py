import re
import sys
import os
import struct
from common import *

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
		if re.match(rb'[#&]', lineData) == None: continue #无数据行
		tmpDic = {}
		#对话
		iter = re.finditer(rb'"[^\w,][^"]+"', lineData)
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
		transData = lTrans[i].encode(NewEncodeName)
		# 检查长度
		lenOrig = end - start
		lenTrans = len(transData)
		#print(contentIndex, start, end)
		count = lenOrig - lenTrans
		#print('Diff', count)
		if count < 0:
			transData = transData[0:lenOrig]
			print('>>>>>> count warning', lTrans[i])
			#print(transData.decode(NewEncodeName))
		#	print('>>>>>> count warning', count, lCtrl[i], lTrans[i])
		#	return False
		else:
			# 右边补足空格
			#print(transData)
			empty = bytearray(count)
			for i in range(int(count)):
				empty[i] = 0x20
			transData += empty
		#写入new
		strNew = content[contentIndex][:start] + transData + content[contentIndex][end:]
		content[contentIndex] = strNew
		return True