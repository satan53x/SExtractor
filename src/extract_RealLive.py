import os
import re
from common import *
from extract_BIN import parseImp as parseImpBIN
from extract_BIN import replaceOnceImp as replaceOnceImpBIN
from extract_TXT import ParseVar, initParseVar, searchLine, dealLastCtrl
from helper_text import generateBytes
from tools.RealLive.seen_fix import fixSeenSub

manager = None

# ---------------- Engine: RealLive -------------------
def parseImp(content, listCtrl, dealOnce):
	ExVar.keepBytes = ''
	var = ParseVar(listCtrl, dealOnce)
	var.OldEncodeName = ExVar.OldEncodeName
	initParseVar(var)
	for contentIndex in range(len(content)):
		if contentIndex < ExVar.startline: continue
		var.lineData = content[contentIndex]
		#每行
		var.contentIndex = contentIndex
		ctrls = searchLine(var)
		if ctrls and len(ctrls) > 0:
			info = manager.infoList[contentIndex]
			if info.type == TextType.SELECT:
				#选项标记
				ctrls[-1]['type'] = 'select'
		if var.checkLast:
			var.lastCtrl = dealLastCtrl(var.lastCtrl, ctrls, contentIndex)
	ExVar.keepBytes = 'auto'
	
# -----------------------------------
def replaceOnceImp(content, lCtrl, lTrans):
	for i in range(len(lCtrl)):
		# 位置
		ctrl = lCtrl[i]
		contentIndex, start, end = ctrl['pos']
		transData = generateBytes(lTrans[i], end - start, ExVar.NewEncodeName)
		if transData == None:
			return False
		#写入new
		strNew = content[contentIndex][:start] + transData + content[contentIndex][end:]
		content[contentIndex] = strNew
		#修正地址
		diff = len(transData) - (end-start)
		if diff != 0:
			info = manager.infoList[contentIndex]
			addrFixer.fix(info.strStart, diff)
	return True

def replaceEndImp(content):
	if not content: return
	#拼装
	data = bytearray()
	pre = 0
	for i, lineData in enumerate(content):
		info = manager.infoList[i]
		if info.type == TextType.MESSAGE or info.type == TextType.SELECT:
			if pre < info.strStart:
				data.extend(manager.data[pre:info.strStart])
			data.extend(lineData)
			pre = info.strEnd
	if pre < len(manager.data):
		data.extend(manager.data[pre:])
	#修正地址
	for i, pointAddr in enumerate(addrFixer.pointList):
		realAddr = addrFixer.realList[i]
		saveAddr = realAddr - manager.cmdStart
		data[pointAddr:pointAddr+4] = int2bytes(saveAddr)
	#加密
	if isinstance(ExVar.decrypt, int):
		data = fixSeenSub(data, ExVar.decrypt)
	#恢复
	content.clear()
	content.append(data)

# -----------------------------------
NotePattern = re.compile(rb'\x23\x00\x03\x78\x00(?:\x00\x00\x01|\x01\x00\x00\x28[^\x29]*?\x29)(?:\x40[\x00-\xFF]{2})?')
LinebreakPattern = re.compile(rb'\x23\x00\x03\xC9\x00\x00\x00\x00(?:\x40[\x00-\xFF]{2})?')

def readFileDataImp(fileOld, contentSeparate):
	data = bytearray(fileOld.read())
	content = []
	global manager
	manager = Manager()
	#解密
	if isinstance(ExVar.decrypt, int):
		data = fixSeenSub(data, ExVar.decrypt)
	#修正
	lst = ExVar.extraData.split(',')
	if 'fixNote' in lst:
		for match in NotePattern.finditer(data):
			data[match.start():match.end()] = b'\x20'*len(match.group())
	if 'fixLinebreak' in lst:
		for match in LinebreakPattern.finditer(data):
			data[match.start():match.end()] = b'\x20'*len(match.group())
			data[match.start():match.start()+3] = b'<n>'
	manager.checkPos = 'checkPos' in lst
	#解析
	manager.init(data)
	for info in manager.infoList:
		if info.type == TextType.MESSAGE or info.type == TextType.SELECT:
			#文本
			text = data[info.strStart:info.strEnd]
			content.append(text)
		else:
			content.append(b'')
	return content, {}


# -----------------------------------
headConfig = { 
	'numStartAddr': 0x8, 'numLenAddr': 0x10, 'cmdStartAddr': 0x20, 'cmdLenAddr': 0x24, 
	'entryStart': 0x34
}

config = None
addrFixer = None

