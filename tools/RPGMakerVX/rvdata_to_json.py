# ------------------------------------------------------------
# https://github.com/satan53x/SExtractor/tree/main/tools/RPGMakerVX
# ------------------------------------------------------------
import sys
import os
import json
from tkinter import filedialog
from rubymarshal import reader, writer
from rubymarshal.classes import RubyObject, Symbol, to_dict, from_dict

DefaultPath = ''
Postfix = ['.rvdata2', '.rvdata', 'rxdata'] #允许的后缀
SkipFile = ['Scripts'] #Scripts.rvdata2不进行转换

# ------------------------------------------------------------
#var
dirpath = ''
filename = ''
content = []
isJsonToData = False

# ------------------------------------------------------------
def handle():
	content.clear()
	filepath = os.path.join(dirpath, filename)
	if not isJsonToData:
		#rvdata to json
		file = open(filepath, 'rb')
		data = file.read()
		file.close()
		obj = reader.loads(data)
		dic = to_dict(obj)
		s = json.dumps(dic, ensure_ascii=False, indent=2, separators=(",", ":")) #设置json是否紧凑
		content.append(s)
	else:
		#json to rvdata
		file = open(filepath, 'r', encoding="utf-8")
		s = file.read()
		file.close()
		dic = json.loads(s)
		obj = from_dict(dic)
		data = writer.writes(obj)
		content.append(data)

	write()

# ------------------------------------------------------------
def write():
	if not isJsonToData:
		path = os.path.join(dirpath, 'Json')
		if not os.path.exists(path):
			os.makedirs(path)
		name = f'{filename}.json'
		filepath = os.path.join(path, name)
		fileNew = open(filepath, 'w', encoding="utf-8")
		print(f'To Json: {filename}')
	else:
		path = os.path.join(dirpath, 'Data')
		if not os.path.exists(path):
			os.makedirs(path)
		name, ext = os.path.splitext(filename)
		filepath = os.path.join(path, name)
		fileNew = open(filepath, 'wb')
		print(f'To Data: {name}')
	fileNew.writelines(content)
	fileNew.close()

def main():
	path = DefaultPath
	if path:
		pass
	elif len(sys.argv) < 2:
		path = filedialog.askdirectory(initialdir=path)
	else:
		path = sys.argv[1]
	#print(path)
	global dirpath, filename, isJsonToData
	if os.path.isdir(path):
		dirpath = path
		for name in os.listdir(dirpath):
			filename = name
			filepath = os.path.join(dirpath, filename)
			if os.path.isfile(filepath):
				name, ext = os.path.splitext(filename)
				if name in SkipFile:
					print('Skip File:', filename)
					continue
				if ext == '.json':
					isJsonToData = True
				else:
					isJsonToData = False
					if ext not in Postfix:
						print('Postfix not support:', filename)
						continue
				handle()
				#break

if __name__ == "__main__":
	main()