import re
import struct
from common import *
from extract_TXT import ParseVar, searchLine, initParseVar
from helper_text import generateBytes


selMinCount = 10 #提取时选项函数最小参数个数
selMaxCount = 99 #提取时选项函数最大参数个数
#版本对应code
Codes = [
	{'min': 0x1DC, 'max': 0x1DC, 'sce': [0x5A], 'sel': [0x1D], 'endpara': []},
	{'min': 0x1E1, 'max': 0x1EB, 'sce': [0x6A], 'sel': [0x2C], 'endpara': []},
	{'min': 0x1F4, 'max': 0x1F4, 'sce': [0x5A], 'sel': [0x1D], 'endpara': []},
	{'min': 0x1C2, 'max': 0x22A, 'sce': [0x5B], 'sel': [0x1D, 0x27], 'endpara': []},
	{'min': 0x22B, 'max': 0xFFF, 'sce': [0x6C], 'sel': [0x2B], 'endpara': []},
	{'min': 0x000, 'max': 0x010, 'sce': [0x33], 'sel': [0x27], 'endpara': [], 'retcode': 0xFF, 'nostr': [0x19, 0x26]},
	{'min': 0x000, 'max': 0x0E0, 'sce': [0x4A], 'sel': [0x16], 'endpara': [0x32], 'retcode': 0xFF, 'nostr': [0x1E, 0x32]},
	{'min': 0x0EE, 'max': 0x0EE, 'sce': [0x25], 'sel': [0x14], 'endpara': [], 'retcode': 0x2D, 'nostr': []},
	{'min': 0x000, 'max': 0x1C1, 'sce': [0x57], 'sel': [0x1A], 'endpara': [], 'retcode': 0x3B, 'nostr': []},
	{'min': 0x000, 'max': 0xFFF, 'sce': [0x5A], 'sel': [0x1D], 'endpara': [], 'retcode': 0xFF, 'nostr': []},
]
Keys = [
	{'min': 0x1E1, 'max': 0x1E8, 'key': b'\x0B\x8F\x00\xB1'},
	{'min': 0x0, 'max': 0x22A, 'key': b'\xD3\x6F\xAC\x96'},
	{'min': 0x22B, 'max': 0xFFF, 'key': b'\xA9\xF8\xCC\x66'},
]

insertContent = {}
outputAll = False
# ---------------- Engine: Yu-ris -------------------
def initExtra():
	global selMinCount, selMaxCount
	global outputAll
	if ExVar.extraData == 'all':
		selMinCount = 1
		outputAll = True
		return
	else:
		outputAll = False
	lst = ExVar.extraData.split(',')
	if len(lst) > 0:
		selMinCount = int(lst[0]) or 10
	if len(lst) > 1:
		selMaxCount = int(lst[1]) or 99

def parseImp(content, listCtrl, dealOnce):
	if not content: return
	initExtra()
	var = ParseVar(listCtrl, dealOnce)
	var.OldEncodeName = ExVar.OldEncodeName
	initParseVar(var)
	paraIndex = 0
	for i, cmd in enumerate(manager.cmdList):
		count, textType = cmd[1], cmd[2]
		if textType == 0 or textType == 10:
			#文本
			dealStr(content, var, paraIndex, cmd)
		elif textType == 1 or (outputAll and textType > -2):
			#选项
			if selMinCount <= count <= selMaxCount:
				for j in range(count):
					dealStr(content, var, paraIndex + j, cmd)
		paraIndex += count

#处理单个bin字符串
def dealStr(content, var:ParseVar, paraIndex, cmd):
	contentIndex = manager.getContentIndex(paraIndex)
	var.lineData = content[contentIndex]['text']
	var.contentIndex = contentIndex
	ctrls = searchLine(var)
	if ctrls and len(ctrls) > 0:
		content[contentIndex]['ref'].append(paraIndex)
		if cmd[2] == 10: #textType
			if 'unfinish' in ctrls[-1]:
				del ctrls[-1]['unfinish']
		if outputAll:
			printDebug(f'Code<{cmd[0]:02X}>: {ExVar.listOrig[-1]}')

