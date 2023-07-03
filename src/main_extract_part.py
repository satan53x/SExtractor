import os
import sys
import json
import re
from common import *
from main_extract import *

#单独处理每个文件的json
#args = [workpath, engineCode, outputFormat]
def mainExtractPart(args, parseImp):
	if len(args) < 3:
		print("main_extract参数错误", args)
		return
	showMessage("开始处理...")
	path = args[0]
	#print(path)
	ret = chooseEngine(args[1], args[2])
	if ret != 0:
		return
	var.partMode = 1
	var.outputDir = 'orig'
	var.inputDir = 'trans'
	print('---------------------------------')
	if os.path.isdir(path):
		var.workpath = path
		#print(var.workpath)
		createFolder()
		for name in os.listdir(var.workpath):
			#print(name)
			var.filename = os.path.splitext(name)[0]
			filepath = os.path.join(var.workpath, var.filename+var.Postfix)
			#print(name, filepath)
			if os.path.isfile(filepath):
				readFormat(var.outputFormat) #读入译文
				parseImp()
				keepAllOrig()
				writeFormat(var.outputFormat)
				#break #测试
		print('读取文件数:', var.inputCount)
		print('新建文件数:', var.outputCount)
	showMessage("输出完成。")
	print('')