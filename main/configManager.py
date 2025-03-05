import os
import re
from PyQt5.QtCore import QSettings, Qt

__all__ = ['ConfigManager']

mainWindow = None
checkDic = None
notInRunning = None

class ConfigManager():
	#data
	configCount = 4 #默认配置数
	configName = 'main/config.ini' #默认配置名字
	isCheckDirIni = False
	isChangeMainDir = True
	builtinConfig = None #内置ini
	oldReg = ''

	def __init__(self, mw) -> None:
		global mainWindow, checkDic, notInRunning
		mainWindow = mw
		checkDic = {
			#勾选功能: [对应控件, 是否同步配置文件, 默认值]
			'cutoff': [mainWindow.cutoffCheck, True, False], #截断
			'cutoffCopy': [mainWindow.cutoffCopyCheck, True, True],
			'noInput': [mainWindow.noInputCheck, False, False], #不导入
			'splitAuto': [mainWindow.splitCheck, True, False], #译文重新分割
			'ignoreSameLineCount': [mainWindow.ignoreSameCheck, True, False],
			'ignoreNotMaxCount': [mainWindow.ignoreNotMaxCheck, True, False],
			'fixedMaxPerLine': [mainWindow.fixedMaxCheck, True, False], #固定长度
			'binEncodeValid': [mainWindow.binEncodeCheck, True, False],
			'pureText': [mainWindow.binPureTextCheck, True, False], #bin纯文本模式
			'tunnelJis': [mainWindow.tunnelJisCheck, True, False],
			'subsJis': [mainWindow.subsJisCheck, True, False],
			'transReplace': [mainWindow.transReplaceCheck, True, False], #译文替换
			'preReplace': [mainWindow.preReplaceCheck, True, False], #分割前替换
			'skipIgnoreCtrl': [mainWindow.skipIgnoreCtrlCheck, True, False],
			'skipIgnoreUnfinish': [mainWindow.skipIgnoreUnfinishCheck, True, False],
			'ignoreEmptyFile': [mainWindow.ignoreEmptyFileCheck, True, True], #提取到的内容为空则不导出
			'nameMoveUp': [mainWindow.nameMoveUpCheck, False, False], #导出时名字向上移动一位
			'outputTextType': [mainWindow.outputTextTypeCheck, True, False], #输出文本类型
			'dontExportWhenImport': [mainWindow.dontExportCheck, True, False], #写入时不导出
			'joinAfterSplit': [mainWindow.joinAfterSplitCheck, True, False], #分割后再合并为一句
			'autoCache': [mainWindow.autoCacheCheck, True, True], #选择文件夹时，自动在ctrl下生成缓存文件config.ini
			'dontInterrupt': [mainWindow.dontInterruptCheck, True, False], #单文件异常时不中断
			'toFullWidth': [mainWindow.toFullWidthCheck, True, False], #转为全角字符
			'nameKeepCtrl': [mainWindow.nameKeepCtrlCheck, True, True], #name分组保留lastCtrl
			'batchCmdCur': [mainWindow.batchCmdCurCheck, True, True], #命令在当前提取目录运行
			'batchAutoStart': [mainWindow.batchAutoStartCheck, True, False], #批处理在提取/导入后自动运行
			'useStructPara': [mainWindow.useStructParaCheck, True, False],
			'autoCustom': [mainWindow.autoCustomCheck, True, True],
		}
		#运行中时不进行读写
		notInRunning = ['batchCmdCur', 'batchAutoStart']

	def showSeq(self):
		#配置选项
		for i in range(1, self.configCount):
			mainWindow.configSeqBox.addItem(str(i))
		path = os.path.abspath(__file__)
		path = os.path.dirname(path)
		for filename in os.listdir(path):
			ret = re.search(r'config([^\d].*?).ini', filename)
			if ret:
				name = ret.group(1)
				mainWindow.configSeqBox.addItem(name)
		mainWindow.configSeqBox.currentIndexChanged.connect(self.changeConfigSeq)

	def changeConfigSeq(self, index):
		self.selectConfig(index)
		self.isCheckDirIni = True
		self.checkDirIni()

	def selectConfig(self, index, path=None):
		if path:
			self.configName = path
		elif index == 0:
			self.configName = 'main/config.ini'
		else:
			self.configName = f'main/config{mainWindow.configSeqBox.currentText()}.ini'
		self.refreshConfig()

	def refreshConfig(self):
		mainWindow.initEnd = False
		#选择配置
		#print('切换到缓存：', self.configName)
		self.mainConfig = QSettings(self.configName, QSettings.IniFormat)
		self.mainConfig.setIniCodec('utf-8')
		mainWindow.mainConfig = self.mainConfig
		if self.configName.startswith('main'):
			#内置ini
			self.builtinConfig = self.mainConfig
		# 不在运行时才进行设置
		if not mainWindow.batchManager.running:
			# 窗口大小
			windowSize = initValue(self.mainConfig, 'windowSize', None)
			if windowSize: mainWindow.resize(windowSize)
			# batch
			text = initValue(self.mainConfig, 'batchCmdListText', '')
			mainWindow.batchCmdListEdit.setText(text)
		# 主目录
		if self.isChangeMainDir:
			mainWindow.mainDirPath = initValue(self.mainConfig, 'mainDirPath', '.')
			mainWindow.mainDirEdit.setText(mainWindow.mainDirPath)
		self.isChangeMainDir = True
		# 当前引擎
		mainWindow.engineCode = int(initValue(self.mainConfig, 'engineCode', 0))
		mainWindow.engineName = initValue(self.mainConfig, 'engineName', '')
		if mainWindow.engineName != '':
			index = getQComboBoxIndex(mainWindow.engineNameBox, mainWindow.engineName)
			if index >= 0:
				mainWindow.engineCode = index
		#print(mainWindow.engineCode)
		#mainWindow.engineNameBox.currentIndexChanged.connect(mainWindow.selectEngine)
		# 当前输出格式
		mainWindow.outputFormat = int(initValue(self.mainConfig, 'outputFormat', 0))
		#print(mainWindow.outputFormat)
		mainWindow.outputFileBox.setCurrentIndex(mainWindow.outputFormat)
		mainWindow.outputFileExtraBox.setCurrentIndex(0)
		# 单个或多个Json模式
		mainWindow.outputPartMode = int(initValue(self.mainConfig, 'outputPartMode', 0))
		#print(mainWindow.outputPartMode)
		mainWindow.outputPartBox.setCurrentIndex(mainWindow.outputPartMode)
		# 合并目录
		mainWindow.mergeDirPath = initValue(self.mainConfig, 'mergeDirPath', '.')
		mainWindow.mergeDirEdit.setText(mainWindow.mergeDirPath)
		text = initValue(self.mainConfig, 'mergeSkipReg', mainWindow.skipRegEdit.text())
		mainWindow.skipRegEdit.setText(text)
		collectSep = initValue(self.mainConfig, 'collectSep', '+')
		mainWindow.collectSepEdit.setText(collectSep)
		# 设置匹配规则
		mainWindow.regIndex = int(initValue(self.mainConfig, 'regIndex', 0))
		mainWindow.regNameBox.setCurrentIndex(mainWindow.regIndex)
		#mainWindow.regNameBox.currentIndexChanged.connect(mainWindow.selectReg)
		# 编码
		index = int(initValue(self.mainConfig, 'encodeIndex', 0))
		mainWindow.txtEncodeBox.setCurrentIndex(index)
		# 译文
		maxCountPerLine = initValue(self.mainConfig, 'maxCountPerLine', 512)
		mainWindow.splitMaxEdit.setText(str(maxCountPerLine))
		# 段落分割符
		splitParaSep = initValue(self.mainConfig, 'splitParaSep', '\\r\\n')
		mainWindow.splitSepEdit.setText(splitParaSep)
		# 读取Check
		self.readCheck()
		# 结束
		mainWindow.engineNameBox.setCurrentIndex(mainWindow.engineCode)
		mainWindow.initEnd = True
		mainWindow.selectEngine(mainWindow.engineCode)
	
	def checkDirIni(self):
		if self.isCheckDirIni:
			self.isCheckDirIni = False
			path = os.path.join(mainWindow.mainDirPath, 'ctrl', 'config.ini')
			if os.path.isfile(path):
				self.isChangeMainDir = False
				self.selectConfig(-1, path)

	def readCheck(self):
		for key, value in checkDic.items():
			if value[1]:
				if mainWindow.batchManager.running and key in notInRunning:
					continue
				#需要读取配置
				checked = initValue(self.mainConfig, key, value[2])
				value[0].setChecked(checked)
	
	def addCheck2Args(self, args):
		for key, value in checkDic.items():
			args[key] = value[0].isChecked()

	def writeCheck(self):
		for key, value in checkDic.items():
			if value[1]:
				if mainWindow.batchManager.running and key in notInRunning:
					continue
				#需要保存配置
				self.mainConfig.setValue(key, value[0].isChecked())

	def saveConfig(self, args, group):
		self.mainConfig.setValue('mainDirPath', args['workpath'])
		self.mainConfig.setValue('engineCode', mainWindow.engineCode)
		self.mainConfig.setValue('engineName', mainWindow.engineName)
		self.mainConfig.setValue('outputFormat', args['outputFormat'])
		self.mainConfig.setValue('outputPartMode', args['outputPartMode'])
		if args['nameList'] != '':
			self.mainConfig.setValue(group+'_nameList', args['nameList'])
		else:
			self.mainConfig.remove(group+'_nameList')
		self.mainConfig.setValue('regIndex', mainWindow.regIndex)
		self.mainConfig.setValue('maxCountPerLine', args['maxCountPerLine'])
		if mainWindow.regNameTab.isEnabled():
			regName = mainWindow.regNameBox.currentText()
			textAll = mainWindow.sampleBrowser.toPlainText()
			if re.match(r'_*Custom', regName):
				#保存自定义规则
				if not re.match(r'sample', textAll):
					self.mainConfig.setValue('reg' + regName, textAll)
			elif mainWindow.autoCustomCheck.isChecked() and self.oldReg != textAll:
				#规则有变化，自动跳转到Custom
				index = mainWindow.regNameBox.findText('Custom', Qt.MatchContains) #包含匹配
				if index >= 0:
					print('规则被编辑，自动转到Custom')
					regName = mainWindow.regNameBox.itemText(index)
					self.mainConfig.setValue('reg' + regName, textAll)
					mainWindow.regNameBox.setCurrentIndex(index)
		self.mainConfig.setValue('encodeIndex', mainWindow.txtEncodeBox.currentIndex())
		#窗口大小
		self.mainConfig.setValue('windowSize', mainWindow.size())
		self.mainConfig.setValue('splitParaSep', args['splitParaSep'])
		#写入check
		self.writeCheck()
		#检查是否是内置ini
		if self.mainConfig != self.builtinConfig:
			self.builtinConfig.setValue('mainDirPath', args['workpath'])

#---------------------------------------------------------------
#设置初始值
def initValue(setting, name, v):
	if setting.value(name) == None:
		if v != None:
			setting.setValue(name, v)
			print('New Config', name, v)
	else:
		v = setting.value(name)
		#print('Load Config', name, v)
		if v == 'false':
			v = False
		elif v == 'true':
			v = True
	return v

def getQComboBoxIndex(combo, text):
	items = [combo.itemText(i) for i in range(combo.count())]
	if text in items:
		return items.index(text)
	else:
		return -1
