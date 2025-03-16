# ------------------------------------------------------------
# 加解密Unity游戏 " 大多数 nobody " 的部分资源
# https://github.com/satan53x/SExtractor/tree/main/tools/Unity
# ------------------------------------------------------------
import os
import sys
from tkinter import filedialog
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad
import base64

ForeEncrypt = 'auto' #按后缀设置加解密
IsEncrypt = False #加密还是解密
DefaultPath = ''
PostfixCipher=''
PostfixPlain='.json'
EncodeName='utf-8'
#key = b'xxxxxxxxxxxxxxxxxxxxxxxxxxxx4444' #S 存档
key = b'xxxxxxxxxxxxxxxxxxxxxxxxxxxx8888' #T 翻译
#keyFilename = b'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx' #文件名

# ------------------------------------------------------------
#var
dirpath = ''
filename = '' 

output = None
# ------------------------------------------------------------
def createManaged():
    cipher = AES.new(key, AES.MODE_ECB)
    return cipher

def encrypt(text_plain):
    cipher = createManaged()
    plaintext_bytes = text_plain.encode('utf-8')
    ciphertext = cipher.encrypt(pad(plaintext_bytes, AES.block_size))
    encrypted_text = base64.b64encode(ciphertext).decode('utf-8')
    return encrypted_text

def decrypt(text_cipher):
    cipher = createManaged()
    ciphertext_bytes = base64.b64decode(text_cipher)
    decrypted_bytes = cipher.decrypt(ciphertext_bytes)
    decrypted_text = unpad(decrypted_bytes, AES.block_size).decode('utf-8')
    return decrypted_text

def parse():
	global IsEncrypt
	global output
	if ForeEncrypt == 'auto':
		if filename.endswith(PostfixPlain):
			#读入是未加密，则进行加密
			IsEncrypt = True
		else:
			#否则进行解密
			IsEncrypt = False
	#print(filename)
	filepath = os.path.join(dirpath, filename)
	fileOld = open(filepath, 'r', encoding=EncodeName)
	input = fileOld.read()
	if IsEncrypt:
		output = encrypt(input)
	else:
		output = decrypt(input)
	write()

# ------------------------------------------------------------
def write():
	path = os.path.join(dirpath, 'new')
	if not os.path.exists(path):
		os.makedirs(path)
	name, _ = os.path.splitext(filename)
	posifx = PostfixCipher if IsEncrypt else PostfixPlain
	filepath = os.path.join(path, name+posifx)
	fileNew = open(filepath, 'w', encoding=EncodeName)
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
			filepath = os.path.join(dirpath, filename)
			if os.path.isfile(filepath):
				parse()
				#break

main()
