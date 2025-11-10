### 解包
* 原始garbro只能解包文本包。
* 但是简中需要修改图片包内的png字库，需要解包DATA索引类型的arc，因此需要使用此改版：https://github.com/satan53x/GARbro/releases/tag/diff-v4

### 封包
由`Steins;Gate`提供
* `arc_DATA_pack.py`: 封DATA索引的arc。

### 字库
* `font_to_png.py`: 从替换后的ttf生成字库图片。
* 游戏原始字库图片为`SJIS_0B.png`，`SJIS_1B.png`，`SJIS_2B.png`。
* txt目录里的文本内容需要和原始图片一致。
* 至少将上述原始1B和2B放入对应目录内，并确认脚本内的字体路径TTF_PATH，再运行脚本。
