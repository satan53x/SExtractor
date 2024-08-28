# ------------------------------------------------------------
# https://github.com/satan53x/SExtractor/tree/main/tools/AZSystem
# ------------------------------------------------------------
import sys
import os
from tkinter import filedialog
import zlib 
DefaultPath = ''
Postfix = '.asb'
InitKey = 0x9E370001

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
	pos += 8
	com = data[pos:]
	uncom = bytearray(uncomSize)
	com = decryptData(com, uncom)
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