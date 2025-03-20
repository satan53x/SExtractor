# ------------------------------------------------------------
# 加密dataXXXX图片的bmp
# https://github.com/satan53x/SExtractor/tree/main/tools/Valkyria
# ------------------------------------------------------------
import sys
import os
from tkinter import filedialog
DefaultPath = 'data01'
Postfix = '.bmp'
PixelByteSize = 4
BmpHeadLen = 0x36

# ------------------------------------------------------------
#var
dirpath = ''
filename = '' 

content = []
# ------------------------------------------------------------
def handle():
	global content
	#print(filename)
	filepath = os.path.join(dirpath, filename+Postfix)
	fileOld = open(filepath, 'rb')
	data = fileOld.read()
	fileOld.close()
	#处理
	header = data[0:BmpHeadLen]
	newdata = compress(data[BmpHeadLen:])
	content = []
	content.append(newdata)
	write()

def compress(data):
	newdata = bytearray()
	ctrl = 0
	ctrlBit = 0
	ctrlPos = 0
	newdata.append(0) #ctrl占位
	count = 0
	for pos in range(0, len(data), PixelByteSize):
		now = data[pos:pos+PixelByteSize]
		count += 1
		if pos < len(data)-PixelByteSize:
			next = data[pos+PixelByteSize:pos+PixelByteSize*2]
		else:
			next = b''
		if now != next or count >= 0xFFFF or ctrlBit >= 7:
			#不一样，写人数据
			newdata.extend(now)
			if count > 1:
				bs = int.to_bytes(count-1, 2, 'big')#写入比实际少
				newdata.extend(bs)
				ctrl += 1 << ctrlBit
			else:
				ctrl += 0 << ctrlBit
			#重置
			ctrlBit += 1
			count = 0
			if ctrlBit >= 8 or next == b'':
				#同步到ctrl占位
				newdata[ctrlPos] = ctrl
				ctrl = 0
				ctrlBit = 0
				if pos < len(data)-PixelByteSize:
					newdata.append(0)
					ctrlPos = len(newdata)-1
	return newdata

# ------------------------------------------------------------
def write():
	path = os.path.join(dirpath, 'new')
	if not os.path.exists(path):
		os.makedirs(path)
	name = filename
	filepath = os.path.join(path, name)
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
	global filename
	if os.path.isdir(path):
		dirpath = path
		#print(dirpath)
		for name in os.listdir(dirpath):
			#print(name)
			filename = name.replace(Postfix, '')
			filepath = os.path.join(dirpath, filename+Postfix)
			if os.path.isfile(filepath):
				#print(filepath)
				handle()
				#break

main()