# ------------------------------------------------------------
# https://github.com/satan53x/SExtractor/tree/main/tools/Tanaka
# ------------------------------------------------------------
import sys
import os
from tkinter import filedialog
DefaultPath = ''
Dirname = '' #需要打包的文件夹，为空则表示与包名相同
Postfix = '.SCB'

# ------------------------------------------------------------
#var
class var:
	arcpath = ''
	subfile_dirpath = ''
	subfile_list = []
	content = []
	out_dirpath = ''
	out_name = ''
# ------------------------------------------------------------
def pack():
	#包
	file = open(var.arcpath, 'rb')
	data = file.read()
	file.close()
	new_data = bytearray()
	#头部
	pos = 0x1C #索引区地址的地址
	index_sec_addr = int.from_bytes(data[pos:pos+4], 'little')
	pos = index_sec_addr
	new_data.extend(data[:pos]) #索引区之前使用旧包数据
	#索引区，保持原始大小不变，因为子文件个数不变
	addr_list = []
	first_addr = len(data)
	while True:
		index_addr = pos
		addr = int.from_bytes(data[pos:pos+4], 'little')
		if addr == 0:
			break
		pos += 4
		length = data[pos]-1
		pos += 1
		name = data[pos:pos+length]
		name = name.rstrip(b'\x00').decode('cp932')
		pos += length
		addr_list.append([addr, name, index_addr])
		if first_addr > addr:
			first_addr = addr
	addr_list.append([len(data), '', 0])
	new_data.extend(data[index_sec_addr:first_addr]) #第一个子文件之前先填充为旧索引区
	#遍历子文件
	for i in range(len(addr_list)-1):
		start, name, index_addr = addr_list[i]
		end = addr_list[i+1][0]
		new_start = len(new_data)
		if name in var.subfile_list:
			#存在独立文件
			file = open(os.path.join(var.subfile_dirpath, name), 'rb')
			new_data.extend(file.read())
			file.close()
			print('Replace:', name)
		else:
			#从原始包中读取
			new_data.extend(data[start:end])
		#修正索引
		new_data[index_addr:index_addr+4] = new_start.to_bytes(4, 'little')
	#导出
	var.content = [new_data]
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
		path = filedialog.askopenfilename(initialfile=path, title=f'请选择原始{Postfix}文件，默认需要封包的文件所在目录与原始包同名')
	else:
		path = sys.argv[1]
	#print(path)
	if os.path.isfile(path):
		var.arcpath = path
		parent_dirpath = os.path.dirname(path)
		if Dirname:
			arcname = Dirname
		else:
			arcname, _ = os.path.splitext(os.path.basename(path))
		var.out_dirpath = os.path.join(parent_dirpath, 'new') 
		var.out_name = arcname + Postfix
		var.subfile_dirpath = os.path.join(parent_dirpath, arcname)
		if not os.path.isdir(var.subfile_dirpath):
			print(f'Not found folder: {var.subfile_dirpath}')
			return
		for filename in os.listdir(var.subfile_dirpath):
			filepath = os.path.join(var.subfile_dirpath, filename)
			if os.path.isfile(filepath):
				var.subfile_list.append(filename)
		pack()
main()