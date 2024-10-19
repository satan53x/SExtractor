# ------------------------------------------------------------
# https://github.com/satan53x/SExtractor/tree/main/tools/HotSoup
# ------------------------------------------------------------
import re
import sys
import os
from tkinter import filedialog
DefaultPath = r''
PackName = '../data.new.dat'

Key = 0 #0xAC52AE58 #为0时可以不需要加密
Signature = b'DPMX'
IndexPadding = b'\xFF\xFF\xFF\xFF'

# ------------------------------------------------------------
#var
dirpath = ''
filenameList = [] 
content = []
# ------------------------------------------------------------
def pack():
	count = len(filenameList)
	headerSize = 0x10
	indexSize = count * 0x20
	#header
	headerSection = bytearray(headerSize)
	headerSection[0:4] = Signature
	headerSection[4:8] = int.to_bytes(headerSize+indexSize, 4, byteorder='little')
	headerSection[8:12] = int.to_bytes(count, 4, byteorder='little')
	#index
	indexSection = bytearray()
	global content
	content = [ headerSection, indexSection ]
	addr = 0
	for i, filename in enumerate(filenameList):
		#读取文件
		print('文件写入名:', filename)
		filepath = os.path.join(dirpath, filename)
		fileOld = open(filepath, 'rb')
		data = fileOld.read()
		fileOld.close()
		#写入索引
		size = len(data)
		bs = bytearray(0x20)
		name = filename.encode('cp932')
		if len(name) > 0x10:
			print('文件名过长', name)
		bs[0:len(name)] = name
		bs[0x10:0x14] = IndexPadding
		bs[0x14:0x18] = int.to_bytes(Key, 4, byteorder='little')
		bs[0x18:0x1C] = int.to_bytes(addr, 4, byteorder='little')
		bs[0x1C:0x20] = int.to_bytes(size, 4, byteorder='little')
		indexSection.extend(bs)
		addr += size
		#写入文件
		content.append(data)
	write()

# ------------------------------------------------------------
def write():
	#path = os.path.join(dirpath, '..')
	# if not os.path.exists(path):
	# 	os.makedirs(path)
	name = PackName
	filepath = os.path.join(dirpath, name)
	fileNew = open(filepath, 'wb')
	fileNew.writelines(content)
	fileNew.close()
	print(f'Write done: {name}')

def listFiles(start_path):
	file_list = []
	for name in os.listdir(start_path):
		filepath = os.path.join(start_path, name)
		if os.path.isfile(filepath):
			file_list.append(name)
	return file_list 
	
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
	global filenameList
	if os.path.isdir(path):
		dirpath = path
		print('工作目录', dirpath)
		files = listFiles(path)
		filenameList.extend(files)
		pack()
main()