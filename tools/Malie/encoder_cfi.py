# ------------------------------------------------------------
# https://github.com/satan53x/SExtractor/tree/main/tools/Malie
# database.json generated from Garbro
# ------------------------------------------------------------
import base64
from tqdm import tqdm
from database_malie import database_malie

BlockLen = 0x10
# ------------------------------------------------------------
def getDatabaseCfi():
	db = {}
	for name, item in database_malie.items():
		if 'RotateKey' not in item: continue
		db[name] = item
		item['Key'] = base64.b64decode(item['Key'])
		#item['Align'] = 0x400
		item['Encoder'] = EncoderCfi
	return db

# ------------------------------------------------------------
class EncoderCfi():
	def __init__(self, config) -> None:
		self.config = config

	def encryptAll(self, data, offset=0, printed=True):
		r = range(len(data) // BlockLen) #因为会填充对齐，所以必定是整数倍
		if printed:
			r = tqdm(r, desc="Processing", unit="line")
		for line in r:
			start = line * BlockLen
			end = start + BlockLen
			block = self.encryptBlock(data[start:end], offset)
			data[start:end] = block
			offset += BlockLen

	def encryptBlock(self, block, offset):
		#位移
		data32 = [0,0,0,0]
		for i in range(4):
			data32[i] = int.from_bytes(block[i*4:(i+1)*4], byteorder='little')
		offset >>= 4
		self.rotateEnc(data32, offset, self.config['RotateKey'], self.config['Key'])
		for i in range(4):
			block[i*4:(i+1)*4] = data32[i].to_bytes(4, byteorder='little')
		#异或
		first = block[0]
		for i in range(1, BlockLen):
			block[i] ^= first
		return block

	def rotateEnc(self, data32, offset, rotateKey, key):
		k = rotateRight(rotateKey[0], key[offset & 0x1F] ^ 0xA5)
		data32[0] = rotateLeft(data32[0], key[(offset + 12) & 0x1F] ^ 0xA5) ^ k
		k = rotateLeft(rotateKey[1], key[(offset + 3) & 0x1F] ^ 0xA5)
		data32[1] = rotateRight(data32[1], key[(offset + 15) & 0x1F] ^ 0xA5) ^ k
		k = rotateRight(rotateKey[2], key[(offset + 6) & 0x1F] ^ 0xA5)
		data32[2] = rotateLeft(data32[2], key[(offset - 14) & 0x1F] ^ 0xA5) ^ k
		k = rotateLeft(rotateKey[3], key[(offset + 9) & 0x1F] ^ 0xA5)
		data32[3] = rotateRight(data32[3], key[(offset - 11) & 0x1F] ^ 0xA5) ^ k

BitLen = 32
ValueMask = (1 << BitLen) - 1
def rotateRight(value, shift):
	value = (value >> shift) | (value << (BitLen - shift)) 
	return value & ValueMask

def rotateLeft(value, shift):
	value = (value << shift) | (value >> (BitLen - shift)) 
	return value & ValueMask
