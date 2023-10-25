# ------------------------------------------------------------
# 加解密Unity框架data.dsm
# https://github.com/satan53x/SExtractor/tree/main/tools/Unity
# ------------------------------------------------------------
import os
import sys
from tkinter import filedialog
from Crypto.Cipher import AES
from Crypto.Protocol.KDF import PBKDF2
from Crypto.Util.Padding import pad, unpad
import base64

ForeEncrypt = 'auto' #按后缀设置加解密
IsEncrypt = False #加密还是解密
DefaultPath = ''
PostfixCipher='.dsm'
PostfixPlain='.txt'
EncodeName='utf-8-sig'
salt = 'saltは必ず8バイト以上'.encode()
password = 'pass'.encode()


# ------------------------------------------------------------
#var
dirpath = ''
filename = '' 

output = None
# ------------------------------------------------------------
def createManaged():
    keyLen = 256 // 8
    ivLen = 128 // 8
    iteration_count = 1000
    
    rfc2898 = PBKDF2(password, salt, dkLen=(keyLen+ivLen), count=iteration_count)
    key = rfc2898[:keyLen]
    iv = rfc2898[keyLen:]
    
    cipher = AES.new(key, AES.MODE_CBC, iv)
    
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
		if filename.endswith(PostfixCipher):
			#读入是已加密，则进行解密
			IsEncrypt = False
		elif filename.endswith(PostfixPlain):
			#读入是未加密，则进行加密
			IsEncrypt = True
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
	#print(path)
	global dirpath
	global filename
	if os.path.isdir(path):
		dirpath = path
		#print(dirpath)
		for name in os.listdir(dirpath):
			#print(name)
			filename = name
			filepath = os.path.join(dirpath, filename)
			if os.path.isfile(filepath):
				#print(filepath)
				parse()
				#break

main()
