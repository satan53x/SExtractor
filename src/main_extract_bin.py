import os
import sys
import json
import re
from main_extract import *
from main_extract_part import mainExtractPart

def read():
	var.listOrig.clear()
	var.listCtrl.clear()
	#源文件
	filepath = os.path.join(var.workpath, var.filename+var.Postfix)
	fileOld = open(filepath, 'rb')
	var.inputCount += 1
	return fileOld

def write():
	#print('write bin')
	#if len(var.listOrig) == 0:
		#print('No orig', var.filename)
		#return
	#print(var.isInput)
	if var.isInput == True:
		#写入译文
		replace()
		#反转义
		separate = var.contentSeparate.decode('unicode_escape').encode('latin-1')
		#新文件
		#print(len(var.content))
		filepath = os.path.join(var.workpath, 'new', var.filename+var.Postfix)
		#print(filepath)
		fileNew = open(filepath, 'wb')
		data = bytearray()
		length = len(var.content)
		for i in range(length):
			if i in var.insertContent:
				data.extend(var.insertContent[i])
			data.extend(var.content[i])
			if i < length-1:
				if var.addSeparate:
					data.extend(separate)
		if length in var.insertContent:
			data.extend(var.insertContent[length])
		if var.addrFixer:
			var.addrFixer.apply(data)
			var.addrFixer = None
		fileNew.write(data)
		fileNew.close()
		#print('导出:', var.filename+var.Postfix)
		var.outputCount += 1

def parse():
	#print('解析文件: '+var.filename)
	fileOld = read()
	if var.readFileDataImp:
		var.content, var.insertContent = var.readFileDataImp(fileOld, var.contentSeparate)
	else:
		data = fileOld.read()
		if var.contentSeparate == b'':
			var.content = [bytearray(data)]
		else:
			var.content = re.split(var.contentSeparate, data)
		var.insertContent.clear()
	fileOld.close()
	if var.addrFix:
		if isinstance(var.addrFix, str):
			var.addrFix = var.addrFix.encode(var.OldEncodeName)
			var.addrFix = re.compile(var.addrFix)
		#进行地址修正的检测
		if not var.addrList:
			if not var.addSeparate:
				#自动生成addr list，仅在addSeparate为False时
				addr = 0
				for i, lineData in enumerate(var.content):
					var.addrList.append(addr)
					addr += len(lineData)
			else:
				printWarning('addrFix仅在separate是捕获分组时有效')
		if var.addrList:
			data = b''.join(var.content) #重组
			#计算基础地址
			baseAddr = 0
			if isinstance(var.addrBase, str):
				lst = var.addrBase.split(',')
				for item in lst:
					if item.startswith('addr'):
						start, end = item[4:].split(':')
						start = eval(start)
						end = eval(end)
						value = int.from_bytes(data[start:end], 'little')
					else:
						value = eval(item)
					baseAddr += value
			else:
				baseAddr = var.addrBase
			#查找地址指针
			var.addrFixer = AddrFixer(baseAddr)
			iter = var.addrFix.finditer(data)
			for r in iter:
				for i in range(1, len(r.groups())+1):
					start = r.start(i)
					end = r.end(i)
					addr = data[start:end]
					addr = int.from_bytes(addr, 'little')
					if addr > len(data):
						continue
					var.addrFixer.listen(start, addr)
					printDebug('发现地址:', f'{start:08X}: {addr:08X}')
			if var.addrFixer.isEmpty():
				var.addrFixer = None
			else:
				printTip('发现地址个数:', len(var.addrFixer.pointList))
	#print(var.content)
	var.parseImp(var.content, var.listCtrl, dealOnce)
	write() #写入
	num = len(var.listOrig)
	#print('count:', num, len(transDic))
	if num == 0:
		printTip('该文件没有提取到文本', var.filename)
		#filepath = os.path.join(var.workpath, var.filename+var.Postfix)
		#if os.path.exists(filepath):
			#os.remove(filepath)

def initDone():
	var.contentSeparate = var.contentSeparate.encode('latin-1')
	if var.contentSeparate.startswith(b'(') or var.contentSeparate == '':
		var.addSeparate = False
	else:
		var.addSeparate = True
	if var.keepBytes:
		var.keepBytes = var.keepBytes.encode('latin-1')

#args = {workpath, engineName, outputFormat, outputPartMode, nameList, regDic}
def mainExtractBin(args):
	outputPartMode = args['outputPartMode']
	if outputPartMode == 0:
		mainExtract(args, parse, initDone)
	else:
		mainExtractPart(args, parse, initDone)