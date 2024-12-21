import re
from common import *
from extract_BIN import replaceOnceImp as replaceOnceImpBIN
from extract_BIN import parseImp as parseImpBIN
from extract_TXT import searchLine, ParseVar, dealLastCtrl, initParseVar

headerList = []
insertContent = {}

# ---------------- Engine: GSD v2 -------------------
def parseImp(content, listCtrl, dealOnce):
	if not content: return
	if manager.isGlobal:
		#manager.nameDic.clear()
		for contentIndex, lineData in enumerate(content):
			text = lineData.decode(ExVar.OldEncodeName)
			#manager.nameDic[contentIndex] = text
			ctrl = {'pos':[contentIndex, 0, len(lineData)]}
			if dealOnce(text, ctrl):
				listCtrl.append(ctrl)
	else:
		# spt
		var = ParseVar(listCtrl, dealOnce)
		var.OldEncodeName = ExVar.OldEncodeName
		initParseVar(var)
		for contentIndex in range(len(content)):
			if contentIndex < ExVar.startline: continue
			info = manager.infoList[contentIndex]
			if 'nameId' in info:
				#额外增加不写回的名字
				name = manager.nameDic[info['nameId']]
				ctrlName = {'pos':[-1, -1, -1]}
				ctrlName['name'] = True
				if dealOnce(name, ctrlName):
					listCtrl.append(ctrlName)
			var.lineData = content[contentIndex]
			var.contentIndex = contentIndex
			ctrls = searchLine(var)
			if var.checkLast:
				var.lastCtrl = dealLastCtrl(var.lastCtrl, ctrls, contentIndex)

# -----------------------------------
def replaceOnceImp(content, lCtrl, lTrans):
	return replaceOnceImpBIN(content, lCtrl, lTrans)

def replaceEndImp(content):
	if not content: return
	if manager.isGlobal:
		# global.dat
		manager.writeGlobal()
	else:
		# spt
		manager.writeSpt()

# -----------------------------------
def readFileDataImp(fileOld, contentSeparate):
	manager.clear()
	if ExVar.isStart == 1:
		#所有提取前，先建立名字字典
		path = os.path.join(ExVar.workpath, 'global.dat')
		f = open(path, 'rb')
		data = f.read()
		f.close()
		manager.readGlobal(data)
		manager.generateNameDic()
		manager.clear()
		#选项用
		strPat = repr(manager.textBytes)[2:-1]
		if ExVar.extractKey:
			#s = ExVar.extractKey + repr(manager.selectBytesAdd)[2:-1]
			s = ExVar.extractKey
			printInfo('用于搜索', s)
			strPat += '|' + s
		manager.patText = re.compile(strPat.encode('ascii'))
	#正常流程
	data = fileOld.read()
	if ExVar.filename == 'global.dat':
		manager.readGlobal(data)
	elif ExVar.filename.endswith('.spt'):
		manager.readSpt(data)
	else:
		manager.insertContent = {0:data}
	return manager.content, manager.insertContent

