# ------------------------------------------------------------
# 为galTransl的json限制每行最大字符数
# 将删除原有换行符并添加新换行符
# ------------------------------------------------------------
import sys
import os
import json
from tkinter import filedialog 
DefaultPath = '.'
EncodeName = 'utf-8'
Postfix = '.json'
MaxLen = 25
Seprate = '\n'

# ------------------------------------------------------------
#var
dirpath = ''
filename = '' 

allJson = {}
listOrig = []
listTrans = []
# ------------------------------------------------------------
def limitMaxLen(old:str, maxLen, sep):
	text = old.replace(sep, '')
	if text == '': return old
	lst = [text[i:i+maxLen]+sep for i in range(0, len(text), maxLen)]
	if lst[-1].endswith(sep):
		lst[-1] = lst[-1][:-len(sep)]
	text = ''.join(lst)
	return text

def replace():
	global EncodeName
	global allJson
	#print(filename)
	filepath = os.path.join(dirpath, filename+Postfix)
	fileOld = open(filepath, 'r', encoding=EncodeName)
	allJson = json.load(fileOld)
	for item in allJson:
		if 'message' not in item: continue
		text = limitMaxLen(item['message'], MaxLen, Seprate)
		item['message'] = text
	write()
	fileOld.close()

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
		for name in os.listdir(dirpath):
			#print(name)
			filename = name.replace(Postfix, '')
			filepath = os.path.join(dirpath, filename+Postfix)
			if os.path.isfile(filepath):
				#print(filepath)
				replace()
				#break

main()