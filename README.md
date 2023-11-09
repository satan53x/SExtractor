# SExtractor
 从GalGame脚本提取和导入文本（大部分需要明文）
 
## Python依赖模块：
国内推荐先配置镜像再下载：`pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple`
* pyqt5
* colorama
* pandas

## 支持的引擎：
同引擎不同游戏的格式也可能不同，请参看程序内示例使用。
* TXT纯文本 (正则匹配。可选utf-8，utf-8-sig，utf-16(LE BOM))
* BIN二进制文本 (正则匹配。默认读shift-jis写GBK)
* JSON文本 (正则匹配，只搜索value，value为空则先自动复制key到value)
* AZ System (Encrypt Isaac)
* Artemis
* Black Rainbow
* CSV
* CScript
* Cyberworks / CSystem
* EAGLS
* FVP
* Kaguya
* Krkr (可正则)
* MED (DxLib)
* MoonHir
* NekoSDK
* RPGMaker MV
* RenPy
* SystemC
* WillPlus
* Yu-ris

## 其他功能
* 可以导出VNT的JIS隧道文件`sjis_ext.bin`，需要配合[VNTProxy](#相关项目)使用。(同时也会导出UIF配置)
* 可以导出UIF的JIS替换配置`uif_config.json`，需要配合[UniversalInjectorFramework](#相关项目)使用。
* `Tools/Font`下有GBK2JIS替换字体，以备dll无法hook游戏时使用。
* 文件夹下自定义的`config*.ini`都会被读取，*中不能以数字开头。(例：`configTest.ini`)
* `reg.ini`中可自定义正则匹配规则

## 当前正则预设
* AST
* Artemis
* EntisGLS
* Krkr
* Nexas
* RealLive (选项分开提取)
* SFA(AOS)
* SystemC
* Valkyria_ODN
* Yuris_txt (非ybn)
* BIN暴力匹配
* 替换符号
* JSON_Key(TXT转JSON)
* 猜测名字
* 两行TXT
* 导出所有(多用于格式转换)
* 自定义规则(自动保存)
* None还原为引擎默认

## 工具
* AZ System: isaac加密
* Cyberworks: UTF-16解封包
* EAGLS: 解封包
* RealLive: 解封包，二次加解密
* SHook: 跳壳
* Unity: data.dsm加解密
* UniversalInjectorFramework: dll

## 支持的导出格式：
* json字典 { 文本 : "" }
* json字典 { 文本 : 文本 }
* json列表 [ { name : 名字, message : 带换行对话 } ]
* json字典 { 带换行文本 : "" }
* json字典 { 带换行文本 : 带换行文本 }
* txt文档  { 文本 }
* txt文档  [ 带换行文本 ]
* json列表 [ 带换行文本 ]

## 相关项目
1. [game_translation](https://github.com/ssynn/game_translation)
2. [SiglusTools](https://github.com/yanhua0518/GALgameScriptTools)
3. [CSystemTools](https://github.com/arcusmaximus/CSystemTools)
4. [VNTranslationTools](https://github.com/arcusmaximus/VNTranslationTools)
5. [UniversalInjectorFramework](https://github.com/AtomCrafty/UniversalInjectorFramework)
6. [GalTransl_DumpInjector](https://github.com/XD2333/GalTransl_DumpInjector)
7. [EAGLS](https://github.com/jszhtian/EAGLS)