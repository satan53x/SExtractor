import re
from common import *
from extract_BIN import replaceOnceImp as replaceOnceImpBIN
from extract_BIN import parseImp as parseImpBIN

headSec = None
# ---------------- Engine: ANIM -------------------
def parseImp(content, listCtrl, dealOnce):
	parseImpBIN(content, listCtrl, dealOnce)

# -----------------------------------
def replaceOnceImp(content, lCtrl, lTrans):
	return replaceOnceImpBIN(content, lCtrl, lTrans)

def replaceEndImp(content):
	strSec = b''.join(content)
	data = headSec + strSec
	data = encrypt(data) #加密
	content.clear()
	content.append(data)

# -----------------------------------
def readFileDataImp(fileOld, contentSeparate):
	data = bytearray(fileOld.read())
	data = decrypt(data)
	if ExVar.filename.endswith('sce'):
		pos = readInt(data, 0x18) + 0x14 #文本区起始地址
	else:
		pos = 0x14
	global headSec
	headSec = data[0:pos]
	content = re.split(contentSeparate, data[pos:])
	return content, {}

# --------------- from game_translation --------------------
#解密
def decrypt(data:bytearray):
	key = data[0x4:0x14]
	v = 0
	for i in range(0x14, len(data)):
		data[i] = key[v] ^ data[i]
		v += 1
		if v == 16:
			v = 0
			key = switch_key(key, data[i-1])
	return data
#加密
def encrypt(data:bytearray):
	new_data = bytearray(data)
	key = data[0x4:0x14]
	v = 0
	for i in range(0x14, len(data)):
		new_data[i] = key[v] ^ data[i]
		v += 1
		if v == 16:
			v = 0
			key = switch_key(key, data[i-1])
	return new_data

def byte_add(*args):
    ans = 0
    for i in args:
        ans += i
    return ans & 0xff

def switch_key(key: bytearray, ch: int):
	t = ch
	ch &= 7
	if ch == 0:
		key[0] = byte_add(key[0], t)
		key[3] = byte_add(key[3], t, 2)
		key[4] = byte_add(key[2], t, 11)
		key[8] = byte_add(key[6]+7)
	elif ch == 1:
		key[2] = byte_add(key[9], key[10])
		key[6] = byte_add(key[7], key[15])
		key[8] = byte_add(key[8], key[1])
		key[15] = byte_add(key[5], key[3])
	elif ch == 2:
		key[1] = byte_add(key[1], key[2])
		key[5] = byte_add(key[5], key[6])
		key[7] = byte_add(key[7], key[8])
		key[10] = byte_add(key[10], key[11])
	elif ch == 3:
		key[9] = byte_add(key[2], key[1])
		key[11] = byte_add(key[6], key[5])
		key[12] = byte_add(key[8], key[7])
		key[13] = byte_add(key[11], key[10])
	elif ch == 4:
		key[0] = byte_add(key[1], 111)
		key[3] = byte_add(key[4], 71)
		key[4] = byte_add(key[5], 17)
		key[14] = byte_add(key[15], 64)
	elif ch == 5:
		key[2] = byte_add(key[2], key[10])
		key[4] = byte_add(key[5], key[12])
		key[6] = byte_add(key[8], key[14])
		key[8] = byte_add(key[11], key[0])
	elif ch == 6:
		key[9] = byte_add(key[11], key[1])
		key[11] = byte_add(key[13], key[3])
		key[13] = byte_add(key[15], key[5])
		key[15] = byte_add(key[9], key[7])
		key[1] = byte_add(key[9], key[5])
		key[2] = byte_add(key[10], key[6])
		key[3] = byte_add(key[11], key[7])
		key[4] = byte_add(key[12], key[8])
	elif ch == 7:
		key[1] = byte_add(key[9], key[5])
		key[2] = byte_add(key[10], key[6])
		key[3] = byte_add(key[11], key[7])
		key[4] = byte_add(key[12], key[8])
	return key