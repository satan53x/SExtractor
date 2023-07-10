import sys
import os
import json 
import re
from common import *

EncodeName = 'utf-8'
OnceLinesCount = 1000
Postfix = '.json'

#var
workpath = ''
filename = ''

allJson = [
	{}, # 0 字典
	[] # 1 列表
]
jsonType = 0

def writeMerge():
	#print(filename)
	name = re.sub(r'\.[0-9]+', '', filename)
	filepath = os.path.join(workpath, name + '.merge' + Postfix)
	fileNew = open(filepath, 'w', encoding=EncodeName)
	json.dump(allJson[jsonType], fileNew, ensure_ascii=False, indent=2)
	fileNew.close()
	print('Write done.')

def writeSeprate(seq):
	filepath = os.path.join(workpath, filename + '.' + str(seq) + Postfix)
	fileNew = open(filepath, 'w', encoding=EncodeName)
	json.dump(allJson[jsonType], fileNew, ensure_ascii=False, indent=2)
	fileNew.close()
	print('Write done.')

def read(funcIndex):
	global jsonType
	print('Load', filename)
	filepath = os.path.join(workpath, filename+Postfix)
	fileOld = open(filepath, 'r', encoding=EncodeName)
	content = json.load(fileOld)
	fileOld.close()
	if isinstance(content, dict):
		jsonType = 0
		#处理
		if funcIndex == 0:
			mergeDic(content)
		else:
			seprateDic(content)
	elif isinstance(content, list):
		jsonType = 1
		#处理
		if funcIndex == 0:
			mergeList(content)
		else:
			seprateList(content)
	else:
		print('请检查Json格式。')
		return

def mergeDic(content):
	for key, value in content.items():
		allJson[0][key] = value

def mergeList(content):
	for item in content:
		allJson[1].append(item)

def seprateDic(content):
	count = 0
	seq = 0
	allJson[0].clear()
	for key, value in content.items():
		allJson[0][key] = value
		count += 1
		if count >= OnceLinesCount:
			seq += 1
			writeSeprate(seq)
			count = 0
			allJson[0].clear()
	if count != 0:
		seq += 1
		writeSeprate(seq)

def seprateList(content):
	count = 0
	seq = 0
	for item in content:
		allJson[1].append(item)
		count += 1
		if count >= OnceLinesCount:
			seq += 1
			writeSeprate(seq)
			count = 0
			allJson[1].clear()
	if count != 0:
		seq += 1
		writeSeprate(seq)

#args: [workpath, funcIndex, lineCount]
def mergeTool(args):
	if len(args) < 3:
		print("参数错误")
		return
	path = args[0]
	funcIndex = args[1]
	global OnceLinesCount
	OnceLinesCount = args[2]
	#print(path)
	global workpath
	global filename
	if os.path.isdir(path):
		workpath = path
		#print(workpath)
		allJson[1].clear()
		for name in os.listdir(workpath):
			#print('Load', name)
			filename = name.replace(Postfix, '')
			filepath = os.path.join(workpath, filename+Postfix)
			if os.path.isfile(filepath):
				#print(filepath)
				read(funcIndex)
				#break
		if funcIndex == 0:
			writeMerge()
	else:
		print('未找到主目录')
