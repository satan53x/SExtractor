### 解包
* 运行`arc_unpack.py`，解包当前文件目录下的`SCX.ARC`到`out`目录

### 封包
* 运行`arc_pack.py`，`out`目录封包到`new/SCX.ARC`。（需要当前目录存在原始ARC）

### 说明
* 初版来自`coroz`，此为修改版
* 默认lzss库仅适配`python 3.11`，如果需要其他版本请从`{SE}/libs/lzss`文件夹中复制过来（其中运行`make.bat`可以预编译）。
