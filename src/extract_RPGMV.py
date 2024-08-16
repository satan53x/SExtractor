import re
from common import *
from extract_TXT import ParseVar, dealLastCtrl, searchLine, initParseVar
import rapidjson

#fixed
HeaderLen = 7 #对每句文本添加的头部长度，不包括<>号
#var
var:ParseVar = None
nodePath = []
compressNodePathList = []
lastCtrl = None
checkLast = True
# ---------------- Group: RPG Maker MV -------------------
class RPGParserMV():
	extractTextCode = []

	def __init__(self, prefix='') -> None:
		#config
		self.prefix = prefix
		self.extractKeyList = []
		self.extractKeyReverse = False
		self.codeTag = self.prefix + 'code'
		self.parametersTag = self.prefix + 'parameters'
		self.compressList = []

	def parseNode(self, node, relCode=0, relItem=None):
		global lastCtrl
		if len(nodePath) > 1 and nodePath[-1] in self.compressList:
			#解压json字符串
			nodeParent = getNode(self.root, nodePath[0:-1])
			node = loads(node) #递归解析
			nodeParent[nodePath[-1]] = node
			compressNodePathList.append(nodePath[0:])
		if isinstance(node, str):
			text = None
			if relCode:
				text = f'<code{relCode:03}>{node}'
			if relItem:
				#影响段落
				if lastCtrl and 'unfinish' in lastCtrl:
					del lastCtrl['unfinish']
				if len(relItem) < HeaderLen:
					c = relItem.ljust(HeaderLen)
				else:
					c = relItem[0:HeaderLen]
				text = f'<{c}>{node}'
			if text:
				var.lineData = text
				var.contentIndex = nodePath[0:]
				ctrls = searchLine(var)
				if checkLast:
					lastCtrl = dealLastCtrl(lastCtrl, ctrls)
		elif isinstance(node, list):
			for index, child in enumerate(node):
				if child == None: continue
				nodePath.append(index)
				self.parseNode(child, relCode, relItem)
				nodePath.pop()
		elif isinstance(node, dict):
			if self.codeTag in node:
				#发现code
				code = node[self.codeTag]
				if (code not in EVENT_COMMAND_CODES) or EVENT_COMMAND_CODES[code][2]:
					#影响段落
					if lastCtrl and 'unfinish' in lastCtrl:
						del lastCtrl['unfinish']
				if code in self.extractTextCode:
					nodePath.append(self.parametersTag)
					for index, child in enumerate(node[self.parametersTag]):
						nodePath.append(index)
						self.parseNode(child, relCode=code)
						nodePath.pop()
					nodePath.pop()
				return
			#其他进行递归
			for index, child in node.items():
				parentIndex = None
				if self.extractKeyList != None:
					#提取指定key
					if (len(self.extractKeyList) == 0) or \
					(not self.extractKeyReverse and index in self.extractKeyList) or \
					(self.extractKeyReverse and index not in self.extractKeyList):
						parentIndex = self.getParentIndex(True)
				nodePath.append(index)
				self.parseNode(child, relItem=parentIndex)
				nodePath.pop()

	def getParentIndex(self, onlyStr=False):
		if len(nodePath) == 0:
			return 'root'
		if not onlyStr:
			return nodePath[-1]
		if isinstance(nodePath[-1], str): 
			return nodePath[-1].lstrip(self.prefix)
		if len(nodePath) == 1:
			return 'root'
		elif isinstance(nodePath[-2], str):
			return nodePath[-2].lstrip(self.prefix)
		else:
			return 'nostr'

	def init(self, content, listCtrl, dealOnce):
		self.root = content
		global var
		var = ParseVar(listCtrl, dealOnce)
		initParseVar(var)
		ExVar.indent = 2 #test
		#code
		self.extractTextCode.clear()
		for code, item in EVENT_COMMAND_CODES.items():
			if item[1]: self.extractTextCode.append(code)
		#非code
		if ExVar.extractKey == '' or ExVar.extractKey == 'none':
			self.extractKeyList = None
		elif ExVar.extractKey == 'all':
			self.extractKeyList = []
		else:
			keys = ExVar.extractKey
			if re.match(r'[!^]', keys):
				keys = keys[1:]
				self.extractKeyReverse = True
			self.extractKeyList.clear()
			lst = keys.split(',')
			for key in lst:
				if not key.startswith(self.prefix):
					key = self.prefix + key
				self.extractKeyList.append(key)
		#解压json字符串
		if ExVar.decrypt:
			lst = ExVar.decrypt.split(',')
			self.compressList = lst
		#清除
		nodePath.clear()
		compressNodePathList.clear()

