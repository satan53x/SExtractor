# ------------------------------------------------------------
# https://github.com/satan53x/SExtractor/tree/main/tools/Tanaka
# ------------------------------------------------------------
import sys
import os
from tkinter import filedialog
DefaultPath = ''
Postfix = '.SCB'

# ------------------------------------------------------------
#var
class var:
	dirpath = ''
	filepath = ''
	content = []
	out_dirpath = ''
	out_name = ''
# ------------------------------------------------------------
def unpack():
	file = open(var.filepath, 'rb')
	data = file.read()
	file.close()
	#头部
	pos = 0x1C #索引区地址的地址
	pos = int.from_bytes(data[pos:pos+4], 'little')
	#索引区
	addr_list = []
	while True:
		addr = int.from_bytes(data[pos:pos+4], 'little')
		if addr == 0:
			break
		pos += 4
		length = data[pos]-1
		pos += 1
		name = data[pos:pos+length]
		name = name.rstrip(b'\x00').decode('cp932')
		pos += length
		addr_list.append([addr, name])
	addr_list.append([len(data), ''])

	#遍历子文件
	for i in range(len(addr_list)-1):
		start = addr_list[i][0]
		end = addr_list[i+1][0]
		var.out_name = addr_list[i][1]
		var.content = [data[start:end]]
		#导出
		write()

# ------------------------------------------------------------
def write():
	path = var.out_dirpath
	if not os.path.exists(path):
		os.makedirs(path)
	filepath = os.path.join(path, var.out_name)
	fileNew = open(filepath, 'wb')
	fileNew.writelines(var.content)
	fileNew.close()
	print(f'Write done: {var.out_name}')

def main():
	path = DefaultPath
	if path:
		pass
	elif len(sys.argv) < 2:
		path = filedialog.askdirectory(initialdir=path)
	else:
		path = sys.argv[1]
	#print(path)
	if os.path.isdir(path):
		var.dirpath = path
		#print(dirpath)
		for filename in os.listdir(var.dirpath):
			#print(name)
			name, post = os.path.splitext(filename)
			if post.lower() != Postfix.lower():
				continue
			var.filepath = os.path.join(var.dirpath, filename)
			var.out_dirpath = os.path.join(var.dirpath, name)
			unpack()
main()