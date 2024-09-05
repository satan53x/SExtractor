# ------------------------------------------------------------
# https://github.com/satan53x/SExtractor/tree/main/tools/RealLive
# ------------------------------------------------------------
import os
import sys
from tkinter import filedialog

GameType = 6 #此处选择预设游戏
OffsetStart = 0x100 #如果是arc_conv解包需要把此处改为0x100
DefaultDir = ''

#每个游戏可能不同，可以通过异或txt截断处和游戏内ocr提取文本获得
XorTable = {
	#緋奈沢智花の絶対女王政
	0: bytearray.fromhex('8A 03 CB 50 99 11 57 06 BD 68 D7 12 45 25 9C DC'),

	#新妻環 環の愛妻日記
	1: bytearray.fromhex('83 0B CF 51 81 15 42 38 A0 67 DB 18 41 25 95 D4'),

	#プリンセスハートリンク 剣姫たちの艶舞 DL版
	2: bytearray.fromhex('83 0B CF 51 87 13 5F 6B 96 4D F6 14 4F 21 97 DE'),
	#プリンセスハートリンク 剣姫たちの艶舞 PKG版
	3: bytearray.fromhex('83 0B CF 51 87 13 5F 6B AE 68 D7 16 45 23 9B 87'),

	#鬼まり。 ～鬼が夢見し常の世に、至る幼き恋の始まり～
	#鬼うた。 ～鬼が来たりて、甘えさせろとのたもうた。～
	4: bytearray.fromhex('AD 2B FE 3E E8 3A 3B 19 82 0D FA 3B 25 01 B5 B5'),

	#クドわふたー
	5: bytearray.fromhex('67 1C 21 BE 6F EF B5 16 4A 82 39 2B AD 3A 71 3F'),

	#仕舞妻 ～姉妹妻3～
	6: bytearray.fromhex('EC 7D BC 6E B2 2A 66 1D C8 4C AC 73 78 49 B2 A4'),

	# >>>>>>> Made by `Cosetto`
	# 3Ping Lovers！☆一夫二妻の世界へようこそ♪
	21: bytearray.fromhex('66 8A 20 D4 6E C3 B4 B8 4B F8 38 93 AC AC 70 0A'),

	# 新妻詩乃
	22: bytearray.fromhex('8C 03 CC 55 9F 1D 41 38 A1 60 D4 12 5D 2D 85 D4'),

	# 新妻こよみ
	23: bytearray.fromhex('80 05 D7 40 89 15 5D 3C A7 62 D3 17 41 39 86 D0'),

	# らぶ撮りハレーション
	24: bytearray.fromhex('74 3C 2F FC 6E CD B4 BF 4B D4 2A 25 A3 84 70 04'),

	# 水着少女と媚薬アイス ～残念なカノジョのしつけ方、教えます～
	25: bytearray.fromhex('93 02 CB 40 89 23 52 38 B0 7E D2 1A 5A 29 AD D1'),
	
	# >>>>>>> Made by `Morph`
	#『彼氏いない歴＝年齢』じゃ、どうしてイケナイのよ!?
	41: bytearray.fromhex('73 ED 33 9F 63 D1 B9 CE 5E 8E 2B D8 A1 E1 7D 22'),

	# >>>>>>> Made by `Steins;Gate` & `先依`
	#素直くーる
	51: bytearray.fromhex('8F 1F C5 41 9E 09 5B 30 A2 7C DD 06 5C 39 9F DC'),

	#ふりフリ～ふつうのまいにちにわりこんできた、フシギなリンジンたちのおはなしおはなし～
	52: bytearray.fromhex('9D 6C AE 33 E2 68 29 0F CD 09 A8 77 39 5E A7 AD'),

	#お姉さん×すくらっち
	53: bytearray.fromhex('B5 3B C6 55 9F 14 5F 69 F8 3B 89 47 1B 7A C5 8D'),

	#オシオキSweetie＋Sweets！！ HD版
	54: bytearray.fromhex('97 02 CB 5A 83 0F 5E 30 A7 66 C9 1B 47 22 9D C6'),

	#ボイン姉妹の個人授業
	55: bytearray.fromhex('8C 05 CC 51 87 1D 41 38 BA 7C D4 16 41 24 9D DB'), 
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
	if len(args) > 1:
		workpath = args[1]
	elif workpath == '':
		workpath = filedialog.askdirectory()
	else:
		workpath = filedialog.askdirectory(initialdir=workpath)
	print('工作目录', workpath)
	if workpath == '':
		return
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

if __name__ == '__main__':
	main(sys.argv)
