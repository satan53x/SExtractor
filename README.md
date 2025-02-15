# SExtractor
 从GalGame脚本提取和导入文本（大部分需要明文）
 
## Python依赖模块：
python版本需要3.9及以上。（推荐使用3.11）
* pyqt5
* colorama
* pandas
* python-rapidjson

## 详细使用教程
* [julixian](https://www.ai2.moe/topic/28969-sextractor%E4%BD%BF%E7%94%A8%E5%BF%83%E5%BE%97)
* [无聊荒芜](https://www.ai2.moe/topic/29048-sextractor%E4%BD%BF%E7%94%A8%E2%80%94%E2%80%94%E8%BF%9B%E9%98%B6%E8%AF%B4%E6%98%8E%E5%8A%A0%E9%83%A8%E5%88%86%E5%BC%95%E6%93%8E%E7%A4%BA%E4%BE%8B%EF%BC%88%E7%9C%8B%E5%AE%8Csextractor%E4%BD%BF%E7%94%A8%E5%BF%83%E5%BE%97%E5%86%8D%E6%9D%A5%EF%BC%89)

## 支持的引擎：
同引擎不同游戏的格式也可能不同，请参看程序内示例使用。
* TXT纯文本 (正则匹配。可选utf-8，utf-8-sig，utf-16(LE BOM))
* BIN二进制文本 (正则匹配。默认读shift-jis写GBK)
* JSON文本 (正则匹配，只搜索value，value为空则先自动复制key到value)
* ANIM
* AZ System (Encrypt Isaac)
* Artemis
* Black Rainbow
* CSV
* CScript (有预编译模块，推荐使用python 3.11)
* Cyberworks / CSystem
* EAGLS
* FVP
* Kaguya
* Krkr
* MED (DxLib改)
* MoonHir
* NekoSDK
* RPG Maker MV
* RPG Maker VX Ace
* RealLive
* RenPy
* SystemC
* WillPlus
* Yu-ris

## 其他功能
* 可以导出VNT的JIS隧道文件`sjis_ext.bin`，需要配合[VNTProxy](#相关项目)使用。(同时也会导出UIF配置)
* 可以导出UIF的JIS替换配置`uif_config.json`，需要配合[UniversalInjectorFramework](#相关项目)使用。
* `Tools/Font`下有JIS替换字体，以备dll无法hook游戏时使用。
* 文件夹下自定义的`config*.ini`都会被读取，*中不能以数字开头。(例：`configTest.ini`)
* `text_conf.json`进行文本处理配置，优先读取工作目录ctrl文件下配置，如果没有则读取工具根目录默认配置。
```
text_conf.json:
  "replace_before_split" 分割前替换
  "trans_replace" 译文替换，受导入编码限制
  "orig_replace" 原文替换与还原
  "name_replace" 仅限name的原文替换与还原
```

## 当前正则预设
<font color=red>（更多预设正则详见根目录`预设正则.fake.ini`）</font>
* AST
* Artemis
* Cyberworks_JIS
* CSV_Livemaker
* EntisGLS
* Krkr
* Nexas
* RealLive (选项分开提取)
* RPGMV_System
* RPGVX_NotMap
* SFA_AOS
* Valkyria_dat_txt
* Valkyria_ODN
* Yuris_txt (非ybn)
* BIN暴力匹配
* 两行TXT
* 导出所有(多用于格式转换)
* 自定义规则(自动保存)
* None还原为引擎默认

## 工具
* AST: arc2封包
* Astronauts: gpx封包，Mwb提取
* AZ System: isaac加密
* BlackRainbow: 封包
* CScript: 封包，解压压缩
* Cyberworks: UTF-16解封包
* DxLib: 解包
* EAGLS: 解封包
* Font: JIS替换字典生成的字体
* Malie: 封包
* RealLive: 解封包，二次加解密
* SHook: 跳壳，Loader
* Silky: 封Azurite包
* Unity: data.dsm加解密
* UniversalInjectorFramework: dll

## 正则相关说明
读取文件方式分为`txt`和`bin`两大类，前者按字符串处理，后者按字节处理。
* `separate=reg` bin方式下的分割符，默认为`separate=\r\n`，导入时会补上separate字符串`\r\n`；如果带捕获分组例如`separate=([\x01-\x02]\x00|\x00)`，则会提取出分割符。
* `startline=0` 每个文件起始处理行数；默认为0。
* `structure=paragraph` 提取结构，当为`paragraph`时才会处理非name或msg的分组名，比如`unfinish`。（不是所有引擎的正则都支持，`TXT`和`BIN`引擎肯定支持）
* `extraData=data` data为引擎自定义的参数，具体参考每个引擎的默认正则，用法不定。
* `ignoreDecodeError=1` bin方式下，忽略文本在提取时的decode编码错误。
* `checkJIS=reg` bin方式下，检查字节是否符合shift-jis编码，默认只允许双字节，`reg`为支持的单字节。比如`checkJIS=[\n]`表示支持换行符。
* `postSkip=reg` 在提取中，对于已经提取到的文本进行`re.search(reg, text)`匹配，如果匹配正则成功则忽略掉该文本，不导出。比如`postSkip=^[0-9]`表示忽略数字开头的文本。
* `sepStr=reg` 仅Krkr_Reg引擎使用，表示分割符匹配；默认为`sepStr=[^\[\]]+`，表示以中括号分割。
* `endStr=reg` 仅Krkr_Reg引擎使用，表示段落结束的匹配。
* `ctrlStr=reg` 仅Krkr_Reg引擎使用，表示需要跳过的控制段的匹配。（类似通用的postSkip）
* `version=0` 主要由Yuris使用，表示文件结构版本
* `decrypt=auto` 主要由Yuris使用，表示解密。auto表示自动猜测，也可以强制指定，如`decrypt=\xD3\x6F\xAC\x96`。如果已解密则删除该行。
* `pureText=1` 等同于勾选`BIN启用纯文本正则模式`
* `writeOffset=1` 主要由CSV使用，向右偏移写入列。

### 正则例子
对于每行文本都会从上到下进行匹配。（skip或search匹配成功都会中断，不进行下边的正则匹配）
```
00_skip=^error
10_search=^(?P<name>Name.*)$
20_search=^(?P<pre_name>「.+」)$
21_search=^(?P<pre_nameANDunfinish>「.*)$
25_search=^(.+?)(?<=」|。)$
26_search=^(?P<unfinish>.+?)$
postSkip=^[0-9]
structure=paragraph
```
* 00 跳过`error`开头的行，skip会打断段落结构（如果用postSkip处理error则不会）
* 10 提取`Name`开头的行，且指定自身为`name`（`name`默认会`predel_unfinish`）
* 20 提取带`「」`的一行，且指定前一行为`name`
* 21 提取`「`开头的一行，且指定前一行为`name`，且自身为`unfinish`
* 25 提取`」`结尾的一行
* 26 提取任意字符的一行（.不包含换行符）
* postSkip 数字开头则跳过，不会打断段落结构
* 最后顺序合并文本，如果是`unfinish`则添加\r\n且不会切换到下一个message。
* 分组名`pre_`和`predel_`后可以自由组合，比如`name`和`unfinish`。`AND`也可以有任意个。
* 原始txt:
```
Text0
Name1
Text1。
MaybeName2
「Text2」
MaybeName3
「
Text3
33text
Text333
error
」
```
* 提取为：
```
[
  {
    "message": "Text0"
  },
  {
    "name": "Name1",
    "message": "Text1。"
  },
  {
    "name": "MaybeName2",
    "message": "「Text2」"
  },
  {
    "name": "MaybeName3",
    "message": "「\r\nText3\r\nText333"
  },
  {
    "message": "」"
  }
]
```

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
8. [MalieTools](https://github.com/Dir-A/MalieTools)
9. [Garbro fork](https://github.com/satan53x/GARbro)


