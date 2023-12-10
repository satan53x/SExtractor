import bisect
import re
from var_extract import *

ExVar = gExtractVar

#----------------------------------------------------------
globalDic = {}

def GetG(key):
	return globalDic[key]

def SetG(key, value):
	globalDic[key] = value

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

def printWarningGreen(tip, *args):
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

#----------------------------------------------------------
def getMatchItem(lst, target):
    for item in lst:
        if item['min'] <= target <= item['max']:
            return item
    return None