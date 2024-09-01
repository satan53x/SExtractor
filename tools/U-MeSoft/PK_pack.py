# ------------------------------------------------------------
# https://github.com/satan53x/SExtractor/tree/main/tools/U-MeSoft
# ------------------------------------------------------------
import io
import sys
import os
from tkinter import filedialog

DefaultPath = r''
CtrlDir = '..' #控制目录相对路径
ArcOld = 'OLD.PK'
ArcNew = 'SCENARIO.PK'
BytesAfterName = bytearray.fromhex('00 20 15 0A 34 40') #子文件名后边的6个字节，尚不知作用，需要自己根据原始包编辑；ArcOld有效时不会使用这个值

# ------------------------------------------------------------
#var
dirpath = ''
filenameList = []
IndexBytesDic = {}

content = []
# ------------------------------------------------------------
def pack():
	count = len(filenameList)
	indexSection = bytearray()
	global content
	content = [  ]
	addr = 0
	for i, filename in enumerate(filenameList):
		#读取文件
		print('文件写入名:', filename)
		filepath = os.path.join(dirpath, filename)
		fileOld = open(filepath, 'rb')
		data = fileOld.read()
		fileOld.close()
		#写入解压长度
		data = bytearray(data)
		data = align(data)
		bs = int.to_bytes(len(data), 4, byteorder='little')
		content.append(bs)
		#写入文件
		data = encrypt(data)
		data = compress(data)
		content.append(data)
		#写入索引
		bs = bytearray()
		name = filename.encode('cp932')
		bs.append(len(name))
		bs.extend(name)
		if filename in IndexBytesDic:
			bs.extend(IndexBytesDic[filename])
		else:
			bs.extend(BytesAfterName)
		size = int.to_bytes(len(data)+4, 4, byteorder='little')
		offset = int.to_bytes(addr, 4, byteorder='little')
		bs.extend(size)
		bs.extend(offset)
		indexSection.extend(bs)
		addr += 4 + len(data)
	#写入index
	#indexSection.extend(b'\0\0')
	content.append(indexSection)
	countSection = int.to_bytes(len(indexSection), 4, byteorder='little')
	content.append(countSection)
	write()

def compress(data):
	#压缩
	data = lz_fake(data)
	return data

def encrypt(data):
	#加密
	for i in range(len(data)):
		data[i] ^= 0x42
	return data

def align(data):
	padding = 8 - len(data) % 8
	data.extend(b' ' * padding)
	return data

def lz_fake(data):
	output = io.BytesIO()
	for i in range(0, len(data), 8): #需要8字节对齐
		output.write(b'\x00')
		output.write(data[i:i+8])
	#添加结束字节
	output.write(b'\xFF')
	output.write(b'\x00\x00')
	return output.getvalue()

# ------------------------------------------------------------
def write():
	#path = os.path.join(dirpath, '..')
	# if not os.path.exists(path):
	# 	os.makedirs(path)
	name = ArcNew
	filepath = os.path.join(dirpath, CtrlDir, name)
	fileNew = open(filepath, 'wb')
	fileNew.writelines(content)
	fileNew.close()
	print(f'Write done: {name}')

#广度优先，系统排序
file_list = []
root_path = ''
def listFiles(dirpath):
	files = []
	path = os.path.join(dirpath, CtrlDir, ArcOld)
	if os.path.isfile(path):
		#读取原始包
		f = open(path, 'rb')
		data = f.read()
		f.close()
		indexSize = int.from_bytes(data[-4:], byteorder='little')
		pos = len(data) - 4 - indexSize
		while (pos < len(data) - 4):
			nameLen = data[pos]
			pos += 1
			filename = data[pos:pos+nameLen].decode('cp932')
			pos += nameLen
			bytesAfterName = data[pos:pos+6]
			pos += 6
			pos += 8 #size & offset
			#加入到额外字节的字典
			IndexBytesDic[filename] = bytesAfterName
			filepath = os.path.join(dirpath, filename)
			if os.path.isfile(filepath):
				files.append(filename)
	else:
		for filename in os.listdir(dirpath):
			filepath = os.path.join(dirpath, filename)
			if os.path.isfile(filepath):
				files.append(filename)
	return files
	
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