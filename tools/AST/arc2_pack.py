# ------------------------------------------------------------
# https://github.com/satan53x/SExtractor/tree/main/tools/AST
# 依赖模块：pip install pylzss
# ------------------------------------------------------------
import sys
import os
from tkinter import filedialog
import lzss # 模块 pylzss
DefaultPath = ''
Postfix = ''
Version = 2 #版本号
IfCompress = True
PackName = 'dat_new'

# ------------------------------------------------------------
#var
dirpath = ''
filenameList = [] 
content = []

# ------------------------------------------------------------
def pack():
	#签名和子文件个数
	signatureSection = bytearray(8)
	signatureSection[0:4] = f'ARC{Version}'.encode('ascii')
	signatureSection[4:8] = int.to_bytes(len(filenameList), 4, byteorder='little')
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
		bs = bytearray(4) #预留偏移
		bs.extend(int.to_bytes(len(data), 4, byteorder='little')) #文件长度（未压缩）
		name = filename.encode('cp932') #名字
		bs.append(len(name)) #名字长度,单字节
		if Version == 2:
			name = xorBytes(name, b'\xFF') #加密
		bs.extend(name)
		indexSection.append(bs)
		indexLen += len(bs)
		#附加文件
		data = xorBytes(data, b'\xFF') #加密
		if IfCompress:
			data = lzss.compress(bytes(data)) #压缩
		fileSection.append(data)
	#修正偏移
	offset = len(signatureSection) + indexLen
	for i, filename in enumerate(filenameList):
		indexSection[i][0:4] = int.to_bytes(offset, 4, byteorder='little')
		offset += len(fileSection[i])
	#合并
	global content
	content = [
		signatureSection, 
		bytes().join(indexSection), 
		bytes().join(fileSection)
	]
	write()

def xorBytes(input, xorTable):
	if not xorTable:
		return bytearray(input)
	result = bytearray()
	xorLen = len(xorTable)
	for i, b in enumerate(input):
		xorByte = xorTable[i % xorLen]
		result.append(b ^ xorByte)
	return result

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