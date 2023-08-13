import bisect

globalDic = {}

def GetG(key):
	return globalDic[key]

def SetG(key, value):
	globalDic[key] = value

#判断是否是日文
def isShiftJis(byte1, byte2):
    # 检查字节范围
    if (byte1 >= 0x81 and byte1 <= 0x9F) or (byte1 >= 0xE0 and byte1 <= 0xEF):
        if (byte2 >= 0x40 and byte2 <= 0x7E) or (byte2 >= 0x80 and byte2 <= 0xFC):
            return True
    return False

#编码生成目标长度的字节数组，会截断和填充字节
def generateBytes(text, lenOrig, NewEncodeName):
    transData = None
    try:
        transData = text.encode(NewEncodeName)
    except Exception as ex:
        print(ex)
        return None
    if GetG('Var').cutoff == False:
         return transData
    # 检查长度
    count = lenOrig - len(transData)
    #print('Diff', count)
    if count < 0:
        dic = GetG('Var').cutoffDic
        if text not in dic:
            if GetG('Var').cutoffCopy:
                 dic[text] = [text, count]
            else:
                dic[text] = ['', count]
        elif dic[text][0] != '':
            #从cutoff字典读取
            transData = dic[text][0].encode(NewEncodeName)
            count = lenOrig - len(transData)
            dic[text][0] = count #刷新长度
        if count < 0:
            print('\033[33m译文长度超出原文，部分截断\033[0m', text)
            transData = transData[0:lenOrig]
            try:
                transData.decode(NewEncodeName)
            except Exception as ex:
                #print('\033[31m截断后编码错误\033[0m')
                return None
    if count > 0:
        # 右边补足空格
        #print(transData)
        empty = bytearray(count)
        for i in range(int(count)):
            empty[i] = 0x20
        transData += empty
    return transData


def findInsertIndex(sortedList, target):
    position = bisect.bisect_left(sortedList, target)
    return position

def readInt(data, pos, byteNum=4):
    return int.from_bytes(data[pos:pos+byteNum], byteorder='little')

