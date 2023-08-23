import os
import sys
from tkinter import filedialog

GameType = 0 #此处选择预设游戏
OffsetStart = 0x100 #如果是arc_conv提取需要把此处改为0x100
DefaultDir = './Seen.txt~/'

#每个游戏可能不同，可以通过异或txt截断处和游戏内ocr提取文本获得
XorTable = {
	#緋奈沢智花の絶対女王政
	0: bytearray.fromhex('8A 03 CB 50 99 11 57 06 BD 68 D7 12 45 25 9C DC'),
	#新妻環 環の愛妻日記
	1: bytearray.fromhex('83 0B CF 51 81 15 42 38 A0 67 DB 18 41 25 95 D4'),
	#プリンセスハートリンク 剣姫たちの艶舞
	2: bytearray.fromhex('83 0B CF 51 87 13 5F 6B 96 4D F6 14 4F 21 97 DE'),
}

#加密解密函数相同
def fixSeenSub(data, tableType):
	pos = 0x20
	start = int.from_bytes(data[pos:pos+4], byteorder='little') + OffsetStart
	size = len(XorTable[tableType])
	for i in range(0x101):
		pos = start + i
		if pos >= len(data):
			break
		b = data[pos] ^ XorTable[tableType][i%size]
		data[pos] = b
	return data

def main(args):
	workpath = DefaultDir
	if os.path.isdir(workpath):
		pass
	elif len(args) > 1:
		workpath = args[1]
	else:
		workpath = filedialog.askdirectory(initialdir='.')
		if workpath == '': return
	print('工作目录', workpath)
	#创建new文件夹
	path = os.path.join(workpath, 'new')
	if not os.path.exists(path):
		os.makedirs(path)
	#遍历txt文件
	for name in os.listdir(workpath):
		if not name.endswith('.txt'): continue
		#读取
		path = os.path.join(workpath, name)
		print('读取:', name)
		file = open(path, 'rb')
		data = bytearray(file.read())
		file.close()
		data = fixSeenSub(data, GameType)
		#写入
		path = os.path.join(workpath, 'new', name)
		file = open(path, 'wb')
		file.write(data)
		file.close()
		print('已处理:', name)
	print('完成')

main(sys.argv)