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
	ContentSeprate = b'\x0D\x0A'
	parseImp = None
	replaceOnceImp = None
	workpath = ''
	#导出格式:
	# 0 json {orig:''}
	# 1 json {orig:orig}
	# 2 json [{name,message}]
	outputFormat = 0

	partMode = 0 # 0 单json; 1 多json
	outputDir = 'ctrl'
	inputDir = 'ctrl'
	ouputFileName = ''
	inputFileName = ''

	#-------------------
	transDic = {}
	allOrig = []

	#-------------------
	filename = ''
	content = None
	isInput = False #是否写入译文
	inputCount = 0 #导出文件个数
	outputCount = 0 #导出文件个数
	listOrig = [] #原文表
	listCtrl = [] #控制表

	#-------------------
	#窗口
	window = None

var = ExtractVar()

def setFileName(formatCode):
	if var.partMode == 0: #总共一个json
		if formatCode == 2:
			var.ouputFileName = 'all.orig.json'
			var.inputFileName = 'all.trans.json'
		else:
			var.ouputFileName = 'transDic.output.json'
			var.inputFileName = 'transDic.json'
	else: #每个文件对应一个json
		var.ouputFileName = var.filename + '.json'
		var.inputFileName = var.filename + '.json'


def readFormat(code):
	setFileName(code)
	if code == 2:
		readFormat2()
	else:
		readFormat1()

def readFormat1():
	#存在则读入译文
	var.isInput = False
	var.transDic.clear()
	filepath = os.path.join(var.workpath, var.inputDir, var.inputFileName)
	if os.path.isfile(filepath):
		fileTransDic = open(filepath, 'r', encoding='utf-8')
		var.transDic = json.load(fileTransDic)
		print('读入Json: ', len(var.transDic), var.inputFileName)
		var.isInput = True
		#print(list(var.transDic.keys())[0])
		#print(list(var.transDic.values())[0])

def readFormat2():
	#存在则读入译文
	var.isInput = False
	var.transDic.clear()
	filepath = os.path.join(var.workpath, var.inputDir, var.inputFileName)
	if os.path.isfile(filepath):
		fileAllTrans = open(filepath, 'r', encoding='utf-8')
		allTrans = json.load(fileAllTrans)
		print('读入Json:', len(allTrans), var.inputFileName)
		var.isInput = True
		#print(list(var.transDic.keys())[0])
		#print(list(var.transDic.values())[0])
		filepath = os.path.join(var.workpath, var.outputDir, var.ouputFileName)
		fileAllOrig = open(filepath, 'r', encoding='utf-8')
		var.allOrig = json.load(fileAllOrig)
		print('读入Json:', len(var.allOrig), var.ouputFileName)
		#合并
		for i in range(len(var.allOrig)):
			itemOrig = var.allOrig[i]
			itemTrans = allTrans[i]
			if 'name' in itemOrig: #名字
				if itemOrig['name'] not in var.transDic:
					var.transDic[itemOrig['name']] = itemTrans['name']
			if 'message' in itemOrig: #对话
				listMsgOrig = itemOrig['message'].split('\r\n')
				listMsgTrans = itemTrans['message'].split('\r\n')
				for j in range(len(listMsgOrig)):
					msgOrig = listMsgOrig[j]
					msgTrans = ' '
					if j<len(listMsgTrans):
						msgTrans = listMsgTrans[j]
					var.transDic[msgOrig] = msgTrans
		fileAllOrig.close()
		fileAllTrans.close()
	var.allOrig.clear()

def writeFormat(code):
	if code == 2:
		writeFormat2()
	elif code == 1:
		writeFormat1()
	else:
		writeFormat0()

def writeFormat0():
	#print(filepath)
	print('输出Json:', len(var.transDic), var.ouputFileName)
	filepath = os.path.join(var.workpath, var.outputDir, var.ouputFileName)
	#print(filepath)
	fileTransDic = open(filepath, 'w', encoding='utf-8')
	#print(var.transDic)
	json.dump(var.transDic, fileTransDic, ensure_ascii=False, indent=4)
	fileTransDic.close()

def writeFormat1():
	#print(filepath)
	print('输出Json:', len(var.transDic), var.ouputFileName)
	filepath = os.path.join(var.workpath, var.outputDir, var.ouputFileName)
	#print(filepath)
	fileTransDic = open(filepath, 'w', encoding='utf-8')
	#print(var.transDic)
	tmpDic = {}
	for orig,trans in var.transDic.items():
		if trans == '':
			tmpDic[orig] = orig
		else:
			tmpDic[orig] = trans
	json.dump(tmpDic, fileTransDic, ensure_ascii=False, indent=4)
	fileTransDic.close()

def writeFormat2():
	print('输出Json:', len(var.allOrig), var.ouputFileName)
	filepath = os.path.join(var.workpath, var.outputDir, var.ouputFileName)
	#print(filepath)
	fileAllOrig = open(filepath, 'w', encoding='utf-8')
	#print(var.transDic)
	json.dump(var.allOrig, fileAllOrig, ensure_ascii=False, indent=2)
	fileAllOrig.close()

def keepAllOrig():
	listIndex = -1
	while(listIndex < len(var.listOrig) - 1):
		item = {}
		while(True):
			listIndex += 1
			ctrl = var.listCtrl[listIndex]
			orig = var.listOrig[listIndex]
			#print(listIndex, orig, ctrl)
			if 'isName'in ctrl:
				item['name'] = orig
				continue
			else:
				if 'message' not in item:
					item['message'] = ""
				item['message'] += orig
				if 'notEnd' in ctrl:
					item['message'] += '\r\n'
					continue
			var.allOrig.append(item)
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
	settings = QSettings('src/engine.ini', QSettings.IniFormat)
	strEngine = 'Engine_' + engineName
	settings.beginGroup(strEngine)
	var.Postfix = settings.value('postfix')
	var.EncodeRead = settings.value('encode')
	#输出格式
	formatList = settings.value('formatList')
	if str(outputFormat) in formatList:
		var.outputFormat = outputFormat
	else:
		var.outputFormat = 0
		showMessage("该引擎暂不支持此输出格式。")
		return 1
	#分割符
	s = settings.value('ContentSeprate')
	#print(s.encode())
	if s: var.ContentSeprate = s.encode()
	else: var.ContentSeprate = None
	settings.endGroup()
	#导入模块
	#print(var.EncodeName, var.Postfix, engineName)
	module = import_module('extract_' + engineName)
	var.parseImp = getattr(module, 'parseImp')
	var.replaceOnceImp = getattr(module, 'replaceOnceImp')
	var.inputCount = 0
	var.outputCount = 0
	return 0

def showMessage(msg):
	if var.window: 
		var.window.statusBar.showMessage(msg)

#args = [workpath, engineCode, outputFormat]
def mainExtract(args, parseImp):
	if len(args) < 3:
		print("main_extract参数错误", args)
		return
	showMessage("开始处理...")
	path = args[0]
	#print(path)
	ret = chooseEngine(args[1], args[2])
	if ret != 0:
		return
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
			#print(name)
			var.filename = os.path.splitext(name)[0]
			filepath = os.path.join(var.workpath, var.filename+var.Postfix)
			#print(name, filepath)
			if os.path.isfile(filepath):
				parseImp()
				keepAllOrig()
				#break #测试
		print('读取文件数:', var.inputCount)
		writeFormat(var.outputFormat)
		print('新建文件数:', var.outputCount)
	showMessage("输出完成。")
	print('')