# SExtractor
 仅用于提取和导入未加密的GalGame脚本文本
 
## Python依赖模块：
国内推荐先配置镜像再下载：`pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple`
* pyqt5

## 支持的引擎：
同引擎不同游戏的格式也可能不同，请参看程序内示例使用。
* TXT纯文本 (正则匹配。默认utf-8)
* BIN二进制文本 (正则匹配。默认读shift-jis写GBK)
* JSON文本 (正则匹配，只搜索value。按行读取，不要压缩Json)
* AST
* Artemis
* EAGLS
* Krkr
* MED (DxLib)
* MoonHir
* NekoSDK
* RPG MV
* RenPy
* SiglusEngine
* SystemC
* WillPlus

#### 配置
* reg.ini中可自定义匹配规则, 当前预设:
 1. Artemis
 2. EntisGLS
 3. Krkr
 4. SFA(AOS)
 5. SystemC
 6. Yuris_txt
 7. 替换符号
 8. JSON_Key(TXT转JSON)
 9. 猜测名字
 10. 两行TXT
 11. 导出所有(多用于格式转换)
 12. 自定义规则(自动保存)

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
