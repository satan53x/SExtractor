import time
from PyQt5.QtCore import QThread, pyqtSignal
import traceback

#import debugpy
class extractThread(QThread):
	finished = pyqtSignal(int)  # 自定义信号，用于传递结果

	def __init__(self):
		super().__init__()

	def run(self):
		#debugpy.debug_this_thread()
		start = time.perf_counter()
		ret = 0
		try:
			self.window.extractFile()
		except Exception as ex:
			print('\033[31m提取时发生错误：\033[0m')
			traceback.print_exc()
			print('\033[31m----------------------------------------------------------------------\033[0m')
			ret = 1
		end = time.perf_counter()
		interval = (end - start) * 1000 // 1 / 1000
		print(f"运行时间：{interval} 秒")
		self.finished.emit(ret)
