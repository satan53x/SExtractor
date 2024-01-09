
import re
from numpy import byte
from common import *
#s1 = '96 BC 96 B3 82 B5 61 01 96 BC 96 B3 82 B5 61 01'
#s2 = '8A 03 CB 50 99 11 57 06 BD 68 D7 12 45 25 9C DC'
s1 = '34 F9 34 E6 34 E7 34 E4 34 E5 34 E2 34 E3 34 E0'
s2 = 'B6'
start = 0x00
end = 0xFF
pattern = re.compile(rb'^[A-Za-z0-9._ !%]$')

def main1():
	if s2 == '':
		main3()
		return
	b1 = bytes.fromhex(s1)
	b2 = bytes.fromhex(s2)
	printHex(b1)
	printHex(b2)
	ret = b''
	for i in range(len(b1)):
		ret += (b1[i] ^ b2[i%len(b2)]).to_bytes(1)
	printHex(ret)
	print(ret)
	text = ret.decode('cp932')
	print(text)

def main2():
	s = '「ダンナ様、斗環は見つかっ'
	b = s.encode('cp932')
	printHex(b)

#----------------------------------
def xorBytes(b1, b2):
	ret = b''
	for i in range(len(b1)):
		ret += (b1[i] ^ b2[i%len(b2)]).to_bytes(1)
	#print(ret)
	if checkJIS(ret, pattern):
		text = ret.decode('cp932')
		print('\033[92m'+ text + '\033[0m')
		printHex(b1)
		printHex(b2)
		printHex(ret)
		return True
	return False

def main3():
	b1 = bytes.fromhex(s1)
	for n in range(start, end+1):
		b2 = bytearray()
		b2.append(n)
		try:
			ret = xorBytes(b1, b2)
			if ret:
				print(f'----------- Try: {n:02X}')
				print('')
			else:
				continue
		except Exception as ex:
			pass

main1()