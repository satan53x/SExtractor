# ------------------------------------------------------------
# https://github.com/satan53x/SExtractor/tree/main/tools/BlackRainbow
# ------------------------------------------------------------
import sys
import os
from tkinter import filedialog
DefaultPath = ''
Postfix = ''
BytesDatSig = b'\x05\x00\x00\x00\x0A\x55\xDC\xA2' #Version和有效标志


# ------------------------------------------------------------
#var
dirpath = ''
filenameList = [] 

content = []
# ------------------------------------------------------------
def pack():
	indexSection = bytearray(8) #个数和偏移
	global content
	content = [ BytesDatSig, indexSection]
	offset = 0
	for i, filename in enumerate(filenameList):
		#print(filename)
		filepath = os.path.join(dirpath, filename+Postfix)
		fileOld = open(filepath, 'rb')
		data = fileOld.read()
		fileOld.close()
		#附加内容
		dataHeader = bytearray(filename.encode('cp932')) #子文件名
		padLen = 0x20 - len(dataHeader)
		if padLen > 0:
			dataHeader += bytearray(padLen)
		else:
			print('文件名过长', filename)
			return
		dataHeader += int.to_bytes(len(data), 4, byteorder='little') #子文件长度
		content.append(dataHeader + data)
		#添加索引
		indexSection.extend(int.to_bytes(offset, 4, byteorder='little'))
		offset += len(content[-1])
	#完成索引
	indexSection[0:4] = int.to_bytes(len(filenameList), 4, byteorder='little')
	indexSection[4:8] = int.to_bytes(len(BytesDatSig)+len(indexSection), 4, byteorder='little')
	write()

# ------------------------------------------------------------
def write():
	path = os.path.join(dirpath, 'new')
	if not os.path.exists(path):
		os.makedirs(path)
	name = 'script.dat'
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