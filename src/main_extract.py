import os
import sys
import json
import re
from var_extract import *
from common import *
from helper_text import *
from importlib import import_module
from PyQt5.QtCore import QSettings
from PyQt5.QtWidgets import QStatusBar
import pandas

var = ExVar
SetG('Var', var)

def setIOFileName(io:IOConfig):
	if var.partMode == 0: #总共一个输出文档
		if io.outputFormat == 5 or io.outputFormat == 6:
			io.ouputFileName = 'all.orig.txt'
			io.inputFileName = 'all.trans.txt'
		elif io.outputFormat == 2 or io.outputFormat == 7:
			io.ouputFileName = 'all.orig.json'
			io.inputFileName = 'all.trans.json'
		elif io.outputFormat == 8:
			io.ouputFileName = 'transDic.output.xlsx'
			io.inputFileName = 'transDic.xlsx'
		else:
			io.ouputFileName = 'transDic.output.json'
			io.inputFileName = 'transDic.json'
	else: #每个文件对应一个输出文档
		if io.outputFormat == 5 or io.outputFormat == 6:
			io.ouputFileName = var.filename + '.txt'
			io.inputFileName = var.filename + '.txt'
		if io.outputFormat == 8:
			io.ouputFileName = var.filename + '.xlsx'
			io.inputFileName = var.filename + '.xlsx'
		else:
			io.ouputFileName = var.filename + '.json'
			io.inputFileName = var.filename + '.json'
	io.ouputFileName = io.prefix + io.ouputFileName 
	io.inputFileName = io.prefix + io.inputFileName

# --------------------------- 读 ---------------------------------
def readFormat():
	setIOFileName(var.io)
	setIOFileName(var.ioExtra)
	code = var.curIO.outputFormat
	var.isInput = False
	var.transDic.clear()
	var.transDicIO.clear()
	var.allOrig.clear()
	if var.noInput: #不读取译文
		return
	if code == 0 or code == 1:
		readFormatDic()
	elif code == 2:
		readFormatItemList()
	elif code == 3 or code == 4:
		readFormatDicIO()
	elif code == 5:
		readFormatTxt(False)
	elif code == 6:
		readFormatTxt(True)
	elif code == 7:
		readFormatList()
	elif code == 8:
		readFormatXlsx()
	#修正译文
	if var.transReplace:
		if 'trans_replace' not in var.textConf: return
		if var.fileType == 'bin':
			charset = var.NewEncodeName
		else:
			charset = var.EncodeRead
		for key, replaceDic in var.textConf['trans_replace'].items():
			if charset not in key: continue
			printDebug('进行译文替换')
			replaceValue(var.transDic, replaceDic)

def readFormatDic():
	#读入transDic字典
	filepath = os.path.join(var.workpath, var.inputDir, var.curIO.inputFileName)
	if os.path.isfile(filepath):
		fileTransDic = open(filepath, 'r', encoding='utf-8')
		var.transDic = json.load(fileTransDic)
		printInfo('读入Json: ', len(var.transDic), var.curIO.inputFileName)
		var.isInput = True
		#print(list(var.transDic.values())[0])

def readFormatDicIO():
	#读入带换行文本的transDicIO字典
	filepath = os.path.join(var.workpath, var.inputDir, var.curIO.inputFileName)
	if os.path.isfile(filepath):
		fileTransDic = open(filepath, 'r', encoding='utf-8')
		var.transDicIO = json.load(fileTransDic)
		printInfo('读入Json: ', len(var.transDicIO), var.curIO.inputFileName)
		var.isInput = True
		#print(list(var.transDic.values())[0])
		#还原transDic
		for orig,trans in var.transDicIO.items():
			splitToTransDic(orig, trans)

