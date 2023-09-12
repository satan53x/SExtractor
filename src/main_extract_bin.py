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
		seprate = var.contentSeprate.decode('unicode_escape').encode('latin-1')
		#新文件
		#print(len(var.content))
		filepath = os.path.join(var.workpath, 'new', var.filename+var.Postfix)
		#print(filepath)
		fileNew = open(filepath, 'wb')
		length = len(var.content)
		for i in range(length):
			if i in var.insertContent:
				fileNew.write(var.insertContent[i])
			fileNew.write(var.content[i])
			if i < length-1:
				if var.addSeprate:
					fileNew.write(seprate)
		if length in var.insertContent:
			fileNew.write(var.insertContent[length])
		fileNew.close()
		#print('导出:', var.filename+var.Postfix)
		var.outputCount += 1

def parse():
	#print('解析文件: '+var.filename)
	fileOld = read()
	if var.readFileDataImp:
		var.content, var.insertContent = var.readFileDataImp(fileOld, var.contentSeprate)
	else:
		data = fileOld.read()
		if var.contentSeprate == b'':
			var.content = [bytearray(data)]
		else:
			var.content = re.split(var.contentSeprate, data)
		var.insertContent.clear()
	fileOld.close()
	#print(var.content)
	var.parseImp(var.content, var.listCtrl, dealOnce)
	write() #写入
	num = len(var.listOrig)
	#print('count:', num, len(transDic))
	if num == 0:
		printWarningGreen('没有解析到有效内容', var.filename)
		#filepath = os.path.join(var.workpath, var.filename+var.Postfix)
		#if os.path.exists(filepath):
			#os.remove(filepath)

def initDone():
	var.contentSeprate = var.contentSeprate.encode('latin-1')
	if var.contentSeprate.startswith(b'(') or var.contentSeprate == '':
		var.addSeprate = False
	else:
		var.addSeprate = True

#args = {workpath, engineName, outputFormat, outputPartMode, nameList, regDic}
def mainExtractBin(args):
	outputPartMode = args['outputPartMode']
	if outputPartMode == 0:
		mainExtract(args, parse, initDone)
	else:
		mainExtractPart(args, parse, initDone)