# ------------------------------------------------------------
# https://github.com/satan53x/SExtractor/tree/main/tools/Unity
# 用于GameFramework的DataTable解压
# table结构为开发者自定义，不通用，需要自行添加RowTypeDic
# read_7bit_encoded_int()函数也可能需要自行修改
# ------------------------------------------------------------
import csv
import io
import json
import sys
import os
import pandas as pd
from tkinter import filedialog
DefaultPath = r''
EncodeName = 'utf-8'
BIN = 'bytes'
TXT = 'json' #支持格式：csv, json
IfBin2Txt = True #True: BIN->TXT ; False: TXT->BIN

RowTypeDic = {
	'tbachievement': [ 
		'str', 'int', 'int', 'str', 'int', 'str', 'str', 'str', 
		'dic', 'dic', 'int',
	],
	'tbuitextlanguage': [ 
		'str', 'dic',
	],
	'tbchaptercontent': [
		'int', 'int', 'int', 'lst', 'str', 
		'lst', 'lst', 
		'dic', 'dic', 'dic', 
		'str', 'str',
	],
	'tboptionscontent': [
		'int', 'str', 'str', 'byte9',
		'dic', 
		'lst', 'bytes', 
		'int', 'str', 'str', 'byte6',
	],
	# 'tbwechatcontent': [
	# 	'int', 'int', 'str', 
	# 	'int', 'int', 'str', 'int',
	# 	'str', 'dic', 'int', 'int', 'int',
	# ]
}

# ------------------------------------------------------------
#var
dirpath = ''
filename = '' 
content:pd.DataFrame = None
# ------------------------------------------------------------
def decompress():
	global content
	data = read()
	if not data:
		return
	reader = io.BytesIO(data)
	#处理
	rowCount = read_7bit_encoded_int(reader, 7)
	header = []
	rowConf = RowTypeDic[filename]
	for i, colType in enumerate(rowConf):
		header.append(f'col{i:02}')
	content = pd.DataFrame(columns=header)
	for i in range(rowCount):
		content.loc[i] = read_row(reader, rowConf)
	#生成
	if reader.tell() < len(data):
		print('Doesn\'t reach the end of file:', filename)
	write()

def compress():
	global content
	data = read()
	if (not isinstance(data, pd.DataFrame) and not data) or data.empty:
		return
	content = data
	writer = io.BytesIO()
	#处理
	rowCount = len(content)
	write_7bit_encoded_int(rowCount, writer)
	rowConf = RowTypeDic[filename]
	for i in range(rowCount):
		try:
			wrtite_row(content.loc[i], writer, rowConf)
		except ValueError as e:
			print('ValueError:', filename, i)
		except Exception as e:
			raise e
	#生成
	content = writer.getvalue()
	write()

# ------------------------------------------------------------
def read_row(reader, rowConf):
	row = []
	for i, colType in enumerate(rowConf):
		if colType == 'str':
			data = read_string(reader)
		elif colType == 'dic':
			data = read_dic(reader)
		elif colType == 'lst':
			data = read_lst(reader)
		elif colType.startswith('byte'):
			if colType[4] == 's':
				length = -1
			else:
				length = int(colType[4:])
			data = read_bytes(reader, length)
		else:
			data = read_7bit_encoded_int(reader)
		if colType in ['dic', 'lst']:
			if TXT in ['csv']: #不支持嵌套的txt格式
				data = json.dumps(data, ensure_ascii=False)
		row.append(data)
	return row

def read_7bit_encoded_int(reader, max=7):
	value = 0
	shift = 0
	while True:
		b = reader.read(1)[0]
		if shift >= max or (b & 0x80) == 0:
			value <<= 8
			value += b
			break
		value <<= 7
		value += b & 0x7f
		shift += 7
	return value

def read_string(reader):
	length = read_7bit_encoded_int(reader)
	if length == 0:
		return ""
	bs =  reader.read(length)
	s = bs.decode(EncodeName)
	return s

def read_dic(reader):
	dic_count = read_7bit_encoded_int(reader)
	if dic_count == 0:
		return {}
	dic = {}
	for i in range(dic_count):
		key = read_7bit_encoded_int(reader)
		val = read_string(reader)
		dic[key] = val
	return dic

def read_lst(reader):
	lst_count = read_7bit_encoded_int(reader)
	if lst_count == 0:
		return []
	lst = []
	for i in range(lst_count):
		val = read_string(reader)
		lst.append(val)
	return lst

def read_bytes(reader, length=-1):
	if length < 0:
		length = reader.read(1)[0] * 8
	bs = reader.read(length)
	return bs.hex()

