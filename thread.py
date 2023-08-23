from PyQt5.Qt import QThread

#import debugpy
class extractThread(QThread):
	def __init__(self):
		super().__init__()

	def run(self):
		#debugpy.debug_this_thread()
		self.window.extractFile()