import os
import sys
import json
import re
from common import *
from importlib import import_module
from PyQt5.QtCore import QSettings
from PyQt5.QtWidgets import QStatusBar

class ExtractVar():
	Postfix = '.txt'
	EncodeRead = 'utf-8'
	contentSeprate = b'\x0D\x0A'
	nameList = []
	regDic = {}
	cutoff = {}
	#
	parseImp = None
	replaceOnceImp = None
	readFileDataImp = None
	workpath = ''
	partMode = 0 # 0 单json; 1 多json
	#导出格式:
	# 0 json {orig:''}
	# 1 json {orig:orig}
	# 2 json [{name,message}]
	outputFormat = 0
	outputFormatExtra = -1

	outputDir = 'ctrl'
	inputDir = 'ctrl'
	ouputFileName = ''
	inputFileName = ''

	#-------------------
	transDic = {}
	transDicIO = {} #读取写入时的原本字典，不参与write()，模式01则不需要
	allOrig = []

	#-------------------
	filename = ''
	content = None
	insertContent = {} #需要插入的内容
	isInput = False #是否写入译文
	inputCount = 0 #导出文件个数
	outputCount = 0 #导出文件个数
	listOrig = [] #原文表
	listCtrl = [] #控制表

	#-------------------
	#窗口
	window = None

class OutputConfig():
	outputDir = 'ctrl'
	inputDir = 'ctrl'
	ouputFileName = ''
	inputFileName = ''

var = ExtractVar()

def setIOFileName(formatCode):
	if var.partMode == 0: #总共一个输出文档
		if formatCode == 5:
			var.ouputFileName = 'all.orig.txt'
			var.inputFileName = 'all.trans.txt'
		elif formatCode == 2:
			var.ouputFileName = 'all.orig.json'
			var.inputFileName = 'all.trans.json'
		else:
			var.ouputFileName = 'transDic.output.json'
			var.inputFileName = 'transDic.json'
	else: #每个文件对应一个输出文档
		if formatCode == 5:
			var.ouputFileName = var.filename + '.txt'
			var.inputFileName = var.filename + '.txt'
		else:
			var.ouputFileName = var.filename + '.json'
			var.inputFileName = var.filename + '.json'

# --------------------------- 读 ---------------------------------
def readFormat(code):
	setIOFileName(code)
	var.isInput = False
	var.transDic.clear()
	var.transDicIO.clear()
	var.allOrig.clear()
	if code == 0 or code == 1:
		readFormat1()
	elif code == 2:
		readFormat2()
	elif code == 3 or code == 4:
		readFormat4()
	elif code == 5:
		readFormat5()

def readFormat1():
	#读入transDic字典
	filepath = os.path.join(var.workpath, var.inputDir, var.inputFileName)
	if os.path.isfile(filepath):
		fileTransDic = open(filepath, 'r', encoding='utf-8')
		var.transDic = json.load(fileTransDic)
		print('读入Json: ', len(var.transDic), var.inputFileName)
		var.isInput = True
		#print(list(var.transDic.values())[0])

def readFormat4():
	#读入带换行文本的transDicIO字典
	filepath = os.path.join(var.workpath, var.inputDir, var.inputFileName)
	if os.path.isfile(filepath):
		fileTransDic = open(filepath, 'r', encoding='utf-8')
		var.transDicIO = json.load(fileTransDic)
		print('读入Json: ', len(var.transDicIO), var.inputFileName)
		var.isInput = True
		#print(list(var.transDic.values())[0])
		#还原transDic
		for orig,trans in var.transDicIO.items():
			splitToTransDic(orig, trans)