def readFormatTxt(boolSplit):
	#读入txt
	filepath = os.path.join(var.workpath, var.inputDir, var.curIO.inputFileName)
	if os.path.isfile(filepath):
		#译文
		fileAllTrans = open(filepath, 'r', encoding='utf-8')
		allTrans = fileAllTrans.readlines()
		printInfo('读入Txt:', len(allTrans), var.curIO.inputFileName)
		#原文
		filepath = os.path.join(var.workpath, var.outputDir, var.curIO.ouputFileName)
		fileAllOrig = open(filepath, 'r', encoding='utf-8')
		allOrig = fileAllOrig.readlines()
		printInfo('读入Txt:', len(allOrig), var.curIO.ouputFileName)
		if len(allTrans) != len(allOrig):
			printError('导入与导出文件行数不一致', var.curIO.inputFileName)
			return
		var.isInput = True
		#合并 
		for i in range(len(allOrig)):
			orig = re.sub(r'\n$', '', allOrig[i])
			trans = re.sub(r'\n$', '', allTrans[i])
			if boolSplit:
				#分割
				splitToTransDic(orig, trans)
			else:
				#不分割
				var.transDic[orig] = trans
		fileAllOrig.close()
		fileAllTrans.close()



def readFormatItemList():
	#读入带换行文本item的all.orig列表和all.trans列表
	filepath = os.path.join(var.workpath, var.inputDir, var.curIO.inputFileName)
	if os.path.isfile(filepath):
		#译文
		fileAllTrans = open(filepath, 'r', encoding='utf-8')
		allTrans = json.load(fileAllTrans)
		printInfo('读入Json:', len(allTrans), var.curIO.inputFileName)
		#原文
		filepath = os.path.join(var.workpath, var.outputDir, var.curIO.ouputFileName)
		fileAllOrig = open(filepath, 'r', encoding='utf-8')
		allOrig = json.load(fileAllOrig)
		printInfo('读入Json:', len(allOrig), var.curIO.ouputFileName)
		if len(allTrans) != len(allOrig):
			printError('导入与导出文件行数不一致', var.curIO.inputFileName)
			return
		var.isInput = True
		#合并
		for i in range(len(allOrig)):
			itemOrig = allOrig[i]
			itemTrans = allTrans[i]
			if 'name' in itemOrig: #名字
				if itemOrig['name'] not in var.transDic:
					var.transDic[itemOrig['name']] = itemTrans['name']
			if 'message' in itemOrig: #对话
				splitToTransDic(itemOrig['message'], itemTrans['message'])
		fileAllOrig.close()
		fileAllTrans.close()

def readFormatList():
	#读入带换行字符串的all.orig列表和all.trans列表
	filepath = os.path.join(var.workpath, var.inputDir, var.curIO.inputFileName)
	if os.path.isfile(filepath):
		#译文
		fileAllTrans = open(filepath, 'r', encoding='utf-8')
		allTrans = json.load(fileAllTrans)
		printInfo('读入Json:', len(allTrans), var.curIO.inputFileName)
		#原文
		filepath = os.path.join(var.workpath, var.outputDir, var.curIO.ouputFileName)
		fileAllOrig = open(filepath, 'r', encoding='utf-8')
		allOrig = json.load(fileAllOrig)
		printInfo('读入Json:', len(allOrig), var.curIO.ouputFileName)
		if len(allTrans) != len(allOrig):
			printError('导入与导出文件行数不一致', var.curIO.inputFileName)
			return
		var.isInput = True
		#合并
		for i in range(len(allOrig)):
			orig = allOrig[i]
			trans = allTrans[i]
			splitToTransDic(orig, trans)
		fileAllOrig.close()
		fileAllTrans.close()

def readFormatXlsx():
	#读入transDic字典的xlsx
	filepath = os.path.join(var.workpath, var.inputDir, var.curIO.inputFileName)
	if os.path.isfile(filepath):
		df = pandas.read_excel(filepath)
		for index, row in df.iterrows():
			value = row['Value']
			if pandas.notna(value):
				var.transDic[row['Key']] = value
			else:
				var.transDic[row['Key']] = ''
		printInfo('读入Xlsx: ', len(var.transDic), var.curIO.inputFileName)
		var.isInput = True
		#print(list(var.transDic.values())[0])

