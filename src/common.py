import bisect
import os
import re
from var_extract import *

ExVar = gExtractVar

#----------------------------------------------------------
class TextType:
     MESSAGE = 1
     NAME = 2
     SELECT = 3

#----------------------------------------------------------
def printError(tip, *args):
    if not ExVar.printSetting[4]: return
    print(f'\033[31m{tip}\033[0m', end=' ')
    for arg in args:
        print(arg, end=' ')
    print('')

def printWarning(tip, *args):
    if not ExVar.printSetting[3]: return
    print(f'\033[33m{tip}\033[0m', end=' ')
    for arg in args:
        print(arg, end=' ')
    print('')

def printTip(tip, *args):
    if not ExVar.printSetting[2]: return
    print(f'\033[32m{tip}\033[0m', end=' ')
    for arg in args:
        print(arg, end=' ')
    print('')

def printInfo(tip, *args):
    if not ExVar.printSetting[1]: return
    print(tip, end=' ')
    for arg in args:
        print(arg, end=' ')
    print('')

def printDebug(tip, *args):
    if not ExVar.printSetting[0]: return
    print(tip, end=' ')
    for arg in args:
        print(arg, end=' ')
    print('')

#----------------------------------------------------------
#判断是否是日文
def isShiftJis(byte1, byte2):
    # 检查字节范围
    if (byte1 >= 0x81 and byte1 <= 0x9F) or (byte1 >= 0xE0 and byte1 <= 0xEF) or (byte1 >= 0xFA and byte1 <= 0xFB):
        if (byte2 >= 0x40 and byte2 <= 0x7E) or (byte2 >= 0x80 and byte2 <= 0xFC):
            return 2
    elif byte1 == 0xFC:
        if (byte2 >= 0x40 and byte2 <= 0x4B):
            return 2
    return 0

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

#查找第一个UTF-8
def findFirstUTF8(data, pos):
    length = 0
    #查询长度
    if (data[pos] & 0x80) == 0x00:
        length = 1
    elif (data[pos] & 0xE0) == 0xC0:
        length = 2
    elif (data[pos] & 0xF0) == 0xE0:
        length = 3
    elif(data[pos] & 0xF8) == 0xF0:
        length = 4
    else:
        return -1
    #检查后续字节是否合法
    for i in range(1, length):
        if (data[pos+i] & 0xC0) != 0x80:
            return -1
    return length

#----------------------------------------------------------
def findInsertIndex(sortedList, target):
    position = bisect.bisect_left(sortedList, target)
    return position

def findNearestIndex(sortedList, target):
    position = bisect.bisect_left(sortedList, target)
    if position >= len(sortedList):
        position = len(sortedList) - 1
    elif position > 0:
        left = sortedList[position - 1]
        right = sortedList[position]
        if right - target >= target - left:
            position -= 1
    return position

def readInt(data, pos, byteNum=4):
    return int.from_bytes(data[pos:pos+byteNum], byteorder='little')

def int2bytes(i, l=4):
    return int.to_bytes(i, byteorder='little', length=l)

def readStr(data, pos, endByte=0):
    start = pos
    while pos < len(data):
        if data[pos] == endByte:
            #不包含结尾字节
            #pos += 1
            break
        pos += 1
    return data[start:pos]

def xorBytes(input, xorTable):
    if not xorTable:
        return bytearray(input)
    result = bytearray()
    xorLen = len(xorTable)
    for i, b in enumerate(input):
        xorByte = xorTable[i % xorLen]
        result.append(b ^ xorByte)
    return result

def printHex(b):
    c = -1
    for i in b:
        c += 1
        if c % 16 == 0 and c > 0: print('')
        print(f'{i:02X} ', end='')
    print('')

#----------------------------------------------------------
def getMatchItem(lst, target):
    for item in lst:
        if item['min'] <= target <= item['max']:
            return item
    return None

def getPatternGroupDict(p:re.Pattern):
    dic = {}
    for name, index in p.groupindex.items(): #分组名信息
        dic[index] = name #序号为key
    return dic

#----------------------------------------------------------
def listFiles(start_path):
	file_list = []
	for root, dirs, files in os.walk(start_path):
		for file in files:
			# 获取相对路径
			relative_path = os.path.relpath(os.path.join(root, file), start_path)
			file_list.append(relative_path)
	return file_list 

#----------------------------------------------------------
class AddrFixer:
	def __init__(self, baseAddr=0) -> None:
		self.pointList = []
		self.realList = []
		self.baseAddr = baseAddr

	def isEmpty(self) -> None:
		return not self.pointList and not self.realList
	
	#pointAddr 指针地址
	#realAddr 真实地址
	def listen(self, pointAddr, realAddr):
		if pointAddr in self.pointList:
			return
		realAddr = self.baseAddr + realAddr
		self.pointList.append(pointAddr)
		self.realList.append(realAddr)
		
	def fix(self, addr, diff):
		for i, pointAddr in enumerate(self.pointList):
			if addr < pointAddr:
				self.pointList[i] += diff
		for i, realAddr in enumerate(self.realList):
			if addr < realAddr:
				self.realList[i] += diff

	def apply(self, data):
		for i, pointAddr in enumerate(self.pointList):
			realAddr = self.realList[i]
			saveAddr = realAddr - self.baseAddr
			data[pointAddr:pointAddr+4] = int2bytes(saveAddr)
			printDebug('地址修正:', f'{pointAddr:08X}: {saveAddr:08X}')
