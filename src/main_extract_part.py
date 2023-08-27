import os
import sys
import json
import re
from common import *
from main_extract import *

#单独处理每个文件的json
#args = [workpath, engineName, outputFormat, nameList]
def mainExtractPart(args, parseImp, initDone=None):
	if len(args) < 4:
		print("main_extract参数错误", args)
		return
	showMessage("开始处理...")
	path = args['workpath']
	var.workpath = path
	if initArgs(args) != 0: return
	if initDone: initDone()
	#print(path)
	var.partMode = 1
	var.outputDir = 'orig'
	var.inputDir = 'trans'
	#print('---------------------------------')
	if os.path.isdir(path):
		#print(var.workpath)
		createFolder()
		for name in os.listdir(var.workpath):
			#print(name)
			if var.Postfix == '':
				var.filename = name
			else:
				var.filename = os.path.splitext(name)[0]
			filepath = os.path.join(var.workpath, var.filename+var.Postfix)
			#print(name, filepath)
			if os.path.isfile(filepath):
				var.curIO = var.io
				readFormat() #读入译文
				parseImp()
				keepAllOrig()
				writeFormat()
				var.curIO = var.ioExtra
				writeFormat()
				#break #测试
		print('读取文件数:', var.inputCount)
		print('新建文件数:', var.outputCount)
		writeCutoffDic()
	else:
		print('未找到主目录')
	showMessage("处理完成。")
	print('Done.\n')