# -----------------------------------
def replaceOnceImp(content, lCtrl, lTrans):
	for i, ctrl in enumerate(lCtrl):
		# 位置
		ctrl = lCtrl[i]
		contentIndex, start, end = ctrl['pos']
		transData = generateBytes(lTrans[i], end - start, ExVar.NewEncodeName)
		if transData == None:
			return False
		#写入new
		data = content[contentIndex]
		strNew = data['text'][:start] + transData + data['text'][end:]
		data['text'] = bytearray(strNew)
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
				item:ParaItem = manager.paraList[paraIndex]
				#修正控制str的内部长度
				if 0x41 <= data['text'][0] <= 0x5A: #A-Z
					inLen = readInt(data['text'], 1, 2)
					if inLen == data['oldLen'] - 3: #去掉开头3个控制字节的长度
						data['text'][1:3] = int2bytes(inLen + diff, 2)
				#修正外部长度
				if item.length != data['oldLen']:
					#检查para中长度
					print('para和str长度不一致', data)
				item.length += diff
				data['oldLen'] += diff
		offset += newLen
	manager.strLen = offset
	#重建paraSec
	manager.paraSec = bytearray()
	for item in manager.paraList:
		if item.length > 0: #长度大于0
			#修正
			contentIndex = manager.offsetDic[item.offset]
			data = content[contentIndex]
			item.offset = data['newOff'] #新的偏移
		#参数区
		bs = item.pack()
		manager.paraSec.extend(bs)
	#合并
	manager.fixSections(content)
	insertContent[0] = manager.headerSec + manager.cmdSec + manager.paraSec
	insertContent[len(content)] = manager.otherSec
	
# -----------------------------------
def readFileDataImp(fileOld, contentSeparate):
	data = fileOld.read()
	if not re.match(r'yst\d+', ExVar.filename):
		#控制脚本
		if ExVar.filename == 'ysc':
			manager.initConfig(data)
		return [], {0:data}
	#解析
	if not manager.init(data):
		return [], {0:data}
	if manager.structType == 2:
		content = manager.splitParaStr2()
	else:
		content = manager.splitParaStr()
	insertContent.clear()
	insertContent[0] = b''
	#insertContent[len(content)] = manager.otherSec
	return content, insertContent

