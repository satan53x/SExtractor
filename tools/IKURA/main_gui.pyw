import sys
import os
import time
import ikura_decryptor
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                               QHBoxLayout, QLabel, QLineEdit, QPushButton, 
                               QTextEdit, QFileDialog, QGroupBox, QTabWidget, QCheckBox)
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QTextCursor
import json
from ISF_FILE import ISF_FILE
from Lib import save_json, open_json, replace_halfwidth_with_fullwidth
from ISF_PACK import auto_pack_isf
import re

# ==========================================
# 1. 自定义支持拖拽的输入框 (保持不变)
# ==========================================
class DropLineEdit(QLineEdit):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setAcceptDrops(True)
        self.setPlaceholderText("可直接将文件或文件夹拖拽至此...")

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.accept()
        else:
            event.ignore()

    def dropEvent(self, event):
        urls = event.mimeData().urls()
        if urls:
            path = urls[0].toLocalFile()
            self.setText(path)

# ==========================================
# 2. 拦截 print() 输出的信号类 (保持不变)
# ==========================================
class EmittingStr(object):
    def __init__(self, signal):
        self.signal = signal

    def write(self, text):
        if text.strip() != "":
            self.signal.emit(text)

    def flush(self):
        pass

# ==========================================
# 3. 后台工作线程 (保持不变)
# ==========================================
class WorkerThread(QThread):
    finished_signal = Signal()
    error_signal = Signal(str)

    def __init__(self, task_func, *args, **kwargs):
        super().__init__()
        self.task_func = task_func
        self.args = args
        self.kwargs = kwargs

    def run(self):
        try:
            self.task_func(*self.args, **self.kwargs)
        except Exception as e:
            self.error_signal.emit(str(e))
        finally:
            self.finished_signal.emit()

