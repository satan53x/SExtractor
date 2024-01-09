def printHex(b):
	c = -1
	for i in b:
		c += 1
		if c % 16 == 0 and c > 0: print('')
		print(f'{i:02X} ', end='')
	print('')

def isShiftJis(byte1, byte2):
	# 检查字节范围
	if (byte1 >= 0x81 and byte1 <= 0x9F) or (byte1 >= 0xE0 and byte1 <= 0xEF) or (byte1 >= 0xFA and byte1 <= 0xFB):
		if (byte2 >= 0x40 and byte2 <= 0x7E) or (byte2 >= 0x80 and byte2 <= 0xFC):
			return 2
	elif byte1 == 0xFC:
		if (byte2 >= 0x40 and byte2 <= 0x4B):
			return 2
	return 0

def isEnglish(bs):
	for b in bs:
		if b < 0x20 or b > 0x7F:
			return 0
	return 1

def checkJIS(bytes, pattern):
    pos = 0
    end = len(bytes)
    while pos < end:
        #检查允许的单字节
        if pattern != '' and pattern.match(bytes[pos:pos+1]):
        #if chr(bytes[pos]) in '\r\n':
            pos += 1
            continue
        #检查双字节
        if end - pos < 2:
            return False
        offset = isShiftJis(bytes[pos], bytes[pos+1])
        if offset <= 0: 
            return False
        else:
            pos += offset
    return True