def readFormat5():
	#读入txt
	filepath = os.path.join(var.workpath, var.inputDir, var.inputFileName)
	if os.path.isfile(filepath):
		#译文
		fileAllTrans = open(filepath, 'r', encoding='utf-8')
		allTrans = fileAllTrans.readlines()
		print('读入Txt:', len(allTrans), var.inputFileName)
		var.isInput = True
		#原文
		filepath = os.path.join(var.workpath, var.outputDir, var.ouputFileName)
		fileAllOrig = open(filepath, 'r', encoding='utf-8')
		allOrig = fileAllOrig.readlines()
		print('读入Txt:', len(allOrig), var.ouputFileName)
		#合并
		for i in range(len(allOrig)):
			itemOrig = re.sub(r'\n$', '', allOrig[i])
			itemTrans = re.sub(r'\n$', '', allTrans[i])
			var.transDic[itemOrig] = itemTrans
		fileAllOrig.close()
		fileAllTrans.close()

def splitToTransDic(orig, trans):
	listMsgOrig = re.split('\r\n', orig)
	listMsgTrans = re.split('\r\n', trans)
	for j in range(len(listMsgOrig)):
		msgOrig = listMsgOrig[j]
		msgTrans = ' '
		if j<len(listMsgTrans) and listMsgTrans[j] != '':
			msgTrans = listMsgTrans[j]
		if  msgOrig not in var.transDic or \
			var.transDic[msgOrig] == '' or \
			var.transDic[msgOrig] == ' ':
			var.transDic[msgOrig] = msgTrans

def readFormat2():
	#读入带换行文本的all.orig列表和all.trans列表
	filepath = os.path.join(var.workpath, var.inputDir, var.inputFileName)
	if os.path.isfile(filepath):
		#译文
		fileAllTrans = open(filepath, 'r', encoding='utf-8')
		allTrans = json.load(fileAllTrans)
		print('读入Json:', len(allTrans), var.inputFileName)
		var.isInput = True
		#原文
		filepath = os.path.join(var.workpath, var.outputDir, var.ouputFileName)
		fileAllOrig = open(filepath, 'r', encoding='utf-8')
		allOrig = json.load(fileAllOrig)
		print('读入Json:', len(allOrig), var.ouputFileName)
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

# --------------------------- 写 ---------------------------------
def writeFormat(code):
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

def writeFormatDirect(targetJson):
	#print(filepath)
	print('输出Json:', len(targetJson), var.ouputFileName)
	filepath = os.path.join(var.workpath, var.outputDir, var.ouputFileName)
	fileOutput = open(filepath, 'w', encoding='utf-8')
	#print(targetJson)
	json.dump(targetJson, fileOutput, ensure_ascii=False, indent=2)
	fileOutput.close()

def writeFormatCopyKey(targetJson):
	#print(filepath)
	print('输出Json:', len(targetJson), var.ouputFileName)
	filepath = os.path.join(var.workpath, var.outputDir, var.ouputFileName)
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
	print('输出Txt:', len(targetJson), var.ouputFileName)
	filepath = os.path.join(var.workpath, var.outputDir, var.ouputFileName)
	fileOutput = open(filepath, 'w', encoding='utf-8')
	#print(targetJson)
	for orig in targetJson.keys():
		fileOutput.write(orig + '\n')
	fileOutput.close()

# ------------------------------------------------------------
def keepAllOrig():
	listIndex = -1
	if len(var.listCtrl) > 0:
		if 'isName' in var.listCtrl[-1] or 'unfinish' in var.listCtrl[-1]:
			print('listCtrl结束行错误', var.filename, var.listCtrl[-1])
	while(listIndex < len(var.listOrig) - 1):
		item = {}
		while(True):
			listIndex += 1
			ctrl = var.listCtrl[listIndex]
			orig = var.listOrig[listIndex]
			#print(listIndex, orig, ctrl)
			if 'isName'in ctrl:
				item['name'] = orig
				if orig not in var.transDicIO:
					#print('Add to transDicIO', orig, listIndex, var.filename)
					var.transDicIO[orig] = ''
				continue
			else:
				if 'message' not in item:
					item['message'] = ""
				item['message'] += orig
				if 'unfinish' in ctrl:
					item['message'] += '\r\n'
					continue
			var.allOrig.append(item)
			#加入transDicIO
			if item['message'] not in var.transDicIO:
				#print('Add to transDicIO', orig, listIndex, var.filename)
				var.transDicIO[item['message']] = ''
			break

