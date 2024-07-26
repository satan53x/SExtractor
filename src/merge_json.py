import shutil
import sys
import os
import json 
import re

import pandas as pd
from common import *
from PyQt5.QtCore import QSettings

EncodeName = 'utf-8'
OnceLinesCount = 0 #为0则需要读入filenameList缓存
Postfix = '.json'
PostfixXlsx = '.xlsx'

#var
mergePath = ''
filename = ''

allJson = [
	{}, # 0 字典
	[] # 1 列表
]
jsonType = 0
filenameList = []

#----------------------------合并/分割json-------------------------------
def writeMerge():
	#print(filename)
	name = None
	if OnceLinesCount == 0:
		name = 'merge' + Postfix
	else:
		name = re.sub(r'\.[0-9]+', '', filename)
		name = name + '.merge' + Postfix
	filepath = os.path.join(mergePath, name)
	fileNew = open(filepath, 'w', encoding=EncodeName)
	json.dump(allJson[jsonType], fileNew, ensure_ascii=False, indent=2)
	fileNew.close()
	print('输出完成:', name, len(allJson[jsonType]))
	#保存合并信息
	filenameList.append([0, name])
	cache = json.dumps(filenameList, indent=2)
	settings = QSettings('main/config.ini', QSettings.IniFormat)
	settings.setValue('filenameList', cache)

def writeSeparate(seq):
	name = None
	if OnceLinesCount == 0:
		name = filenameList[seq][1] + Postfix
	else:
		name = filename + '.' + str(seq) + Postfix
		name = f'{filename}.{seq:04d}{Postfix}'
	filepath = os.path.join(mergePath, name)
	fileNew = open(filepath, 'w', encoding=EncodeName)
	json.dump(allJson[jsonType], fileNew, ensure_ascii=False, indent=2)
	fileNew.close()
	print('输出完成:', name, len(allJson[jsonType]))

def read(funcIndex):
	global jsonType
	print('Load', filename)
	filepath = os.path.join(mergePath, filename+Postfix)
	fileOld = open(filepath, 'r', encoding=EncodeName)
	content = json.load(fileOld)
	fileOld.close()
	if isinstance(content, dict):
		jsonType = 0
		#字典
		if funcIndex == 0:
			mergeDic(content)
		else:
			separateDic(content)
	elif isinstance(content, list):
		jsonType = 1
		#列表
		if funcIndex == 0:
			mergeList(content)
		else:
			separateList(content)
	else:
		print('请检查Json格式。')
		return
	# 合并时缓存信息
	if funcIndex == 0:
		item = [len(content), filename] #行数，文件名
		filenameList.append(item)
		if filename.endswith('merge'):
			print('\033[33m合并前已存在merge.json，请确定操作是否重复\033[0m')

def mergeDic(content):
	for key, value in content.items():
		allJson[0][key] = value

def mergeList(content):
	for item in content:
		allJson[1].append(item)

def separateDic(content):
	count = 0
	seq = 0
	for key, value in content.items():
		while getOnceLinesCount(seq) == 0:
			writeSeparate(seq)
			seq += 1
			count = 0
			allJson[0].clear()
		allJson[0][key] = value
		count += 1
		if count >= OnceLinesCount:
			writeSeparate(seq)
			seq += 1
			count = 0
			allJson[0].clear()
	if count != 0:
		writeSeparate(seq)
		seq += 1
	elif OnceLinesCount == 0:
		allJson[0].clear()
		while seq < len(filenameList) - 1:
			writeSeparate(seq)
			seq += 1

def separateList(content):
	count = 0
	seq = 0
	for item in content:
		while getOnceLinesCount(seq) == 0:
			writeSeparate(seq)
			seq += 1
			count = 0
			allJson[1].clear()
		allJson[1].append(item)
		count += 1
		if count >= getOnceLinesCount(seq):
			writeSeparate(seq)
			seq += 1
			count = 0
			allJson[1].clear()
	if count != 0:
		writeSeparate(seq)
		seq += 1
	elif OnceLinesCount == 0:
		allJson[1].clear()
		while seq < len(filenameList) - 1:
			writeSeparate(seq)
			seq += 1