class Manager():
	checkPos = False

	def init(self, data):
		global config, addrFixer
		config = Config(ExVar.version)
		addrFixer = AddrFixer()
		self.data = data
		self.numStart = readInt(data, headConfig['numStartAddr'])
		#entryPoint
		self.entryStart = headConfig['entryStart']
		self.entryEnd = self.numStart
		#lineNumber
		length = readInt(data, headConfig['numLenAddr'])
		self.numEnd = self.numStart+length
		#command
		self.cmdStart = readInt(data, headConfig['cmdStartAddr'])
		self.cmdLen = readInt(data, headConfig['cmdLenAddr'])
		self.cmdEnd = self.cmdStart + self.cmdLen
		#cmd长度记录地址
		real_addr = self.cmdLen + manager.cmdStart
		addrFixer.listen(headConfig['cmdLenAddr'], real_addr)
		#解析命令区域
		self.parseCmd()

	def parseCmd(self):
		self.current_module = None
		self.current_function = None
		self.cmdList = [] #指令列表
		self.infoList = [] #文本信息列表
		self.pos = self.cmdStart
		self.oldPosList = []
		while self.cmdStart <= self.pos < self.cmdEnd:
			Command().init()


def read(length, autoInc=True):
	bs = manager.data[manager.pos:manager.pos+length]
	if (autoInc):
		manager.pos += length
	return bs

def readInteger(length):
	bs = read(length)
	value = int.from_bytes(bs, byteorder='little')
	return value

PosCheckCountInterval = 100
PosCheckMinWidth = 50
class Command():
	# ------------------------------------
	def init(self) -> None:
		self.code = read(1)
		self.start = manager.pos
		if manager.checkPos:
			manager.oldPosList.append(manager.pos)
			if len(manager.oldPosList) >= PosCheckCountInterval:
				oldPos = manager.oldPosList[0]
				manager.oldPosList.clear()
				if abs(manager.pos - oldPos) <= PosCheckMinWidth:
					printError('pos may be wrong', ExVar.filename, hex(manager.pos))
					raise ValueError('pos may be wrong')
		if self.code == b'\0':
			manager.pos = manager.cmdEnd #结束
		elif self.code == b'\n':
			manager.pos += 2
		elif self.code in (b'!', b'@'):
			self.read_kidoku_flag()
		elif self.code in (b',', b'?'):
			pass
		elif self.code == b'#':
			self.read_function_call()
		elif self.code == b'$':
			self.read_expression()
		elif self.code in (b'\\', b'a'):
			manager.pos += 1
		elif self.code == b'(':
			manager.pos -= 1
			self.read_block(b'(', b')')
		elif self.code == b'{':
			manager.pos -= 1
			self.read_block(b'{', b'}')
		elif self.code == b'"':
			manager.pos -= 1
			self.read_string(True)
		else:
			manager.pos -= 1
			self.read_string(False)
		#保存数据
		self.end = manager.pos
		manager.cmdList.append(self)

	#指令：读取代码块
	def read_block(self, open_char, close_char, read_item=None):
		c = read(1)
		if c != open_char:
			raise ValueError("Invalid data: expected opening character")
		while True:
			c = read(1, False)
			if c == close_char:
				read(1)
				return
			if read_item:
				read_item()
			else:
				Command().init()

	def read_kidoku_flag(self):
		line_number_index = readInteger(2)
		line_number = readInt(manager.data, manager.numStart + 4 * line_number_index) - 1000000
		if line_number >= 0:
			entry_point_offset = manager.entryStart + line_number * 4
			save_addr = readInt(manager.data, entry_point_offset)
			real_addr = save_addr + manager.cmdStart
			addrFixer.listen(entry_point_offset, real_addr)

	#指令：函数调用
	def read_function_call(self):
		type = readInteger(1)
		manager.current_module = readInteger(1)
		manager.current_function = readInteger(2)
		num_args = readInteger(2)
		overload = readInteger(1)

		if not self.is_current_function_one_of(config.PARAMETERLESS_GOTO_FUNCTIONS) and read(1, False) == b'(':
			self.read_block(b'(', b')')

		if self.is_current_function_one_of(config.GOTO_FUNCTIONS):
			self.read_goto()
		elif self.is_current_function_one_of(config.GOTO_ON_FUNCTIONS):
			self.read_goto_on(num_args)
		elif self.is_current_function_one_of(config.GOTO_CASE_FUNCTIONS):
			self.read_goto_case()
		elif self.is_current_function_one_of(config.SELECT_MODULE):
			self.read_select()

		# if self.is_current_function_one_of(config.PARAGRAPH_END_FUNCTIONS):
		# 	pass

		manager.current_module = None
		manager.current_function = None

	#指令：表达式
	def read_expression(self):
		variable = readInteger(1)
		if variable == 0xC8:
			return
		if variable == 0xFF:
			read(4)
			return
		self.read_block(b'[', b']')

	def read_string_any(self):
		quoted = read(1, False) == b'"'
		self.read_string(quoted)

	special_chars = tuple(b'\0\n!@,?#$\\a(){}[]')
	#quoted 是否首尾有引号
	def read_string(self, quoted):
		quotedInline = False
		start = manager.pos
		if quoted:
			open_char = read(1)
			if open_char != b'"':
				raise ValueError("Invalid data: expected opening quotation mark")
		while True:
			i = readInteger(1)
			if quoted or quotedInline:
				#引号字符串
				if i == ord(b'\\'):
					read(1)
					continue
				elif i == ord(b'"'):
					if quotedInline:
						quotedInline = False
						continue #内部引号不退出
					else:
						break
			else:
				#非引号字符串
				if i == ord(b'"'):
					#内部引号
					quotedInline = True
					continue
				if i in self.special_chars:
					manager.pos -= 1 # Move back one byte
					break
			if isShiftJis(i, 0x40):
				read(1)
		end = manager.pos
		#保存文本：没有模块 or MESSAGE模块 or 选择模块
		if not self.is_in_function_call() or self.is_current_function_one_of(config.MESSAGE_FUNCTIONS): 
			if not self.range_equals(start, end-start, config.SCENE_END_MARKER):
				manager.infoList.append(Info(TextType.MESSAGE, start, end))
		elif self.is_current_function_one_of(config.SELECT_MODULE):
			manager.infoList.append(Info(TextType.SELECT, start, end))
		# elif self.is_current_function_one_of(config.NOTE_FUNCTIONS):
		# 	#注音的上标
		# 	for i in range(start, end):
		# 		manager.data[i] = 0x20

	# -----------------------------------
	#跳转
	def read_goto(self):
		self.read_offset()
	
	#跳转
	def read_goto_on(self, num_args):
		open_char = read(1)
		if open_char != b'{':
			raise ValueError("Invalid data: expected opening brace")
		for _ in range(num_args):
			self.read_offset()
		close_char = read(1)
		if close_char != b'}':
			raise ValueError("Invalid data: expected closing brace")
		
	#条件跳转
	def read_goto_case(self):
		self.read_block(b'{', b'}', self.read_goto_case_item)

	def read_goto_case_item(self):
		self.read_block(b'(', b')')
		self.read_offset()

	#选项跳转
	def read_select(self):
		if read(1, False) == b'{':
			self.read_block(b'{', b'}', self.read_select_item)

	def read_select_item(self):
		self.skip_debug_markers()
		if read(1, False) == b'(':
			read(1)
			if read(1, False) == b'(':
				# Read condition
				self.read_block(b'(', b')')
			# Read function
			read(1)
			# Read argument
			while read(1, False) != b')':
				Command().init()
			read(1)
		# Read text
		self.read_string_any()
		self.skip_debug_markers()

	def skip_debug_markers(self):
		while read(1, False) == b'\n':
			Command().init()

	#读取跳转地址
	def read_offset(self):
		point_addr = manager.pos
		save_addr = readInteger(4)
		real_addr = save_addr + manager.cmdStart
		addrFixer.listen(point_addr, real_addr)
		
	# -----------------------------------
	def is_current_function_one_of(self, functions):
		if manager.current_module not in functions:
			return False
		functions_of_module = functions[manager.current_module]
		if functions_of_module == []:
			return True
		return manager.current_function in functions_of_module
	
	def is_in_function_call(self):
		return manager.current_function is not None
	
	def range_equals(self, offset, length, compare_to):
		if length != len(compare_to):
			return False
		ret = manager.data[offset:offset+length] == compare_to
		return ret

