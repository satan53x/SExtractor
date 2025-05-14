# ------------------------------------------------------------
# https://github.com/satan53x/SExtractor/tree/main/tools/AZSystem
# ------------------------------------------------------------
import sys
import os
from tkinter import filedialog
import zlib 
DefaultPath = ''
Postfix = '.asb'
Version = 0 #为0时表示自动判断，允许的值：0, 1, 2
GameType = "Zwei Worter"

#这个Key可以用dbg调试搜索asb的头部signature，也就是ASB `41 53 42` 进行断点，下方的解密函数中有最终数值。
#否则需要用exe自己的非标准MT19937梅森旋转算法进行random，这样虽然是由静态字符串的crc作为seed生成，但是找字符串位置比调试更麻烦，不推荐
ConfigTable = { #MiddleKey
	"Zwei Worter": 0x14D04873
}

# ------------------------------------------------------------
#var
dirpath = ''
filename = ''
content = []
# ------------------------------------------------------------
def decryptFile():
	#print(filename)
	filepath = os.path.join(dirpath, filename+Postfix)
	fileOld = open(filepath, 'rb')
	data = fileOld.read()
	fileOld.close()
	#处理
	header = bytearray(data[0:0x10])
	sig = header[0:4]
	global Version
	if sig == b'ASB\0':
		Version = 1
	elif sig == b'ASB2':
		Version = 2
	else:
		print('>>>>> Not supported signature', sig)
		return
	pos = 4
	crcComSize = int.from_bytes(data[pos:pos+4], byteorder='little')
	pos += 4
	uncomSize = int.from_bytes(data[pos:pos+4], byteorder='little')
	pos += 4
	#解密
	crc_and_com = data[pos:]
	crc_and_com = decryptData(crc_and_com, uncomSize)
	header[0xC:0x10] = crc_and_com[0:4] #crc
	#解压
	com = crc_and_com[4:]
	uncom = zlib.decompress(com)
	if len(uncom) != uncomSize:
		print('>>>>> Decompress Error:', filename)
		return
	#导出
	content.clear()
	content.append(header)
	content.append(uncom)
	write()

def decryptData(com, uncomSize):
	com = bytearray(com)
	key = uncomSize ^ ConfigTable[GameType]
	if Version == 2:
		key = (((key >> 7) | (key << 19)) << 0) ^ key
	else:
		key = (((key >> 0) | (key << 12)) << 11) ^ key
	key = key & 0xFFFFFFFF
	for pos in range(0, len(com)//4*4, 4):
		d = int.from_bytes(com[pos:pos+4], byteorder='little')
		d = (d - key) % 0x100000000
		bs = int.to_bytes(d, 4, byteorder='little')
		com[pos:pos+4] = bs
	return com

# ------------------------------------------------------------
def write():
	path = os.path.join(dirpath, 'new')
	if not os.path.exists(path):
		os.makedirs(path)
	name = filename
	filepath = os.path.join(path, name+Postfix)
	fileNew = open(filepath, 'wb')
	fileNew.writelines(content)
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
		for name in os.listdir(dirpath):
			filename = name.replace(Postfix, '')
			filepath = os.path.join(dirpath, filename+Postfix)
			if os.path.isfile(filepath):
				decryptFile()

if __name__ == "__main__":
	main()