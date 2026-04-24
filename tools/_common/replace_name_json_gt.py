# ------------------------------------------------------------
# 为galTransl的json替换名字
# ------------------------------------------------------------
import re
import sys
import os
import json
from tkinter import filedialog 
EncodeName = 'utf-8'
OnceLinesCount = 50
Postfix = '.json'
Reverse = False
DefaultPath = ''

#------------替换--------------
NameDic = {
}

# ------------------------------------------------------------
#var
dirpath = ''
filename = '' 

allJson = {}
listOrig = []
listTrans = []

# ------------------------------------------------------------
def replace():
	global allJson
	#print(filename)
	filepath = os.path.join(dirpath, filename+Postfix)
	fileOld = open(filepath, 'r', encoding=EncodeName)
	allJson = json.load(fileOld)
	if not Reverse:
		nameListOld = [str.lower(v) for v in NameDic.keys()]
		nameListNew = list(NameDic.values())
	else:
		nameListOld = list(NameDic.values())
		nameListNew = [str.lower(v) for v in NameDic.keys()]
	for item in allJson:
		if 'name' not in item: continue
		if item['name'] in nameListOld:
			i = nameListOld.index(item['name'])
			item['name'] = nameListNew[i]
	write()
	fileOld.close()

#读取nameDic
def read():
	global NameDic
	if len(NameDic) > 0: return #已有则不读取
	path = os.path.join(dirpath, 'ctrl')
	name = 'nameDic'
	filepath = os.path.join(path, name+Postfix)
	file = open(filepath, 'r', encoding=EncodeName)
	NameDic = json.load(file)
	file.close()
	print(f'Read done: {name}')

# ------------------------------------------------------------
def write():
	path = os.path.join(dirpath, 'new')
	if not os.path.exists(path):
		os.makedirs(path)
	name = filename
	filepath = os.path.join(path, name+Postfix)
	fileNew = open(filepath, 'w', encoding=EncodeName)
	json.dump(allJson, fileNew, ensure_ascii=False, indent=2)
	fileNew.close()
	print(f'Write done: {name}')

def main():
	path = DefaultPath
	if len(sys.argv) < 2:
		path = filedialog.askdirectory(initialdir=path)
	else:
		path = sys.argv[1]
	#print(path)
	global dirpath
	global filename
	if os.path.isdir(path):
		dirpath = path
		#print(dirpath)
		read()
		for name in os.listdir(dirpath):
			#print(name)
			filename = name.replace(Postfix, '')
			filepath = os.path.join(dirpath, filename+Postfix)
			if os.path.isfile(filepath):
				#print(filepath)
				replace()
				#break

main()