import re
from common import *
from extract_BIN import replaceOnceImp as replaceOnceImpBIN
from extract_BIN import parseImp as parseImpBIN
from extract_TXT import ParseVar, searchLine, initParseVar, dealLastCtrl

MessageCode = 0x5E
StrCode = { #0不修正且不提取 -1修正但不提取 1修正且提取
	0x5E: [1, -1, 1], #对话
	0x65: [0, 1], #选项
	0x6B: [-1],
	0x6D: [-1],
	0x6F: [-1],
	0x70: [-1],
	0x72: [-1],
	0x84: [-1],
}
StrCodeList = StrCode.keys()
# ---------------- Engine: ScrPlayer -------------------
def parseImp(content, listCtrl, dealOnce):
	lastCtrl = None
	var = ParseVar(listCtrl, dealOnce)
	var.OldEncodeName = ExVar.OldEncodeName
	initParseVar(var)
	for cmd in manager.cmdList:
		for i, param in enumerate(cmd.params):
			if StrCode[cmd.code][i] != 1: #不需要提取的文本
				continue
			if param == cmd.IgnoreParam: #无效参数
				lastCtrl = None
				continue
			var.contentIndex = param
			var.lineData = content[var.contentIndex]
			ctrls = searchLine(var)
			if cmd.code == MessageCode and i == 0 and len(ctrls) == 1:
				ctrls[0]['name'] = True # 对话的参数0指向名字
			lastCtrl = dealLastCtrl(lastCtrl, ctrls, var.contentIndex)

# -----------------------------------
def replaceOnceImp(content, lCtrl, lTrans):
	return replaceOnceImpBIN(content, lCtrl, lTrans)

def replaceEndImp(content):
	data = manager.write()
	content.clear()
	content.append(data)

# -----------------------------------
def readFileDataImp(fileOld, contentSeparate):
	data = fileOld.read()
	manager.read(data)
	content = manager.strList
	return content, {}

# -----------------------------------
def generateAddrList(dataList, padLen=1):
	addrList = []
	addr = 0
	for data in dataList:
		addrList.append(addr)
		addr += len(data) + padLen
	return addrList

#Count = []
class Script:
	#config
	XorKey = b'\x7F'
	StrSep = b'\0'
	#var
	headSec = None
	cmdSec = None
	strSec = None
	cmdList = []
	strList = []
	strAddrList = []

	def read(self, data):
		#读取
		self.headSec = data[0:0x10] #头部
		pos = 0x10
		cmdLen = readInt(data, pos)
		pos += 4
		self.cmdSec = data[pos:pos+cmdLen] #指令区
		pos += cmdLen
		strLen = readInt(data, pos)
		pos += 4
		self.strSec = data[pos:pos+strLen] #字符串区
		self.strSec = xorBytes(self.strSec, self.XorKey) #解密
		pos += strLen 
		#解析字符串区
		self.strList = re.split(self.StrSep, self.strSec)
		self.strAddrList = generateAddrList(self.strList)
		#解析指令区
		self.cmdList.clear()
		pos = 0
		#Count.clear()
		while pos < len(self.cmdSec):
			cmd = Command()
			pos = cmd.read(self.cmdSec, pos)
			self.cmdList.append(cmd)
		# #校验
		# j = 0
		# for i in range(0, len(self.strList) - 1):
		# 	if j >= len(Count) or i != Count[j]:
		# 		printError('缺少', i, hex(self.strAddrList[i]), self.strList[i])
		# 		continue
		# 	j += 1
			
	def write(self):
		#恢复字符串区
		self.strAddrList = generateAddrList(self.strList)
		self.strSec = self.StrSep.join(self.strList)
		self.strSec = xorBytes(self.strSec, self.XorKey) #加密
		#恢复指令区
		lst = []
		for cmd in self.cmdList:
			data = cmd.write()
			lst.append(data)
		self.cmdSec = b''.join(lst)
		#合并
		data = bytearray()
		data.extend(self.headSec)
		bs = int2bytes(len(self.cmdSec))
		data.extend(bs)
		data.extend(self.cmdSec)
		bs = int2bytes(len(self.strSec))
		data.extend(bs)
		data.extend(self.strSec)
		return data

manager = Script()

class Command:
	IgnoreParam = 0xFFFFFFFF

	def read(self, data, pos):
		self.code = data[pos]
		self.length = data[pos+1]
		self.data = bytearray(data[pos:pos+self.length])
		pos += self.length
		self.params = []
		#索引
		if self.code in StrCodeList:
			for i in range(0, self.length//4-1):
				p = (i+1) * 4
				param = readInt(self.data, p)
				if StrCode[self.code][i] != 0:
					#需要进行偏移修正
					if param != self.IgnoreParam:
						#查询地址对应索引
						param = manager.strAddrList.index(param)
						#Count.append(param)
				self.params.append(param)
		return pos

	def write(self):
		#索引
		if self.code in StrCodeList:
			for i in range(0, self.length//4-1):
				p = (i+1) * 4
				param = self.params[i]
				if StrCode[self.code][i] != 0:
					#需要进行偏移修正
					if param != self.IgnoreParam:
						#恢复索引对应地址
						param = manager.strAddrList[param]
				self.params[i] = param
				self.data[p:p+4] = int2bytes(param)
		return self.data
