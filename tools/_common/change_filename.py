# ------------------------------------------------------------
# 一些不封包的日文资源在中文系统环境下
# 不转区运行的话，文件需要重命名为乱码才能正常读取
# ------------------------------------------------------------
import sys
import os
import shutil
from tkinter import filedialog 
DefaultPath = ''
Postfix = ''
OldEncode = 'cp932'
NewEncode = 'gbk'

# ------------------------------------------------------------
#var
dirpath = ''
filename = '' 

# ------------------------------------------------------------
def change():
	try:
		bs = filename.encode(OldEncode)
		newname = bs.decode(NewEncode)
	except Exception as e:
		print(e)
		return
	oldpath = os.path.join(dirpath, filename)
	newpath = os.path.join(dirpath, 'new', newname)
	os.makedirs(os.path.join(dirpath, 'new'), exist_ok=True)
	shutil.copy(oldpath, newpath)

# ------------------------------------------------------------
def write():
	pass

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
		for name in os.listdir(dirpath):
			#print(name)
			filename = name
			change()

main()