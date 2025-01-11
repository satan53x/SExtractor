import re
import struct
from common import *
from extract_BIN import replaceOnceImp as replaceOnceImpBIN
from extract_BIN import parseImp as parseImpBIN

# ---------------- Engine: Silky map -------------------
def parseImp(content, listCtrl, dealOnce):
	parseImpBIN(content, listCtrl, dealOnce)

# -----------------------------------
def replaceOnceImp(content, lCtrl, lTrans):
	return replaceOnceImpBIN(content, lCtrl, lTrans)

def replaceEndImp(content):
	data = manager.write(content)
	content.clear()
	content.append(data)

# -----------------------------------
def readFileDataImp(fileOld, contentSeparate):
	#init
	lst = ExVar.extractKey.split(',')
	lst = [int(i) for i in lst]
	manager.init(lst)
	#读取
	data = fileOld.read()
	content = manager.read(data)
	return content, {}

# ------------------------------------------------------
class Manager:
	secNum = 4 #分区数

	def init(self, lst):
		self.secIndexList = lst #需要处理的分区序号列表

	def read(self, data):
		self.sectionList = []
		pos = 0
		for i in range(self.secNum):
			offset = readInt(data, pos)
			pos += 4
			count = readInt(data, pos)
			pos += 4
			section = Section()
			section.read(data, offset, count)
			self.sectionList.append(section)
		#合并需要处理的分区
		content = []
		for secIndex in self.secIndexList:
			section = self.sectionList[secIndex]
			content.extend(section.itemList)
		return content
	
	def write(self, content):
		#覆盖需要处理的分区
		start = 0
		for secIndex in self.secIndexList:
			section = self.sectionList[secIndex]
			end = start + len(section.itemList)
			section.itemList = content[start:end]
			start = end
		#文件头
		data = bytearray(self.secNum*8)
		pos = 0
		for i in range(self.secNum):
			section = self.sectionList[i]
			#索引
			data[pos:pos+4] = int2bytes(len(data))
			pos += 4
			data[pos:pos+4] = int2bytes(len(section.itemList))
			pos += 4
			#内容
			section.write(data)
		return data

class Section:
	pattern = re.compile(rb'\x00{2}')

	def read(self, data, indexPos, count):
		self.itemList = []
		for i in range(count):
			itemPos = readInt(data, indexPos)
			indexPos += 4
			m = self.pattern.search(data, itemPos)
			if not m:
				printError('Wrong item address at ', hex(itemPos))
				raise Exception('Wrong item address')
			item = data[itemPos : m.end()]
			self.itemList.append(item)
	
	def write(self, data):
		indexPos = len(data)
		count = len(self.itemList)
		secHead = bytearray(count * 4)
		data.extend(secHead)
		itemPos = indexPos + len(secHead)
		#写入
		for item in self.itemList:
			#索引
			data[indexPos:indexPos+4] = int2bytes(itemPos)
			indexPos += 4
			#内容
			data.extend(item)
			itemPos += len(item)

manager = Manager()