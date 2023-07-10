from PyQt5.QtCore import QSettings
from PyQt5.QtWidgets import QMainWindow, QFileDialog
from PyQt5.Qt import QThread
from ui_mainWindow import Ui_MainWindow
import sys
sys.path.append('.\src')
from main_extract_txt import mainExtractTxt
from main_extract_bin import mainExtractBin
from main_extract import var
from merge_json import mergeTool

#设置初始值
def initValue(setting, name, v):
	if setting.value(name) == None:
		setting.setValue(name, v)
		print('New Config', name, v)
	else:
		v = setting.value(name)
		#print('Load Config', name, v)
	return v

class MainWindow(QMainWindow, Ui_MainWindow):
	def __init__(self, parent=None):
		super(MainWindow, self).__init__(parent)
		self.setupUi(self)
		#提取
		self.mainDirButton.clicked.connect(self.chooseMainDir)
		self.extractButton.clicked.connect(self.extractFileThread)
		#self.engineNameBox.currentIndexChanged.connect(self.selectEngine)
		self.outputFileBox.currentIndexChanged.connect(self.selectFormat)
		self.outputPartBox.currentIndexChanged.connect(self.selectOutputPart)
		#merge工具
		self.mergeDirButton.clicked.connect(self.chooseMergeDir)
		self.mergeButton.clicked.connect(self.mergeFile)

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
				self.engineNameBox.addItem(value)
			elif group == 'OutputFormat':
				for key in self.engineConfig.childKeys():
					value = self.engineConfig.value(key)
					self.outputFileBox.addItem(value)
			self.engineConfig.endGroup()
		# 当前引擎
		self.engineCode = int(initValue(self.mainConfig, 'engineCode', 0))
		#print(self.engineCode)
		self.engineNameBox.currentIndexChanged.connect(self.selectEngine)
		self.engineNameBox.setCurrentIndex(self.engineCode)
		# 当前输出格式
		self.outputFormat = int(initValue(self.mainConfig, 'outputFormat', 0))
		#print(self.outputFormat)
		self.outputFileBox.setCurrentIndex(self.outputFormat)
		# 单个或多个Json模式
		self.outputPartMode = int(initValue(self.mainConfig, 'outputPartMode', 0))
		#print(self.outputPartMode)
		self.outputPartBox.setCurrentIndex(self.outputPartMode)
		# 合并目录
		self.mergeDirPath = initValue(self.mainConfig, 'mergeDirPath', '.')
		self.mergeDirEdit.setText(self.mergeDirPath)

	#初始化
	def afterShow(self):
		pass

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
			self.nameListConfig = ''
		self.nameListEdit.setText(self.nameListConfig)
		self.engineConfig.endGroup()

	#选择格式
	def selectFormat(self, index):
		self.outputFormat = index
		#print('selectFormat', self.engineCode)

	#选择导出模式
	def selectOutputPart(self, index):
		self.outputPartMode = index
		#print('selectOutputPart', self.outputPartMode)

	#提取
	def extractFile(self):
		engineName = self.engineNameBox.currentText()
		group = "Engine_" + engineName
		fileType = self.engineConfig.value(group + '/file')
		workpath = self.mainDirEdit.text()
		nameList = self.nameListEdit.text()
		args = {
			'workpath':workpath,
			'engineName':engineName,
			'outputFormat':self.outputFormat,
			'outputPartMode':self.outputPartMode,
			'nameList':nameList
		}
		var.window = self
		print(args)
		if fileType == 'txt': 
			mainExtractTxt(args)
		elif fileType == 'bin':
			mainExtractBin(args)
		else:
			print('extractFile:', 'Error file type.')
		#保存配置
		self.mainConfig.setValue('engineCode', self.engineCode)
		self.mainConfig.setValue('outputFormat', self.outputFormat)
		self.mainConfig.setValue('outputPartMode', self.outputPartMode)
		self.mainConfig.setValue('mainDirPath', workpath)
		if nameList != '':
			self.mainConfig.setValue(group+'_nameList', nameList)
		else:
			self.mainConfig.remove(group+'_nameList')

	def extractFileThread(self):
		self.thread = extractThread()
		self.thread.window = self
		self.thread.start()

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
		dirpath = self.mergeDirEdit.text()
		func = self.mergeFuncBox.currentIndex()
		edit = self.mergeLineEdit.text()
		lineCount = 0
		if edit: lineCount = int(edit)
		if lineCount == 0: lineCount = 1000
		args = [dirpath, func, lineCount]
		print(args)
		mergeTool(args)
		#保存配置
		self.mainConfig.setValue('mergeDirPath', dirpath)

#import debugpy
class extractThread(QThread):
	def __init__(self):
		super().__init__()

	def run(self):
		#debugpy.debug_this_thread()
		self.window.extractFile()