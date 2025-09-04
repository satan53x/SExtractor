import os
import json
import re
import traceback
from PyQt5.QtCore import QSettings
from importlib import import_module
from var_extract import *
from common import *
from helper_text import *
from helper_read import readFormat, replaceTransAll
from helper_write import writeFormat, replaceOrig

var = ExVar

# ------------------------------------------------------------
allOrig = []
allOrigAppend = []
def keepAllOrig(insertBegin=False):
	# if len(var.listCtrl) > 0:
	# 	if 'name' in var.listCtrl[-1] or 'unfinish' in var.listCtrl[-1]:
	# 		printError('listCtrl结束行错误', var.filename, var.listCtrl[-1], var.listOrig[-1])
	listIndex = -1
	item = {}
	ctrl = {}
	checkRN = 1
	allOrig.clear()
	allOrigAppend.clear()
	needAppend = 0
	if not var.splitParaSep == '\r\n' or (var.splitAuto and var.joinAfterSplit):
		checkRN = 0
	while(listIndex < len(var.listOrig) - 1):
		listIndex += 1
		ctrl = var.listCtrl[listIndex]
		orig = var.listOrig[listIndex]
		if checkRN > 0 and var.splitParaSep in orig:
			checkRN = -1
		#print(listIndex, orig, ctrl)
		if 'name'in ctrl:
			item = tryAddToDic(item, ctrl, needAppend) #前一个结束
			needAppend = 0
			item['name'] = orig
			#判断是否需要追加
			if var.textAppend and orig in var.transDicAppend:
				needAppend |= 0x1
			continue
		else:
			if 'message' not in item:
				item['message'] = ""
			item['message'] += orig
			#判断是否需要追加
			if var.textAppend and orig in var.transDicAppend:
				needAppend |= 0x10
			if var.outputTextType:
				#导出文本类型标记
				if 'type' in ctrl:
					item['type'] = ctrl['type']
			if 'unfinish' in ctrl:
				if listIndex < len(var.listCtrl) - 1:
					nextCtrl = var.listCtrl[listIndex + 1]
					if 'name'in nextCtrl: #下一个是名字则不加分隔符
						continue
				elif listIndex == len(var.listCtrl) - 1:
					continue #最后一行
				item['message'] += var.splitParaSep
				continue
			item = tryAddToDic(item, ctrl, needAppend)
			needAppend = 0
	item = tryAddToDic(item, ctrl, needAppend)
	if checkRN < 0:
		printWarning('文本内容与段落分隔符重复，建议修改设置中分隔符', repr(var.splitParaSep))
	if insertBegin:
		var.allOrig = allOrig + var.allOrig
		var.allOrigAppend = allOrigAppend + var.allOrigAppend
	else:
		var.allOrig = var.allOrig + allOrig
		var.allOrigAppend = var.allOrigAppend + allOrigAppend

def tryAddToDic(item:dict, ctrl, needAppend):
	if item != {}:
		allOrig.append(item)
		if needAppend:
			#if needAppend&0x10 or 'message' not in item:
			allOrigAppend.append(item)
		#加入transDicRN
		if 'name' in item:
			if item['name'] not in var.transDicRN:
				#print('Add to transDicRN', orig, listIndex, var.filename)
				var.transDicRN[item['name']] = ''
			if needAppend and item['name'] not in var.transDicRNAppend:
				var.transDicRNAppend[item['name']] = ''
		if 'message' in item:
			if item['message'] not in var.transDicRN:
				#print('Add to transDicRN', orig, listIndex, var.filename)
				var.transDicRN[item['message']] = ''
			if needAppend and item['message'] not in var.transDicRNAppend:
				var.transDicRNAppend[item['message']] = ''
		else:
			printWarning('message为空', var.filename, ctrl, item['name'])
			item['message'] = '' #message为空时补一个空字符串
		item = {}
	return item

def dealOnce(text, ctrl):
	#print(orig)
	orig = text
	#if orig.isspace() == False:
		#orig = orig.strip()
	if orig == '': 
		printWarning('提取时原文为空', var.filename, str(ctrl))
		return False
	#if orig.isspace(): return False
	orig = replaceOrig(orig, ctrl)
	#输出原文
	var.listOrig.append(orig)
	#print(orig)
	if orig not in var.transDic:
		#print('Add to transDic', orig, var.filename, str(contentIndex))
		var.transDic[orig] = ['']
		if var.textAppend:
			var.transDicAppend[orig] = ['']
	return True

