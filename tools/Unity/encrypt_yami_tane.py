# ------------------------------------------------------------
# https://github.com/satan53x/SExtractor/tree/main/tools/Unity
# 加解密Unity游戏 "闇種" 的部分资源，加解密都使用本脚本
# 安装依赖：pip install pythonnet
# 安装依赖：可能需要自行安装 .NET Framework
# ------------------------------------------------------------
import os
import sys
from tkinter import filedialog
from tqdm import tqdm

import clr
clr.AddReference("mscorlib")
from System import Array, Byte
from System.Security.Cryptography import PasswordDeriveBytes, AesManaged
from System.Security.Cryptography import CipherMode, PaddingMode

DefaultPath = ''
password = 'mei_players_sarvice'.encode('utf-8')
#salt = 文件名

#key = b'9FixqbGNSq798HFY' #save文件是CBC模式
#iv = b'9Fix4L4HB4PKeKWY'

# ------------------------------------------------------------
#var
dirpath = ''
filename = '' 

output = None
BlockSize = 0
# ------------------------------------------------------------
def createManaged():
	salt = filename.encode('utf-8')
	key = PasswordDeriveBytes(password, salt)
	key_bytes = key.GetBytes(16)
	key = bytes(list(key_bytes))
	#cipher = AES.new(key, AES.MODE_ECB)
	cipher = AesManaged()
	cipher.KeySize = 128
	cipher.Mode = CipherMode.ECB
	cipher.Padding = getattr(PaddingMode, 'None')
	cipher.Key = key
	cipher.IV = b'\x00' * 16
	cryptor = cipher.CreateEncryptor(cipher.Key, cipher.IV)
	global BlockSize
	BlockSize = cipher.BlockSize
	return cryptor

def decrypt(text_cipher):
	cryptor = createManaged()
	ciphertext_bytes = bytearray(text_cipher)
	decrypted_bytes = calc_block(cryptor, ciphertext_bytes, 0, len(ciphertext_bytes), 0)
	return decrypted_bytes

def calc_block(cryptor, buffer, offset, count, stream_pos):
	block_size_in_byte = BlockSize // 8
	block_number = (stream_pos // block_size_in_byte) + 1
	key_pos = stream_pos % block_size_in_byte
	
	# 初始化缓冲区
	zero = bytes(block_size_in_byte)
	out_buffer = Array[Byte](zero)
	nonce = Array[Byte](zero)
	initialized = False
	
	for i in tqdm(range(offset, count)):
		# 当需要新块时，加密nonce生成新的xor缓冲区
		if not initialized or (key_pos % block_size_in_byte == 0):
			bs = block_number.to_bytes(8, 'little') #最大i64
			for j in range(0, 8):
				nonce[j] = bs[j]
			cryptor.TransformBlock(nonce, 0, len(nonce), out_buffer, 0)
			if initialized:
				key_pos = 0
			initialized = True
			block_number += 1
		
		buffer[i] ^= out_buffer[key_pos]  # 简单的XOR操作
		key_pos += 1
	return buffer

def parse():
	global output
	#print(filename)
	filepath = os.path.join(dirpath, filename)
	fileOld = open(filepath, 'rb')
	input = fileOld.read()
	fileOld.close()
	output = decrypt(input)
	write()

# ------------------------------------------------------------
def write():
	path = os.path.join(dirpath, 'new')
	if not os.path.exists(path):
		os.makedirs(path)
	name, _ = os.path.splitext(filename)
	filepath = os.path.join(path, name)
	fileNew = open(filepath, 'wb')
	fileNew.write(output)
	fileNew.close()
	print(f'Write done: {name}')

def main():
	path = DefaultPath
	if len(sys.argv) < 2:
		path = filedialog.askdirectory(initialdir=path)
	else:
		path = sys.argv[1]
	global dirpath
	global filename
	if os.path.isdir(path):
		dirpath = path
		for name in os.listdir(dirpath):
			filename = name
			if name == 'pic': continue
			filepath = os.path.join(dirpath, filename)
			if os.path.isfile(filepath):
				parse()
				#break

main()
