GRP.vfa 结构说明
================
用法
直接把 `grp.vfa` 放到根目录下，我已经调整过了，可回写
- 运行顺序：在本目录执行 `python extract.py`，再执行 `python repack.py`，预期打印 `equal: True ...`。

总体
- 容器是 RIFF，form type 为 `VFA1`。RIFF size = 文件总长减 8。
- 本文件中按顺序出现的 chunk：`hdri`、`data`、`dent`，均为小端 `uint32` 长度，无填充对齐字节。
- 目录字符串为 UTF-16LE。

hdri（16 字节负载）
- 四个 dword：`0x00010000`、`0x00000001`、ASCII `dent`、ASCII `data`，后两项标出目录 chunk 名和数据 chunk 名。

data
- 起始于偏移 44，大小 `0x1d18378d`。负载是所有文件内容的顺序拼接；目录里的 offset 相对于 data 负载起点。
- 尾部是一大段 PNG 资源；部分头是 XOR 混淆：加密签名 `0xD0185F10`，PNG 签名 `0x89504E47`，密钥 `0x59481157`。避免一次性拷走整段。

dent（目录表）
- 由若干项组成：4 字节 tag，4 字节 size，随后是 size 长度的负载。
- `dir `：负载是 UTF-16LE 路径（含末尾 0）。首项 size=2，表示根目录空串。
- `file`：负载 = UTF-16LE 文件名（含末尾 0） + 4 个 dword，布局 `[data_offset, data_length, timestamp_like, flags]`。offset 相对 data 起点，flags 在本文件为 0，第三项类似 Unix 秒级时间戳。
- `file` 的 size 计算：`2*(len(name)+1) + 16`。

示例（来自当前文件）
- 23th_kiss.ani -> offset 0，length 1260016，stamp 1164443008，flags 0
- apple_image.ani -> offset 1260016，length 84016，stamp 1164134407，flags 0
- apple_image2.ani -> offset 1344032，length 42016，stamp 1164474341，flags 0
- at_gate.ani -> offset 1386048，length 630016，stamp 1156576035，flags 0
- at_port.ani -> offset 2016064，length 630016，stamp 1156575919，flags 0

重打包要点
- RIFF size = 最终文件长度 - 8。
- `hdri` 固定 16 字节；`data` size = 数据总长；`dent` size = 目录表总长。
- chunk 紧挨着写，不要插入填充。

脚本
- `extract.py`：按 exe 读序解析 RIFF/hdri/data/dent，写出文件到 `extracted/`，并生成 `index.json`。
- `repack.py`：用 `extracted/` 与 `index.json` 重新生成 `grp_repack.vfa`，重新计算每个文件的 offset/length（支持修改后大小变化），时间戳/flags 沿用 index，最后做字节级对比。
