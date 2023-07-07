# SExtractor
 仅用于提取和导入未加密脚本的文本
 
### Python依赖模块：
国内推荐先配置镜像再下载：pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple
* pyqt5

### 支持的引擎：
同引擎不同游戏的格式可能不同，请参看程序内示例使用。
* AST
* Artemis
* EAGLS
* Krkr
* MED

### 支持的导出格式：
* json字典 { 文本 : "" }
* json字典 { 文本 : 文本 }
* json列表 [ { name : 名字, message : 带换行对话 } ]
* json字典 { 带换行文本 : "" }
* json字典 { 带换行文本 : 带换行文本 }
