import os
import re
from PyQt5.QtCore import QCoreApplication
from main.thread import extractThread

class BatchManager():
	mainWindow = None
	oldDir = None
	cmdList = []
	index = 0
	running = False

	def __init__(self, mainWindow):
		self.mainWindow = mainWindow

	def runCommand(self, cmd=None):
		#运行子线程
		self.thread = extractThread(cmd)
		self.thread.window = self.mainWindow
		self.thread.finished.connect(self.handleThreadFinished)
		self.thread.start()

	def handleThreadFinished(self, ret):
		if ret == 1:
			self.mainWindow.statusBar.showMessage(QCoreApplication.translate('MainWindow','提取或导入时发生错误！！！    具体错误详见控制台打印！！！'), 'red')
		self.next()

	# ------------------------- 命令 -------------------------
	def getCmdList(self, text='', join=True):
		if text == '':
			join = True
		if join == True:
			edit = self.mainWindow.batchCmdListEdit.toPlainText()
			self.mainWindow.mainConfig.setValue('batchCmdListText', edit) #保存设置
			self.runInCurPath = self.mainWindow.batchCmdCurCheck.isChecked()
			text += '\n' + edit
		cmdList = []
		strList = re.split(r'[\r\n]+', text)
		for i, str in enumerate(strList):
			str = str.strip()
			if re.search(r'^\s*($|#|//|:: |;)', str):
				continue
			if re.search(r'^extract ', str):
				dirpath = str[8:]
				cmd = {
					"type": "extract",
					"data": dirpath
				}
			elif re.search(r'^run$', str):
				cmd = {
					"type": "run",
					"data": None
				}
			else:
				cmd = {
					"type": "command",
					"data": str
				}
			cmdList.append(cmd)
		return cmdList
	
	def start(self, status=False, cmd='', join=False):
		if self.running:
			self.resultAppend("正在运行中...")
			return
		self.mainWindow.batchResultBrowser.clear()
		self.running = True
		self.oldDir = self.mainWindow.mainDirPath
		self.index = 0
		self.cmdList = self.getCmdList(cmd, join)
		if len(self.cmdList) == 0:
			self.resultAppend("支持的命令：")
			self.resultAppend("extract dirpath")
			self.resultAppend("simple-command")
		self.next()

	def next(self):
		if len(self.cmdList) <= self.index:
			self.resultAppend(">> Done.\n")
			self.mainWindow.chooseMainDir(dir=self.oldDir)
			self.oldDir = None
			self.running = False
			return
		cmd = self.cmdList[self.index]
		self.index += 1
		data = cmd["data"]
		print(f"--------------------------- {self.index}/{len(self.cmdList)} ---------------------------")
		if cmd["type"] == "run":
			# 仅运行
			self.resultAppend(f"提取目录：{self.mainWindow.mainDirPath}")
			self.runCommand()
		elif cmd["type"] == "extract":
			# 提取
			if not os.path.isdir(data):
				self.resultAppend(f'目录不存在：{data}')
				self.next()
				return
			self.resultAppend(f"提取目录：{data}")
			self.mainWindow.chooseMainDir(dir=data) #切换到指定目录
			self.mainWindow.prepareArgs()
			self.runCommand()
		else:
			# 系统命令
			if self.runInCurPath:
				data = f'cd /d "{self.mainWindow.mainDirPath}" && {data}'
			self.resultAppend(f"系统命令：{data}")
			self.runCommand(data)

	# ------------------------- 结果 -------------------------
	def resultAppend(self, line):
		self.mainWindow.batchResultBrowser.append(line)
		print(line)
