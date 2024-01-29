import os
import re
from main_extract import *
from main_extract_part import mainExtractPart
import rapidjson

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
		fileNew = open(filepath, 'w', encoding=var.EncodeRead)
		rapidjson.dump(var.content, fileNew, ensure_ascii=False, indent=var.indent, write_mode=var.jsonWrite)
		fileNew.close()
		#print('导出:', filename+Postfix)
		var.outputCount += 1

def parse():
	var.indent = 2
	#print('解析文件: '+filename)
	fileOld = read() #判断流程
	var.content = rapidjson.load(fileOld)
	fileOld.close()
	#print(content)
	var.parseImp(var.content, var.listCtrl, dealOnce)
	write() #写入
	num = len(var.listOrig)
	#print('count:', num, len(transDic))
	if num == 0:
		printWarningGreen('没有解析到有效内容', var.filename)
		#filepath = os.path.join(var.workpath, var.filename+var.Postfix)
		#if os.path.exists(filepath):
			#os.remove(filepath)

#args = {workpath, engineName, outputFormat, outputPartMode, nameList, regDic}
def mainExtractJson(args):
	outputPartMode = args['outputPartMode']
	if outputPartMode == 0:
		mainExtract(args, parse)
	else:
		mainExtractPart(args, parse)