# -----------------------------------
#解析
def parseImp(content, listCtrl, dealOnce):
	parser = RPGParserMV()
	parser.init(content, listCtrl, dealOnce)
	
	#处理
	parser.parseNode(content)

# -----------------------------------
def replaceOnceImp(content, lCtrl, lTrans):
	num = len(lCtrl)
	for index in range(num):
		# 位置
		ctrl = lCtrl[index]
		posData = ctrl['pos']
		contentIndex = posData[0]
		start = posData[1] - HeaderLen - 2 #原文中并没有头部
		end = posData[2] - HeaderLen - 2
		trans = lTrans[index]
		#按nodeList写入
		nodePath = contentIndex
		getNode(content, nodePath, trans, start, end)
	return True

def replaceEndImp(content):
	for nodePath in compressNodePathList:
		nodeParent = getNode(content, nodePath[0:-1])
		node = nodeParent[nodePath[-1]]
		node = dumps(node) #递归序列化
		nodeParent[nodePath[-1]] = node

def getNode(content, nodePath, replace=None, start=0, end=1):
	node = content
	for i, index in enumerate(nodePath):
		if replace and i == len(nodePath) - 1:
			#替换
			oldStr = node[index]
			newStr = oldStr[0:start] + replace + oldStr[end:]
			node[index] = newStr
		node = node[index]
	return node

# -----------------------------------
#递归解析json字符串
patIter = re.compile(r'[\[{]')
def loads(node):
	if isinstance(node, str):
		if patIter.match(node):
			node = rapidjson.loads(node)
		else:
			return node
	if isinstance(node, list):
		for i, n in enumerate(node):
			node[i] = loads(n)
	elif isinstance(node, dict):
		for k, v in node.items():
			node[k] = loads(v)
	return node

#返回值: node-节点, isEnd-不需要继续进行递归
def dumps(node):
	if isinstance(node, list):
		for i, n in enumerate(node):
			node[i] = dumps(n)
		node = rapidjson.dumps(node, ensure_ascii=False)
	elif isinstance(node, dict):
		for k, v in node.items():
			node[k] = dumps(v)
		node = rapidjson.dumps(node, ensure_ascii=False)
	return node

