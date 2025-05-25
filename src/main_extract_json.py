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
		#新文件
		#print(len(content))
		filepath = os.path.join(var.workpath, 'new', var.filename+var.Postfix)
		#print(filepath)
		if ExVar.newline != None:
			fileNew = open(filepath, 'w', encoding=var.NewEncodeName, newline=ExVar.newline)
		else:
			fileNew = open(filepath, 'w', encoding=var.NewEncodeName)
		if var.jsonWrite == 10:
			#除了第一层，其它WM_COMPACT
			if isinstance(var.content, list):
				writeList(fileNew, var.content)
			elif isinstance(var.content, dict):
				fileNew.write('{\n')
				first = True
				for key, value in var.content.items():
					if first:
						first = False
					else:
						fileNew.write(',')
						if isinstance(value, list):
							fileNew.write('\n')
					s = rapidjson.dumps(key, ensure_ascii=False, write_mode=0)
					fileNew.write(s)
					fileNew.write(': ')
					if isinstance(value, list):
						writeList(fileNew, value)
					else:
						s = rapidjson.dumps(value, ensure_ascii=False, write_mode=0)
						fileNew.write(s)
				fileNew.write('}')
			else:
				rapidjson.dump(var.content, fileNew, ensure_ascii=False, indent=var.indent, write_mode=1)
		else:
			rapidjson.dump(var.content, fileNew, ensure_ascii=False, indent=var.indent, write_mode=var.jsonWrite)
		fileNew.close()
		#print('导出:', filename+Postfix)
		var.outputCount += 1

def writeList(fileNew, lst):
	fileNew.write('[\n')
	for i, item in enumerate(lst):
		s = rapidjson.dumps(item, ensure_ascii=False, write_mode=0)
		fileNew.write(s)
		if i < len(lst)-1:
			fileNew.write(',\n')
	fileNew.write('\n]')

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
		printTip('该文件没有提取到文本', var.filename)
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