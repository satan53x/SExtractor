import sys
#PyQt5中使用的基本控件都在PyQt5.QtWidgets模块中
from PyQt5.QtWidgets import QApplication
from main.mainWindow import MainWindow

Version = '1.2.0' #软件版本号

if __name__ == "__main__":
    #固定的，PyQt5程序都需要QApplication对象。sys.argv是命令行参数列表，确保程序可以双击运行
    app = QApplication(sys.argv)
    #初始化
    win = MainWindow(version=Version)
    #将窗口控件显示在屏幕上
    win.beforeShow()
    win.show()
    win.afterShow()
    #程序运行，sys.exit方法确保程序完整退出。
    sys.exit(app.exec_())