def replace():
	replaceTransAll()
	for listIndex in range(len(var.listOrig)-1, -1, -1): #倒序
		orig = var.listOrig[listIndex]
		ctrl = var.listCtrl[listIndex]
		trans:list = var.transDic[orig]
		var.curOrig = orig
		if len(trans) == 0:
			printError('译文列表中元素个数不足:', var.filename, orig)
			newStr = ''
		else:
			if len(trans) == 1:
				newStr = trans[0]
			else:
				newStr = trans.pop()
		if newStr == '':
			printTip('译文为空, 不替换', var.filename, orig)
			#trans = 'te'.format(listIndex) #测试
			continue
		#开始处理段落
		if 'name' in ctrl:
			if var.dontImportName: #不导入名字
				continue
			if var.transReplace and 'name_replace' in var.textConf:
				for old, new in var.textConf['name_replace'].items():
					if newStr == new:
						newStr = old
		elif 'ignore' in ctrl:
			#忽略
			continue
		ret = var.replaceOnceImp(var.content, [ctrl], [newStr])
		if ret == False:
			printError('替换错误，请检查文本', var.filename, newStr)
			continue
		#break #测试
	if var.replaceEndImp:
		var.replaceEndImp(var.content)

# ------------------------------------------------------------
def createFolder():
	path = os.path.join(var.workpath, 'ctrl')
	if not os.path.exists(path):
		os.makedirs(path)
	path = os.path.join(var.workpath, 'new')
	if not os.path.exists(path):
		os.makedirs(path)
	if var.inputDir != 'ctrl' or var.outputDir != 'ctrl':
		path = os.path.join(var.workpath, var.inputDir)
		if not os.path.exists(path):
			os.makedirs(path)
		path = os.path.join(var.workpath, var.outputDir)
		if not os.path.exists(path):
			os.makedirs(path)

def chooseEngine(args):
	var.engineName = args['engineName']
	var.fileType = args['file']
	#读取配置
	settings = QSettings('src/engine.ini', QSettings.IniFormat)
	strEngine = 'Engine_' + var.engineName
	settings.beginGroup(strEngine)
	var.Postfix = settings.value('postfix')
	var.encode = settings.value('encode')
	#输出格式
	formatList = settings.value('formatList')
	if formatList == None or str(args['outputFormat']) in formatList:
		var.io.outputFormat = args['outputFormat']
		var.io.init()
	else:
		var.io.outputFormat = -1
		showMessage("该引擎暂不支持此输出格式。", 'red')
		return 1
	# 额外输出
	if formatList == None or str(args['outputFormatExtra']) in formatList:
		var.ioExtra.outputFormat = args['outputFormatExtra']
		var.ioExtra.prefix = 'extra_'
		if var.ioExtra.outputFormat == var.io.outputFormat:
			var.ioExtra.outputFormat = -1
		var.ioExtra.init()
	else:
		var.ioExtra.outputFormat = -1
		showMessage("该引擎暂不支持此输出格式。(额外)", 'red')
		return 2
	#分割符
	var.contentSeparate = settings.value('contentSeparate')
	if var.contentSeparate == None:
		var.contentSeparate = ''
	#导入模块
	#print(var.EncodeName, var.Postfix, var.engineName)
	module = import_module('extract_' + var.engineName)
	var.parseImp = getattr(module, 'parseImp')
	var.replaceOnceImp = getattr(module, 'replaceOnceImp')
	if hasattr(module, 'readFileDataImp'):
		var.readFileDataImp = getattr(module, 'readFileDataImp')
	else:
		var.readFileDataImp = None
	if hasattr(module, 'replaceEndImp'):
		var.replaceEndImp = getattr(module, 'replaceEndImp')
	else:
		var.replaceEndImp = None
	settings.endGroup()
	return 0

def setNameList(str):
	if str:
		printTip('进行强制设定名字')
	l = str.split(',')
	var.nameList = [x for x in l if x != '']

