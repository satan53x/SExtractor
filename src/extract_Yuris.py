import re
from common import *
from extract_TXT import ParseVar, searchLine, initParseVar
from helper_text import generateBytes


selMinCount = 10 #提取时选项函数最小参数个数
selMaxCount = 99 #提取时选项函数最大参数个数
#版本对应code
Codes = [
	{'min': 0x1DC, 'max': 0x1DC, 'sce': 0x5A, 'sel': 0x1D},
	{'min': 0x1E1, 'max': 0x1EB, 'sce': 0x6A, 'sel': 0x2C},
	{'min': 0x1F4, 'max': 0x1F4, 'sce': 0x5A, 'sel': 0x1D},
	{'min': 0x1C2, 'max': 0x22A, 'sce': 0x5B, 'sel': 0x1D},
	{'min': 0x22B, 'max': 0xFFF, 'sce': 0x6C, 'sel': 0x2B},
	{'min': 0x0, 'max': 0xFFF, 'sce': 0x5A, 'sel': 0x1D},
]
Keys = [
	{'min': 0x1E1, 'max': 0x1E8, 'key': b'\x0B\x8F\x00\xB1'},
	{'min': 0x1C2, 'max': 0x22A, 'key': b'\xD3\x6F\xAC\x96'},
	{'min': 0x22B, 'max': 0xFFF, 'key': b'\xA9\xF8\xCC\x66'},
]

insertContent = {}
# ---------------- Engine: Yu-ris -------------------
def initExtra():
	global selMinCount
	global selMaxCount
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
	cmdList = manager.splitCmd()
	paraIndex = 0
	for i in range(len(cmdList)):
		code, count, textType = cmdList[i]
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
		transData = generateBytes(lTrans[i], end - start, ExVar.NewEncodeName)
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
	manager.fixSections(content)
	insertContent[0] = manager.headerSec + manager.cmdSec + manager.paraSec
	insertContent[len(content)] = manager.otherSec
	
# -----------------------------------
def readFileDataImp(fileOld, contentSeparate):
	if not re.match(r'yst\d+', ExVar.filename):
		#控制脚本
		if ExVar.filename == 'ysc':
			data = fileOld.read()
			manager.initConfig(data)
		return [], {}
	data = fileOld.read()
	#解析
	if not manager.init(data):
		return [], {}
	content = manager.splitParaStr()
	insertContent.clear()
	insertContent[0] = b''
	#insertContent[len(content)] = manager.otherSec
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

	def splitCmd(self):
		cmdList = []
		pos = 0
		while pos < self.cmdLen:
			#单个command
			code = readInt(self.cmdSec, pos, 1)
			pos += 1
			count = readInt(self.cmdSec, pos, 1)
			pos += 3
			textType = -1
			if code == self.codeSce: #文本
				textType = 0
			elif code == self.codeSel: #选项
				textType = 1
			#正常保存字节
			cmdList.append([
				code,
				count,
				textType
			])
		return cmdList

	def fixSections(self, content:list):
		if self.version >= 0x1C2:
			self.headerSec[20:24] = int2bytes(self.strLen)
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
		v = int(ExVar.version, 0)
		if v > 0: 
			self.version = v
		else:
			self.version = readInt(data, 4)
		if self.version >= 0x1C2:
			self.cmdLen = readInt(data, 12)
			self.paraLen = readInt(data, 16)
			self.strLen = readInt(data, 20)
			self.otherLen = readInt(data, 24)
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
		#header
		start = 0
		end = self.headerLen
		self.headerSec = bytearray(data[start:end])
		#cmd
		start = end
		end = start + self.cmdLen
		self.cmdSec = data[start:end]
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
		bOffset = xorBytes(self.paraSec[8:12], self.xorKey) #第一个偏移，一般应该为0
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
				Codes[-1]['sce'] = cmdCode
				printInfo('命令：', text, hex(cmdCode), paraCount)
			elif text == 'GOSUB':
				Codes[-1]['sel'] = cmdCode
				printInfo('命令：', text, hex(cmdCode), paraCount)
			#else:
				#printDebug('命令：', text, hex(cmdCode), paraCount)
			for paraCode in range(paraCount):
				#参数
				bs = readStr(data, pos)
				#text = bs.decode('cp932')
				pos += len(bs) + 3
				#printDebug('    参数：', text, hex(paraCode))

manager = DataManager()