def getOnceLinesCount(seq):
	if OnceLinesCount > 0: return OnceLinesCount
	item = filenameList[seq]
	return item[0]

def loadFilenameList(funcIndex):
	global filenameList
	filenameList.clear()
	if funcIndex == 1 and OnceLinesCount == 0:
		settings = QSettings('main/config.ini', QSettings.IniFormat)
		cache = settings.value('filenameList')
		filenameList = json.loads(cache)

#args: { mergePath, funcIndex, lineCount }
def mergeTool(args):
	if len(args) < 3:
		print("参数错误")
		return
	path = args['mergePath']
	funcIndex = args['funcIndex'] # 0合并 1分割
	global OnceLinesCount
	OnceLinesCount = args['lineCount']
	#print(path)
	global mergePath
	global filename
	if os.path.isdir(path):
		mergePath = path
		#print(mergePath)
		allJson[0].clear()
		allJson[1].clear()
		loadFilenameList(funcIndex)
		for name in os.listdir(mergePath):
			if name.endswith(PostfixXlsx):
				filename = name.replace(PostfixXlsx, '')
				filepath = os.path.join(mergePath, filename+PostfixXlsx)
				if os.path.isfile(filepath):
					readXlsx(funcIndex)
			else:
				#print('Load', name)
				filename = name.replace(Postfix, '')
				filepath = os.path.join(mergePath, filename+Postfix)
				if os.path.isfile(filepath):
					#print(filepath)
					read(funcIndex)
					#break
		if funcIndex == 0:
			if jsonType == -1:
				writeMergeXlsx()
			else:
				writeMerge()
		print('处理结束')
	else:
		print('未找到主目录')

#----------------------------合并/分割xlsx-------------------------------
def readXlsx(funcIndex):
	global jsonType
	jsonType = -1 #xlsx
	filepath = os.path.join(mergePath, filename+PostfixXlsx)
	xls = pd.ExcelFile(filepath)
	if funcIndex == 0:
		#合并
		sheet_name = xls.sheet_names[0]
		df = pd.read_excel(filepath)
		allJson[0][sheet_name] = df
	else:
		#分割
		for sheet_name in xls.sheet_names:
			df = pd.read_excel(filepath, sheet_name=sheet_name)
			filenameNew = sheet_name + PostfixXlsx
			filepathNew = os.path.join(mergePath, filenameNew)
			df.to_excel(filepathNew, index=False, sheet_name=sheet_name)
			print('输出完成:', filenameNew)

def writeMergeXlsx():
	filepath = os.path.join(mergePath, 'merge'+PostfixXlsx)
	writer = pd.ExcelWriter(filepath)
	dic = allJson[0]
	for sheet_name, df in dic.items():
		df.to_excel(writer, sheet_name=sheet_name, index=False)
	writer.close()

#----------------------------生成字典-------------------------------
#args: { mergePath }
def createDicTool(args):
	global OnceLinesCount
	global mergePath
	OnceLinesCount = 0
	mergePath = args['mergePath']
	#正则
	args['file'] = 'json'
	ret = createDic(args, 'all.orig.json', 'all.trans.json')
	if ret != 1: return
	ret = createDic(args, 'key.json', 'value.json')
	if ret != 1: return
	args['file'] = 'txt'
	ret = createDic(args, 'key.txt', 'value.txt')
	if ret != 1: return
	print('\033[33m未找到文件名:\033[0m key/value[.txt/.json] 或 all.orig/all.trans[.json]')