def setRegDic(str):
	var.regDic = {}
	if str == None or str == '': return
	list = re.split('\n', str)
	for line in list:
		# 结束
		if line == '' or line.startswith('sample'): 
			break
		elif line[0] in ['<', ';', '/', '#']:
			continue
		pair = line.split('=', 1)
		# 控制
		if pair[0] == 'separate':
			var.contentSeparate = pair[1]
			continue
		elif pair[0] == 'flag':
			lst = pair[1].split(',')
			for flag in lst:
				if hasattr(var, flag):
					setattr(var, flag, True)
				else:
					printWarning('没有找到预设的参数名:', flag) 
			continue
		elif ('_skip' not in pair[0]) and ('_search' not in pair[0]):
			if pair[0] == 'struct':
				pair[0] = 'structure'
			if hasattr(var, pair[0]):
				if pair[1] == 'False' or pair[1] == 'false':
					pair[1] = False
				elif pair[1] == 'True' or pair[1] == 'true':
					pair[1] = True
				elif pair[1].isdecimal():
					if pair[0] not in ['extraData', 'extractKey']:
						pair[1] = int(pair[1])
				setattr(var, pair[0], pair[1])
				printInfo('额外参数:', pair[0], pair[1])
			else:
				printWarning('没有找到预设的参数名:', pair[0])
			continue
		# 规则
		var.regDic[pair[0]] = pair[1]
		printInfo('正则规则:', pair[0], pair[1])

def readCutoffDic():
	var.cutoffDic = {}
	#读入cutoff字典
	filepath = os.path.join(var.workpath, 'ctrl', 'cutoff.json')
	if os.path.isfile(filepath):
		fileCutoffDic = open(filepath, 'r', encoding='utf-8')
		var.cutoffDic = json.load(fileCutoffDic)
		printInfo('读入Json: ', len(var.cutoffDic), 'cutoff.json')

def writeCutoffDic():
	if len(var.cutoffDic) == 0: return
	#print(filepath)
	printInfo('输出Json:', len(var.cutoffDic), 'cutoff.json')
	filepath = os.path.join(var.workpath, 'ctrl', 'cutoff.json')
	fileOutput = open(filepath, 'w', encoding='utf-8')
	#print(targetJson)
	json.dump(var.cutoffDic, fileOutput, ensure_ascii=False, indent=2)
	fileOutput.close()

def readTextConf():
	if not (var.transReplace or var.preReplace or var.dynamicReplace): return
	filepath = os.path.join(var.workpath, 'ctrl', 'text_conf.json')
	if not os.path.isfile(filepath):
		filepath = os.path.join('.', 'text_conf.json')
		if not os.path.isfile(filepath):
			return
	fileOld = open(filepath, 'r', encoding='utf-8')
	var.textConf = json.load(fileOld)
	fileOld.close()
	if 'dynamic_replace' not in var.textConf:
		var.textConf['dynamic_replace'] = ['', []] 
	if var.dynamicReplace == True:
		var.dynamicReplace = var.textConf['dynamic_replace'][0]
	var.dynamicReplaceOldList = []
	var.dynamicReplaceNewList = var.textConf['dynamic_replace'][1] #元素不多时list查询效率更高

def readFullWidthDic():
	if not var.toFullWidth: return
	filepath = os.path.join('./tools/WideChar.json')
	if not os.path.isfile(filepath):
		return
	fileOld = open(filepath, 'r', encoding='utf-8')
	var.fullWidthDic = json.load(fileOld)
	fileOld.close()

def showMessage(msg, color='black'):
	if var.window: 
		var.window.statusBar.sendMessage(msg, color)
def showProgress(value, max=100):
	if var.window:
		var.window.statusBar.sendProgress(value, max)

