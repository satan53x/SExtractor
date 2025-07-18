# ------------------------------------------------------------
# https://github.com/satan53x/SExtractor/tree/main/tools/Ransel
# ------------------------------------------------------------
import sys
import os
from tkinter import filedialog
DefaultPath = ''
Encoding = 'cp932'
PackName = 'text' #必须和实际包名一致
ContentPostfix = '.bcd' 
IndexPostfix = '.bcl'

# ------------------------------------------------------------
#var
dirpath = ''
filenameList = [] 
content = []
# ------------------------------------------------------------
def pack():
	#头部
	contentData = bytearray(b'BinaryCombineData\0')
	indexData = [
		'[BinaryCombineData]', 
		f'{PackName}{ContentPostfix}', 
		''
	]
	#pack
	addr = len(contentData)
	for i, filename in enumerate(filenameList):
		print('Packing:', filename)
		filepath = os.path.join(dirpath, filename)
		fileOld = open(filepath, 'rb')
		data = fileOld.read()
		fileOld.close()
		#内容
		contentData.extend(data)
		#索引
		length = len(data)
		indexData.append(f'[{filename}]') #子文件名
		indexData.append(str(addr)) #子文件地址
		indexData.append(str(length)) #子文件长度
		indexData.append('')
		#单文件完成
		addr += length
	#输出内容
	global content
	content = [contentData]
	write()
	#输出索引
	content = indexData
	write()

# ------------------------------------------------------------
def write():
	path = os.path.dirname(dirpath)
	if not os.path.exists(path):
		os.makedirs(path)
	if len(content) == 1:
		#content file
		filepath = os.path.join(path, PackName + ContentPostfix)
		fileNew = open(filepath, 'wb')
		fileNew.writelines(content)
		fileNew.close()
	else:
		#index file
		filepath = os.path.join(path, PackName + IndexPostfix)
		fileNew = open(filepath, 'w', encoding=Encoding)
		for i, line in enumerate(content):
			fileNew.write(line)
			fileNew.write('\n')
		fileNew.close()
	print(f'Write done: {filepath}')

def get_files(start_path):
	file_list = os.listdir(start_path)
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
	global dirpath, filenameList
	if os.path.isdir(path):
		dirpath = path
		files = get_files(dirpath)
		for name in files:
			filenameList.append(name)
		pack()
main()