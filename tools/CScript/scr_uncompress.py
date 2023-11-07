# ------------------------------------------------------------
# https://github.com/satan53x/SExtractor/tree/main/tools/CScript
# 解压和压缩，根据头部定义压缩长度和实际文件长度判断
# ------------------------------------------------------------
import io
import re
import sys
import os
import json
from tkinter import filedialog
#import lzss
#from lzss_s import decode, encode
import lzss_s
DefaultPath = ''
EncodeName = 'utf-8'
Postfix = ''

# ------------------------------------------------------------
#var
dirpath = ''
filename = '' 

content = []
# ------------------------------------------------------------
def uncomFile():
	global EncodeName
	global content
	#print(filename)
	filepath = os.path.join(dirpath, filename+Postfix)
	fileOld = open(filepath, 'rb')
	data = fileOld.read()
	fileOld.close()
	#处理
	pos = 12
	comSize = int.from_bytes(data[pos:pos+4], byteorder='little')
	pos += 4
	uncomSize = int.from_bytes(data[pos:pos+4], byteorder='little')
	pos += 4
	content = [bytearray(data[0:pos])]
	#判断是解压还是压缩
	#lzss = LZSS(12)
	if len(data) - pos == comSize:
		#解压
		com = data[pos:pos+comSize]
		uncom = bytearray(uncomSize)
		uncomSize = lzss_s.decompress(uncom, com)
		uncom = uncom[0:uncomSize]
		content.append(uncom)
		#修正长度
		content[0][16:20] = int.to_bytes(len(uncom), 4, byteorder='little')
		print(f'解压: {filename}, {uncomSize}')
	else:
		#压缩
		uncomSize = len(data) - pos
		uncom = data[pos:pos+uncomSize]
		com = bytearray(uncomSize) #按最大
		comSize = lzss_s.compress(com, uncom)
		com = com[0:comSize]
		content.append(com)
		#修正长度
		content[0][12:16] = int.to_bytes(len(com), 4, byteorder='little')
		content[0][16:20] = int.to_bytes(uncomSize, 4, byteorder='little')
		print(f'压缩: {filename}, {comSize}')
	write()

# ------------------------------------------------------------
def write():
	path = os.path.join(dirpath, 'new')
	if not os.path.exists(path):
		os.makedirs(path)
	name = filename
	filepath = os.path.join(path, name+Postfix)
	fileNew = open(filepath, 'wb')
	fileNew.writelines(content)
	fileNew.close()
	#print(f'Write done: {name}')

def main():
	path = DefaultPath
	if len(sys.argv) < 2:
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
				uncomFile()
				#break

main()