# --------------------------- 写 ---------------------------------
def writeFormat():
	code = var.curIO.outputFormat
	if code == 0:
		writeFormatDirect(var.transDic)
	elif code == 1:
		writeFormatCopyKey(var.transDic)
	elif code == 2:
		writeFormatDirect(var.allOrig)
	elif code == 3:
		writeFormatDirect(var.transDicIO)
	elif code == 4:
		writeFormatCopyKey(var.transDicIO)
	elif code == 5:
		writeFormatTxt(var.transDic)
	elif code == 6:
		writeFormatTxtByItem(var.allOrig)
	elif code == 7:
		writeFormatListByItem(var.allOrig)
	elif code == 8:
		writeFormatXlsx(var.transDic)

def writeFormatDirect(targetJson):
	#print(filepath)
	printInfo('输出Json:', len(targetJson), var.curIO.ouputFileName)
	filepath = os.path.join(var.workpath, var.outputDir, var.curIO.ouputFileName)
	fileOutput = open(filepath, 'w', encoding='utf-8')
	#print(targetJson)
	json.dump(targetJson, fileOutput, ensure_ascii=False, indent=2)
	fileOutput.close()

def writeFormatCopyKey(targetJson):
	#print(filepath)
	printInfo('输出Json:', len(targetJson), var.curIO.ouputFileName)
	filepath = os.path.join(var.workpath, var.outputDir, var.curIO.ouputFileName)
	fileOutput = open(filepath, 'w', encoding='utf-8')
	#print(targetJson)
	tmpDic = {}
	for orig,trans in targetJson.items():
		if trans == '':
			tmpDic[orig] = orig
		else:
			tmpDic[orig] = trans
	json.dump(tmpDic, fileOutput, ensure_ascii=False, indent=2)
	fileOutput.close()

def writeFormatTxt(targetJson):
	#print(filepath)
	printInfo('输出Txt:', len(targetJson), var.curIO.ouputFileName)
	filepath = os.path.join(var.workpath, var.outputDir, var.curIO.ouputFileName)
	fileOutput = open(filepath, 'w', encoding='utf-8')
	#print(targetJson)
	for orig in targetJson.keys():
		fileOutput.write(orig + '\n')
	fileOutput.close()

def writeFormatTxtByItem(targetJson):
	#print(filepath)
	printInfo('输出Txt:', len(targetJson), var.curIO.ouputFileName)
	filepath = os.path.join(var.workpath, var.outputDir, var.curIO.ouputFileName)
	fileOutput = open(filepath, 'w', encoding='utf-8')
	#print(targetJson)
	for item in targetJson:
		if 'name' in item:
			fileOutput.write(item['name'] + '\n')
		if 'message' in item:
			fileOutput.write(item['message'] + '\n')
	fileOutput.close()

def writeFormatListByItem(targetJson):
	#print(filepath)
	printInfo('输出Json:', len(targetJson), var.curIO.ouputFileName)
	filepath = os.path.join(var.workpath, var.outputDir, var.curIO.ouputFileName)
	fileOutput = open(filepath, 'w', encoding='utf-8')
	#print(targetJson)
	tmpList = []
	for item in targetJson:
		if 'name' in item:
			tmpList.append(item['name'])
		if 'message' in item:
			tmpList.append(item['message'])
	json.dump(tmpList, fileOutput, ensure_ascii=False, indent=2)
	fileOutput.close()

def writeFormatXlsx(targetJson):
	#print(filepath)
	printInfo('输出Xlsx:', len(targetJson), var.curIO.ouputFileName)
	filepath = os.path.join(var.workpath, var.outputDir, var.curIO.ouputFileName)
	#fileOutput = open(filepath, 'w', encoding='utf-8')
	#print(targetJson)
	df = pandas.DataFrame(list(targetJson.items()), columns=['Key', 'Value'], dtype=str)
	df.to_excel(filepath, index=False, engine='openpyxl')
	#fileOutput.close()

