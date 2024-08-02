# ------------------------------------------------------------
# https://github.com/satan53x/SExtractor/tree/main/tools/EmonEngine
# 仅用于剧本打包，不能处理图片音频等资源
# ------------------------------------------------------------
import sys
import os
import lzss_s
from tkinter import filedialog
DefaultPath = ''
CtrlDir = '../..' #控制目录相对路径，需要放入原始eme文件
ArcOld = 'BKscene.eme'
ArcNew = 'BKscene.new.eme'
FilenamesTxt = 'filenames.txt' #如果有文件列表txt，优先使用txt内容
IndexLen = 0x60 #单个索引长度

# ------------------------------------------------------------
#var
dirpath = ''
filenameList = [] 
content = []

class Arc:
	def __init__(self):
		#旧
		print(f'Read old archive: {ArcOld}')
		path = os.path.join(dirpath, CtrlDir, ArcOld)
		f = open(path, 'rb')
		dataOld = f.read()
		f.close()
		self.arcHeadSec = dataOld[0:8] #文件头
		self.filesSec = [] #子文件区
		count = int.from_bytes(dataOld[-4:], 'little')
		indexAddr = len(dataOld) - 4 - count * IndexLen
		self.keySec = dataOld[indexAddr-0x28:indexAddr] #密钥区
		#新
		self.keySec = bytearray(0x28) #全0，等效于不加密
		self.count = len(filenameList)
		self.indexSec = [] #索引区
		self.countSec = int.to_bytes(self.count, 4, 'little') #个数区

	def pack(self):
		addr = len(self.arcHeadSec)
		print('子文件数量:', self.count)
		for i, filename in enumerate(filenameList):
			#print(filename)
			filepath = os.path.join(dirpath, filename)
			f = open(filepath, 'rb')
			uncom = f.read()
			f.close()
			#文件头
			head = bytearray(0xC) #全0
			head = self.encrypt(head) #加密
			#压缩文件
			uncomSize = len(uncom)
			com = bytearray(uncomSize + 0x200) #按最大
			comSize = lzss_s.compress(com, uncom)
			com = com[0:comSize]
			self.filesSec.append(head + com)
			#索引
			index = bytearray(IndexLen) #全0
			name = filename.encode('cp932')
			index[0:len(name)] = name #名字
			index[0x40:0x42] = int.to_bytes(0x1000, 2, 'little') #LzssFrameSize
			index[0x42:0x44] = int.to_bytes(0x12, 2, 'little') #LzssInitPos
			index[0x44:0x48] = int.to_bytes(0x1, 4, 'little') #也许是压缩标志
			index[0x48:0x4C] = int.to_bytes(0x3, 4, 'little') #SubType 3-剧本
			index[0x4C:0x50] = int.to_bytes(comSize, 4, 'little') #压缩后长度
			index[0x50:0x54] = int.to_bytes(uncomSize, 4, 'little') #未压缩长度
			index[0x54:0x58] = int.to_bytes(addr, 4, 'little') #起始地址
			index = self.encrypt(index) #加密
			self.indexSec.append(index)
			#地址增加
			addr += len(head) + comSize
		#合并
		self.filesSec = b''.join(self.filesSec)
		self.indexSec = b''.join(self.indexSec)

	def encrypt(self, data):
		# keySec全0则等效于不加密
		return data

# ------------------------------------------------------------
def pack():
	arc = Arc() #从旧文件初始化：读取文件头和密钥
	arc.pack()
	global content
	content = [arc.arcHeadSec, arc.filesSec, arc.keySec, arc.indexSec, arc.countSec]
	write()

# ------------------------------------------------------------
def write():
	path = os.path.join(dirpath, CtrlDir)
	name = ArcNew
	filepath = os.path.join(path, name)
	fileNew = open(filepath, 'wb')
	fileNew.writelines(content)
	fileNew.close()
	print(f'Write done: {name}')

def get_files():
	files = []
	path = os.path.join(dirpath, CtrlDir, FilenamesTxt)
	if os.path.isfile(path):
		f = open(path, 'r', encoding= 'utf-8')
		for line in f.readlines():
			line = line.strip()
			if len(line) > 0:
				files.append(line)
	else:
		for filename in os.listdir(dirpath):
			filepath = os.path.join(dirpath, filename)
			if os.path.isfile(filepath):
				files.append(filename)
	return files

def main():
	path = DefaultPath
	if len(sys.argv) < 2:
		path = filedialog.askdirectory(initialdir=path)
	else:
		path = sys.argv[1]
	#print(path)
	global dirpath, filenameList
	filenameList.clear()
	if os.path.isdir(path):
		dirpath = path
		#print(dirpath)
		filenameList = get_files()
		pack()
main()