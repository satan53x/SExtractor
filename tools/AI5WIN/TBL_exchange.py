# ------------------------------------------------------------
# https://github.com/satan53x/SExtractor/tree/main/tools/AI5WIN
# ------------------------------------------------------------
import sys
import os
from tkinter import filedialog
DefaultPath = ''
Postfix = '.TBL'

# ------------------------------------------------------------
#var
class var:
	dirpath = ''
	filepath = ''
	content = []
	out_dirpath = ''
	out_name = ''
# ------------------------------------------------------------
def exchange():
	file = open(var.filepath, 'rb')
	data = file.read()
	file.close()
	#头部
	data = bytearray(data)
	for i in range(0, len(data), 2):
		tmp = data[i]
		data[i] = data[i + 1]
		data[i + 1] = tmp
	var.content = [data]
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
		var.out_dirpath = os.path.join(var.dirpath, 'new')
		#print(dirpath)
		for filename in os.listdir(var.dirpath):
			filepath = os.path.join(var.dirpath, filename)
			if not os.path.isfile(filepath):
				continue
			if not filename.endswith(Postfix):
				continue
			var.filepath = filepath
			var.out_name = filename
			exchange()
main()