import os
import sys
import json
import re
from common import *
from main_extract import *

#多文档导出：单独处理每个文件的json
def mainExtractPart(args, parseImp, initDone=None):
	if len(args) < 4:
		printError("main_extract参数错误", args)
		return
	#showMessage("开始处理...")
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
		files = getFiles(var.workpath)
		for i, name in enumerate(files):
			showProgress(i, len(files))
			var.filename = name
			var.curIO = var.io
			readFormat() #读入译文
			printDebug('读取文件:', var.filename)
			parse(parseImp)
			keepAllOrig()
			writeFormat()
			var.curIO = var.ioExtra
			writeFormat()
			#break #测试
			var.isStart = False
		showProgress(100)
		printInfo('读取文件数:', var.inputCount)
		printInfo('新建文件数:', var.outputCount)
		writeCutoffDic()
	else:
		printError('未找到主目录')
	extractDone()