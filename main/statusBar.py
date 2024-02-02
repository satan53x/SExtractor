from PyQt5.QtWidgets import QStatusBar, QLabel, QProgressBar, QStackedWidget, QHBoxLayout
from PyQt5.QtCore import pyqtSignal

class StatusBar(QStatusBar):
	textSig = pyqtSignal(str, str)
	progressSig = pyqtSignal(int, int)

	def __init__(self, parent=None):
		super().__init__(parent)
		self.setStyleSheet("QStatusBar::item { border: 0px solid black; }")
		self.layer = QStackedWidget()
		self.layer.setContentsMargins(10, 4, 1, 5)
		self.addWidget(self.layer, 16)
		#文本
		self.label:QLabel = QLabel()
		self.label.setFont(self.font())
		self.layer.addWidget(self.label)
		self.textSig.connect(self.showMessage)
		#进度条
		self.progress:QProgressBar = QProgressBar(self)
		self.progress.setFixedHeight(18)
		self.progress.setLayout(QHBoxLayout())
		self.progress.setFormat(' %p%')
		self.layer.addWidget(self.progress)
		self.layer.setCurrentIndex(0)
		self.progressSig.connect(self.showProgress)
		
	#------------------------------------------------------
	def showMessage(self, text, color='black'):
		self.label.setStyleSheet(f'color: {color};')
		self.label.setText(text)
		self.layer.setCurrentIndex(0)

	def showProgress(self, value, max=100):
		self.progress.setValue(value * 100 // max)
		self.layer.setCurrentIndex(1)
	
	#------------------------------------------------------
	def sendMessage(self, text, color='black'):
		self.textSig.emit(text, color)

	def sendProgress(self, value, max=100):
		self.progressSig.emit(value, max)