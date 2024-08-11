# ------------------------------------------------------------
# https://github.com/satan53x/SExtractor/tree/main/tools/BlackRainbow
# ------------------------------------------------------------
import sys
import os
from tkinter import filedialog
import zlib
DefaultPath = ''
Postfix = ''
PackName = 'data.pak'
Compressed = True


# ------------------------------------------------------------
#var
dirpath = ''
filenameList = [] 

content = []
# ------------------------------------------------------------
def pack():
	indexSection = bytearray()
	countSection = bytearray(8) #个数和偏移
	global content
	content = []
	offset = 0
	for i, filename in enumerate(filenameList):
		print('Packing:', filename)
		filepath = os.path.join(dirpath, filename+Postfix)
		fileOld = open(filepath, 'rb')
		data = fileOld.read()
		fileOld.close()
		#附加内容
		dataHeader = bytearray()
		dataHeader.extend(int.to_bytes(offset, 4, byteorder='little')) #子文件偏移
		uncomSize = len(data)
		comSize = uncomSize
		if Compressed:
			data = zlib.compress(data)
			comSize = len(data)
		else:
			uncomSize = 0xFFFFFFFF
		dataHeader.extend(int.to_bytes(comSize, 4, byteorder='little')) #压缩后长度
		dataHeader.extend(int.to_bytes(uncomSize, 4, byteorder='little')) #未压缩长度
		nameBytes = filename.replace('\\', '/').encode('utf-16-le')
		nameLen = len(nameBytes) // 2 #字符数，不是字节数
		dataHeader.extend(int.to_bytes(nameLen, 4, byteorder='little')) #文件名长度
		dataHeader.extend(nameBytes) #文件名
		#添加索引
		indexSection.extend(dataHeader)
		#添加内容
		content.append(data)
		offset += len(content[-1])
	#完成索引
	content.append(indexSection)
	countSection[0:4] = int.to_bytes(len(filenameList), 4, byteorder='little')
	countSection[4:8] = int.to_bytes(len(indexSection), 4, byteorder='little')
	content.append(countSection)
	write()

# ------------------------------------------------------------
def write():
	path = os.path.join(dirpath, '..')
	if not os.path.exists(path):
		os.makedirs(path)
	filepath = os.path.join(path, PackName)
	fileNew = open(filepath, 'wb')
	fileNew.writelines(content)
	fileNew.close()
	print(f'Write done: {filepath}')

def get_files(start_path):
	file_list = []
	for root, dirs, files in os.walk(start_path):
		for file in files:
			# 获取相对路径
			relative_path = os.path.relpath(os.path.join(root, file), start_path)
			file_list.append(relative_path)
	return file_list 

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
		files = get_files(dirpath)
		for name in files:
			filename = name.replace(Postfix, '')
			filenameList.append(filename)
		pack()
main()