# -----------------------------------
#管理器
class DataManager():
	OneParaLen = 0xC
	structType = 1 #文件结构 1:v>=1C2, 2:v<1C2

	def splitParaStr(self):
		self.splitCmd()
		self.paraList = []
		dataDic = {}
		pos = 0
		while pos < self.paraLen:
			#单个para对应单个str
			item = ParaItem()
			item.unpack(self.paraSec[pos:pos+self.OneParaLen])
			pos += self.OneParaLen
			#正常保存字节
			self.paraList.append(item)
			if item.length > 0:
				#关联str
				if item.offset not in dataDic:
					#新增
					dataDic[item.offset] = {'oldOff': item.offset, 'ref': []}
		return self.splitContent(dataDic)

	def splitContent(self, dataDic):
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
		offset = self.paraList[paraIndex].offset
		return self.offsetDic[offset]

	def splitCmd(self):
		self.cmdList = []
		pos = 0
		while pos < self.cmdLen:
			#单个command
			code = readInt(self.cmdSec, pos, 1)
			pos += 1
			count = readInt(self.cmdSec, pos, 1)
			pos += 3
			textType = -1
			if code in self.codeSce: #文本
				textType = 0
			elif code in self.codeSel: #选项
				textType = 1
			if code in self.codeEndpara: #段落结束
				if textType == 0:
					textType = 10
				elif len(self.cmdList) > 0:
					if self.cmdList[-1][textType] == 0:
						self.cmdList[-1][textType] = 10
			#正常保存字节
			self.cmdList.append([code, count, textType])

	def fixSections(self, content:list):
		if self.structType == 2:
			self.headerSec[0xC:0x10] = int2bytes(self.strLen)
			self.fixSectionCmd2()
		else:
			self.headerSec[0x14:0x18] = int2bytes(self.strLen)
		#还原content
		self.strSec = bytearray()
		for i, data in enumerate(content):
			self.strSec.extend(data['text'])
		#加密
		self.decodeAll()
		#设置content
		content.clear()
		content.append(self.strSec)

	def init(self, data):
		#header
		self.headerLen = 0x20
		self.OneParaLen = 0xC
		v = int(ExVar.version, 0)
		if v > 0: 
			self.version = v
		else:
			self.version = readInt(data, 4)
		if self.version >= 0x1C2:
			self.cmdLen = readInt(data, 0xC)
			self.paraLen = readInt(data, 0x10)
			self.strLen = readInt(data, 0x14)
			self.otherLen = readInt(data, 0x18)
			self.structType = 1
		elif self.version < 0x1C2:
			self.cmdLen = readInt(data, 0x8)
			self.paraLen = 0
			self.strLen = readInt(data, 0xC)
			self.otherLen = 0
			self.structType = 2
			if self.version <= 0xE0:
				self.OneParaLen = 0x10
			if self.version <= 0x10:
				self.cmdHeadLen = 0xC
			else:
				self.cmdHeadLen = 0x6
		else:
			print(f'\033[33m当前ybn版本暂不支持\033[0m: 0x{self.version:X}')
			return None
		#code
		self.codeSce = 0
		self.codeSel = 0
		if self.codeDic != {}:
			#从ysc设置
			item = Codes[-1]
		else:
			item = getMatchItem(Codes, self.version)
		if item:
			self.codeSce = item['sce']
			self.codeSel = item['sel']
			self.codeEndpara = item['endpara']
			if 'retcode' in item:
				self.codeRetcode = item['retcode']
			if 'nostr' in item:
				self.codeNostr = item['nostr']
		if ExVar.endStr:
			lst = ExVar.endStr.split(',')
			self.codeEndpara = [int(c, 16) for c in lst]
		#header
		start = 0
		end = self.headerLen
		self.headerSec = bytearray(data[start:end])
		#cmd
		start = end
		end = start + self.cmdLen
		self.cmdSec = bytearray(data[start:end])
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
		self.otherSec = data[start:end]
		#解密
		self.findKey()
		self.decodeAll()
		return self
	
	def findKey(self):
		if ExVar.decrypt == '': return
		if ExVar.decrypt.startswith('auto') or ExVar.decrypt == 'default':
			#自动
			item = getMatchItem(Keys, self.version)
			if item:
				self.xorKey = item['key']
			else:
				print(f'\033[33m没有匹配的密钥\033[0m: 0x{self.version:X}')
				return
		else:
			#escape
			self.xorKey =  ExVar.decrypt.encode().decode('unicode_escape').encode('latin-1')
		#解密验证
		#第一个偏移，一般应该为0
		if self.structType == 2:
			bOffset = xorBytes(self.cmdSec[self.OneParaLen+2:self.OneParaLen+6], self.xorKey)
		else:
			bOffset = xorBytes(self.paraSec[0x8:0xC], self.xorKey) 
		if readInt(bOffset, 0) != 0:
			key = xorBytes(bOffset, self.xorKey)
			keyStr = f'\\x{key[0]:02X}\\x{key[1]:02X}\\x{key[2]:02X}\\x{key[3]:02X}'
			if ExVar.decrypt == 'auto':
				self.xorKey = key
				printWarning('默认密钥可能不正确，密钥已自动替换为:', keyStr)
			else:
				printWarning('默认密钥可能不正确，猜测密钥为:', keyStr)

	def decodeAll(self):
		if ExVar.decrypt == '': return
		#解密
		self.cmdSec = xorBytes(self.cmdSec, self.xorKey)
		self.paraSec = xorBytes(self.paraSec, self.xorKey)
		self.strSec = xorBytes(self.strSec, self.xorKey)
		self.otherSec = xorBytes(self.otherSec, self.xorKey)

	codeDic = {}
	#ysc.bin初始化配置
	def initConfig(self, data):
		printWarningGreen('尝试从ysc.bin读取指令配置')
		self.codeDic.clear()
		pos = 0x8
		codeNum = readInt(data, pos)
		pos += 0x8
		for cmdCode in range(codeNum):
			#命令
			bs = readStr(data, pos)
			text = bs.decode('cp932')
			pos += len(bs) + 1 #结束\0
			paraCount = data[pos]
			pos += 1
			self.codeDic[text] = [cmdCode, paraCount]
			if text == 'WORD':
				Codes[-1]['sce'] = [cmdCode]
				printInfo('命令：', text, hex(cmdCode), paraCount)
			elif text == 'GOSUB':
				Codes[-1]['sel'] = [cmdCode]
				printInfo('命令：', text, hex(cmdCode), paraCount)
			elif text == 'RETURNCODE':
				Codes[-1]['retcode'] = cmdCode
				printInfo('命令：', text, hex(cmdCode), paraCount)
			else:
				printDebug('命令：', text, hex(cmdCode), paraCount)
			for paraCode in range(paraCount):
				#参数
				bs = readStr(data, pos)
				#text = bs.decode('cp932')
				pos += len(bs) + 3
				#printDebug('    参数：', text, hex(paraCode))

	#-------------------------- structType 2 ------------------------------
	def splitParaStr2(self):
		self.splitCmd2()
		self.paraList = []
		dataDic = {}
		pos = 0
		for _, count, textType, headLen in self.cmdList:
			pos += headLen
			for i in range(count):
				#单个para对应单个str
				item = ParaItem()
				item.unpack(self.cmdSec[pos:pos+self.OneParaLen], textType <= -2)
				pos += self.OneParaLen
				#正常保存字节
				self.paraList.append(item)
				if item.length > 0:
					#关联str
					if item.offset not in dataDic:
						#新增
						dataDic[item.offset] = {'oldOff': item.offset, 'ref': []}
		return self.splitContent(dataDic)

	def splitCmd2(self):
		self.cmdList = []
		pos = 0
		while pos < self.cmdLen:
			#单个command
			headLen = self.cmdHeadLen
			if self.cmdHeadLen == 0xC:
				code, count = struct.unpack('<II', self.cmdSec[pos:pos+8])
			else:
				code, count = struct.unpack('<BB', self.cmdSec[pos:pos+2])
			textType = -1
			if code in self.codeSce: #文本
				textType = 0
			elif code in self.codeSel: #选项
				textType = 1
			elif code == self.codeRetcode: #retcode
				count = 0
				headLen += 8
			elif code in self.codeNostr: #无str
				textType = -2
			if code in self.codeEndpara: #段落结束
				if textType == 0:
					textType = 10
				elif len(self.cmdList) > 0:
					if self.cmdList[-1][textType] == 0:
						self.cmdList[-1][textType] = 10
			pos += headLen
			pos += count * self.OneParaLen
			#正常保存字节
			self.cmdList.append([code, count, textType, headLen])

	def fixSectionCmd2(self):
		#该结构并没有paraSec，并入cmdSec
		posInPara = 0
		pos = 0
		for _, count, textType, headLen in self.cmdList:
			pos += headLen
			for i in range(count):
				#单个para对应单个str
				self.cmdSec[pos:pos+self.OneParaLen] = self.paraSec[posInPara:posInPara+self.OneParaLen]
				pos += self.OneParaLen
				posInPara += self.OneParaLen
		#清空paraSec
		self.paraSec = b''

# ---------------------------------------------------------
class ParaItem():
	def __init__(self):
		self.pre = b''
		self.length = -1
		self.offset = -1

	def unpack(self, data, nostr=False):
		if manager.OneParaLen == 0x10:
			if nostr:
				self.pre = struct.unpack('<16s', data)[0] #pre
			else:
				self.pre, self.length, self.offset = struct.unpack('<8sII', data)
		else:
			self.pre, self.length, self.offset  = struct.unpack('<4sII', data)

	def pack(self):
		if manager.OneParaLen == 0x10:
			if self.length < 0:
				bs = struct.pack('<16s', self.pre)
			else:
				bs = struct.pack('<8sII', self.pre, self.length, self.offset)
		else:
			bs = struct.pack('<4sII', self.pre, self.length, self.offset)
		return bs

manager = DataManager()