def initArgs(args):
	var.clear()
	# 打印
	var.printSetting = args['print']
	ret = chooseEngine(args)
	if ret != 0:
		return ret
	#遍历参数
	for key, value in args.items():
		if hasattr(var, key):
			setattr(var, key, value)
	# 匹配
	setNameList(args['nameList'])
	if var.useStructPara and not var.structure:
		var.structure = 'paragraph'
	# 截断
	readCutoffDic()
	# 分割
	var.splitParaSepRegex = args['splitParaSep']
	if '\\' in var.splitParaSepRegex:
		var.splitParaSep = var.splitParaSepRegex.encode('latin-1').decode('unicode_escape')
	else:
		var.splitParaSep = var.splitParaSepRegex
	if var.tunnelJis:
		generateJisList()
	elif var.subsJis:
		generateSubsDic()
	# 正则
	setRegDic(args['regDic'])
	# 编码
	if var.binEncodeValid or var.fileType != 'bin':
		lst = var.encode.split(',')
		var.binEncodeValid = True
		var.OldEncodeName = lst[0]
		if len(lst) > 1:
			var.NewEncodeName = lst[1]
		else:
			var.NewEncodeName = var.OldEncodeName
		if var.fileType == 'bin':
			printTip('已启用: 编码也对BIN生效', var.OldEncodeName, var.NewEncodeName)
	# 双行标志
	if isinstance(var.twoLineFlag, str):
		var.twoLineFlag = var.twoLineFlag.split(',')
	# 其他配置
	readFullWidthDic()
	# 修正参数
	if var.tunnelJis or var.subsJis:
		WirteEncodeName = var.JisEncodeName
	else:
		WirteEncodeName = var.NewEncodeName
	var.padding = var.padding.encode(WirteEncodeName).decode('unicode_escape').encode('latin-1')
	# 处理preLen
	if var.preLen != None:
		if var.preLenOffset == None:
			var.preLenOffset = -var.preLen
		elif isinstance(var.preLenOffset, str):
			if var.preLenOffset not in ['start']:
				var.preLenOffset = int(var.preLenOffset)
		if isinstance(var.preLenScale, str):
			var.preLenScale = eval(var.preLenScale)
		if isinstance(var.preLenAdd, str):
			var.preLenAdd = eval(var.preLenAdd)
	readTextConf()
	# 处理动态替换
	if var.dynamicReplace and isinstance(var.dynamicReplace, str):
		#printTip('已开启动态替换')
		var.dynamicReplace = re.compile(var.dynamicReplace)
	else:
		var.dynamicReplace = None
	return 0

def outputDone():
	#if var.dynamicReplace:
	#	printTip('动态替换原文:', var.dynamicReplaceOldList)
	pass

def extractDone():
	if var.dynamicReplace:
		count = len(var.dynamicReplaceOldList)
		countNew = len(var.dynamicReplaceNewList)
		if count > countNew:
			printWarning(f'替换表可用元素不足，请在text_conf中添加{count - countNew}个')
			count = countNew
		printTip('动态替换:', var.dynamicReplaceOldList)
		printTip('　　　　>', var.dynamicReplaceNewList[:count])
	if var.tunnelJis:
		generateTunnelJisMap()
	elif var.subsJis:
		generateSubsConfig()
	showMessage("处理完成。")
	#print('Done.\n')

def getFiles(dirpath, reverse=False):
	files = []
	for name in os.listdir(dirpath):
		#print('File:', name)
		if var.Postfix == '':
			filename = name
		else:
			filename = os.path.splitext(name)[0]
		filepath = os.path.join(dirpath, filename+var.Postfix)
		#print(name, filepath)
		if os.path.isfile(filepath):
			files.append(filename)
	if reverse:
		files = list(reversed(files))
	return files

def parse(parseImp):
	try:
		parseImp()
	except Exception as ex:
		if ExVar.dontInterrupt:
			print('\033[31m---------------------------提取时发生错误---------------------------\033[0m')
			traceback.print_exc()
			print('\033[31m--------------------------------------------------------------------------\033[0m')
			print(f'\033[33m异常中断文件名: {ExVar.filename}\033[0m')
		else:
			raise

#合并为单文档导出
def mainExtract(args, parseImp, initDone=None):
	if len(args) < 4:
		printError("main_extract参数错误", args)
		return
	#showMessage("开始处理...")
	path = args['workpath']
	var.workpath = path
	if initArgs(args) != 0: return
	if initDone: initDone()
	#print(path)
	var.partMode = 0
	var.outputDir = 'ctrl'
	var.inputDir = 'ctrl'
	#print('---------------------------------')
	if os.path.isdir(path):
		#print(var.workpath)
		createFolder()
		var.curIO = var.io
		readFormat() #读入译文
		if var.curIO.isList: #属于列表格式
			needReverse = True
		else:
			needReverse = False
		files = getFiles(var.workpath, needReverse)
		for i, name in enumerate(files):
			showProgress(i, len(files))
			if i == 0:
				var.isStart = 1
			elif i == len(files)-1:
				var.isStart = 3
			else:
				var.isStart = 2
			var.filename = name
			printDebug('读取文件:', var.filename)
			parse(parseImp)
			keepAllOrig(needReverse)
			#break #测试
		showProgress(100)
		printInfo('读取文件数:', var.inputCount)
		writeFormat()
		printInfo('新建文件数:', var.outputCount)
		var.curIO = var.ioExtra
		writeFormat(False)
		outputDone()
		writeCutoffDic()
	else:
		printError('未找到主目录')
	extractDone()

