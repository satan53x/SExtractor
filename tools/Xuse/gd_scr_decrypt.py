# ------------------------------------------------------------
# https://github.com/satan53x/SExtractor/tree/main/tools/Xuse
# 同时适用于加解密
# ------------------------------------------------------------
import sys
import os
from tkinter import filedialog
DefaultPath = ''
Key = [0x51, 0x51, 0x51, 0x00]
Size = len(Key)

# ------------------------------------------------------------
#var
dirpath = ''
filename = '' 
content = []
# ------------------------------------------------------------
def decryptFile():
	#print(filename)
	filepath = os.path.join(dirpath, filename)
	fileOld = open(filepath, 'rb')
	data = fileOld.read()
	fileOld.close()
	#处理
	data = decryptData(data)
	#导出
	content.clear()
	content.append(data)
	write()

def decryptData(data):
	data = bytearray(data)
	for pos in range(0, len(data)):
		data[pos] = data[pos] ^ Key[pos % Size]
	return data

# ------------------------------------------------------------
def write():
	path = os.path.join(dirpath, 'new')
	if not os.path.exists(path):
		os.makedirs(path)
	name = filename
	filepath = os.path.join(path, name)
	fileNew = open(filepath, 'wb')
	fileNew.writelines(content)
	fileNew.close()
	print(f'Write done: {name}')

def main():
	path = DefaultPath
	if path:
		pass
	elif len(sys.argv) < 2:
		path = filedialog.askdirectory(initialdir=path)
	else:
		path = sys.argv[1]
	#print(path)
	global dirpath
	global filename
	if os.path.isdir(path):
		dirpath = path
		for name in os.listdir(dirpath):
			filename = name
			filepath = os.path.join(dirpath, filename)
			if os.path.isfile(filepath):
				decryptFile()
				#break

main()