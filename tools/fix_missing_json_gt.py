# ------------------------------------------------------------
# 为galTransl的json添加缺失的item
# 仅用于新orig比旧orig增加的情况
# ------------------------------------------------------------
import sys
import os
import json
from tkinter import filedialog 
DefaultPath = ''
EncodeName = 'utf-8'
Postfix = '.json'
OrigOldDir = 'orig_old'
OrigNewDir = 'orig'
TransOldDir = 'trans_old'
TransNewDir = 'trans'
FixOrigItems = 'fix.orig.json'
FixTransItems = 'fix.trans.json'

# ------------------------------------------------------------
#var
dirpath = ''
filename = '' 

allJson = {}
# ------------------------------------------------------------
def fix():
	global allJson, filename
	fix_orig_items = []
	fixDone = False
	path = os.path.join(dirpath, TransNewDir, FixTransItems)
	if os.path.exists(path):
		f = open(path, 'r', encoding=EncodeName)
		fix_trans_items = json.load(f)
		fixDone = True
		print('Read:', FixTransItems)
	#遍历
	for orig_name in os.listdir(os.path.join(dirpath, OrigOldDir)):
		#单文件
		if not orig_name.endswith(Postfix):
			continue
		with open(os.path.join(dirpath, OrigOldDir, orig_name), 'r', encoding=EncodeName) as f:
			orig_old_list = json.load(f)
		with open(os.path.join(dirpath, OrigNewDir, orig_name), 'r', encoding=EncodeName) as f:
			orig_new_list = json.load(f)
		with open(os.path.join(dirpath, TransOldDir, orig_name), 'r', encoding=EncodeName) as f:
			trans_old_list = json.load(f)
		trans_new_list = []
		orig_index = 0
		new_index = 0
		while new_index < len(orig_new_list):
			#单item
			orig_old = orig_old_list[orig_index]
			orig_new = orig_new_list[new_index]
			trans_old = trans_old_list[orig_index]
			if orig_old['message'] == orig_new['message']:
				#相同item
				trans_new = trans_old
				orig_index += 1
				if 'name' not in orig_old and 'name' in orig_new:
					#补上名字
					trans_new['name'] = orig_new['name']
					trans_new['fix'] = 'new_name'
			else:
				#不同item，orig_index不增加
				if fixDone:
					#修正完成，导入
					seq = len(fix_orig_items)
					trans_new = fix_trans_items[seq]
				else:
					#补上orig_new
					trans_new = {
						'message': orig_new['message'],
						'fix': 'new_item',
					}
					if 'name' in orig_new:
						trans_new['name'] = orig_new['name']
				fix_orig_items.append(orig_new)
			trans_new_list.append(trans_new)
			new_index += 1
		#输出到trans_new
		allJson = trans_new_list
		filename = orig_name
		write()
	if len(fix_orig_items) > 0:
		#dump额外
		allJson = fix_orig_items
		filename = FixOrigItems
		write()
		if fixDone:
			print('Import Done.')
	else:
		print('No need to fix.')

# ------------------------------------------------------------
def write():
	path = os.path.join(dirpath, TransNewDir)
	os.makedirs(path, exist_ok=True)
	name = filename
	filepath = os.path.join(path, name)
	fileNew = open(filepath, 'w', encoding=EncodeName)
	json.dump(allJson, fileNew, ensure_ascii=False, indent=2)
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
	global dirpath
	if os.path.isdir(path):
		dirpath = path
		fix()

main()