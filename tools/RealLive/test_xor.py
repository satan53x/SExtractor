import re
from numpy import byte
from common import *
#s1 = '96 BC 96 B3 82 B5 61 01 96 BC 96 B3 82 B5 61 01'
#s2 = '8A 03 CB 50 99 11 57 06 BD 68 D7 12 45 25 9C DC'
s1 = '6A 73 48 06 1C 57 D0 6B 20 1A 5F 63 D9 A2 02 56'
s2 = '83 7C 81 5B 83 5E 81 5B 81 7A 81 77 83 81 83 8B'
start = 0x00
end = 0xFF
pattern = re.compile(rb'') #re.compile(rb'^[A-Za-z0-9._ !%]$')

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
	try:
		text = ret.decode('cp932')
		print(ret)
		print(text)
	except:
		pass

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
	return ret

def main3():
	b1 = bytes.fromhex(s1)
	for n in range(start, end+1):
		b2 = bytearray()
		b2.append(n)
		ret = xorBytes(b1, b2)
		if checkJIS(ret, pattern):
			for dec in range(0, 3):
				try:
					text = ret[:len(ret)-dec].decode('cp932')
					print('\033[92m'+ text + '\033[0m')
					#printHex(b1)
					#printHex(b2)
					#printHex(ret)
					print(f'----------- Try: {n:02X}')
					print('')
					break
				except Exception as ex:
					pass

#--------------------------------------------------
def rotate_left(n, d, bits=32):
	return ((n << d) | (n >> (bits - d))) & ((1 << bits) - 1)

def main4():
	byte_count = 1
	b1 = bytes.fromhex(s1)
	for shift in range(0, byte_count*8):
		b2 = bytearray()
		for i in range(0, len(b1), byte_count):
			v = int.from_bytes(b1[i:i+byte_count], 'little')
			v = rotate_left(v, shift, byte_count*8)
			bs = v.to_bytes(byte_count, 'little')
			b2.extend(bs)
		for dec in range(0, 3):
			try:
				text = b2[:len(b2)-dec].decode('cp932')
				print('\033[92m'+ text + '\033[0m')
				print(f'----------- Try: {shift}')
			except Exception as ex:
				pass

main1()