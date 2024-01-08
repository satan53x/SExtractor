# ------------------------------------------------------------
# https://github.com/satan53x/SExtractor/tree/main/tools/Silky
# 仅限Azurite arc包
# ------------------------------------------------------------
import sys
import os
from tkinter import filedialog
DefaultPath = ''
Postfix = ''
PackName = 'new.arc'

# ------------------------------------------------------------
#var
dirpath = ''
filenameList = [] 
content = []

# ------------------------------------------------------------
def pack():
	#索引长度+0000
	signatureSection = bytearray(4)
	signatureSection[2:4] = b'\0\0'
	#子文件索引区
	indexSection = []
	indexLen = 0
	#子文件区
	fileSection = []
	for i, filename in enumerate(filenameList):
		#读取文件
		filepath = os.path.join(dirpath, filename+Postfix)
		fileOld = open(filepath, 'rb')
		data = fileOld.read()
		fileOld.close()
		#添加索引
		bs = bytearray()
		name = filename.encode('cp932') #名字
		name = encrypt(name)
		bs.append(len(name)) #名字长度,单字节
		bs.extend(name)
		bs.extend(int.to_bytes(len(data), 4, byteorder='big')) #文件长度(包外)
		bs.extend(int.to_bytes(len(data), 4, byteorder='big')) #文件长度(包里)
		bs.extend(b'\0\0\0\0') #预留偏移
		indexSection.append(bs)
		indexLen += len(bs)
		#附加文件
		fileSection.append(data)

	#修正偏移
	offset = len(signatureSection) + indexLen
	#修正sig
	signatureSection[0:2] = int.to_bytes(indexLen, 2, byteorder='little')
	#修正索引区
	for i, filename in enumerate(filenameList):
		indexSection[i][-4:] = int.to_bytes(offset, 4, byteorder='big')
		offset += len(fileSection[i])
	
	#合并
	global content
	content = [
		signatureSection, 
		bytes().join(indexSection), 
		bytes().join(fileSection)
	]
	write()

def encrypt(t):
	bs = bytearray(t)
	key = len(bs)
	for i in range(len(bs)):
		bs[i] -= key
		key -= 1
	return bs

# ------------------------------------------------------------
def write():
	path = os.path.join(dirpath, '..')
	if not os.path.exists(path):
		os.makedirs(path)
	name = PackName
	filepath = os.path.join(path, name)
	fileNew = open(filepath, 'wb')
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
	global filenameList
	if os.path.isdir(path):
		dirpath = path
		#print(dirpath)
		for name in os.listdir(dirpath):
			#print(name)
			filename = name.replace(Postfix, '')
			filepath = os.path.join(dirpath, filename+Postfix)
			if os.path.isfile(filepath):
				#print(filepath)
				filenameList.append(filename)
				#break
		pack()
main()