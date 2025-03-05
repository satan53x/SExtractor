import os
import sys
#PyQt5中使用的基本控件都在PyQt5.QtWidgets模块中
from PyQt5.QtCore import QCoreApplication, Qt
from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import QLocale, QTranslator
from main.mainWindow import MainWindow

Version = '3.7.0' #软件版本号

if __name__ == "__main__":
    # 使程序按系统比例放大，免得字体变形
    QCoreApplication.setAttribute(Qt.AA_EnableHighDpiScaling)
    QCoreApplication.setAttribute(Qt.AA_UseHighDpiPixmaps)
    #固定的，PyQt5程序都需要QApplication对象。sys.argv是命令行参数列表，确保程序可以双击运行
    app = QApplication(sys.argv)

    translator = QTranslator()
    lang_code = QLocale.system().name()
    #lang_code = 'en_US' #test, force Language
    if not lang_code.startswith('zh_'):
        file = './main/locale/' + lang_code + '.qm'
        if not os.path.exists(file):
            file = './main/locale/en_US.qm' # default use EN
        translator.load(file)
        app.installTranslator(translator)

    #初始化
    win = MainWindow(version=Version)
    #将窗口控件显示在屏幕上
    win.beforeShow()
    win.show()
    win.afterShow()
    if len(sys.argv) >= 2:
        if sys.argv[1] in ('-e', '--extract'):
            win.extractFile()
    #程序运行，sys.exit方法确保程序完整退出。
    sys.exit(app.exec_())