class GSDManager():
	#selectStr = 'select.spt'
	#selectBytesAdd = b'\x01\x00\x00\x00\xFF\xFF\xFF\xFF'
	charBytes = b'\x07' #None
	patZero = re.compile(b'\x00')
	patText = None
	infoList = []
	content = []
	insertContent = {}
	nameDic = {}
	isGlobal = False

	def clear(self):
		self.infoList.clear()
		self.content.clear()
		self.insertContent.clear()
		self.isGlobal = False
		self.version = ExVar.version
		if self.version == 2:
			self.textBytes = b'\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00'
		else:
			self.textBytes = b'\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\xFF\xFF\xFF\xFF'

	# ----------------- global.dat -------------------
	def readGlobal(self, data):
		self.isGlobal = True
		pos = 8
		secMax = -1 #14 #名字之前，需要跳过的区域数量
		if ExVar.extraData:
			secMax = int(ExVar.extraData)
		#跳过区域
		for secIndex in range(0x100):
			if secMax > 0:
				if secIndex >= secMax:
					break
			else:
				#不依靠区域数量，而是检测长度
				l = readInt(data, pos+4) #测试长度
				if l >= 0x100:
					break
			cmdCount = readInt(data, pos)
			pos += 4
			for i in range(cmdCount):
				for j in range(3): #最多3个str
					length = readInt(data, pos)
					pos += 4 + length
				pos += 4 * 0x22 #22个int
		#名字区域
		cmdCount = readInt(data, pos)
		pos += 4
		self.insertContent[0] = data[0:pos]
		cmdLen = 0x104 #单个名字命令长度
		for i in range(cmdCount):
			end = pos + cmdLen
			zero = self.patZero.search(data, pos=pos) 
			self.infoList.append({'head': bytearray(data[pos:end])}) #整个cmd
			self.content.append(data[pos:zero.start()]) #文本
			pos = end
		#文件末尾
		if pos < len(data):
			self.insertContent[len(self.content)] = data[pos:]
	
	def generateNameDic(self):
		# global.dat 建立名字字典
		self.nameDic.clear()
		for contentIndex, lineData in enumerate(self.content):
			text = lineData.decode(ExVar.OldEncodeName)
			self.nameDic[contentIndex] = text

	def writeGlobal(self):
		head = None #复用上一个命令的字节块
		for i, line in enumerate(self.content):
			info = self.infoList[i]
			if self.version == 2:
				head = bytearray(len(info['head']))
			elif not head:
				head = info['head']
			head[0:len(line)+1] = line + b'\x00'
			self.content[i] = bytes(head) #固定
	
	# ------------------ spt -------------------
	def readSpt(self, data):
		pre = 0
		matchs = self.patText.finditer(data)
		for m in matchs:
			if data[m.start()] == self.textBytes[0]:
				#文本
				if m.start() < pre:
					printDebug('忽略重叠', m.start())
					break
				pre = self.getText(data, pre, m)
			else:
				#选项
				old = pre
				pre = self.getSelect(data, pre, m)
				if pre == old:
					printWarning('选项搜索失败:', ExVar.filename, hex(pre))
		#文件末尾
		if pre < len(data):
			self.insertContent[len(self.content)] = data[pre:]
	
	def getText(self, data, pre, m):
		pos = m.start()
		info = { 'type': 0 } #文本
		if pre < pos:
			info['pre'] = data[pre:pos]
		else:
			info['pre'] = b''
		#名字变量
		pos += 0x28
		nameId = readInt(data, pos)
		pos += 0xC
		charCount = readInt(data, pos)
		if charCount <= 1 or charCount > 0x300:
			printDebug('文字个数可能不正确', pos)
			return pre
		pos += 0xC
		info['head'] = bytearray(data[m.start():pos])
		if nameId != 0xFFFFFFFF:
			info['nameId'] = nameId
		end = pos + charCount * 0xC
		#处理文本
		bs = bytearray()
		for i in range(charCount-1): #最后一个是结尾char
			if self.charBytes and self.charBytes[0] != data[pos]:
				printDebug('单字检查失败', pos)
				return pre
			pos += 0x8
			for j in range(4):
				if data[pos+j] == 0:
					break
				bs.append(data[pos+j])
			pos += 0x4
		self.content.append(bs)
		self.infoList.append(info)
		pre = end
		return pre

	def getSelect(self, data, pre, m):
		pos = m.end()
		while True:
			info = { 'type': 2 }  #选项
			if pre < pos:
				info['pre'] = data[pre:pos]
			else:
				info['pre'] = b''
			start = pos
			code = readInt(data, pos)
			if code != 0x23:
				break
			pos += 0xC
			strLen = readInt(data, pos)
			pos += 0xC
			if strLen == 0:
				break
			else:
				pos += 1 #首尾有\x00
				info['head'] = bytearray(data[start:pos])
				zero = self.patZero.search(data, pos=pos)
				self.content.append(data[pos:zero.start()])
				self.infoList.append(info)
				pre = zero.start()
				pos = pre + 9
		return pre
	
	def writeSpt(self):
		for i, lineData in enumerate(self.content):
			info = self.infoList[i]
			if info['type'] == 0:
				#文本
				bs = bytearray()
				#生成文本
				charCount = 0
				pos = 0
				pre = 0
				while pos < len(lineData):
					bs.extend(int2bytes(0x07))
					bs.extend(int2bytes(0))
					bs.append(lineData[pos])
					pre = pos
					if lineData[pos] >= 0x80:
						#双字节
						bs.append(lineData[pos+1])
						pos += 2
					else:
						pos += 1
					bs.extend(b'\x00' * (4 + pre - pos))
					charCount += 1
				if self.version == 2:
					#固定
					bs.extend(int2bytes(0x0A))
					bs.extend(int2bytes(0x00))
					bs.extend(int2bytes(0x00))
				else:
					#最后一个字符需要写入两次，单独处理
					bs.extend(int2bytes(0x08))
					bs.extend(int2bytes(0))
					bs.extend(lineData[pre:])
					bs.extend(b'\x00' * (4 + pre - pos))
				charCount += 1
				#恢复所有字节
				head = info['head']
				head[0x34:0x38] = int2bytes(charCount) #字符个数
				self.content[i] = info['pre'] + head + bs
			else:
				#选项
				bs = lineData
				head = info['head']
				head[0xC:0x10] = int2bytes(len(bs)) #字节个数
				self.content[i] = info['pre'] + head + bs

manager = GSDManager()