# ------------------------------------------------------------
def wrtite_row(row, writer, rowConf):
	for i, colType in enumerate(rowConf):
		data = row[i]
		if colType in ['dic', 'lst']:
			if TXT in ['csv']:
				#不支持嵌套的txt格式
				data = json.loads(data)
		if colType == 'str':
			write_string(data, writer)
		elif colType == 'dic':
			write_dic(data, writer)
		elif colType.startswith('byte'):
			if colType[4] == 's':
				length = -1
			else:
				length = int(colType[4:])
			data = write_bytes(data, writer, length)
		elif colType == 'lst':
			write_lst(data, writer)
		else:
			write_7bit_encoded_int(data, writer)


def write_7bit_encoded_int(value, writer, max=7):
	ba = []
	shift = 8
	b = int(value & 0xFF)
	ba.append(b)
	value >>= 8
	while value > 0:
		ba.append(int(value & 0x7F) + 0x80)
		value >>= 7
		shift += 7
		if shift >= max:
			if value > 0:
				print("Error: too long number for compression")
				raise ValueError("too long number for compression")
			break
	if len(ba) == 1 and ba[0] > 0x7F:
		ba.append(0x80)
	for i in reversed(range(len(ba))):
		writer.write(ba[i].to_bytes(1, byteorder="big"))

def write_string(value, writer):
	if pd.isnull(value):
		write_7bit_encoded_int(0, writer)
		return
	bs = value.encode(EncodeName)
	length = len(bs)
	write_7bit_encoded_int(length, writer)
	writer.write(bs)

def write_dic(dic, writer):
	dic_count = len(dic.items())
	write_7bit_encoded_int(dic_count, writer)
	for key, value in dic.items():
		try:
			key = int(key) #key可能是字符串
		except Exception:
			pass
		write_7bit_encoded_int(key, writer)
		write_string(value, writer)

def write_lst(lst, writer):
	lst_count = len(lst)
	write_7bit_encoded_int(lst_count, writer)
	for item in lst:
		write_string(item, writer)

def write_bytes(str, writer, length=-1):
	bs = bytes.fromhex(str)
	if length < 0:
		if len(bs) % 8 != 0:
			print("Error: bytes must be a multiple of 8 bytes.")
			raise ValueError("bytes must be a multiple of 8 bits.")
		b = (len(bs) // 8).to_bytes(1, byteorder="big")
		writer.write(b)
	writer.write(bs)
# ------------------------------------------------------------
def read():
	#print(filename)
	if filename not in RowTypeDic:
		return None
	if IfBin2Txt:
		filepath = os.path.join(dirpath, BIN, filename+'.'+BIN)
		if not os.path.exists(filepath):
			return None
		fileOld = open(filepath, 'rb')
		data = fileOld.read()
		fileOld.close()
	else:
		filepath = os.path.join(dirpath, TXT, filename+'.'+TXT)
		if not os.path.exists(filepath):
			return None
		fileOld = open(filepath, 'rb')
		if TXT == 'csv':
			data = pd.read_csv(fileOld, header=None, sep='\t', quoting=csv.QUOTE_MINIMAL)
		elif TXT == 'json':
			data = pd.read_json(fileOld, orient ='values')
		fileOld.close()
	return data

def write():
	global content
	name = filename
	if IfBin2Txt:
		path = os.path.join(dirpath, TXT)
		if not os.path.exists(path):
			os.makedirs(path)
		filepath = os.path.join(path, name+'.'+TXT)
		fileNew = open(filepath, 'w', encoding=EncodeName, newline='')
		if TXT == 'csv':
			content = content.to_csv(None, header=None, index=False, sep='\t')
			fileNew.write(content)
		elif TXT == 'json':
			content = content.to_json(orient ='values', indent=2, force_ascii=False)
			fileNew.write(content)
		else:
			print('Unsupported output format:', TXT)
	else:
		path = os.path.join(dirpath, BIN+'.new')
		if not os.path.exists(path):
			os.makedirs(path)
		filepath = os.path.join(path, name+'.'+BIN)
		fileNew = open(filepath, 'wb')
		fileNew.write(content)
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
		#print(dirpath)
		if IfBin2Txt:
			binpath = os.path.join(dirpath, BIN)
			for name in os.listdir(binpath):
				#解压
				if not name.endswith('.'+BIN):
					continue
				filename = name[:-len(BIN)-1]
				decompress()
		else:
			txtpath = os.path.join(dirpath, TXT)
			for name in os.listdir(txtpath):
				#压缩
				if not name.endswith('.'+TXT):
					continue
				filename = name[:-len(TXT)-1]
				compress()

main()