#------------------------------------------
# Table of what type of event command the event codes corresponds to.
# code 不能大于 999
EVENT_COMMAND_CODES = {
	#编号: [用途, 是否提取, 是否中断段落]
	0 : ["Empty", False, True],
	101 : ["Show Text Attributes", True, True],
	102 : ["Show Choices", True, True],
	103 : ["Input Number", False, True],
	104 : ["Select Key Item", False, True],
	105 : ["Show Scrolling Text Attributes", False, True],
	108 : ["Comment", True, False],
	111 : ["Conditional Branch", False, True],
	112 : ["Loop", False, True],
	113 : ["Break Loop", False, True],
	115 : ["Exit Event Processing", False, True],
	117 : ["Call Common Event", False, True],
	118 : ["Label", False, True],
	119 : ["Jump to Label", False, True],
	121 : ["Control Switches", False, True],
	122 : ["Control Variables", False, True],
	123 : ["Control Self Switch", False, True],
	124 : ["Control Timer", False, True],
	125 : ["Change Gold", False, True],
	126 : ["Change Items", False, True],
	127 : ["Change Weapons", False, True],
	128 : ["Change Armor", False, True],
	129 : ["Change Party Member", False, True],
	132 : ["Change Battle BGM", False, True],
	133 : ["Change Battle End ME", False, True],
	134 : ["Change Save Access", False, True],
	135 : ["Change Menu Access", False, True],
	136 : ["Change Encounter", False, True],
	137 : ["Change Formation Access", False, True],
	138 : ["Change Window Color", False, True],
	201 : ["Transfer Player", False, True],
	202 : ["Set Vehicle Location", False, True],
	203 : ["Set Event Location", False, True],
	204 : ["Scroll Map", False, True],
	205 : ["Set Move Route", False, True],
	206 : ["Get on/off Vehicle", False, True],
	211 : ["Change Transparency", False, True],
	212 : ["Show Animation", False, True],
	213 : ["Shot Balloon Icon", False, True],
	214 : ["Erase Event", False, True],
	216 : ["Change Player Followers", False, True],
	217 : ["Gather Followers", False, True],
	221 : ["Fadeout Screen", False, True],
	222 : ["Fadein Screen", False, True],
	223 : ["Tint Screen", False, True],
	224 : ["Flash Screen", False, True],
	225 : ["Shake Screen", False, True],
	230 : ["Wait", False, True],
	231 : ["Show Picture", False, True],
	232 : ["Move Picture", False, True],
	233 : ["Rotate Picture", False, True],
	234 : ["Tint Picture", False, True],
	235 : ["Erase Picture", False, True],
	236 : ["Set Weather Effects", False, True],
	241 : ["Play BGM", False, True],
	242 : ["Fadeout BGM", False, True],
	243 : ["Save BGM", False, True],
	244 : ["Replay BGM", False, True],
	245 : ["Play BGS", False, True],
	246 : ["Fadeout BGS", False, True],
	249 : ["Play ME", False, True],
	250 : ["Play SE", False, True],
	251 : ["Stop SE", False, True],
	261 : ["Play Movie", False, True],
	281 : ["Change Map Display", False, True],
	282 : ["Change Tileset", False, True],
	283 : ["Change Battle Back", False, True],
	284 : ["Change Parallax Back", False, True],
	285 : ["Get Location Info", False, True],
	301 : ["Battle Processing", False, True],
	302 : ["Shop Processing", False, True],
	303 : ["Name Input Processing", False, True],
	311 : ["Change HP", False, True],
	312 : ["Change MP", False, True],
	313 : ["Change State", False, True],
	314 : ["Recover All", False, True],
	315 : ["Change EXP", False, True],
	316 : ["Change Level", False, True],
	317 : ["Change Parameters", False, True],
	318 : ["Change Skills", False, True],
	319 : ["Change Equipment", False, True],
	320 : ["Change Actor Name", True, False],
	321 : ["Change Actor Class", False, True],
	322 : ["Change Actor Graphic", False, True],
	323 : ["Change Vehicle Graphic", False, True],
	324 : ["Change Actor Nickname", True, False],
	331 : ["Change Enemy HP", False, True],
	332 : ["Change Enemy MP", False, True],
	333 : ["Change Enemy State", False, True],
	334 : ["Enemy Recover All", False, True],
	335 : ["Enemy Appear", False, True],
	336 : ["Enemy Transform", False, True],
	337 : ["Show Battle Animation", False, True],
	339 : ["Force Action", False, True],
	340 : ["Abort Battle", False, True],
	351 : ["Open Menu Screen", False, True],
	352 : ["Open Save Screen", False, True],
	353 : ["Game Over", False, True],
	354 : ["Return to Title Screen", False, True],
	355 : ["Script", True, False],
	401 : ["Show Text", True, False],
	402 : ["When", False, True],
	403 : ["When Cancel", False, True],
	404 : ["Choices End", False, True],
	405 : ["Show Scrolling Text", True, False],
	408 : ["Comment More", True, False],
	411 : ["Else", False, True],
	412 : ["Branch End", False, True],
	413 : ["Repeat Above", False, True],
	601 : ["If Win", False, True],
	602 : ["If Escape", False, True],
	603 : ["If Lose", False, True],
	604 : ["Battle Processing End", False, True],
	605 : ["Shop Item", False, True],
	655 : ["Script More", True, False],
	657 : ["Other", True, False],
}