import json

output_file = 'cjk.txt'
sample_txt_1 = 'CHS1-GBK符号+通用规范汉字表(一级).txt'
sample_json_1 = '../../src/subs_cn_jp.json'
list = []

def main():
	#ascii
	for i in range(0x20, 0x7F):
		c = chr(i)
		if c not in list:
			list.append(c)
	list.append('\n')
	#Cyrillic
	for i in range(0x400, 0x4FF):
		c = chr(i)
		if c not in list:
			list.append(c)
	list.append('\n')
	#一般符号
	# for i in range(0x20, 0x21):
	# 	for j in range(0x00, 0x70):
	# 		try:
	# 			c = bytes([i, j]).decode('utf-16-be')
	# 			if c not in list:
	# 				list.append(c)
	# 		except UnicodeDecodeError:
	# 			continue
	# list.append('\n')
	#符号
	for i in range(0x24, 0x28):
		for j in range(0x00, 0x100):
			try:
				c = bytes([i, j]).decode('utf-16-be')
				if c not in list:
					list.append(c)
			except UnicodeDecodeError:
				continue
	list.append('\n')
	#日文符号
	for i in range(0x30, 0x31):
		for j in range(0x00, 0xFF):
			try:
				c = bytes([i, j]).decode('utf-16-be')
				if c not in list:
					list.append(c)
			except UnicodeDecodeError:
				continue
	list.append('\n')
	#GBK
	# for i in range(0x81, 0xFF):
	# 	for j in range(0x40, 0xFF):
	# 		try:
	# 			c = bytes([i, j]).decode('gbk')
	# 			if c not in list:
	# 				list.append(c)
	# 		except UnicodeDecodeError:
	# 			continue
	# list.append('\n')
	#符号
	for i in range(0xFF, 0x100):
		for j in range(0x00, 0xF0):
			try:
				c = bytes([i, j]).decode('utf-16-be')
				if c not in list:
					list.append(c)
			except UnicodeDecodeError:
				continue
	list.append('\n')
	#sample 1
	with open(sample_txt_1, 'r', encoding='utf-8') as file:
		for line in file:
			for c in line:
				if c not in list:
					list.append(c)
	list.append('\n')
	# sample 2
	with open(sample_json_1, 'r', encoding='utf-8') as f:
		data = json.load(f)
		for k, v in data.items():
			if k not in list:
				list.append(k)

	#生成文件
	file = open(output_file, 'w', encoding='utf-8')
	file.write(''.join(list))

main()
print('Done.')