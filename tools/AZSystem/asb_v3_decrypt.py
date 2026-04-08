# ------------------------------------------------------------
# https://github.com/satan53x/SExtractor/tree/main/tools/AZSystem
# ------------------------------------------------------------
import sys
import os
from tkinter import filedialog
import zlib 
DefaultPath = ''
Postfix = '.asb'
InitKey = 0xAF20179F

# ------------------------------------------------------------
#var
dirpath = ''
filename = ''

content = []
# ------------------------------------------------------------
def decryptFile():
	#print(filename)
	filepath = os.path.join(dirpath, filename+Postfix)
	fileOld = open(filepath, 'rb')
	data = fileOld.read()
	fileOld.close()
	#处理
	pos = 4
	comSize = int.from_bytes(data[pos:pos+4], byteorder='little')
	pos += 4
	uncomSize = int.from_bytes(data[pos:pos+4], byteorder='little')
	pos += 4
	#crc和com需要一起进行解密
	crc_com = data[pos:]
	uncom = bytearray(uncomSize)
	crc_com = decryptData(crc_com, uncom)
	crc = int.from_bytes(crc_com[0:4], byteorder='little')
	#print(f'crc: {crc:08X}')
	com = crc_com[4:]
	uncom = zlib.decompress(com)
	if len(uncom) != uncomSize:
		print('Decompress Error:', filename)
		return
	#导出
	content.clear()
	header = data[0:16]
	content.append(header)
	content.append(uncom)
	write()

def decryptData(com, uncom):
	com = bytearray(com)
	key = len(uncom) ^ InitKey
	key = (((key | (key << 12)) << 11) ^ key) & 0xFFFFFFFF
	for pos in range(0, len(com)//4*4, 4):
		d = int.from_bytes(com[pos:pos+4], byteorder='little')
		d = (d - key) % 0x100000000
		bs = int.to_bytes(d, 4, byteorder='little')
		com[pos:pos+4] = bs
	return com

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
	print(f'Write done: {name}')

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
				decryptFile()
				#break

main()