
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
    try:
        transData = text.encode(NewEncodeName)
    except Exception as ex:
        print(ex)
        return None
    # 检查长度
    lenTrans = len(transData)
    #print(contentIndex, start, end)
    count = lenOrig - lenTrans
    #print('Diff', count)
    if count < 0:
        transData = transData[0:lenOrig]
        print('\033[33m译文长度超出原文，部分截断\033[0m', text)
        try:
            transData.decode(NewEncodeName)
        except Exception as ex:
            #print('\033[31m截断后编码错误\033[0m')
            return None
    else:
        # 右边补足空格
        #print(transData)
        empty = bytearray(count)
        for i in range(int(count)):
            empty[i] = 0x20
        transData += empty
    return transData