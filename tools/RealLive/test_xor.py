
from numpy import byte
from common import printHex

def main1():
	#s1 = '96 BC 96 B3 82 B5 61 01 96 BC 96 B3 82 B5 61 01'
	#s2 = '8A 03 CB 50 99 11 57 06 BD 68 D7 12 45 25 9C DC'
	s1 = '59 89 62 D3 3A 91 E0 E9 4E FB B8 9B 1F A1 57 09'
	s2 = 'DA 82 AD 82 BD 82 BF 82 E0 93 6F 8D 5A 82 CC 8E'
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