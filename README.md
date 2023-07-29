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
* NekoSDK
* RPG MV
* RenPy
* SiglusEngine
* WillPlus

#### 配置
* reg.ini中可自定义匹配规则, 当前预设:
 1. Krkr
 2. SFA(AOS)
 3. SystemC
 4. Yuris_txt
 5. 替换符号
 6. JSON_Key(TXT转JSON)
 7. 猜测名字
 8. 两行TXT
 9. 导出所有(多用于格式转换)
 10. 自定义规则(自动保存)

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
