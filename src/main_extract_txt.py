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
	fileOld = open(filepath, 'r', encoding=var.EncodeRead)
	var.inputCount += 1
	return fileOld

def write():
	#if len(var.listOrig) == 0:
		#print('No orig', filename)
		#return
	if var.isInput == True:
		#写入译文
		replace()
		#新文件
		#print(len(content))
		filepath = os.path.join(var.workpath, 'new', var.filename+var.Postfix)
		#print(filepath)
		if ExVar.newline != None:
			fileNew = open(filepath, 'w', encoding=var.EncodeRead, newline=ExVar.newline)
		else:
			fileNew = open(filepath, 'w', encoding=var.EncodeRead)
		length = len(var.content)
		for i in range(length):
			fileNew.write(var.content[i])
		fileNew.close()
		#print('导出:', filename+Postfix)
		var.outputCount += 1

def parse():
	#print('解析文件: '+filename)
	fileOld = read() #判断流程
	if var.readFileDataImp:
		var.content, _ = var.readFileDataImp(fileOld, var.contentSeparate)
	else:
		var.content = fileOld.readlines() #会保留换行符
		if var.content:
			#签名检查
			s = var.content[0]
			if s[0] == '\ufeff' or s[0] == '\ufffe':
				printWarning('请检查文件编码是否正确，疑似含有签名', var.filename)
			if not var.content[-1].endswith('\n'):
				printDebug('已补足文件末尾缺少的一个换行符')
				var.content[-1] += '\n'
	fileOld.close()
	#print(content)
	var.parseImp(var.content, var.listCtrl, dealOnce)
	write() #写入
	num = len(var.listOrig)
	#print('count:', num, len(transDic))
	if num == 0:
		printWarningGreen('该文件没有提取到文本', var.filename)
		#filepath = os.path.join(var.workpath, var.filename+var.Postfix)
		#if os.path.exists(filepath):
			#os.remove(filepath)

#args = {workpath, engineName, outputFormat, outputPartMode, nameList, regDic}
def mainExtractTxt(args):
	outputPartMode = args['outputPartMode']
	if outputPartMode == 0:
		mainExtract(args, parse)
	else:
		mainExtractPart(args, parse)