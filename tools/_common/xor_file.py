# ------------------------------------------------------------
# 
# ------------------------------------------------------------
import sys
import os
import shutil
from tkinter import filedialog 
DefaultPath = ''
XorKey = b'\xFF' # 异或密钥，字节数不限

# ------------------------------------------------------------
#var
dirpath = ''
filename = '' 

# ------------------------------------------------------------
def xor():
	filepath = os.path.join(dirpath, filename)
	with open(filepath, 'rb') as f:
		data = f.read()
		xored_data = bytearray(len(data))
		keyIndex = 0
		for i, byte in enumerate(data):
			xored_data[i] = byte ^ XorKey[keyIndex]
			keyIndex = (keyIndex + 1) % len(XorKey)
		write(xored_data)

# ------------------------------------------------------------
def write(data):
	path = os.path.join(dirpath, 'new')
	if not os.path.exists(path):
		os.makedirs(path)
	name = filename
	filepath = os.path.join(path, name)
	fileNew = open(filepath, 'wb')
	fileNew.write(data)
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
	global dirpath, filename
	if os.path.isdir(path):
		dirpath = path
		for name in os.listdir(dirpath):
			#print(name)
			filepath = os.path.join(dirpath, name)
			if os.path.isfile(filepath):
				filename = name
				xor()

main()