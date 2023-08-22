
from numpy import byte
from common import printHex

def main1():
	#s1 = '96 BC 96 B3 82 B5 61 01 96 BC 96 B3 82 B5 61 01'
	#s2 = '8A 03 CB 50 99 11 57 06 BD 68 D7 12 45 25 9C DC'
	s1 = '6C 81 41 93 6C 8A C2 82 CD 8C A9 82 C2 82 A9 82'
	s2 = 'EF 8A 8E C2 ED 9F 80 BA 6D EB 72 9A 83 A7 3C 56'
	b1 = bytes.fromhex(s1)
	b2 = bytes.fromhex(s2)
	printHex(b1)
	printHex(b2)
	ret = b''
	for i in range(len(b1)):
		ret += (b1[i] ^ b2[i]).to_bytes(1)
	printHex(ret)

def main2():
	s = '「ダンナ様、斗環は見つかっ'
	b = s.encode('cp932')
	printHex(b)

main1()