def dealOnce(text, listIndex):
	#print(orig)
	orig = text
	#if orig.isspace() == False:
		#orig = orig.strip()
	if orig == '': 
		print('>>>>>> Empty orig', listIndex, var.filename)
		return False
	#if orig.isspace(): return False
	#输出原文
	var.listOrig.append(orig)
	#print(orig)
	if orig not in var.transDic:
		#print('Add to transDic', orig, listIndex, var.filename)
		var.transDic[orig] = ''
	return True

def createFolder():
	path = os.path.join(var.workpath, var.inputDir)
	if not os.path.exists(path):
		os.makedirs(path)
	path = os.path.join(var.workpath, var.outputDir)
	if not os.path.exists(path):
		os.makedirs(path)
	path = os.path.join(var.workpath, 'new')
	if not os.path.exists(path):
		os.makedirs(path)

def chooseEngine(engineName, outputFormat):
	var.inputCount = 0
	var.outputCount = 0
	settings = QSettings('src/engine.ini', QSettings.IniFormat)
	strEngine = 'Engine_' + engineName
	settings.beginGroup(strEngine)
	var.Postfix = settings.value('postfix')
	var.EncodeRead = settings.value('encode')
	#输出格式
	formatList = settings.value('formatList')
	if formatList == None or str(outputFormat) in formatList:
		var.outputFormat = outputFormat
	else:
		var.outputFormat = 0
		showMessage("该引擎暂不支持此输出格式。")
		return 1
	#分割符
	s = settings.value('contentSeprate')
	#print(s.encode())
	if s: var.contentSeprate = s.encode()
	else: var.contentSeprate = None
	#导入模块
	#print(var.EncodeName, var.Postfix, engineName)
	module = import_module('extract_' + engineName)
	var.parseImp = getattr(module, 'parseImp')
	var.replaceOnceImp = getattr(module, 'replaceOnceImp')
	if settings.value('readFileData'):
		var.readFileDataImp = getattr(module, 'readFileDataImp')
	else:
		var.readFileDataImp = None
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
		if line == '' or line.startswith('sample'): 
			break
		pair = line.split('=', 1)
		# 控制
		if pair[0] == 'seprate':
			s = bytearray.fromhex(pair[1])
			var.contentSeprate = bytes(s)
			continue
		# 规则
		var.regDic[pair[0]] = pair[1]
		print('正则规则:', pair[0], pair[1])

def showMessage(msg):
	if var.window: 
		var.window.statusBar.showMessage(msg)

def initCommon(args):
	SetG('Var', var)
	ret = chooseEngine(args['engineName'], args['outputFormat'])
	if ret != 0:
		return ret
	# 匹配
	setNameList(args['nameList'])
	# 正则
	setRegDic(args['regDic'])
	# 截断
	if args['cutoff']:
		var.cutoff = True
	else:
		var.cutoff = False
	# 额外输出
	var.outputFormatExtra = args['outputFormatExtra']
	return 0

#args = [workpath, engineName, outputFormat, nameList]
def mainExtract(args, parseImp):
	if len(args) < 4:
		print("main_extract参数错误", args)
		return
	showMessage("开始处理...")
	path = args['workpath']
	if initCommon(args) != 0: return
	#print(path)
	var.partMode = 0
	var.outputDir = 'ctrl'
	var.inputDir = 'ctrl'
	print('---------------------------------')
	if os.path.isdir(path):
		var.workpath = path
		#print(var.workpath)
		createFolder()
		readFormat(var.outputFormat) #读入译文
		for name in os.listdir(var.workpath):
			#print('File:', name)
			if var.Postfix == '':
				var.filename = name
			else:
				var.filename = os.path.splitext(name)[0]
			filepath = os.path.join(var.workpath, var.filename+var.Postfix)
			#print(name, filepath)
			if os.path.isfile(filepath):
				#print('File:', name)
				parseImp()
				keepAllOrig()
				#break #测试
		print('读取文件数:', var.inputCount)
		writeFormat(var.outputFormat)
		print('新建文件数:', var.outputCount)
	else:
		print('未找到主目录')
	showMessage("处理完成。")
	print('')