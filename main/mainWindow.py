import os
from PyQt5.QtCore import QSettings
from PyQt5.QtWidgets import QMainWindow, QFileDialog
from PyQt5.QtGui import QIcon
from main.ui_mainWindow import Ui_MainWindow
import re
import sys
import ctypes
sys.path.append('./src')
from main_extract_txt import mainExtractTxt
from main_extract_bin import mainExtractBin
from main_extract_json import mainExtractJson
from main_extract import var
from merge_json import mergeTool, createDicTool
from main.thread import extractThread

ConfigCount = 4

class MainWindow(QMainWindow, Ui_MainWindow):
	def __init__(self, parent=None):
		super(MainWindow, self).__init__(parent)
		self.setupUi(self)
		self.initEnd = False
		# 设置图标
		icon = QIcon("main/main.ico")
		self.setWindowIcon(icon)
		ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("myappid")
		#提取
		self.mainDirButton.clicked.connect(self.chooseMainDir)
		self.extractButton.clicked.connect(self.extractFileThread)
		self.engineNameBox.currentIndexChanged.connect(self.selectEngine)
		#self.outputFileBox.currentIndexChanged.connect(self.selectFormat)
		#self.outputPartBox.currentIndexChanged.connect(self.selectOutputPart)
		self.regNameBox.currentIndexChanged.connect(self.selectReg)
		#merge工具
		self.mergeDirButton.clicked.connect(self.chooseMergeDir)
		self.mergeButton.clicked.connect(self.mergeFile)
		self.collectButton.clicked.connect(self.collectFiles)
		#创建字典
		self.createDicButton.clicked.connect(self.createDic)
		#配置选项
		self.configName = 'main/config.ini'
		for i in range(1, ConfigCount):
			self.configSeqBox.addItem(str(i))
		path = os.path.abspath(__file__)
		path = os.path.dirname(path)
		for filename in os.listdir(path):
			ret = re.search(r'config([^\d].*?).ini', filename)
			if ret:
				name = ret.group(1)
				self.configSeqBox.addItem(name)
		self.configSeqBox.currentIndexChanged.connect(self.selectConfig)

	def selectConfig(self, index):
		if index == 0:
			self.configName = 'main/config.ini'
		else:
			self.configName = f'main/config{self.configSeqBox.currentText()}.ini'
		self.refreshConfig()

	#初始化
	def beforeShow(self):
		# 引擎列表
		self.engineConfig = QSettings('src/engine.ini', QSettings.IniFormat)
		self.engineConfig.setIniCodec('utf-8')
		groupList = self.engineConfig.childGroups()
		for group in groupList: 
			#print(group)
			self.engineConfig.beginGroup(group)
			if group.startswith('Engine_'):
				value = group[len("Engine_"):]
				if self.engineConfig.value('regDic') == '1':
					self.engineNameBox.insertItem(0, value)
				else:
					self.engineNameBox.addItem(value)
			elif group == 'OutputFormat':
				self.outputFileExtraBox.addItem('无')
				for key in self.engineConfig.childKeys():
					value = self.engineConfig.value(key)
					self.outputFileBox.addItem(value)
					self.outputFileExtraBox.addItem(value)
			self.engineConfig.endGroup()
		# 设置匹配规则
		self.regConfig = QSettings('src/reg.ini', QSettings.IniFormat)
		self.regConfig.setIniCodec('utf-8')
		groupList = self.regConfig.childGroups()
		for group in groupList: 
			#print(group)
			self.regNameBox.addItem(group)
		#刷新
		self.refreshConfig()

	#初始化
	def afterShow(self):
		#修正打印颜色
		from colorama import init
		init(autoreset=True)
	
	def refreshConfig(self):
		self.initEnd = False
		#选择配置
		self.mainConfig = QSettings(self.configName, QSettings.IniFormat)
		self.mainConfig.setIniCodec('utf-8')
		# 窗口大小
		windowSize = initValue(self.mainConfig, 'windowSize', None)
		if windowSize: self.resize(windowSize)
		# 主目录
		self.mainDirPath = initValue(self.mainConfig, 'mainDirPath', '.')
		self.mainDirEdit.setText(self.mainDirPath)
		# 当前引擎
		self.engineCode = int(initValue(self.mainConfig, 'engineCode', 0))
		#print(self.engineCode)
		#self.engineNameBox.currentIndexChanged.connect(self.selectEngine)
		# 当前输出格式
		self.outputFormat = int(initValue(self.mainConfig, 'outputFormat', 0))
		#print(self.outputFormat)
		self.outputFileBox.setCurrentIndex(self.outputFormat)
		self.outputFileExtraBox.setCurrentIndex(0)
		# 单个或多个Json模式
		self.outputPartMode = int(initValue(self.mainConfig, 'outputPartMode', 0))
		#print(self.outputPartMode)
		self.outputPartBox.setCurrentIndex(self.outputPartMode)
		# 合并目录
		self.mergeDirPath = initValue(self.mainConfig, 'mergeDirPath', '.')
		self.mergeDirEdit.setText(self.mergeDirPath)
		text = initValue(self.mainConfig, 'mergeSkipReg', self.skipRegEdit.text())
		self.skipRegEdit.setText(text)
		# 设置匹配规则
		self.regIndex = int(initValue(self.mainConfig, 'regIndex', 0))
		self.regNameBox.setCurrentIndex(self.regIndex)
		#self.regNameBox.currentIndexChanged.connect(self.selectReg)
		# 截断
		checked = initValue(self.mainConfig, 'cutoff', False)
		self.cutoffCheck.setChecked(checked)
		checked = initValue(self.mainConfig, 'cutoffCopy', True)
		self.cutoffCopyCheck.setChecked(checked)
		# 编码
		index = int(initValue(self.mainConfig, 'encodeIndex', 0))
		self.txtEncodeBox.setCurrentIndex(index)
		# 译文
		checked = initValue(self.mainConfig, 'splitAuto', False)
		self.splitCheck.setChecked(checked)
		checked = initValue(self.mainConfig, 'ignoreSameLineCount', False)
		self.ignoreSameCheck.setChecked(checked)
		maxCountPerLine = initValue(self.mainConfig, 'maxCountPerLine', 512)
		self.splitMaxEdit.setText(str(maxCountPerLine))
		# 段落分割符
		splitParaSep = initValue(self.mainConfig, 'splitParaSep', '\\r\\n')
		self.splitSepEdit.setText(splitParaSep)
		# 固定长度
		fixedMaxPerLine = initValue(self.mainConfig, 'fixedMaxPerLine', False)
		self.fixedMaxCheck.setChecked(fixedMaxPerLine)
		# bin纯文本模式
		checked = initValue(self.mainConfig, 'pureText', False)
		self.binPureTextCheck.setChecked(checked)
		# 译文替换
		checked = initValue(self.mainConfig, 'transReplace', True)
		self.transReplaceCheck.setChecked(checked)
		# 分割前替换
		checked = initValue(self.mainConfig, 'preReplace', False)
		self.preReplaceCheck.setChecked(checked)
		# 段落：skip不影响ctrl（lastCtrl不会置为None）
		checked = initValue(self.mainConfig, 'skipIgnoreCtrl', False)
		self.skipIgnoreCtrlCheck.setChecked(checked)
		# 段落：skip不影响unfinish（不会添加predel_unfinish）
		checked = initValue(self.mainConfig, 'skipIgnoreUnfinish', False)
		self.skipIgnoreUnfinishCheck.setChecked(checked)
		# 结束
		self.engineNameBox.setCurrentIndex(self.engineCode)
		self.initEnd = True
		self.selectEngine(self.engineCode)

	#---------------------------------------------------------------
	#选择主文件夹
	def chooseMainDir(self):
		dirpath = self.mainConfig.value('mainDirPath')
		dirpath = QFileDialog.getExistingDirectory(None, self.mainDirButton.text(), dirpath)
		if dirpath != '':
			self.mainDirPath = dirpath
			self.mainDirEdit.setText(dirpath)
			self.mainConfig.setValue('mainDirPath', dirpath)

	#选择引擎
	def selectEngine(self, index):
		if not self.initEnd: return
		self.engineCode = index
		#print('selectEngine', self.engineCode)
		#显示示例
		engineName = self.engineNameBox.currentText()
		group = 'Engine_' + engineName
		self.engineConfig.beginGroup(group)
		#示例
		value = self.engineConfig.value('sample')
		if value:
			self.sampleBrowser.setText(value)
		else:
			self.sampleBrowser.setText('')
		#名字列表
		self.nameListConfig = self.mainConfig.value(group + '_nameList')
		if self.nameListConfig == None:
			self.nameListConfig = self.engineConfig.value('nameList')
		if self.nameListConfig == None:
			self.nameListTab.setEnabled(False)
			self.nameListConfig = ''
		else:
			self.nameListTab.setEnabled(True)
		self.nameListEdit.setText(self.nameListConfig)
		#特殊处理正则
		if self.engineConfig.value('regDic'):
			self.sampleLabel.setText('正则匹配规则（可在此编辑）')
			if self.engineConfig.value('regDic') == '1':
				self.regNameTab.setEnabled(True)
				self.extraFuncTabs.setCurrentIndex(1)
				self.selectReg(self.regNameBox.currentIndex())
			elif self.engineConfig.value('regDic') == '2':
				self.regNameTab.setEnabled(True)
				self.extraFuncTabs.setCurrentIndex(1)
				regName = self.regNameBox.currentText()
				#只有在custom时才自动替换
				name = engineName.split('_')[0]
				if re.match(r'_*Custom', regName) or re.search(name, regName):
					self.selectReg(self.regNameBox.currentIndex())
			else:
				self.regNameTab.setEnabled(False)
		else:
			self.regNameTab.setEnabled(False)
			self.sampleLabel.setText('引擎脚本示例')
		#引擎类型
		file = self.engineConfig.value('file')
		self.statusBar.showMessage('读取文件方式：'+file)
		self.engineConfig.endGroup()

	#选择预设正则规则
	def selectReg(self, index):
		if not self.initEnd: return
		self.regIndex = index
		#print('selectReg', self.regIndex)
		regName = self.regNameBox.currentText()
		if re.match(r'_*None', regName):
			#还原
			group = 'Engine_' + self.engineNameBox.currentText()
			#示例
			value = self.engineConfig.value(group+'/sample')
			if value:
				self.sampleBrowser.setText(value)
			else:
				self.sampleBrowser.setText('')
			return
		if re.match(r'_*Custom', regName):
			#优先读取自定义规则
			textAll = self.mainConfig.value('reg' + regName)
			if textAll:
				self.sampleBrowser.setText(textAll)
				return
		self.regConfig.beginGroup(regName)
		textPart0 = ''
		textPart1 = ''
		textPart2 = ''
		for key in self.regConfig.childKeys():
			value = self.regConfig.value(key)
			text = key + '=' + value + '\n'
			if re.match(r'\d', key):
				textPart0 += text
			elif key.startswith('sample'):
				textPart2 += text
			else:
				textPart1 += text
		self.regConfig.endGroup()
		self.sampleBrowser.setText(textPart0 + textPart1 + textPart2)

	#提取
	def extractFile(self):
		engineName = self.engineNameBox.currentText()
		group = "Engine_" + engineName
		fileType = self.engineConfig.value(group + '/file')
		regDic = None
		if self.engineConfig.value(group + '/regDic'):
			regDic = self.sampleBrowser.toPlainText()
		args = {
			'file':fileType,
			'workpath':self.mainDirEdit.text(),
			'engineName':engineName,
			'outputFormat':self.outputFileBox.currentIndex(),
			'outputPartMode':self.outputPartBox.currentIndex(),
			'nameList':self.nameListEdit.text(),
			'regDic':regDic,
			'cutoff':self.cutoffCheck.isChecked(),
			'cutoffCopy':self.cutoffCopyCheck.isChecked(),
			'outputFormatExtra':self.outputFileExtraBox.currentIndex() - 1,
			'noInput':  self.noInputCheck.isChecked(),
			'encode': self.txtEncodeBox.currentText(),
			'print': self.getExtractPrintSetting(),
			'splitAuto': self.splitCheck.isChecked(),
			'splitParaSep': self.splitSepEdit.text(),
			'ignoreSameLineCount': self.ignoreSameCheck.isChecked(),
			'fixedMaxPerLine': self.fixedMaxCheck.isChecked(),
			'maxCountPerLine': int(self.splitMaxEdit.text()),
			'binEncodeValid': self.binEncodeCheck.isChecked(),
			'pureText': self.binPureTextCheck.isChecked(),
			'tunnelJis': self.tunnelJisCheck.isChecked(),
			'subsJis': self.subsJisCheck.isChecked(),
			'transReplace': self.transReplaceCheck.isChecked(),
			'preReplace': self.preReplaceCheck.isChecked(),
			'skipIgnoreCtrl': self.skipIgnoreCtrlCheck.isChecked(),
			'skipIgnoreUnfinish': self.skipIgnoreUnfinishCheck.isChecked()
		}
		var.window = self
		#保存配置
		self.saveConfig(args, group)
		print('---------------------------------')
		print(args)
		if fileType == 'txt': 
			mainExtractTxt(args)
		elif fileType == 'bin':
			mainExtractBin(args)
		elif fileType == 'json':
			mainExtractJson(args)
		else:
			print('extractFile:', 'Error file type.')

	def saveConfig(self, args, group):
		self.mainConfig.setValue('mainDirPath', args['workpath'])
		self.mainConfig.setValue('engineCode', self.engineCode)
		self.mainConfig.setValue('outputFormat', args['outputFormat'])
		self.mainConfig.setValue('outputPartMode', args['outputPartMode'])
		if args['nameList'] != '':
			self.mainConfig.setValue(group+'_nameList', args['nameList'])
		else:
			self.mainConfig.remove(group+'_nameList')
		self.mainConfig.setValue('regIndex', self.regIndex)
		self.mainConfig.setValue('cutoff', args['cutoff'])
		self.mainConfig.setValue('cutoffCopy', args['cutoffCopy'])
		self.mainConfig.setValue('maxCountPerLine', args['maxCountPerLine'])
		if self.regNameTab.isEnabled():
			regName = self.regNameBox.currentText()
			if re.match(r'_*Custom', regName):
				#保存自定义规则
				textAll = self.sampleBrowser.toPlainText()
				if not re.match(r'sample', textAll):
					self.mainConfig.setValue('reg' + regName, textAll)
		self.mainConfig.setValue('encodeIndex', self.txtEncodeBox.currentIndex())
		#窗口大小
		self.mainConfig.setValue('windowSize', self.size())
		self.mainConfig.setValue('splitAuto', self.splitCheck.isChecked())
		self.mainConfig.setValue('splitParaSep', args['splitParaSep'])
		self.mainConfig.setValue('ignoreSameLineCount', self.ignoreSameCheck.isChecked())
		self.mainConfig.setValue('fixedMaxPerLine', self.fixedMaxCheck.isChecked())
		self.mainConfig.setValue('pureText', self.binPureTextCheck.isChecked())
		self.mainConfig.setValue('transReplace', self.transReplaceCheck.isChecked())
		self.mainConfig.setValue('preReplace', self.preReplaceCheck.isChecked())
		self.mainConfig.setValue('skipIgnoreCtrl', self.skipIgnoreCtrlCheck.isChecked())
		self.mainConfig.setValue('skipIgnoreUnfinish', self.skipIgnoreUnfinishCheck.isChecked())
		
	#提取打印设置
	def getExtractPrintSetting(self):
		lst = []
		lst.append(self.printCheck0.isChecked()) #info
		lst.append(self.printCheck1.isChecked()) #info
		lst.append(self.printCheck2.isChecked()) #warningGreen
		lst.append(self.printCheck3.isChecked()) #warning
		lst.append(self.printCheck4.isChecked()) #error
		return lst

	def extractFileThread(self):
		self.thread = extractThread()
		self.thread.window = self
		self.thread.finished.connect(self.handleThreadFinished)
		self.thread.start()

	def handleThreadFinished(self, ret):
		if ret == 1:
			self.statusBar.showMessage('提取时发生错误！！！    具体错误详见控制台打印！！！')

	#---------------------------------------------------------------
	#选择工作目录
	def chooseMergeDir(self):
		dirpath = self.mainConfig.value('mergeDirPath')
		dirpath = QFileDialog.getExistingDirectory(None, self.mainDirButton.text(), dirpath)
		if dirpath != '':
			self.mergeDirPath = dirpath
			self.mergeDirEdit.setText(dirpath)
			self.mainConfig.setValue('mergeDirPath', dirpath)

	#合并
	def mergeFile(self):
		workpath = self.mergeDirEdit.text()
		funcIndex = self.mergeFuncBox.currentIndex()
		edit = self.mergeLineEdit.text()
		lineCount = 0
		if edit: lineCount = int(edit)
		args = {
			'workpath':workpath,
			'funcIndex':funcIndex,
			'lineCount':lineCount
		}
		print('---------------------------------')
		print(args)
		mergeTool(args)
		#保存配置
		self.mainConfig.setValue('mergeDirPath', workpath)

	#---------------------------------------------------------------
	#创建字典
	def createDic(self):
		workpath = self.mergeDirEdit.text()
		skipReg = self.skipRegEdit.text()
		args = {
			'workpath':workpath,
			'skipReg':skipReg
		}
		print('---------------------------------')
		print(args)
		createDicTool(args)
		self.mainConfig.setValue('mergeSkipReg', skipReg)

	#收集
	def collectFiles(self):
		self.statusBar.showMessage('暂不支持此功能')

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