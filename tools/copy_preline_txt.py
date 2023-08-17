# ------------------------------------------------------------
# 为txt文本复制上一行的原文到译文
# ------------------------------------------------------------
import re
import sys
import os
import json
from tkinter import filedialog 
DefaultPath = '.'
EncodeName = 'utf-8'
Postfix = '.txt'
SearchStr = r'^>'
LineStart = '>'
PreOffset = -1

# ------------------------------------------------------------
#var
dirpath = ''
filename = '' 

content = []
# ------------------------------------------------------------
def replace():
	global EncodeName
	global content
	#print(filename)
	filepath = os.path.join(dirpath, filename+Postfix)
	fileOld = open(filepath, 'r', encoding=EncodeName)
	content = fileOld.readlines()
	for contentIndex in range(len(content)):
		line = content[contentIndex]
		if re.search(SearchStr, line):
			#匹配成功则复制
			preLine = content[contentIndex + PreOffset]
			if LineStart != '':
				#重新组合
				content[contentIndex] = LineStart + preLine
			else:
				#在原句追加
				content[contentIndex] = line + preLine
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
	fileNew.writelines(content)
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