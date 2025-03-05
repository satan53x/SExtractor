import os
import shutil
from PyQt5.QtCore import QSettings, QCoreApplication
from PyQt5.QtWidgets import QMainWindow, QFileDialog
from PyQt5.QtGui import QIcon
from main.ui_mainWindow import Ui_MainWindow
import re
import sys
import ctypes
import platform
sys.path.append('./src')
from main_extract_txt import mainExtractTxt
from main_extract_bin import mainExtractBin
from main_extract_json import mainExtractJson
from main_extract import var
from merge_json import mergeTool, createDicTool, collectFilesTool, distFilesTool
from main.configManager import ConfigManager
from main.batchManager import BatchManager
from main.statusBar import StatusBar

class MainWindow(QMainWindow, Ui_MainWindow):

	def __init__(self, parent=None, version='1.0.0'):
		super(MainWindow, self).__init__(parent)
		self.version = version
		self.setupUi(self)
		self.initEnd = False
		#设置图标
		icon = QIcon("main/main.ico")
		self.setWindowIcon(icon)
		if platform.system() == "Windows":
			ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("myappid")
		#设置状态栏
		self.statusBar = StatusBar(self)
		self.setStatusBar(self.statusBar)
		#信号
		self.mainTab.currentChanged.connect(self.changeTab)
		self.mainDirButton.clicked.connect(self.chooseMainDir)
		self.extractButton.clicked.connect(self.extractFile)
		self.engineNameBox.currentIndexChanged.connect(self.selectEngine)
		#self.outputFileBox.currentIndexChanged.connect(self.selectFormat)
		#self.outputPartBox.currentIndexChanged.connect(self.selectOutputPart)
		self.regNameBox.currentIndexChanged.connect(self.selectReg)
		#merge工具
		self.mergeDirButton.clicked.connect(self.chooseMergeDir)
		self.mergeButton.clicked.connect(self.mergeFile)
		self.collectButton.clicked.connect(self.collectFiles)
		self.distButton.clicked.connect(self.distFiles)
		#创建字典
		self.createDicButton.clicked.connect(self.createDic)
		#配置
		self.configManager = ConfigManager(self)
		self.configManager.showSeq()
		#批量
		self.batchManager = BatchManager(self)
		self.batchStartButton.clicked.connect(self.batchManager.start)

	def changeTab(self, index):
		if index == 3: #readme
			self.statusBar.showMessage(f'版本号：Ver{self.version}')

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
		self.configManager.changeConfigSeq(0)

	#初始化
	def afterShow(self):
		#修正打印颜色
		from colorama import init
		init(autoreset=True)

	#---------------------------------------------------------------
	#选择提取目录
	def chooseMainDir(self, status=False, dir=None):
		if dir == None:
			dirpath = self.mainConfig.value('mainDirPath')
			dirpath = QFileDialog.getExistingDirectory(None, self.mainDirButton.text(), dirpath)
		else:
			dirpath = dir
		if os.path.isdir(dirpath):
			if os.path.isdir(self.mainDirPath):
				if os.path.samefile(dirpath, self.mainDirPath):
					return #已在当前目录
			self.mainDirPath = os.path.normpath(dirpath)
			#是否自动生成ini
			if self.autoCacheCheck.isChecked():
				path = os.path.join(self.mainDirPath, 'ctrl', 'config.ini')
				if not os.path.isfile(path):
					os.makedirs(os.path.dirname(path), exist_ok=True)
					oldConfigName = self.configManager.configName
					if not os.path.isfile(oldConfigName):
						oldConfigName = 'main/config.ini'
					shutil.copyfile(oldConfigName, path)
			#检查ini
			self.configManager.isCheckDirIni = True
			self.configManager.checkDirIni()
			self.mainDirEdit.setText(dirpath)
			self.mainConfig.setValue('mainDirPath', dirpath)
			#检查是否是内置ini
			if self.mainConfig != self.configManager.builtinConfig:
				self.configManager.builtinConfig.setValue('mainDirPath', dirpath)

	#选择引擎
	def selectEngine(self, index):
		if not self.initEnd: return
		self.engineCode = index
		#print('selectEngine', self.engineCode)
		#显示示例
		self.engineName = self.engineNameBox.currentText()
		group = 'Engine_' + self.engineName
		self.engineConfig.beginGroup(group)
		#示例
		value = self.engineConfig.value('sample')
		self.setSampleText(value)
		#名字列表
		self.nameListConfig = self.mainConfig.value(group + '_nameList')
		if self.nameListConfig == None:
			self.nameListConfig = self.engineConfig.value('nameList')
		if self.nameListConfig == None:
			self.nameListTab.setEnabled(True)
			self.nameListConfig = ''
		else:
			self.nameListTab.setEnabled(True)
		self.nameListEdit.setText(self.nameListConfig)
		#特殊处理正则
		if self.engineConfig.value('regDic'):
			self.sampleLabel.setText(QCoreApplication.translate('MainWindow', '正则匹配规则（可在此编辑）'))
			if self.engineConfig.value('regDic') == '1':
				self.regNameTab.setEnabled(True)
				self.extraFuncTabs.setCurrentIndex(1)
				self.selectReg(self.regNameBox.currentIndex())
			elif self.engineConfig.value('regDic') == '2':
				self.regNameTab.setEnabled(True)
				self.extraFuncTabs.setCurrentIndex(1)
				regName = self.regNameBox.currentText()
				#只有在custom时才自动替换
				name = self.engineName.split('_')[0]
				if re.match(r'_*Custom', regName) or re.search(name, regName):
					self.selectReg(self.regNameBox.currentIndex())
			else:
				self.regNameTab.setEnabled(False)
		else:
			self.regNameTab.setEnabled(False)
			self.sampleLabel.setText(QCoreApplication.translate('MainWindow', '引擎脚本示例'))
		#引擎类型
		file = self.engineConfig.value('file')
		self.statusBar.showMessage(QCoreApplication.translate('MainWindow', '读取文件方式：')+file)
		self.engineConfig.endGroup()

	#选择预设正则规则
	def selectReg(self, index):
		if not self.initEnd: return
		self.regIndex = index
		#print('selectReg', self.regIndex)
		regName = self.regNameBox.currentText()
		if re.match(r'_*None', regName):
			#还原
			group = 'Engine_' + self.engineName
			#示例
			value = self.engineConfig.value(group+'/sample')
			self.setSampleText(value)
			return
		if re.match(r'_*Custom', regName):
			#优先读取自定义规则
			textAll = self.mainConfig.value('reg' + regName)
			if textAll:
				self.setSampleText(textAll)
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
		self.setSampleText(textPart0 + textPart1 + textPart2)
		
	def setSampleText(self, value):
		if value:
			self.sampleBrowser.setText(value)
		else:
			self.sampleBrowser.setText('')
		self.configManager.oldReg = self.sampleBrowser.toPlainText()

	#提取打印设置
	def getExtractPrintSetting(self):
		lst = []
		lst.append(self.printCheck0.isChecked()) #info
		lst.append(self.printCheck1.isChecked()) #info
		lst.append(self.printCheck2.isChecked()) #warningGreen
		lst.append(self.printCheck3.isChecked()) #warning
		lst.append(self.printCheck4.isChecked()) #error
		return lst

	def prepareArgs(self):
		group = "Engine_" + self.engineName
		fileType = self.engineConfig.value(group + '/file')
		regDic = None
		if self.engineConfig.value(group + '/regDic'):
			regDic = self.sampleBrowser.toPlainText()
		args = {
			'file':fileType,
			'workpath':self.mainDirEdit.text(),
			'engineName':self.engineName,
			'outputFormat':self.outputFileBox.currentIndex(),
			'outputPartMode':self.outputPartBox.currentIndex(),
			'nameList':self.nameListEdit.text(),
			'regDic':regDic,
			'outputFormatExtra':self.outputFileExtraBox.currentIndex() - 1,
			'encode': self.txtEncodeBox.currentText(),
			'print': self.getExtractPrintSetting(),
			'splitParaSep': self.splitSepEdit.text(),
			'maxCountPerLine': int(self.splitMaxEdit.text()),
		}
		self.configManager.addCheck2Args(args)
		var.window = self
		self.args = args
		#保存配置
		self.configManager.saveConfig(args, group)

	def extractFile(self):
		auto = self.batchAutoStartCheck.isChecked()
		self.batchManager.start(cmd=f'extract {self.mainDirPath}', join=auto)
	
	#提取
	def extractFileThread(self):
		args = self.args
		#print('------------------------------------------')
		print(args)
		if args['file'] == 'txt': 
			mainExtractTxt(args)
		elif args['file'] == 'bin':
			mainExtractBin(args)
		elif args['file'] == 'json':
			mainExtractJson(args)
		else:
			print('extractFile:', 'Error file type.')

	#---------------------------------------------------------------
	#选择合并目录
	def chooseMergeDir(self):
		dirpath = self.mainConfig.value('mergeDirPath')
		dirpath = QFileDialog.getExistingDirectory(None, self.mainDirButton.text(), dirpath)
		if dirpath != '':
			self.mergeDirPath = dirpath
			self.mergeDirEdit.setText(dirpath)
			self.mainConfig.setValue('mergeDirPath', dirpath)

	#合并
	def mergeFile(self):
		mergePath = self.mergeDirEdit.text()
		funcIndex = self.mergeFuncBox.currentIndex()
		edit = self.mergeLineEdit.text()
		lineCount = 0
		if edit: lineCount = int(edit)
		args = {
			'mergePath':mergePath,
			'funcIndex':funcIndex,
			'lineCount':lineCount
		}
		print('---------------------------------')
		print(args)
		mergeTool(args)
		#保存配置
		self.mainConfig.setValue('mergeDirPath', mergePath)

	#---------------------------------------------------------------
	#创建字典
	def createDic(self):
		mergePath = self.mergeDirEdit.text()
		skipReg = self.skipRegEdit.text()
		args = {
			'mergePath':mergePath,
			'skipReg':skipReg
		}
		print('---------------------------------')
		print(args)
		createDicTool(args)
		self.mainConfig.setValue('mergeSkipReg', skipReg)

	#---------------------------------------------------------------
	#收集
	def collectFiles(self):
		mergePath = self.mergeDirEdit.text()
		extractPath = self.mainDirEdit.text()
		filenameReg = self.collectFilenameEdit.text() #文件名匹配
		collectSep = self.collectSepEdit.text() #多级目录分割符
		args = {
			'mergePath':mergePath,
			'extractPath':extractPath,
			'filenameReg':filenameReg,
			'collectSep':collectSep,
		}
		print('---------------------------------')
		print(args)
		collectFilesTool(args)
		self.statusBar.showMessage(QCoreApplication.translate('MainWindow','收集完成。'))
		#保存配置
		self.mainConfig.setValue('mergeDirPath', mergePath)
		self.mainConfig.setValue('mainDirPath', extractPath)
		self.mainConfig.setValue('collectSep', collectSep)

	#分发
	def distFiles(self):
		mergePath = self.mergeDirEdit.text()
		extractPath = self.mainDirEdit.text()
		filenameReg = self.collectFilenameEdit.text() #文件名匹配
		collectSep = self.collectSepEdit.text() #多级目录分割符
		args = {
			'mergePath':mergePath,
			'extractPath':extractPath,
			'filenameReg':filenameReg,
			'collectSep':collectSep,
		}
		print('---------------------------------')
		print(args)
		distFilesTool(args)
		self.statusBar.showMessage(QCoreApplication.translate('MainWindow','分发完成。'))
		#保存配置
		self.mainConfig.setValue('mergeDirPath', mergePath)
		self.mainConfig.setValue('mainDirPath', extractPath)
		self.mainConfig.setValue('collectSep', collectSep)