# ------------------------------------------------------------
def keepAllOrig():
	# if len(var.listCtrl) > 0:
	# 	if 'isName' in var.listCtrl[-1] or 'unfinish' in var.listCtrl[-1]:
	# 		printError('listCtrl结束行错误', var.filename, var.listCtrl[-1], var.listOrig[-1])
	listIndex = -1
	item = {}
	ctrl = {}
	while(listIndex < len(var.listOrig) - 1):
		listIndex += 1
		ctrl = var.listCtrl[listIndex]
		orig = var.listOrig[listIndex]
		#print(listIndex, orig, ctrl)
		if 'isName'in ctrl:
			item = tryAddToDic(item, ctrl) #前一个结束
			item['name'] = orig
			continue
		else:
			if 'message' not in item:
				item['message'] = ""
			item['message'] += orig
			if 'unfinish' in ctrl:
				item['message'] += var.splitParaSep
				continue
			item = tryAddToDic(item, ctrl)
	item = tryAddToDic(item, ctrl)

def tryAddToDic(item:dict, ctrl):
	if item != {}:
		var.allOrig.append(item)
		#加入transDicIO
		if 'name' in item:
			if item['name'] not in var.transDicIO:
				#print('Add to transDicIO', orig, listIndex, var.filename)
				var.transDicIO[item['name']] = ''
		if 'message' in item:
			if item['message'] not in var.transDicIO:
				#print('Add to transDicIO', orig, listIndex, var.filename)
				var.transDicIO[item['message']] = ''
		else:
			printWarning('message为空', var.filename, ctrl)
		item = {}
	return item

def dealOnce(text, contentIndex=0):
	#print(orig)
	orig = text
	#if orig.isspace() == False:
		#orig = orig.strip()
	if orig == '': 
		printWarning('提取时原文为空', var.filename, str(contentIndex))
		return False
	#if orig.isspace(): return False
	#输出原文
	var.listOrig.append(orig)
	#print(orig)
	if orig not in var.transDic:
		#print('Add to transDic', orig, var.filename, str(contentIndex))
		var.transDic[orig] = ''
	return True

def replace():
	for listIndex in range(len(var.listOrig)-1, -1, -1): #倒序
		orig = var.listOrig[listIndex]
		ctrl = var.listCtrl[listIndex]
		trans = var.transDic[orig]
		if trans == '':
			printWarningGreen('译文为空, 不替换', var.filename, orig)
			#trans = 'te'.format(listIndex) #测试
			continue
		#开始处理段落
		ret = var.replaceOnceImp(var.content, [ctrl], [trans])
		if ret == False:
			printError('替换错误，请检查文本', var.filename, trans)
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
	engineName = args['engineName']
	var.clear()
	var.fileType = args['file']
	#读取配置
	settings = QSettings('src/engine.ini', QSettings.IniFormat)
	strEngine = 'Engine_' + engineName
	settings.beginGroup(strEngine)
	var.Postfix = settings.value('postfix')
	var.EncodeRead = settings.value('encode')
	#输出格式
	formatList = settings.value('formatList')
	if formatList == None or str(args['outputFormat']) in formatList:
		var.io.outputFormat = args['outputFormat']
	else:
		var.io.outputFormat = -1
		showMessage("该引擎暂不支持此输出格式。")
		return 1
	# 额外输出
	if formatList == None or str(args['outputFormatExtra']) in formatList:
		var.ioExtra.outputFormat = args['outputFormatExtra']
		var.ioExtra.prefix = 'extra_'
		if var.ioExtra.outputFormat == var.io.outputFormat:
			var.ioExtra.outputFormat = -1
	else:
		var.ioExtra.outputFormat = -1
		showMessage("该引擎暂不支持此输出格式。(额外)")
		return 2
	#分割符
	var.contentSeprate = settings.value('contentSeprate')
	#导入模块
	#print(var.EncodeName, var.Postfix, engineName)
	module = import_module('extract_' + engineName)
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
	l = str.split(',')
	var.nameList = [x for x in l if x != '']