# ==========================================
# 4. 主窗口 (升级为选项卡布局)
# ==========================================
class IKURAToolbox(QMainWindow):
    print_signal = Signal(str)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("IKURA GDL 汉化工具箱通用版")
        self.resize(850, 650)

        # 重定向标准输出
        sys.stdout = EmittingStr(self.print_signal)
        sys.stderr = EmittingStr(self.print_signal)
        self.print_signal.connect(self.append_log)

        self.init_ui()

    def init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # 主布局分为上下两部分：上部是选项卡，下部是全局日志
        main_layout = QVBoxLayout(central_widget)

        # --- 顶部：模块选项卡 (QTabWidget) ---
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet("QTabBar::tab { height: 35px; width: 150px; font-weight: bold; }")
        
        # 创建四个模块的面板
        self.tab_a = QWidget()
        self.tab_b = QWidget()
        self.tab_c = QWidget()
        self.tab_d = QWidget()

        # 将面板添加到选项卡中
        self.tabs.addTab(self.tab_a, "模块 A: 解包提取")
        self.tabs.addTab(self.tab_b, "模块 B: 文本导出")
        self.tabs.addTab(self.tab_c, "模块 C: 文本导入")
        self.tabs.addTab(self.tab_d, "模块 D: 重打包")

        main_layout.addWidget(self.tabs, stretch=1) # 占比参数 1

        # 初始化各个选项卡的具体内容
        self.init_tab_a_ui()
        self.init_tab_b_ui()
        self.init_tab_c_ui()
        self.init_tab_d_ui()  # <--- 新增这行，激活模块 D
        # (删除了 self.init_tab_placeholders() 这行)

        # --- 底部：全局运行日志 ---
        log_group = QGroupBox("全局运行日志")
        log_layout = QVBoxLayout()
        self.log_console = QTextEdit()
        self.log_console.setReadOnly(True)
        self.log_console.setStyleSheet("background-color: #1e1e1e; color: #d4d4d4; font-family: Consolas; font-size: 13px;")
        log_layout.addWidget(self.log_console)
        log_group.setLayout(log_layout)
        
        main_layout.addWidget(log_group, stretch=2) # 日志区域可以稍微给大一点空间 (占比 2)

        print("欢迎使用 IKURA GDL 汉化工具箱！已切换至通用模式。")

    def init_tab_a_ui(self):
        """初始化模块 A 的界面"""
        layout = QVBoxLayout(self.tab_a)
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)

        # 游戏 EXE 路径 (更普遍适配)
        exe_layout = QHBoxLayout()
        exe_layout.addWidget(QLabel("游戏 EXE 路径:"))
        self.exe_input = DropLineEdit()
        exe_layout.addWidget(self.exe_input)
        btn_browse_exe = QPushButton("浏览...")
        btn_browse_exe.clicked.connect(lambda: self.browse_file(self.exe_input, "选择游戏主程序", "*.exe"))
        exe_layout.addWidget(btn_browse_exe)
        layout.addLayout(exe_layout)

        # ISF 数据包路径 (更普遍适配)
        dat_layout = QHBoxLayout()
        dat_layout.addWidget(QLabel("ISF 数据包路径:"))
        self.dat_input = DropLineEdit()
        dat_layout.addWidget(self.dat_input)
        btn_browse_dat = QPushButton("浏览...")
        btn_browse_dat.clicked.connect(lambda: self.browse_file(self.dat_input, "选择原始封包数据", "*.*"))
        dat_layout.addWidget(btn_browse_dat)
        layout.addLayout(dat_layout)

        # 执行按钮
        self.btn_unpack = QPushButton(">> 执行解包与解密 <<")
        self.btn_unpack.setMinimumHeight(45)
        self.btn_unpack.setStyleSheet("font-size: 14px; font-weight: bold;")
        self.btn_unpack.clicked.connect(self.start_unpack_task)
        layout.addWidget(self.btn_unpack)
        
        layout.addStretch() # 把控件往上顶

    def init_tab_b_ui(self):
        """初始化模块 B 的界面"""
        layout = QVBoxLayout(self.tab_b)
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)

        # 解包后的 ISF 输入目录
        in_layout = QHBoxLayout()
        in_layout.addWidget(QLabel("已解包的 ISF 目录:"))
        self.b_in_input = DropLineEdit()
        # 默认贴心地填上模块A的输出路径
        self.b_in_input.setText(os.path.join(os.getcwd(), "isf_origin"))
        in_layout.addWidget(self.b_in_input)
        btn_in = QPushButton("浏览...")
        btn_in.clicked.connect(lambda: self.browse_dir(self.b_in_input, "选择解包后的 ISF 目录"))
        in_layout.addWidget(btn_in)
        layout.addLayout(in_layout)

        # JSON 导出目录
        out_layout = QHBoxLayout()
        out_layout.addWidget(QLabel("JSON 翻译导出目录:"))
        self.b_out_input = DropLineEdit()
        # 默认填上你习惯的 gt_input
        self.b_out_input.setText(os.path.join(os.getcwd(), "gt_input"))
        out_layout.addWidget(self.b_out_input)
        btn_out = QPushButton("浏览...")
        btn_out.clicked.connect(lambda: self.browse_dir(self.b_out_input, "选择 JSON 保存目录"))
        out_layout.addWidget(btn_out)
        layout.addLayout(out_layout)

        # 自动化选项
        self.chk_auto_name = QCheckBox("智能提取：自动解析 start.isf 并生成人名表 (nameidx.json)")
        self.chk_auto_name.setChecked(True)
        self.chk_auto_name.setStyleSheet("font-weight: bold; color: #0078D7;")
        layout.addWidget(self.chk_auto_name)

        # 执行按钮
        self.btn_dump = QPushButton(">> 执行文本批量导出 <<")
        self.btn_dump.setMinimumHeight(45)
        self.btn_dump.setStyleSheet("font-size: 14px; font-weight: bold;")
        self.btn_dump.clicked.connect(self.start_dump_task)
        layout.addWidget(self.btn_dump)
        
        layout.addStretch()

    def init_tab_c_ui(self):
        """初始化模块 C 的界面"""
        layout = QVBoxLayout(self.tab_c)
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)

        # 1. 原始 ISF 目录
        ori_layout = QHBoxLayout()
        ori_layout.addWidget(QLabel("原始 ISF 目录 (解包后的文件夹):"))
        self.c_ori_input = DropLineEdit()
        self.c_ori_input.setText(os.path.join(os.getcwd(), "isf_origin"))
        ori_layout.addWidget(self.c_ori_input)
        btn_ori = QPushButton("浏览...")
        btn_ori.clicked.connect(lambda: self.browse_dir(self.c_ori_input, "选择原始 ISF 目录"))
        ori_layout.addWidget(btn_ori)
        layout.addLayout(ori_layout)

        # 2. 翻译 JSON 目录
        trans_layout = QHBoxLayout()
        trans_layout.addWidget(QLabel("翻译好的 JSON 目录:"))
        self.c_trans_input = DropLineEdit()
        self.c_trans_input.setText(os.path.join(os.getcwd(), "gt_input"))
        trans_layout.addWidget(self.c_trans_input)
        btn_trans = QPushButton("浏览...")
        btn_trans.clicked.connect(lambda: self.browse_dir(self.c_trans_input, "选择翻译 JSON 目录"))
        trans_layout.addWidget(btn_trans)
        layout.addLayout(trans_layout)

        # 3. 封包输出目录
        out_layout = QHBoxLayout()
        out_layout.addWidget(QLabel("新 ISF 封包输出目录:"))
        self.c_out_input = DropLineEdit()
        self.c_out_input.setText(os.path.join(os.getcwd(), "release", "ISF_final"))
        out_layout.addWidget(self.c_out_input)
        btn_out = QPushButton("浏览...")
        btn_out.clicked.connect(lambda: self.browse_dir(self.c_out_input, "选择输出目录"))
        out_layout.addWidget(btn_out)
        layout.addLayout(out_layout)

        # 执行按钮
        self.btn_pack = QPushButton(">> 执行文本导入与生成新 ISF <<")
        self.btn_pack.setMinimumHeight(45)
        self.btn_pack.setStyleSheet("font-size: 14px; font-weight: bold;")
        self.btn_pack.clicked.connect(self.start_pack_task)
        layout.addWidget(self.btn_pack)
        
        layout.addStretch()

    def init_tab_d_ui(self):
        """初始化模块 D 的界面"""
        layout = QVBoxLayout(self.tab_d)
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)

        # 1. 散文件输入目录
        in_layout = QHBoxLayout()
        in_layout.addWidget(QLabel("修改后的散文件目录:"))
        self.d_in_input = DropLineEdit()
        self.d_in_input.setText(os.path.join(os.getcwd(), "release", "ISF_final"))
        in_layout.addWidget(self.d_in_input)
        btn_in = QPushButton("浏览...")
        btn_in.clicked.connect(lambda: self.browse_dir(self.d_in_input, "选择修改后的散文件目录"))
        in_layout.addWidget(btn_in)
        layout.addLayout(in_layout)

        # 2. 新大包输出路径
        out_layout = QHBoxLayout()
        out_layout.addWidget(QLabel("生成的新大包保存目录:")) 
        self.d_out_input = DropLineEdit()
        self.d_out_input.setText(os.path.join(os.getcwd(), "release")) 
        out_layout.addWidget(self.d_out_input)
        btn_out = QPushButton("浏览...")
        btn_out.clicked.connect(lambda: self.browse_dir(self.d_out_input, "选择保存目录")) 
        out_layout.addWidget(btn_out)
        layout.addLayout(out_layout)

        # 执行按钮
        self.btn_repack = QPushButton(">> 执行终极智能封包 <<")
        self.btn_repack.setMinimumHeight(45)
        self.btn_repack.setStyleSheet("font-size: 14px; font-weight: bold; color: #d83b01;")
        self.btn_repack.clicked.connect(self.start_repack_task)
        layout.addWidget(self.btn_repack)
        
        layout.addStretch()           

    def append_log(self, text):
        self.log_console.moveCursor(QTextCursor.End)
        self.log_console.insertPlainText(text + "\n")
        self.log_console.moveCursor(QTextCursor.End)

    def browse_file(self, line_edit, title, filter_str):
        file_path, _ = QFileDialog.getOpenFileName(self, title, "", filter_str)
        if file_path:
            line_edit.setText(file_path)

    def browse_dir(self, line_edit, title):
        """通用文件夹浏览对话框"""
        dir_path = QFileDialog.getExistingDirectory(self, title)
        if dir_path:
            line_edit.setText(dir_path)  

    def browse_save_file(self, line_edit, title, filter_str):
        """通用文件保存对话框"""
        file_path, _ = QFileDialog.getSaveFileName(self, title, "", filter_str)
        if file_path:
            line_edit.setText(file_path)              

    # === 业务逻辑模拟 ===
    def start_unpack_task(self):
        exe_path = self.exe_input.text().strip()
        dat_path = self.dat_input.text().strip()
        
        # 增加严格的路径存在性校验
        if not os.path.exists(exe_path) or not os.path.exists(dat_path):
            print("[-] 错误：请填入真实存在的游戏 EXE 和 ISF 数据包路径！")
            return

        self.btn_unpack.setEnabled(False)
        print("\n" + "="*50)
        print("开始执行模块 A: 真·解包任务...")

        # 启动真实的工作线程，将路径传给 real_unpack_task
        self.thread = WorkerThread(self.real_unpack_task, exe_path, dat_path)
        self.thread.finished_signal.connect(self.on_task_finished)
        self.thread.error_signal.connect(lambda e: print(f"[-] 发生严重异常: {e}"))
        self.thread.start()

    def real_unpack_task(self, exe_path, dat_path):
        """调用 ikura_decryptor 的核心逻辑，并自动管理输出目录"""
        
        # 1. 动态生成 isf_origin 路径 (修改为：直接在工具当前目录下生成)
        out_dir = os.path.join(os.getcwd(), "isf_origin")
        os.makedirs(out_dir, exist_ok=True)
        print(f"[*] 自动创建/定位输出目录: {out_dir}")

        # 2. 调用你写的提取秘钥功能
        secret_data = ikura_decryptor.auto_extract_secret(exe_path)
        
        if not secret_data:
            print("[-] 警告：未能在 EXE 中自动提取到秘钥，尝试直接提取文件。")

        # 3. 调用你的核心解包功能
        # (因为你的函数里已经写了打印提取日志的代码，这里直接调用即可，GUI会自动捕获打印)
        ikura_decryptor.unpack_and_decrypt(dat_path, secret_data, out_dir)
        
        print(f"\n[!] 模块 A 处理完成！解密文件已全部就绪。")

    def start_dump_task(self):
        in_dir = self.b_in_input.text().strip()
        out_dir = self.b_out_input.text().strip()
        auto_name = self.chk_auto_name.isChecked()
        
        if not os.path.isdir(in_dir):
            print("[-] 错误：找不到解包后的 ISF 目录，请检查路径！")
            return

        self.btn_dump.setEnabled(False)
        print("\n" + "="*50)
        print("开始执行模块 B: 文本导出任务...")

        self.thread = WorkerThread(self.real_dump_task, in_dir, out_dir, auto_name)
        self.thread.finished_signal.connect(lambda: self.btn_dump.setEnabled(True))
        self.thread.error_signal.connect(lambda e: print(f"[-] 发生严重异常: {e}"))
        self.thread.start()

    def real_dump_task(self, in_dir, out_dir, auto_name):
        # ========== 新增：高级字典解析器 ==========
        def parse_advanced_nameidx(raw_dict):
            flat_dict = {}
            for name, id_str in raw_dict.items():
                # 跳过说明文字和未填写的项
                if name == "_使用说明_" or not id_str: 
                    continue 
                
                # 如果是旁白，实际的名字应该是空字符串
                actual_name = "" if name == "[旁白/无名字]" else name
                
                # 兼容容错：把中文全角逗号统统替换成英文半角逗号
                normalized_id_str = str(id_str).replace('，', ',')
                
                parts = normalized_id_str.split(',')
                for part in parts:
                    part = part.strip()
                    if not part: continue
                    if '-' in part:
                        try:
                            start, end = map(int, part.split('-'))
                            for i in range(start, end + 1):
                                flat_dict[str(i)] = actual_name
                        except ValueError:
                            pass
                    else:
                        try:
                            flat_dict[str(int(part))] = actual_name
                        except ValueError:
                            pass
            return flat_dict
        # ========== 新增：读取当前工程的引擎类型 ==========
        engine_type = "MPX"
        try:
            config_data = open_json("file_order.json")
            engine_type = config_data.get("engine", "MPX")
            print(f"[*] 读取工程配置成功，当前引擎模式: {engine_type}")
        except:
            print("[*] 未找到 file_order.json，默认使用 MPX 引擎模式。")
        # ===================================================

        os.makedirs(out_dir, exist_ok=True)
        nameidx_dict = {}

        split_mode = len(nameidx_dict) == 0 
        if split_mode:
            print("[*] 检测到全局人名表为空，将开启【剧本内置人名】自动分离模式。")

        apply_space_clean = False    


        # 智能整合：一键解析 start.isf 获取人物字典
        if auto_name:
            print("[*] 正在尝试从 start.isf 提取人名表...")
            start_isf_path = os.path.join(in_dir, "start.isf")
            if os.path.exists(start_isf_path):
                f = ISF_FILE(engine=engine_type) # 记得这里也要带上引擎参数
                f.load_from_path(start_isf_path)
                outlist, _ = f.dumptext({}) # 第一次空跑，专门抓取 System_CNS
                
                # ====== 彻底替换为你脚本里的绝对顺序逻辑 ======
                all_names = []
                for item in outlist:
                    if item.get("name") == "System_CNS":
                        name = item.get("ori")
                        # 只要存在就塞进去，保留所有重复项和 NULL，对齐底层 ID
                        if name is not None:
                            all_names.append(name)
                
                nameidx_dict = {str(i): name for i, name in enumerate(all_names)}
                save_json("nameidx.json", nameidx_dict)
                print(f"[+] 成功生成 nameidx.json，共截获 {len(all_names)} 个人物名。")

                if engine_type == "MPX" and len(all_names) > 0:
                    apply_space_clean = True
                    print("[*] 满足条件 (MPX引擎且成功提取人名)，已开启全角空格智能清洗。")

            else:
                print("[-] 警告: 未找到 start.isf，无法自动生成人名表。")
        else:
            try:
                # 优先读取高级自定义人名表
                if os.path.exists("nameidx_custom.json"):
                    raw_dict = open_json("nameidx_custom.json")
                    nameidx_dict = parse_advanced_nameidx(raw_dict)
                    print("[*] 已加载高级多合一人名表 (nameidx_custom.json)")
                else:
                    nameidx_dict = open_json("nameidx.json")
                    print("[*] 已加载基础人名表 (nameidx.json)")
            except FileNotFoundError:
                print("[-] 警告: 未找到人名表，导出文本将不包含人物名称。")

        # 核心：批量导出所有 ISF 文本
        ori_files = [f for f in os.listdir(in_dir) if f.upper().endswith(('.ISF', '.SNR'))]
        textcount = 0
        savetitles = {}
        
        # ================= 新增：预编译正则规则 =================
        punct_pattern = re.compile(r'(?<!^)(?<![、。！？…—「」『』（）>》【】,.\?!:;：；\'"])\u3000')
        # ========================================================

        global_unmapped_ids = set()
        print(f"[*] 开始批量导出文本，共发现 {len(ori_files)} 个脚本文件...")
        for file in ori_files:
            ori_file_path = os.path.join(in_dir, file)
            out_file_path = os.path.join(out_dir, file + '.json')
            
            f = ISF_FILE(engine=engine_type)
            try:
                f.load_from_path(ori_file_path)
                outlist, savetitle_dict = f.dumptext(nameidx_dict, split_embedded=split_mode)
                savetitles.update(savetitle_dict)
                
                # ====== 新增：把这个文件里未知的 ID 汇总 ======
                if hasattr(f, 'unmapped_ids'):
                    global_unmapped_ids.update(f.unmapped_ids)
                
                # ================= 新增：文本后处理清洗 =================
                for item in outlist:
                    # 如果是 System_CNS（如人名表等系统文本），则跳过正则清洗
                    if item.get("name") == "System_CNS":
                        # 仅统计字符数，不进行替换
                        if "message" in item and isinstance(item["message"], str):
                            textcount += len(item["message"])
                        continue
                        
                    if apply_space_clean:
                        if "ori" in item and isinstance(item["ori"], str):
                            item["ori"] = punct_pattern.sub('', item["ori"])
                        if "message" in item and isinstance(item["message"], str):
                            item["message"] = punct_pattern.sub('', item["message"])
                    
                    # 无论是否替换，都正常统计字数
                    if "message" in item and isinstance(item["message"], str):
                        textcount += len(item["message"])
                # ========================================================
                
                save_json(out_file_path, outlist)
                
                # print(f"  [>] 成功导出: {file}") # 如果文件太多刷屏，可以把这句注释掉
            except Exception as e:
                print(f"  [!] 导出失败: {file}, 错误: {e}")

        save_json("savetitle_dict.json", savetitles)
        print(f"\n[+] 提取完成！总提取文本字符数: {textcount}")
        print(f"[!] 存档标题字典已汇总并保存至: savetitle_dict.json")   

        if global_unmapped_ids and not split_mode:
            print("\n" + "!"*50)
            print(f"[!] 警告: 剧本中出现了 {len(global_unmapped_ids)} 个未在字典中的 Name ID！")
            
            id_info = [f"{i}(0x{i:02X})" for i in sorted(list(global_unmapped_ids))]
            print(f"[*] 缺失的 ID 列表: {', '.join(id_info)}")
            
            template_dict = {}
            
            # 1. 顶部写入详细说明（键名前加下划线，确保视觉上好区分）
            template_dict["_使用说明_"] = "请用Garbro解包GGD文件后查看人名id范围，比如fw224.gg2就表示id为224.然后在右侧双引号内填入十进制ID。支持单个(如: 227)、多个(如: 227, 230)、连续(如: 100-150)及混合(如: 12, 100-110)。中英文逗号均可识别。不需要填写的项请直接留空。"
            
            # 2. 默认添加旁白项（右侧留空）
            template_dict["[旁白/无名字]"] = ""
            
            # 3. 载入已有的人名，并留空等待填写
            if os.path.exists("nameidx.json"):
                try:
                    old_dict = open_json("nameidx.json")
                    for old_id, name in old_dict.items():
                        if name not in template_dict:
                            template_dict[name] = ""  # 右边留空，等你填ID
                except: pass
            
            save_json("nameidx_custom_template.json", template_dict)
            print("[+] 已生成反向映射模板：nameidx_custom_template.json")
            print("[*] 请打开模板，阅读顶部的 _使用说明_ ，并填入你查证的十进制数字。")
            print("[*] 修改完成后，将其重命名为 nameidx_custom.json，然后取消勾选智能提取后进行提取即可！")
            print("!"*50 + "\n")

    def start_pack_task(self):
        ori_path = self.c_ori_input.text().strip()
        trans_path = self.c_trans_input.text().strip()
        out_path = self.c_out_input.text().strip()
        
        if not os.path.isdir(ori_path) or not os.path.isdir(trans_path):
            print("[-] 错误：找不到原始 ISF 目录或翻译 JSON 目录，请检查路径！")
            return

        self.btn_pack.setEnabled(False)
        print("\n" + "="*50)
        print("开始执行模块 C: 文本导入与加密封包任务...")

        self.pack_thread = WorkerThread(self.real_pack_task, ori_path, trans_path, out_path)
        self.pack_thread.finished_signal.connect(lambda: self.btn_pack.setEnabled(True))
        self.pack_thread.error_signal.connect(lambda e: print(f"[-] 发生严重异常: {e}"))
        self.pack_thread.start()

    def real_pack_task(self, ori_path, trans_path, out_path):
        # ========== 新增：读取当前工程的引擎类型 ==========
        engine_type = "MPX"
        try:
            config_data = open_json("file_order.json")
            engine_type = config_data.get("engine", "MPX")
        except:
            pass # 静默默认 MPX
        # 1. 首先加载人名表，判断是否处于内置模式
        embedded_mode = False
        try:
            n_dict = open_json("nameidx.json")
            if not n_dict: embedded_mode = True # 字典为空 [cite: 4]
        except:
            embedded_mode = True # 文件不存在也视为内置模式
        os.makedirs(out_path, exist_ok=True)

        try:
            stdict = open_json("savetitle_dict.json")
            print("[*] 成功加载 savetitle_dict.json 系统字典。")
        except FileNotFoundError:
            stdict = {}
            print("[-] 警告: 找不到 savetitle_dict.json，部分系统短语将不会被替换。")

        ori_files = [f for f in os.listdir(ori_path) if f.upper().endswith('.ISF')]
        print(f"[*] 准备封包，共发现 {len(ori_files)} 个原始 ISF 文件...")

        for file in ori_files:
            ori_file_path = os.path.join(ori_path, file)
            trans_file_path = os.path.join(trans_path, file + '.json')
            out_file_path = os.path.join(out_path, file)
            
            if not os.path.exists(trans_file_path):
                print(f"  [!] 跳过 {file}，找不到对应的 JSON 文件。")
                continue
                
            print(f"  [>] 正在封包: {file}")
            
            json_data = open_json(trans_file_path)
            trans_list = []
            
            for item in json_data:
                name = item.get("name", "")
                text = item.get("message", "")
                
                # --- [新增] 获取换行标记 ---
                has_name_br = item.get("has_name_br", False)
                
                # --- 关键：如果是内置模式且 JSON 里有名字，就拼回剧本 ---
                if embedded_mode and name and name not in ["System", "System_CNS"]:
                    text = f"【{name}】{text}"
                # 【神级保险机制】调用全角转换！
                text = replace_halfwidth_with_fullwidth(text) 
                
                # --- [修改] 以前传纯文本，现在传入包含标记的元组 ---
                trans_list.append((text, has_name_br))
                
            trans_iter = iter(trans_list)
            
            f = ISF_FILE(engine=engine_type)
            try:
                f.load_from_path(ori_file_path)
                f.trans(trans_iter, stdict)
            except StopIteration:
                print(f"  [-] 错误: {file} 的 JSON 文本行数少于原始文本行数！请检查是否有漏翻。")
                continue
            except Exception as e:
                print(f"  [-] 错误: 封包 {file} 时发生异常: {e}")
                continue
            
            # 重新计算长度并保存加密后的 ISF 文件
            f.savefile(out_file_path, isEnc=True)

        print("\n[+] ============ 全部 ISF 文本封包完成！============")
        print(f"[!] 新的 ISF 文件已生成在: {out_path} 目录下。")

    def start_repack_task(self):
        src_folder = self.d_in_input.text().strip()
        output_path = self.d_out_input.text().strip()

        if not os.path.isdir(src_folder) or not output_path:
            print("[-] 错误：请检查【散文件目录】和【输出目录】是否填写完整！")
            return

        self.btn_repack.setEnabled(False)
        print("\n" + "="*50)
        print("开始执行模块 D: 读取工程配置进行自动化打包...")

        self.repack_thread = WorkerThread(self.real_repack_task, src_folder, output_path)
        self.repack_thread.finished_signal.connect(lambda: self.btn_repack.setEnabled(True))
        self.repack_thread.error_signal.connect(lambda e: print(f"[-] 发生严重异常: {e}"))
        self.repack_thread.start()

    def real_repack_task(self, src_folder, output_path):
        import ISF_PACK  
        try:
            # 现在只需要传入源文件夹和输出目录即可，引擎判断交由 JSON 处理
            final_file = ISF_PACK.auto_pack_isf(src_folder, output_path)
            print(f"\n[!] 打包流全部完成！最终文件已保存至: {final_file}")
        except Exception as e:
            print(f"[-] 打包过程发生异常: {e}")         

    def on_task_finished(self):
        self.btn_unpack.setEnabled(True)
        print("="*50 + "\n")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    font = app.font()
    font.setFamily("Microsoft YaHei")
    app.setFont(font)
    window = IKURAToolbox()
    window.show()
    sys.exit(app.exec())