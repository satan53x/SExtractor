# ------------------------------------------------------------
# 为galTransl的json导出名字
# ------------------------------------------------------------
import sys
import os
import json
from tkinter import filedialog 
DefaultPath = ''
EncodeName = 'utf-8'
Postfix = '.json'

# ------------------------------------------------------------
#var
dirpath = ''
filename = '' 

allJson = {}
listOrig = []
listTrans = []
# ------------------------------------------------------------
def findname():
	global EncodeName
	global allJson
	#print(filename)
	filepath = os.path.join(dirpath, filename+Postfix)
	fileOld = open(filepath, 'r', encoding=EncodeName)
	content = json.load(fileOld)
	for item in content:
		if 'name' not in item: continue
		name = item['name']
		allJson[name] = name
	fileOld.close()

# ------------------------------------------------------------
def write():
	path = os.path.join(dirpath, 'ctrl')
	if not os.path.exists(path):
		os.makedirs(path)
	name = 'nameDic'
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
		for name in os.listdir(dirpath):
			#print(name)
			filename = name.replace(Postfix, '')
			filepath = os.path.join(dirpath, filename+Postfix)
			if os.path.isfile(filepath):
				#print(filepath)
				findname()
				#break
	write()

main()