class Info:
	def __init__(self, type, strStart, strEnd):
		#类型：0默认, 1文本, 3选项, -1注音下标，-2注音上标，-3段落结束
		self.type = type
		self.strStart = strStart
		self.strEnd = strEnd

# -----------------------------------
class Config:
	def __init__(self, version):
		self.GOTO_FUNCTIONS = {
			0x01: [0x0000, 0x0001, 0x0002, 0x0005, 0x0006, 0x0007, 0x0010],
			0x05: [0x0001, 0x0002, 0x0005, 0x0006, 0x0007]
		}
		self.PARAMETERLESS_GOTO_FUNCTIONS = {
			0x01: [0x0000, 0x0005],
			0x05: [0x0001, 0x0005]
		}
		self.GOTO_ON_FUNCTIONS = {
			0x01: [0x0003, 0x0008],
			0x05: [0x0003, 0x0008]
		}
		self.GOTO_CASE_FUNCTIONS = {
			0x01: [0x0004, 0x0009],
			0x05: [0x0004, 0x0009]
		}
		self.MESSAGE_FUNCTIONS = {
			0x03: [0x0070]
		}
		self.SCENE_END_MARKER = bytes([
			0x82, 0x72, 0x82, 0x85, 0x82, 0x85, 0x82, 0x8E, 0x82, 0x64, 0x82, 0x8E,
			0x82, 0x84, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF,
			0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF,
			0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF
		])
		self.SELECT_MODULE = {
			0x02: []
		}
		self.NOTE_FUNCTIONS = {
			0x03: [0x0078]
		}
		self.LINEBREAK_FUNCTIONS = {
			0x03: [0x00C9]
		}
		# self.PARAGRAPH_END_FUNCTIONS = {
		# 	0x03: [0x0011]
		# }
		# -----------------------------------
		if version == 2:
			self.SELECT_MODULE[0x02] = [0x0002, 0x0003]
		elif version == 3:
			self.MESSAGE_FUNCTIONS[0x01] = [0x0012]
			self.SELECT_MODULE[0x02] = [0x0002, 0x0003]
		elif version == 4:
			self.MESSAGE_FUNCTIONS[0x04] = [0x0000]



