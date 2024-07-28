# ------------------------------------------------------------
# https://github.com/satan53x/SExtractor/tree/main/tools/CScript
# 依赖模块：pip install natsort
# ------------------------------------------------------------
import locale
import re
import sys
import os
from tkinter import filedialog
from natsort import ns, natsorted, os_sorted
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

#广度优先，系统排序
file_list = []
root_path = ''
def listFiles(start_path):
	global root_path
	root_path = start_path
	file_list.clear()
	locale.setlocale(locale.LC_ALL, 'ja_JP')
	listDir('')
	return file_list

def listDir(middle_path):
	dir_path = os.path.join(root_path, middle_path)
	#所有文件
	files = [filename for filename in os.listdir(dir_path) if os.path.isfile(os.path.join(dir_path, filename))]
	files = sortWindows(files)
	for filename in files:
		relative_path = os.path.join(middle_path, filename)
		file_list.append(relative_path)
	#所有文件夹
	files = [filename for filename in os.listdir(dir_path) if os.path.isdir(os.path.join(dir_path, filename))]
	files = sortWindows(files)
	for dirname in files:
		relative_path = os.path.join(middle_path, dirname)
		listDir(relative_path)

#按windows顺序
def sortWindows(filenames):
	#分出ascii开头
	filesAscii = []
	files = []
	for filename in filenames:
		if re.match(r'^[ -~]', filename):
			filesAscii.append(filename)
		else:
			files.append(filename)
	#排序
	filesAscii = os_sorted(filesAscii) #系统排序
	files = natsorted(files, alg=ns.LOCALE) #local排序
	return filesAscii + files
	
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