import json
import pandas
from common import *
from helper_text import *

var = ExVar
filepathOrig = ''
filepathTrans = ''
# --------------------------- io ---------------------------------
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
		elif io.outputFormat == 9:
			io.ouputFileName = 'transDic.output.txt'
			io.inputFileName = 'transDic.txt'
		else:
			io.ouputFileName = 'transDic.output.json'
			io.inputFileName = 'transDic.json'
	else: #每个文件对应一个输出文档
		if io.isTxt:
			io.ouputFileName = var.filename + '.txt'
			io.inputFileName = var.filename + '.txt'
		elif io.outputFormat == 8:
			io.ouputFileName = var.filename + '.xlsx'
			io.inputFileName = var.filename + '.xlsx'
		else:
			io.ouputFileName = var.filename + '.json'
			io.inputFileName = var.filename + '.json'
	io.ouputFileName = io.prefix + io.ouputFileName 
	io.inputFileName = io.prefix + io.inputFileName

#修正译文
def transReplace():
	if var.transReplace:
		if var.fileType == 'bin':
			if var.tunnelJis or var.subsJis:
				charset = 'cp932'
			else:
				charset = var.NewEncodeName.lower()
		else:
			charset = var.EncodeRead.lower()
		#译文替换
		if 'trans_replace' in var.textConf:
			for key, replaceDic in var.textConf['trans_replace'].items():
				if charset not in key: continue
				printDebug('进行译文替换')
				replaceValueRE(var.transDic, replaceDic)
		if 'orig_replace' in var.textConf:
			printDebug('进行译文的原文替换还原')
			replaceDic = {}
			for key, value in var.textConf['orig_replace'].items():
				if value == '': continue
				replaceDic[value] = key
			replaceValue(var.transDic, replaceDic)
		#原文保留
		if 'orig_keep' in var.textConf:
			for key, keepList in var.textConf['orig_keep'].items():
				if charset not in key: continue
				printDebug('进行原文保留')
				for orig, trans in var.transDic.items():
					for keep in keepList:
						if keep == orig:
							for i, t in enumerate(trans):
								trans[i] = ''
	if var.toFullWidth:
		printDebug('进行半角转全角')
		replaceDic = var.fullWidthDic
		replaceValue(var.transDic, replaceDic)
	if var.engineName in TextConfig['trans_fix']:
		replaceDic = TextConfig['trans_fix'][var.engineName]
		printDebug('进行译文修正')
		replaceValueRE(var.transDic, replaceDic)

# --------------------------- 读 ---------------------------------
def readFormat():
	setIOFileName(var.io)
	setIOFileName(var.ioExtra)
	fmt = var.curIO.outputFormat
	var.isInput = False
	var.transDic.clear()
	var.transDicIO.clear()
	var.allOrig.clear()
	global filepathOrig, filepathTrans
	filepathOrig = os.path.join(var.workpath, var.outputDir, var.curIO.ouputFileName)
	filepathTrans = os.path.join(var.workpath, var.inputDir, var.curIO.inputFileName)
	if var.noInput: #不读取译文
		return
	if not os.path.isfile(filepathTrans):
		return
	if fmt == 0 or fmt == 1:
		readFormatDic()
	elif fmt == 2:
		readFormatItemList()
	elif fmt == 3 or fmt == 4:
		readFormatDicIO()
	elif fmt == 5:
		readFormatTxt(False)
	elif fmt == 6:
		readFormatTxt(True)
	elif fmt == 7:
		readFormatList()
	elif fmt == 8:
		readFormatXlsx()
	elif fmt == 9:
		readFormatTxtTwoLine()
	elif fmt == 10 or fmt == 11:
		readFormatDicList()
	#修正译文
	transReplace()

def readFormatDic():
	#读入transDic字典
	fileTransDic = open(filepathTrans, 'r', encoding='utf-8')
	var.transDic = json.load(fileTransDic)
	printInfo('读入Json: ', len(var.transDic), var.curIO.inputFileName)
	var.isInput = True
	#print(list(var.transDic.values())[0])
	for orig, trans in var.transDic.items():
		var.transDic[orig] = [trans]

def readFormatDicIO():
	#读入带换行文本的transDicIO字典
	fileTransDic = open(filepathTrans, 'r', encoding='utf-8')
	var.transDicIO = json.load(fileTransDic)
	printInfo('读入Json: ', len(var.transDicIO), var.curIO.inputFileName)
	var.isInput = True
	#print(list(var.transDic.values())[0])
	#还原transDic
	for orig, trans in var.transDicIO.items():
		splitToTransDic(orig, trans)

