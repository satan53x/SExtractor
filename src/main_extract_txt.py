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
	fileOld = open(filepath, 'r', encoding=var.OldEncodeName)
	var.inputCount += 1
	return fileOld

def write():
	#if len(var.listOrig) == 0:
		#print('No orig', filename)
		#return
	if var.isInput == True:
		#写入译文
		replace()
		#反转义
		separate = var.contentSeparate.encode().decode('unicode_escape')
		#新文件
		#print(len(content))
		filepath = os.path.join(var.workpath, 'new', var.filename+var.Postfix)
		#print(filepath)
		if ExVar.newline != None:
			fileNew = open(filepath, 'w', encoding=var.NewEncodeName, newline=ExVar.newline)
		else:
			fileNew = open(filepath, 'w', encoding=var.NewEncodeName)
		length = len(var.content)
		for i in range(length):
			try:
				fileNew.write(var.content[i])
			except:
				printError(f'无法编码为{var.NewEncodeName}', var.content[i])
				if var.ignoreDecodeError:
					fileNew.write('// Error: Encoding')
				else:
					raise
			if i < length-1:
				if var.addSeparate:
					fileNew.write(separate)
		fileNew.close()
		#print('导出:', filename+Postfix)
		var.outputCount += 1

def parse():
	#print('解析文件: '+filename)
	fileOld = read() #判断流程
	if var.readFileDataImp:
		var.content, _ = var.readFileDataImp(fileOld, var.contentSeparate)
	else:
		data = fileOld.read() #文本文件读入内存后都是utf-8字符串
		if var.contentSeparate == '' or var.contentSeparate == '\n' or var.contentSeparate == '\r\n':
			var.content = data.splitlines()
			if len(var.content) > 0 and var.content[-1] != '':
				var.content.append('')
			var.contentSeparate = '\n'
		else:
			#自定义分割
			var.content = re.split(var.contentSeparate, data)
		if var.content:
			#签名检查
			s = var.content[0]
			if len(s) > 0 and (s[0] == '\ufeff' or s[0] == '\ufffe'):
				printWarning('请检查文件编码是否正确，疑似含有签名', var.filename)
	fileOld.close()
	#print(content)
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
	if var.contentSeparate.startswith(b'('):
		var.addSeparate = False
	else:
		var.addSeparate = True

#args = {workpath, engineName, outputFormat, outputPartMode, nameList, regDic}
def mainExtractTxt(args):
	outputPartMode = args['outputPartMode']
	if outputPartMode == 0:
		mainExtract(args, parse)
	else:
		mainExtractPart(args, parse)