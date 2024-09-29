import re
from common import *
from extract_TXT import searchLine, ParseVar, initParseVar, dealLastCtrl
from extract_BIN import parseImp as parseImpBIN
from extract_BIN import replaceOnceImp as replaceOnceImpBIN

manager = None

# ---------------- Engine: TmrHiro -------------------
def parseImp(content, listCtrl, dealOnce):
	parseImpBIN(content, listCtrl, dealOnce)

# -----------------------------------
def replaceOnceImp(content, lCtrl, lTrans):
	replaceOnceImpBIN(content, lCtrl, lTrans)

def replaceEndImp(content):
	data = manager.write()
	content.clear()
	content.append(data)

# -----------------------------------
def readFileDataImp(fileOld, contentSeparate):
	data = fileOld.read()
	global manager
	manager = Manager(ExVar.version)
	content = manager.read(data, ExVar.filename)
	return content, {}

# -----------------------------------
Config = {
	1 : {
		'fileMacro': '^_',
		'str': [0x00150050],
		'strMask': 0x0000FFFF,
		'sel': [0x00140010],
	}
}

class Manager():
	def __init__(self, version=0):
		self.strList = []
		self.infoList = []
		self.version = version
		if version in Config:
			self.config = Config[version]
		else:
			self.config = Config[1]

	# -----------------------------------
	def read(self, data, filename):
		self.data = data
		self.isMacro = re.search(self.config['fileMacro'], filename)
		if self.isMacro:
			if ExVar.extraData:
				ExVar.regDic = {
					'10_search': ExVar.extraData,
				}
			self.readMacro(data)
		else:
			self.readScr(data)
		return self.strList

	def readScr(self, data):
		pos = 0
		self.count = readInt(data, pos)
		pos += 4
		while pos < len(data):
			length = readInt(data, pos, 2)
			pos += 2
			info = {'length':length, 'type':0}
			code = readInt(data, pos, 4)
			if code in self.config['str'] or (code & self.config['strMask']) == 0: #文本
				preLen = 4
			elif code in self.config['sel']: #选项
				preLen = 7
				info['type'] = 2
			else:
				preLen = length
			strLen = length - preLen
			#缓存
			info['pre'] = data[pos:pos+preLen]
			pos += preLen
			text = data[pos:pos+strLen]
			pos += strLen
			self.infoList.append(info)
			self.strList.append(text)
		if self.count != len(self.infoList):
			printError('实际命令数量与记录不符')

	def readMacro(self, data):
		pos = 0
		while pos < len(data):
			length = readInt(data, pos, 2)
			pos += 2
			info = {'length':length, 'type':0, 'pre':b''}
			text = data[pos:pos+length]
			pos += length
			#缓存
			self.infoList.append(info)
			self.strList.append(text)

	# -----------------------------------
	def write(self):
		self.data = []
		if self.isMacro:
			self.writeAll()
		else:
			bs = int.to_bytes(len(self.infoList), 4, "little")
			self.data.append(bs)
			self.writeAll()
		self.data = b''.join(self.data)
		return self.data

	def writeAll(self):
		for i in range(len(self.infoList)):
			info = self.infoList[i]
			text = self.strList[i]
			bs = bytearray()
			length = len(info['pre']) + len(text)
			bs.extend(int.to_bytes(length, 2, "little"))
			bs.extend(info['pre'])
			bs.extend(text)
			self.data.append(bs)




