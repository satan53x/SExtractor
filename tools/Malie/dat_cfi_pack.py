# ------------------------------------------------------------
# https://github.com/satan53x/SExtractor/tree/main/tools/Malie
# 依赖模块 tqdm
# ------------------------------------------------------------
import sys
import os
from tkinter import filedialog
from tqdm import tqdm
DefaultPath = ''
PackName = 'new.dat'
GameType = 30 #见脚本末尾
IfEncrypt = True

# ------------------------------------------------------------
#var
dirpath = ''
filenameList = [] 
content = []

BlockLen = 0x10

config = None
indexSection = []
offsetSection = []
fileSection = []
indexSeq = 0

def test():
	filepath = os.path.join(dirpath, 'tmp.dat')
	fileOld = open(filepath, 'rb')
	data = fileOld.read()
	fileOld.close()
	data = encrypt(bytearray(data), 0)
	global content
	content = [data]

# ------------------------------------------------------------
def pack():
	indexSection.clear()
	offsetSection.clear()
	fileSection.clear()
	#遍历
	print('Indexing...')
	root = Index('', 0)
	indexSection.append(root)
	traverse(dirpath, root)
	#写入
	#head
	output = bytearray(0x10)
	output[0:4] = 'LIBP'.encode('cp932')
	output[4:8] = len(indexSection).to_bytes(4, byteorder='little')
	output[8:12] = len(offsetSection).to_bytes(4, byteorder='little')
	#index
	for index in indexSection:
		output.extend(index.data)
	#offset
	offsetAddr = len(output)
	for offset in offsetSection:
		offset.addr = offsetAddr
		output.extend(offset.data)
		offsetAddr = len(output)
	fillingAlign(output)
	#file
	fileAddr = len(output)
	fileStart = fileAddr
	for file in fileSection:
		#修正offset
		file.offset.set(fileAddr - fileStart, output)
		output.extend(file.data)
		fillingAlign(output)
		fileAddr = len(output)
	#生成
	#test()
	global content
	if IfEncrypt:
		print(f'Encrypting... Each line\'s bytes: 0x{BlockLen:x}')
		output = encrypt(output)
		print('Encrypted.')
	content = [output]
	write()

def traverse(path, index):
	#文件
	if os.path.isfile(path):
		file = File(path)
		index.set(0x1, file.seq, len(file.data))
		return
	# 获取文件夹中的所有文件和子文件夹
	children = os.listdir(path)
	children = sorted(children)
	if len(children) == 0:
		index.set(0, 0, 0)
		print('\033[31m文件夹为空：\033[0m', path)
		return
	#先占位
	indexList = []
	for name in children:
		#print('index:', name)
		childIndex = Index(name, len(indexSection))
		indexSection.append(childIndex)
		indexList.append(childIndex)
	#设置当前索引
	index.set(0, indexList[0].indexSeq, len(indexList))
	#后序遍历
	for i, name in enumerate(children):
		pathChild = os.path.join(path, name)
		if os.path.isfile(pathChild): #文件
			traverse(pathChild, indexList[i])
	for i, name in enumerate(children):
		pathChild = os.path.join(path, name)
		if os.path.isdir(pathChild): #目录
			traverse(pathChild, indexList[i])
	return 

def fillingAlign(output):
	size = config['DataAlign']
	remain = len(output) - len(output) // size * size 
	if remain == 0: return
	#填充
	bs = bytes([0x00] * (size - remain))
	output.extend(bs)

def encrypt(data, offset=0):
	enc = EncryptCfi()
	r = range(len(data) // BlockLen)
	for line in tqdm(r, desc="Processing", unit="line"):
		start = line * BlockLen
		end = start + BlockLen
		block = enc.encryptBlock(data[start:end], offset)
		data[start:end] = block
		offset += BlockLen
	return data
# ------------------------------------------------------------
class Index():
	def __init__(self, name, indexSeq) -> None:
		self.data = bytearray(0x20)
		bs = name.encode('cp932')
		self.data[0:len(bs)] = bs
		self.indexSeq = indexSeq
	
	def set(self, flag, seq, count):
		self.data[0x16:0x18] = flag.to_bytes(2, byteorder='little')
		self.data[0x18:0x1C] = seq.to_bytes(4, byteorder='little')
		self.data[0x1C:0x20] = count.to_bytes(4, byteorder='little')

class Offset():
	def __init__(self) -> None:
		self.data = bytearray(4)
		self.addr = 0 #在包里的地址
	
	def set(self, fileAddr, output):
		i = fileAddr // config['DataAlign']
		output[self.addr:self.addr+4] = i.to_bytes(4, byteorder='little')

class File():
	def __init__(self, path) -> None:
		fileOld = open(path, 'rb')
		self.data = fileOld.read()
		fileOld.close()
		self.name = os.path.basename(path)
		self.seq = len(fileSection)
		fileSection.append(self)
		self.offset = Offset()
		offsetSection.append(self.offset)

# ------------------------------------------------------------
class EncryptCfi():
	def encryptBlock(self, block, offset):
		#位移
		data32 = [0,0,0,0]
		for i in range(4):
			data32[i] = int.from_bytes(block[i*4:(i+1)*4], byteorder='little')
		offset >>= 4
		self.rotateEnc(data32, offset, config['RotateKey'], config['Key'])
		for i in range(4):
			block[i*4:(i+1)*4] = data32[i].to_bytes(4, byteorder='little')
		#异或
		first = block[0]
		for i in range(1, BlockLen):
			block[i] ^= first
		return block

	def rotateEnc(self, data32, offset, rotateKey, key):
		k = rotateRight(rotateKey[0], key[offset & 0x1F] ^ 0xA5)
		data32[0] = rotateLeft(data32[0], key[(offset + 12) & 0x1F] ^ 0xA5) ^ k
		k = rotateLeft(rotateKey[1], key[(offset + 3) & 0x1F] ^ 0xA5)
		data32[1] = rotateRight(data32[1], key[(offset + 15) & 0x1F] ^ 0xA5) ^ k
		k = rotateRight(rotateKey[2], key[(offset + 6) & 0x1F] ^ 0xA5)
		data32[2] = rotateLeft(data32[2], key[(offset - 14) & 0x1F] ^ 0xA5) ^ k
		k = rotateLeft(rotateKey[3], key[(offset + 9) & 0x1F] ^ 0xA5)
		data32[3] = rotateRight(data32[3], key[(offset - 11) & 0x1F] ^ 0xA5) ^ k

BitLen = 32
ValueMask = (1 << BitLen) - 1
def rotateRight(value, shift):
	value = (value >> shift) | (value << (BitLen - shift)) 
	return value & ValueMask

def rotateLeft(value, shift):
	value = (value << shift) | (value >> (BitLen - shift)) 
	return value & ValueMask

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

def listFiles(start_path):
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
	global dirpath, config
	config = GameConfig[GameType]
	if os.path.isdir(path):
		dirpath = path
		files = listFiles(path)
		filenameList.extend(files)
		pack()

# ------------------------------------------------------------
GameConfig = { # From Garbro
	30 : {
		'DataAlign' : 0x400,
		'Key' : bytes.fromhex('a4 a7 a6 a1 a0 a3 a2 ac af ae a9 a8 ab aa b4 b7 b6 b1 b0 b3 b2 bc bf be b9 b8 bb ba a1 a9 b1 b9'),
		'RotateKey' : [0x79404664, 0x772d7635, 0x346b7230, 0x6e7e7935],
	}
}

main()