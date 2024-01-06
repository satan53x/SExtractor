
from numpy import byte
from common import printHex

def main1():
	#s1 = '96 BC 96 B3 82 B5 61 01 96 BC 96 B3 82 B5 61 01'
	#s2 = '8A 03 CB 50 99 11 57 06 BD 68 D7 12 45 25 9C DC'
	s1 = '00 45 1B C7 0C EF 1C 2C 14 F6 14 F6 03 F9 17 59'
	s2 = '95'
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
main1()