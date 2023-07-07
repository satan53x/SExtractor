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
		#print('write trans')
		lCtrl = []
		lTrans = []
		for listIndex in range(len(var.listOrig)-1, -1, -1): #倒序
			orig = var.listOrig[listIndex]
			ctrl = var.listCtrl[listIndex]
			trans = var.transDic[orig]
			if trans == '':
				print('>>>>>> Empty trans', var.filename, listIndex, orig, ctrl)
				#trans = 'te'.format(listIndex) #测试
				break
			lCtrl.append(ctrl)
			lTrans.append(trans)
			#if 'notEnd' in ctrl:
			#	continue
			#开始处理段落
			ret = var.replaceOnceImp(var.content, lCtrl, lTrans)
			if ret == False:
				print('replace false', var.filename)
			lCtrl.clear()
			lTrans.clear()
			#break #测试
		#新文件
		#print(len(var.content))
		filepath = os.path.join(var.workpath, 'new', var.filename+var.Postfix)
		#print(filepath)
		fileNew = open(filepath, 'wb')
		length = len(var.content)
		for i in range(length):
			fileNew.write(var.content[i])
			if i < length-1:
				fileNew.write(var.ContentSeprate)
		fileNew.close()
		#print('导出:', var.filename+var.Postfix)
		var.outputCount += 1

def parse():
	#print('解析文件: '+var.filename)
	fileOld = read()
	if var.readFileDataImp:
		var.content = var.readFileDataImp(fileOld, var.ContentSeprate)
	else:
		data = fileOld.read()
		var.content = data.split(var.ContentSeprate)
	fileOld.close()
	#print(var.content)
	var.parseImp(var.content, var.listCtrl, dealOnce)
	write() #写入
	num = len(var.listOrig)
	#print('count:', num, len(transDic))
	if num == 0:
		print('该文件没有有效文本', var.filename)
		#filepath = os.path.join(var.workpath, var.filename+var.Postfix)
		#if os.path.exists(filepath):
			#os.remove(filepath)

#args = [workpath, engineName, outputFormat, outputPartMode]
def mainExtractBin(args):
	outputPartMode = args[3]
	if outputPartMode == 0:
		mainExtract(args, parse)
	else:
		mainExtractPart(args, parse)