def setRegDic(str):
	var.regDic.clear()
	if str == None or str == '': return
	list = re.split('\n', str)
	for line in list:
		# 结束
		if line == '' or line.startswith('sample') or line.startswith('<'): 
			break
		pair = line.split('=', 1)
		# 控制
		if pair[0] == 'seprate':
			var.contentSeprate = pair[1]
			continue
		elif pair[0] == 'startline':
			var.startline = int(pair[1])
			continue
		elif pair[0] == 'flag':
			lst = pair[1].split(',')
			for flag in lst:
				if hasattr(var, flag):
					setattr(var, flag, True)
				else:
					printWarning('没有找到预设的参数名:', flag) 
			continue
		elif ('skip' not in pair[0]) and ('search' not in pair[0]):
			if hasattr(var, pair[0]):
				setattr(var, pair[0], pair[1])
			else:
				printWarning('没有找到预设的参数名:', pair[0])
		# 规则
		var.regDic[pair[0]] = pair[1]
		print('正则规则:', pair[0], pair[1])

def readCutoffDic():
	var.cutoffDic.clear()
	#读入cutoff字典
	filepath = os.path.join(var.workpath, 'ctrl', 'cutoff.json')
	if os.path.isfile(filepath):
		fileTransDic = open(filepath, 'r', encoding='utf-8')
		var.cutoffDic = json.load(fileTransDic)
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
	if not var.transReplace: return
	filepath = os.path.join(var.workpath, 'ctrl', 'text_conf.json')
	if not os.path.isfile(filepath):
		filepath = os.path.join('.', 'text_conf.json')
		if not os.path.isfile(filepath):
			return
	fileOld = open(filepath, 'r', encoding='utf-8')
	var.textConf = json.load(fileOld)
	fileOld.close()

def showMessage(msg):
	if var.window: 
		var.window.statusBar.showMessage(msg)

def initArgs(args):
	# 打印
	var.printSetting = args['print']
	ret = chooseEngine(args)
	if ret != 0:
		return ret
	# 匹配
	setNameList(args['nameList'])
	# 正则
	setRegDic(args['regDic'])
	# 截断
	var.cutoff = args['cutoff']
	var.cutoffCopy = args['cutoffCopy']
	readCutoffDic()
	# 是否不读取译文
	var.noInput =  args['noInput']
	# 编码
	var.EncodeRead = args['encode']
	if args['binEncodeValid']:
		var.OldEncodeName = var.EncodeRead
		var.NewEncodeName = var.EncodeRead
	# 分割
	var.splitAuto = args['splitAuto']
	var.splitParaSep:str = args['splitParaSep']
	if '\\' in var.splitParaSep: #需要处理转义
		var.splitParaSep = var.splitParaSep.encode().decode('unicode_escape')
	var.ignoreSameLineCount = args['ignoreSameLineCount']
	var.fixedMaxPerLine = args['fixedMaxPerLine']
	var.maxCountPerLine = args['maxCountPerLine']
	var.pureText = args['pureText']
	var.tunnelJis = args['tunnelJis']
	var.subsJis = args['subsJis']
	if var.tunnelJis:
		generateJisList()
	elif var.subsJis:
		generateSubsDic()
	var.transReplace = args['transReplace']
	readTextConf()
	return 0

def extractDone():
	if var.tunnelJis:
		generateTunnelJisMap()
	elif var.subsJis:
		generateSubsConfig()
	showMessage("处理完成。")
	print('Done.\n')

#args = [workpath, engineName, outputFormat, nameList]
def mainExtract(args, parseImp, initDone=None):
	if len(args) < 4:
		printError("main_extract参数错误", args)
		return
	showMessage("开始处理...")
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
		for name in os.listdir(var.workpath):
			#print('File:', name)
			if var.Postfix == '':
				var.filename = name
			else:
				var.filename = os.path.splitext(name)[0]
			filepath = os.path.join(var.workpath, var.filename+var.Postfix)
			#print(name, filepath)
			if os.path.isfile(filepath):
				printDebug('读取文件:', var.filename)
				parseImp()
				keepAllOrig()
				#break #测试
		printInfo('读取文件数:', var.inputCount)
		writeFormat()
		printInfo('新建文件数:', var.outputCount)
		var.curIO = var.ioExtra
		writeFormat()
		writeCutoffDic()
	else:
		printError('未找到主目录')
	extractDone()

