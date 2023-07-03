import re
import os
from bisect import bisect_left

globalDic = {}

def GetG(key):
	return globalDic[key]

def SetG(key, value):
	globalDic[key] = value

#查找最近数字
def findClosest(myList, myNumber):
	pos = bisect_left(myList, myNumber)
	#print('bisect_left ', pos)
	if pos == 0:
		return pos
	if pos == len(myList):
		return pos - 1
	before = myList[pos - 1]
	after = myList[pos]
	#print(before, myNumber, after)
	#print(after - myNumber, myNumber - before)
	if after - myNumber <= myNumber - before:
		#print('after')
		return pos
	else:
		#print('before')
		return pos - 1

#重新划分
# text 总文本
# lengthList 每行长度列表
def redistributeLines(text, lengthList, splitPattern):
	if len(lengthList) == 1: return [text] #只有一行
	#print(text)
	#print(posList)
	# 旧索引表
	oldIndexes = []
	for length in lengthList:
		count = len(oldIndexes)
		if count == 0:
			oldIndexes.append(length)
		else:
			oldIndexes.append(length + oldIndexes[count-1])
	#print(oldIndexes)
	# 搜索结果索引表
	ret = re.finditer(splitPattern, text)
	retList = list(ret)
	#print(retList)
	findIndexes = []
	textEnd = len(text)
	for pos in retList:
		findIndexes.append(pos.end())
	if len(findIndexes) == 0 or findIndexes[-1] != textEnd:
		#添加行尾
		findIndexes.append(textEnd)
	#print(findIndexes)
	# 新索引表
	newIndexes = []
	oldCount = len(oldIndexes)
	findCount = len(findIndexes)
	if findCount < oldCount:
		#搜索表小 则 保持原样
		newIndexes = oldIndexes
		#print('Keep text: ', posList[0][0])
	elif findCount == oldCount:
		#表行不变 则 使用搜索结果
		newIndexes = findIndexes
	else:
		#搜索表大 则 取接近值
		start = 0
		end = 0
		for i in range(oldCount - 1):
			oldIndex = oldIndexes[i]
			end = i - oldCount + 1
			pos = findClosest(findIndexes[start:end], oldIndex) + start
			start = pos + 1
			#print(pos)
			newIndex = findIndexes[pos]
			#print(newIndex)
			newIndexes.append(newIndex)
		newIndexes.append(oldIndexes[-1]) #最后一个固定为末尾
	#print(newIndexes)
	# 新行
	lines = []
	start = 0
	end = 0
	for index in newIndexes:
		start = end
		end = index
		#print(start, end)
		newLine = text[start:end]
		if newLine == '':
			print('-------------------------------------------------')
			print(text)
			print(oldIndexes)
			print(findIndexes)
			print(newIndexes)
			#os.system("pause")
		lines.append(newLine)
	#print(lines)
	#os.system("pause")
	return lines
