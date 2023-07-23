from PyQt5.QtCore import QSettings
from PyQt5.QtWidgets import QMainWindow, QFileDialog
from PyQt5.Qt import QThread
from ui_mainWindow import Ui_MainWindow
import re
import sys
sys.path.append('.\src')
from main_extract_txt import mainExtractTxt
from main_extract_bin import mainExtractBin
from main_extract import var
from merge_json import mergeTool, createDicTool

class MainWindow(QMainWindow, Ui_MainWindow):
	def __init__(self, parent=None):
		super(MainWindow, self).__init__(parent)
		self.setupUi(self)
		#提取
		self.mainDirButton.clicked.connect(self.chooseMainDir)
		self.extractButton.clicked.connect(self.extractFileThread)
		#self.engineNameBox.currentIndexChanged.connect(self.selectEngine)
		#self.outputFileBox.currentIndexChanged.connect(self.selectFormat)
		#self.outputPartBox.currentIndexChanged.connect(self.selectOutputPart)
		#merge工具
		self.mergeDirButton.clicked.connect(self.chooseMergeDir)
		self.mergeButton.clicked.connect(self.mergeFile)
		#创建字典
		self.createDicButton.clicked.connect(self.createDic)

	#初始化
	def beforeShow(self):
		self.mainConfig = QSettings('config.ini', QSettings.IniFormat)
		self.mainConfig.setIniCodec('utf-8')
		# 主目录
		self.mainDirPath = initValue(self.mainConfig, 'mainDirPath', '.')
		self.mainDirEdit.setText(self.mainDirPath)
		# 引擎列表
		self.engineConfig = QSettings('src/engine.ini', QSettings.IniFormat)
		self.engineConfig.setIniCodec('utf-8')
		groupList = self.engineConfig.childGroups()
		for group in groupList: 
			#print(group)
			self.engineConfig.beginGroup(group)
			if group.startswith('Engine_'):
				value = group[len("Engine_"):]
				if self.engineConfig.value('regDic'):
					self.engineNameBox.insertItem(0, value)
				else:
					self.engineNameBox.addItem(value)
			elif group == 'OutputFormat':
				for key in self.engineConfig.childKeys():
					value = self.engineConfig.value(key)
					self.outputFileBox.addItem(value)
					self.outputFileExtraBox.addItem(value)
			self.engineConfig.endGroup()
		# 当前引擎
		self.engineCode = int(initValue(self.mainConfig, 'engineCode', 0))
		#print(self.engineCode)
		self.engineNameBox.currentIndexChanged.connect(self.selectEngine)
		# 当前输出格式
		self.outputFormat = int(initValue(self.mainConfig, 'outputFormat', 0))
		#print(self.outputFormat)
		self.outputFileBox.setCurrentIndex(self.outputFormat)
		self.outputFileExtraBox.addItem('无')
		self.outputFileExtraBox.setCurrentIndex(self.outputFileExtraBox.count() - 1)
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
		self.regConfig = QSettings('src/reg.ini', QSettings.IniFormat)
		self.regConfig.setIniCodec('utf-8')
		groupList = self.regConfig.childGroups()
		for group in groupList: 
			#print(group)
			self.regNameBox.addItem(group)
		self.regIndex = int(initValue(self.mainConfig, 'regIndex', 0))
		self.regNameBox.setCurrentIndex(self.regIndex)
		self.regNameBox.currentIndexChanged.connect(self.selectReg)
		# 结束
		self.engineNameBox.setCurrentIndex(self.engineCode)
		# 截断
		checked = initValue(self.mainConfig, 'cutoff', False) != 'false'
		self.cutOffCheck.setChecked(checked)

	#初始化
	def afterShow(self):
		pass
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
			self.regNameTab.setEnabled(True)
			self.sampleLabel.setText('正则匹配规则（可在此编辑）')
			self.extraFuncTabs.setCurrentIndex(1)
			self.selectReg(self.regNameBox.currentIndex())
		else:
			self.regNameTab.setEnabled(False)
			self.sampleLabel.setText('引擎脚本示例')
		self.engineConfig.endGroup()

	#选择预设正则规则
	def selectReg(self, index):
		self.regIndex = index
		#print('selectReg', self.regIndex)
		regName = self.regNameBox.currentText()
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
		workpath = self.mainDirEdit.text()
		outputFormat = self.outputFileBox.currentIndex()
		outputPartMode = self.outputPartBox.currentIndex()
		nameList = self.nameListEdit.text()
		regDic = None
		if self.engineConfig.value(group + '/regDic'):
			regDic = self.sampleBrowser.toPlainText()
		cutoff = self.cutOffCheck.isChecked()
		outputFormatExtra = self.outputFileExtraBox.currentIndex()
		args = {
			'workpath':workpath,
			'engineName':engineName,
			'outputFormat':outputFormat,
			'outputPartMode':outputPartMode,
			'nameList':nameList,
			'regDic':regDic,
			'cutoff':cutoff,
			'outputFormatExtra':outputFormatExtra
		}
		var.window = self
		#保存配置
		self.saveConfig(args, group)
		print('---------------------------------')
		print(args)
		fileType = self.engineConfig.value(group + '/file')
		if fileType == 'txt': 
			mainExtractTxt(args)
		elif fileType == 'bin':
			mainExtractBin(args)
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

	def extractFileThread(self):
		self.thread = extractThread()
		self.thread.window = self
		self.thread.start()

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

#---------------------------------------------------------------
#import debugpy
class extractThread(QThread):
	def __init__(self):
		super().__init__()

	def run(self):
		#debugpy.debug_this_thread()
		self.window.extractFile()

#设置初始值
def initValue(setting, name, v):
	if setting.value(name) == None:
		setting.setValue(name, v)
		print('New Config', name, v)
	else:
		v = setting.value(name)
		#print('Load Config', name, v)
	return v