def readFormatTxt(boolSplit):
	#读入txt
	#译文
	fileAllTrans = open(filepathTrans, 'r', encoding='utf-8')
	allTrans = fileAllTrans.readlines()
	printInfo('读入Txt:', len(allTrans), var.curIO.inputFileName)
	#原文
	fileAllOrig = open(filepathOrig, 'r', encoding='utf-8')
	allOrig = fileAllOrig.readlines()
	if var.partMode == 0:
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
			var.transDic[orig] = [trans]
	fileAllOrig.close()
	fileAllTrans.close()

def readFormatItemList():
	#读入带换行文本item的all.orig列表和all.trans列表
	#译文
	fileAllTrans = open(filepathTrans, 'r', encoding='utf-8')
	allTrans = json.load(fileAllTrans)
	printInfo('读入Json:', len(allTrans), var.curIO.inputFileName)
	#原文
	fileAllOrig = open(filepathOrig, 'r', encoding='utf-8')
	allOrig = json.load(fileAllOrig)
	if var.partMode == 0:
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
			orig = itemOrig['name']
			if orig not in var.transDic:
				var.transDic[orig] = []
			var.transDic[orig].append(itemTrans['name'])
		if 'message' in itemOrig: #对话
			splitToTransDic(itemOrig['message'], itemTrans['message'])
	fileAllOrig.close()
	fileAllTrans.close()

def readFormatList():
	#读入带换行字符串的all.orig列表和all.trans列表
	#译文
	fileAllTrans = open(filepathTrans, 'r', encoding='utf-8')
	allTrans = json.load(fileAllTrans)
	printInfo('读入Json:', len(allTrans), var.curIO.inputFileName)
	#原文
	fileAllOrig = open(filepathOrig, 'r', encoding='utf-8')
	allOrig = json.load(fileAllOrig)
	if var.partMode == 0:
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
	df = pandas.read_excel(filepathTrans)
	for index, row in df.iterrows():
		value = row['Value']
		if pandas.notna(value):
			var.transDic[row['Key']] = [value]
		else:
			var.transDic[row['Key']] = ['']
	printInfo('读入Xlsx: ', len(var.transDic), var.curIO.inputFileName)
	var.isInput = True
	#print(list(var.transDic.values())[0])

def readFormatTxtTwoLine():
	#读入txt
	#列表
	fileTransDic = open(filepathTrans, 'r', encoding='utf-8')
	content = fileTransDic.readlines()
	fileTransDic.close()
	allOrig = []
	allTrans = []
	for line in content:
		ret = re.match(var.twoLineFlag[0], line)
		if ret:
			allOrig.append(line[:-1])
			continue
		ret = re.match(var.twoLineFlag[1], line)
		if ret:
			allTrans.append(line[:-1])
			continue
	printInfo('读入Txt:', len(allTrans), var.curIO.inputFileName)
	if len(allTrans) != len(allOrig):
		printError('列表有效行数不一致', var.curIO.inputFileName)
		return
	var.isInput = True
	#合并 
	sep = ExVar.splitParaSep
	sepRegex = ExVar.splitParaSepRegex
	for i in range(len(allOrig)):
		origLine = allOrig[i]
		origList = re.split(var.twoLineFlag[0], origLine, 3)
		transLine = allTrans[i]
		transList = re.split(var.twoLineFlag[1], transLine, 3)
		if len(origList) != len(transList):
			printError(f'{var.twoLineFlag[0]}{var.twoLineFlag[1]}个数不一致', var.curIO.inputFileName, origLine)
			continue
		if len(origList) >= 4:
			#有名字
			splitToTransDic(origList[2], transList[2])
		#文本
		if sep != sepRegex:	
			orig = origList[-1].replace(sepRegex, sep)
			trans = transList[-1].replace(sepRegex, sep)
		else:
			orig = origList[-1]
			trans = transList[-1]
		splitToTransDic(orig, trans)

def readFormatDicList():
	#读入带换行文本字典的transDic列表
	#原文：译文
	fileAll = open(filepathTrans, 'r', encoding='utf-8')
	itemList = json.load(fileAll)
	printInfo('读入Json:', len(itemList), var.curIO.inputFileName)
	var.isInput = True
	#合并
	for item in itemList:
		for orig, trans in item.items():
			splitToTransDic(orig, trans)
	fileAll.close()