def createDic(args, keyName, valueName):
	#print('开始查找key/value文件:', keyName, valueName)
	keyPath = os.path.join(mergePath, keyName)
	valuePath = os.path.join(mergePath, valueName)
	if not os.path.isfile(keyPath) or not os.path.isfile(valuePath):
		#print('未找到key/value文件', keyName, valueName)
		return 1
	print('找到key/value文件', keyName, valueName)
	fileKey = open(keyPath, 'r', encoding=EncodeName)
	fileValue = open(valuePath, 'r', encoding=EncodeName)
	ret = 0
	allJson[0].clear()
	if args['file'] == 'json':
		ret = createDicByJson(args, fileKey, fileValue)
	elif args['file'] == 'txt':
		ret = createDicByTxt(args, fileKey, fileValue)
	else:
		print('后缀错误')
	fileKey.close()
	fileValue.close()
	if ret == 0:
		#导出
		filenameList.clear()
		writeMerge()
	return ret

def createDicByJson(args, fileKey, fileValue):
	keyContent = json.load(fileKey)
	valueContent = json.load(fileValue)
	if len(keyContent) != len(valueContent):
		print('\033[33mkey/value文件长度不一致\033[0m')
		return 2
	if not isinstance(keyContent, list) or not isinstance(valueContent, list):
		print('\033[33mkey/value文件不是列表形式\033[0m')
		return 3
	for i in range(len(keyContent)):
		keyItem = keyContent[i]
		valueItem = valueContent[i]
		# item: 字符串
		if isinstance(keyItem, str):
			allJson[0][keyItem] = valueItem
		# item: 字典
		elif isinstance(keyItem, dict):
			keys = list(keyItem.values())
			values = list(valueItem.values())
			for i in range(len(keys)):
				key = keys[i]
				value = values[i]
				setPair(key, value, args['skipReg'])
	return 0

def createDicByTxt(args, fileKey, fileValue):
	keyContent = fileKey.readlines()
	valueContent = fileValue.readlines()
	if len(keyContent) != len(valueContent):
		print('\033[33mkey/value文件长度不一致\033[0m')
		return 2
	for i in range(len(keyContent)):
		key = keyContent[i][:-1] #去换行
		value = valueContent[i][:-1] #去换行
		setPair(key, value, args['skipReg'])
	return 0

def setPair(key, value, skipReg):
	if skipReg and re.search(skipReg, key): return 
	allJson[0][key] = value

#----------------------------收集分发-------------------------------
def collectFilesTool(args):
	mergePath = args['mergePath']
	extractPath = args['extractPath']
	filenameReg = args['filenameReg']
	collectSep = args['collectSep']
	files = listFiles(mergePath)
	count = 0
	for relativePath in files:
		filename = os.path.basename(relativePath)
		if filenameReg:
			#检查文件名
			if not re.search(filenameReg, filename):
				continue
		#包含路径信息的新名字
		lst = re.split(r'[\\/]', relativePath)
		newname = ''
		for n in lst:
			if newname != '':
				newname += collectSep
			newname += n
		#收集
		newpath = os.path.join(extractPath, newname)
		oldpath = os.path.join(mergePath, relativePath)
		print('收集文件:', relativePath)
		shutil.copy(oldpath, newpath)
		count += 1
	print('收集完成，处理文件总数:', count)

def distFilesTool(args):
	mergePath = args['mergePath']
	extractPath = args['extractPath']
	filenameReg = args['filenameReg']
	collectSep = args['collectSep']
	#检查extractPath下new目录
	path = os.path.join(extractPath, 'new')
	if os.path.isdir(path):
		print('\033[32m提取目录存在new文件夹，目录重定向到new\033[0m')
		extractPath = path 
	count = 0
	for newname in os.listdir(extractPath):
		if os.path.isdir(newname):
			continue
		filename = newname
		if filenameReg:
			#检查文件名
			if not re.search(filenameReg, filename):
				continue
		#还原路径
		lst = newname.split(collectSep)
		relativePath = os.path.join(*lst)
		#分发
		newpath = os.path.join(extractPath, newname)
		oldpath = os.path.join(mergePath, relativePath)
		print('分发文件:', relativePath)
		olddir = os.path.dirname(oldpath)
		os.makedirs(olddir, exist_ok=True) #创建路径上的文件夹
		shutil.copy(newpath, oldpath)
		count += 1
	print('分发完成，处理文件总数:', count)
