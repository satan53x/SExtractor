import time
from PyQt5.Qt import QThread

#import debugpy
class extractThread(QThread):
	def __init__(self):
		super().__init__()

	def run(self):
		#debugpy.debug_this_thread()
		start = time.perf_counter()
		self.window.extractFile()
		end = time.perf_counter()
		interval = (end - start) * 1000 // 1 / 1000
		print(f"运行时间：{interval} 秒")
