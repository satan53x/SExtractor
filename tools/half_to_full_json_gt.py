# ------------------------------------------------------------
# 为galTransl的json进行半角转全角
# ------------------------------------------------------------
import sys
import os
import json
from tkinter import filedialog 
DefaultPath = ''
EncodeName = 'utf-8'
Postfix = '.json'
ReplaceDic = {
  " ": "　",
  "!": "！",
  "\"": "＂",
  "#": "＃",
  "$": "＄",
  "%": "％",
  "&": "＆",
  "'": "＇",
  "(": "（",
  ")": "）",
  "*": "＊",
  "+": "＋",
  ",": "，",
  "-": "－",
  ".": "．",
  "/": "／",
  "0": "０",
  "1": "１",
  "2": "２",
  "3": "３",
  "4": "４",
  "5": "５",
  "6": "６",
  "7": "７",
  "8": "８",
  "9": "９",
  ":": "：",
  ";": "；",
  "<": "＜",
  "=": "＝",
  ">": "＞",
  "?": "？",
  "@": "＠",
  "A": "Ａ",
  "B": "Ｂ",
  "C": "Ｃ",
  "D": "Ｄ",
  "E": "Ｅ",
  "F": "Ｆ",
  "G": "Ｇ",
  "H": "Ｈ",
  "I": "Ｉ",
  "J": "Ｊ",
  "K": "Ｋ",
  "L": "Ｌ",
  "M": "Ｍ",
  "N": "Ｎ",
  "O": "Ｏ",
  "P": "Ｐ",
  "Q": "Ｑ",
  "R": "Ｒ",
  "S": "Ｓ",
  "T": "Ｔ",
  "U": "Ｕ",
  "V": "Ｖ",
  "W": "Ｗ",
  "X": "Ｘ",
  "Y": "Ｙ",
  "Z": "Ｚ",
  "[": "［",
  "\\": "＼",
  "]": "］",
  "^": "＾",
  "_": "＿",
  "`": "｀",
  "a": "ａ",
  "b": "ｂ",
  "c": "ｃ",
  "d": "ｄ",
  "e": "ｅ",
  "f": "ｆ",
  "g": "ｇ",
  "h": "ｈ",
  "i": "ｉ",
  "j": "ｊ",
  "k": "ｋ",
  "l": "ｌ",
  "m": "ｍ",
  "n": "ｎ",
  "o": "ｏ",
  "p": "ｐ",
  "q": "ｑ",
  "r": "ｒ",
  "s": "ｓ",
  "t": "ｔ",
  "u": "ｕ",
  "v": "ｖ",
  "w": "ｗ",
  "x": "ｘ",
  "y": "ｙ",
  "z": "ｚ",
  "{": "｛",
  "|": "｜",
  "}": "｝",
  "~": "～"
}

# ------------------------------------------------------------
#var
dirpath = ''
filename = '' 

allJson = {}
listOrig = []
listTrans = []
# ------------------------------------------------------------
def replaceText(old:str):
	for key, value in ReplaceDic.items():
		old = old.replace(key, value)
	return old

def replace():
	global EncodeName
	global allJson
	#print(filename)
	filepath = os.path.join(dirpath, filename+Postfix)
	fileOld = open(filepath, 'r', encoding=EncodeName)
	allJson = json.load(fileOld)
	for item in allJson:
		if 'name' in item:
			text = replaceText(item['name'])
			item['name'] = text
		if 'message' in item:
			text = replaceText(item['message'])
			item['message'] = text
	write()
	fileOld.close()

# ------------------------------------------------------------
def write():
	path = os.path.join(dirpath, 'new')
	if not os.path.exists(path):
		os.makedirs(path)
	name = filename
	filepath = os.path.join(path, name+Postfix)
	fileNew = open(filepath, 'w', encoding=EncodeName)
	json.dump(allJson, fileNew, ensure_ascii=False, indent=2)
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
				replace()
				#break

main()