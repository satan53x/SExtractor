### 字库生成流程（.FNT/.PAL/.TBL）
* 运行`TBL_exchange.py`: 原始`FONT.TBL` -> 明文TBL
* 删除末尾多余的00字节并重命名: 明文TBL -> `tbl.txt`
* 运行`generate_char_list.py`添加所有cp932全角字符，并且80字一次换行: `tbl.txt` -> `char_list.txt`
* 下载合适的等宽字体，推荐更纱黑体SarasaMonoSC（https://github.com/be5invis/Sarasa-Gothic/releases）：`SarasaMonoSC.ttf`
* 运行`tools/FONT/font_CN_JP.py`生成替换字体ttf，并且安装：`SarasaMonoSC_cnjp.ttf`
* 用PS新建Text图层，选择上述字体，把char_list.txt的内容复制粘贴到Text。
* 自行调整设置，需要每个字符占据28宽34高（根据`png_to_FNT.py`的配置来），字形本身要小一圈免得和旁边的重叠。
* 最后添加纯绿色的背景层，合并，图像改为索引颜色，局部调板，16个颜色，纯绿占1个表示透明。导出为8位`char_list.png`。
* 运行`png_to_FNT.py`，会读取`char_list.txt`/`char_list.png`，生成最终的`.FNT/.PAL/.TBL`

### 测试游戏`Refrain Blue`
* 对应资源：`FONT.7z`
* 因为FNT和TBL大小都增加了很多，exe里原始的缓冲区严重不足，所以直接把TBL和FNT追加到了exe文件末尾，并修复Header。（TBL物理地址18C600，对齐长度3800；FNT物理地址18FE00，对齐长度2C0400）
* 修改exe的`sub_449570`和`sub_449EE0`函数内buffer赋值语句，把mov指令指向上述追加区域的虚拟地址。（运行游戏后，dbg搜索内存，匹配特征为TBL和FNT文件内的部分字节，下读取断点可以找到调用函数）
* 因为地址是硬编码，如果运行有问题可能需要关闭windows的ASLR功能。

