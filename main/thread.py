import os
import sys
import time
from PyQt5.QtCore import QThread, pyqtSignal
import traceback
from src.common import ExVar

isDebug = True if sys.gettrace() else False
class extractThread(QThread):
	finished = pyqtSignal(int)  # 自定义信号，用于传递结果

	def __init__(self, cmd=None):
		super().__init__()
		self.cmd = cmd

	def run(self):
		if isDebug:
			#import debugpy
			#debugpy.debug_this_thread()
			pass
		start = time.perf_counter()
		ret = 0
		try:
			if self.cmd:
				os.system(self.cmd)
			else:
				self.window.extractFileThread()
		except Exception as ex:
			print('\033[31m---------------------------提取或导入时发生错误---------------------------\033[0m')
			traceback.print_exc()
			print('\033[31m--------------------------------------------------------------------------\033[0m')
			print(f'\033[33m异常中断文件名: {ExVar.filename}\033[0m')
			ret = 1
			#raise
		end = time.perf_counter()
		interval = (end - start) * 1000 // 1 / 1000
		print(f"运行时间：{interval} 秒")
		self.finished.emit(ret)
