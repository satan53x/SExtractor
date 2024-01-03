# ------------------------------------------------------------
# https://github.com/satan53x/SExtractor/tree/main/tools/CScript
# ------------------------------------------------------------
import sys
import os
from tkinter import filedialog
DefaultPath = r''
PackName = '../scr.dat'
NameLen = 0x2C #根据原包头部的单个名字长度进行设定，常见值为：0x2C, 0x44, 0x64

# ------------------------------------------------------------
#var
dirpath = ''
filenameList = [] 

content = []
# ------------------------------------------------------------
def pack():
	count = len(filenameList)
	headerSection = bytearray(4) #个数
	headerSection[0:4] = int.to_bytes(count, 4, byteorder='little')
	indexSection = bytearray()
	global content
	content = [ headerSection, indexSection ]
	addr = len(headerSection) + (NameLen + 8) * count #文件在包内的偏移
	for i, filename in enumerate(filenameList):
		#读取文件
		print('文件写入名:', filename)
		filepath = os.path.join(dirpath, filename)
		fileOld = open(filepath, 'rb')
		data = fileOld.read()
		fileOld.close()
		#写入索引
		bs = bytearray(NameLen + 8)
		name = filename.encode('cp932')
		bs[0:len(name)] = name
		bs[-8:-4] = int.to_bytes(len(data), 4, byteorder='little')
		bs[-4:] = int.to_bytes(addr, 4, byteorder='little')
		indexSection.extend(bs)
		addr += len(data)
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
		for root, dirs, files in os.walk(dirpath):
			for file in files:
				filepath = os.path.join(root, file)
				#print(filepath)
				if filepath.startswith(dirpath):
					filename = filepath[len(dirpath):].lstrip(os.path.sep)
				else:
					print('绝对路径不匹配:', filepath, dirpath)
					continue
				filenameList.append(filename)
		pack()
main()