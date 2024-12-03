# ------------------------------------------------------------
# https://github.com/satan53x/SExtractor/tree/main/tools/SystemC
# 伪压缩，不推荐用于大容量压缩包
# ------------------------------------------------------------
import sys
import os
from tkinter import filedialog
DefaultPath = ''
PackName = 'Chip.fpk'
NameLen = 0x18

# ------------------------------------------------------------
#var
dirpath = ''
filenameList = [] 

content = []
# ------------------------------------------------------------
def pack():
	global content
	content = []
	#头部
	countSection = bytearray(4) #个数
	content.append(countSection)
	countSection[0:4] = int.to_bytes(len(filenameList), 4, byteorder='little')
	#
	indexLen = (8 + NameLen) * len(filenameList)
	indexSection = []
	content.append(indexSection)
	offset = len(countSection) + indexLen
	for i, filename in enumerate(filenameList):
		print('Packing:', filename)
		filepath = os.path.join(dirpath, filename)
		fileOld = open(filepath, 'rb')
		data = fileOld.read()
		fileOld.close()
		#压缩
		uncomSize = len(data)
		data = compress(data, len(data))
		comSize = len(data)
		#索引
		dataHeader = bytearray()
		dataHeader.extend(int.to_bytes(offset, 4, byteorder='little')) #子文件偏移
		dataHeader.extend(int.to_bytes(comSize, 4, byteorder='little')) #压缩后长度
		nameBytes = bytearray(NameLen)
		name = filename.encode('cp932')
		nameBytes[0:len(name)] = name
		dataHeader.extend(nameBytes) #文件名
		#添加索引
		indexSection.append(dataHeader)
		#添加内容
		bs = bytearray()
		bs.extend(b'ZLC2')
		bs.extend(int.to_bytes(uncomSize, 4, byteorder='little')) #未压缩长度
		bs.extend(data)
		content.append(bs)
		offset += len(content[-1])
	#完成索引
	content[1] = b''.join(indexSection)
	write()

def compress(input, inputLen):
	output = bytearray()
	pos = 0
	while pos < inputLen:
		ctrl = 0
		count = 8
		tmp = b''
		if pos >= inputLen:
			break
		if pos + count > inputLen:
			count = inputLen - pos
		tmp = input[pos:pos+count]
		pos += count
		output.extend(ctrl.to_bytes(1))
		output.extend(tmp)
	return output

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
			filename = name
			filenameList.append(filename)
		pack()
main()