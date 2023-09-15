# SExtractor
 仅用于提取和导入未加密的GalGame脚本文本
 
## Python依赖模块：
国内推荐先配置镜像再下载：`pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple`
* pyqt5
* colorama
* pandas

## 支持的引擎：
同引擎不同游戏的格式也可能不同，请参看程序内示例使用。
* TXT纯文本 (正则匹配。可选utf-8，utf-8-sig，utf-16(LE BOM))
* BIN二进制文本 (正则匹配。默认读shift-jis写GBK)
* JSON文本 (正则匹配，只搜索value)
* AST
* Artemis
* CSV
* EAGLS
* FVP
* Kaguya
* Krkr (可正则)
* MED (DxLib)
* MoonHir
* NekoSDK
* RPGMaker MV
* RenPy
* SiglusEngine (弃用)
* SystemC
* WillPlus
* Yu-ris

#### 配置
* 文件夹下自定义的config*.ini都会被读取，*中不能以数字开头。(例：configTest.ini)
* reg.ini中可自定义匹配规则, 当前预设:
 1. Artemis
 2. EntisGLS
 3. Krkr
 4. Nexas
 5. RealLive (选项分开提取)
 6. SFA(AOS)
 7. SystemC
 8. Yuris_txt (非ybn)
 9. BIN暴力匹配
 10. 替换符号
 11. JSON_Key(TXT转JSON)
 12. 猜测名字
 13. 两行TXT
 14. 导出所有(多用于格式转换)
 15. 自定义规则(自动保存)
 16. None还原为引擎默认

## 支持的导出格式：
* json字典 { 文本 : "" }
* json字典 { 文本 : 文本 }
* json列表 [ { name : 名字, message : 带换行对话 } ]
* json字典 { 带换行文本 : "" }
* json字典 { 带换行文本 : 带换行文本 }
* txt文档  { 文本 }
* txt文档  [ 带换行文本 ]
* json列表 [ 带换行文本 ]

## 相关参考项目
1. [ssynn](https://github.com/ssynn/game_translation)
2. [SiglusTools](https://github.com/yanhua0518/GALgameScriptTools)
