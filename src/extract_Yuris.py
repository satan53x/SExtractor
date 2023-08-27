import re
from common import *
from extract_BIN import replaceOnceImp as replaceOnceImpBIN
from extract_BIN import parseImp as parseImpBIN
from extract_TXT import ParseVar, searchLine, initParseVar

OldEncodeName = 'cp932'
NewEncodeName = 'gbk'
selMinCount = 10 #提取时选项函数最小参数个数
selMaxCount = 99 #提取时选项函数最大参数个数
#版本对应code
Codes = [
	{'min': 0x1DC, 'max': 0x1DC, 'sce': 0x5A, 'sel': 0x1D},
	{'min': 0x1E1, 'max': 0x1E8, 'sce': 0x6A, 'sel': 0x2C},
	{'min': 0x1F4, 'max': 0x1F4, 'sce': 0x5A, 'sel': 0x1D},
	{'min': 0x1C2, 'max': 0xFFF, 'sce': 0x5B, 'sel': 0x1D}
]

insertContent = {}
# ---------------- Engine: Yu-ris -------------------
def initExtra():
	global selMinCount
	global selMaxCount
	lst = GetG('Var').extraData.split(',')
	if len(lst) > 0:
		selMinCount = int(lst[0]) or 10
	if len(lst) > 1:
		selMaxCount = int(lst[1]) or 99

def parseImp(content, listCtrl, dealOnce):
	if not content: return
	initExtra()
	var = ParseVar(listCtrl, dealOnce)
	var.OldEncodeName = OldEncodeName
	initParseVar(var)
	funcList = manager.splitFunc()
	paraIndex = 0
	for i in range(len(funcList)):
		code, count, textType = funcList[i]
		if textType == 0:
			#文本
			dealStr(content, var, paraIndex)
		elif textType == 1:
			#选项
			if selMinCount <= count <= selMaxCount:
				for j in range(count):
					dealStr(content, var, paraIndex + j)
		paraIndex += count

#处理单个bin字符串
def dealStr(content, var:ParseVar, paraIndex):
	contentIndex = manager.getContentIndex(paraIndex)
	var.lineData = content[contentIndex]['text']
	var.contentIndex = contentIndex
	ctrls = searchLine(var)
	if ctrls and len(ctrls) > 0:
		content[contentIndex]['ref'].append(paraIndex)

# -----------------------------------
def replaceOnceImp(content, lCtrl, lTrans):
	for i, ctrl in enumerate(lCtrl):
		# 位置
		ctrl = lCtrl[i]
		posData = ctrl['pos']
		contentIndex = posData[0]
		start = posData[1]
		end = posData[2]
		transData = generateBytes(lTrans[i], end - start, NewEncodeName)
		if transData == None:
			return False
		#写入new
		data = content[contentIndex]
		strNew = data['text'][:start] + transData + data['text'][end:]
		data['text'] = strNew
	return True

#修正长度与偏移
def replaceEndImp(content):
	if not content: return
	#重新计算str区偏移
	offset = 0
	for data in content:
		#计算偏移
		data['newOff'] = offset
		newLen = len(data['text'])
		diff = newLen - data['oldLen']
		if diff != 0:
			#修正para中长度
			for paraIndex in data['ref']:
				item = manager.paraList[paraIndex]
				if item[1] != data['oldLen']:
					#检查para中长度
					print('para和str长度不一致', data)
				item[1] += diff 
		offset += newLen
	manager.strLen = offset
	#重建paraSec
	manager.paraSec = bytearray()
	for item in manager.paraList:
		other, length, offset = item
		if length > 0:
			#修正
			contentIndex = manager.offsetDic[offset]
			data = content[contentIndex]
			offset = data['newOff'] #新的偏移
		#参数区
		manager.paraSec.extend(int2bytes(other))
		manager.paraSec.extend(int2bytes(length))
		manager.paraSec.extend(int2bytes(offset))
	#合并
	manager.fixHeader()
	insertContent[0] = manager.headerSec + manager.funcSec + manager.paraSec
	#还原content
	for i, data in enumerate(content):
		content[i] = data['text']
	
# -----------------------------------
def readFileDataImp(fileOld, contentSeprate):
	data = fileOld.read()
	#解析
	if not manager.init(data):
		return [], []
	content = manager.splitParaStr()
	insertContent.clear()
	insertContent[0] = b''
	insertContent[len(content)] = manager.otherSec
	return content, insertContent

# -----------------------------------
#管理器
class DataManager():
	def splitParaStr(self):
		self.paraList = []
		dataDic = {}
		pos = 0
		while pos < self.paraLen:
			#单个para对应单个str
			other = readInt(self.paraSec, pos)
			pos += 4
			length = readInt(self.paraSec, pos)
			pos += 4
			offset = readInt(self.paraSec, pos)
			pos += 4
			#正常保存字节
			self.paraList.append([
				other,
				length,
				offset
			])
			if length > 0:
				#关联str
				if offset not in dataDic:
					#新增
					dataDic[offset] = {
						'oldOff': offset,
						'ref': []
					}
		#字典排序
		dataDic = dict(sorted(dataDic.items()))
		content = []
		contentIndex = 0
		self.offsetDic = {}
		#新增到content
		for offset, data in dataDic.items():
			self.offsetDic[offset] = contentIndex
			contentIndex += 1
			content.append(data)
		#计算content子项长度
		for i in range(len(content)):
			data = content[i]
			offset = data['oldOff']
			if i >= len(content) - 1:
				nextOff = self.strLen
			else:
				nextOff = content[i+1]['oldOff']
			data['oldLen'] = nextOff - offset
			data['text'] = self.strSec[offset:nextOff]
		return content
	
	def getContentIndex(self, paraIndex):
		offset = self.paraList[paraIndex][2]
		return self.offsetDic[offset]

	def splitFunc(self):
		funcList = []
		pos = 0
		while pos < self.funcLen:
			#单个func
			code = readInt(self.funcSec, pos, 1)
			pos += 1
			count = readInt(self.funcSec, pos, 1)
			pos += 3
			textType = -1
			if code == self.codeSce: #文本
				textType = 0
			elif code == self.codeSel: #选项
				textType = 1
			#正常保存字节
			funcList.append([
				code,
				count,
				textType
			])
		return funcList

	def fixHeader(self):
		if self.version >= 0x1C2:
			self.headerSec[20:24] = int2bytes(self.strLen)

	def init(self, data):
		#header
		self.headerLen = 0x20
		self.version = readInt(data, 4)
		if self.version >= 0x1C2:
			self.funcLen = readInt(data, 12)
			self.paraLen = readInt(data, 16)
			self.strLen = readInt(data, 20)
			self.otherLen = readInt(data, 24)
		else:
			print(f'\033[33m当前ybn版本暂不支持\033[0m: {self.version:X}')
			return None
		#code
		self.codeSce = 0
		self.codeSel = 0
		for item in Codes:
			if item['min'] <= self.version <= item['max']:
				self.codeSce = item['sce']
				self.codeSel = item['sel']
				break
		#header
		start = 0
		end = self.headerLen
		self.headerSec = bytearray(data[start:end])
		#func
		start = end
		end = start + self.funcLen
		self.funcSec = bytearray(data[start:end])
		#para
		start = end
		end = start + self.paraLen
		self.paraSec = data[start:end]
		#str
		start = end
		end = start + self.strLen
		self.strSec = data[start:end]
		#other
		start = end
		end = start + self.otherLen
		self.otherSec = bytearray(data[start:end])
		return self
	
manager = DataManager()