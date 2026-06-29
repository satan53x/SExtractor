# ICE 引擎 文本提取/注入 + 字库扩充 工具（v2）

适用：エグゼキュート.exe / ICE Soft 引擎（脚本在 Event.grp 内，字符表在 System.grp 内）。
配套：`grp_tool.py`（解包/封包）、`ice_op.py`（引擎模型）、`ice_text.py`（提取/注入/字库）。
方案：**方案 B**（变长，注入时自动重算所有相对跳转，文件大小可变）。

---

## 一、这次修了什么

### 1. 提取规范 / 杂质（已修复）
旧版在 **op69「定位多行文本」**（片尾、字幕等特殊排版）上解析错误，产生：
- 大量空条目（`"message":""`），无法翻译；
- `の。』．{/C}`、`の。Ｇ．{/C}` 之类乱码（其实是被误读成文字的「行内重定位坐标头」）；
- `{C}` 等颜色控制符混进正文。

v2 已彻底修正：
- 正确解析 op69 结构（头部 x/y 坐标、清屏标记、逐行重定位头），结构信息全部存进 meta；
- **首尾控制符**（`{C}` `{/C}` 等）自动剥离进 meta，`message` 只保留干净正文（符合备忘录：控制符在首尾→进 meta）；
- **中间控制符**保留为内联标签并在提取时打印告警，由你决定去留（符合备忘录：控制符在中间→提示用户）；
- **纯空条目过滤**：清屏/占位指令不进翻译 JSON，注入时原样保留；
- op72（条件名字，极少）整体原样保留，不翻译。

> 对照：旧 `0158.json` 104 条（含空条目+乱码）→ 新版 64 条，全部干净可译。

### 2. 字库不够用 / 新增字（已实现）
游戏用 **GDI 系统字体（SHIFT-JIS）** 渲染：脚本存的是**索引**，`System.grp` 里的 `0001.bin`
把索引映射到 SJIS 码，再由字体（用 FontMod 换成你的中文字体）画出字形。
所以**加字 = 往 `0001.bin` 增补需要的 SJIS 码位**，字形交给字体，不用画位图。

`0001.bin` 表缓冲在 EXE 对象里是**定长**的（约 2400 条上限，紧挨屏幕文字缓冲）。
**安全做法 = 原地重建 `0001.bin`（保持原 4772 字节不变）**：
注入本来就在重编码索引，于是——
- 译文里**仍在用**的原字保留其原索引（未改动的日文行字节不变，原样复用）；
- 释放出来的「纯日文专用」槽位，重新分配给中文新字。

`build_charset` 子命令自动完成这件事，并做 cp932 可编码校验。

---

## 二、完整工作流程

```bash
# 0) 解包（grp_tool）
python grp_tool.py unpack Event.grp  -o ev_unpacked
python grp_tool.py unpack System.grp -o sys_unpacked     # sys_unpacked/0001.bin = 字符表

# 1) 提取文本  →  proj/json/*.json（翻译用）+ proj/meta/*.json（注入用）
python ice_text.py extract ev_unpacked sys_unpacked/0001.bin -o proj

# 2) 用 GalTransl 翻译 proj/json/*.json 的 message 字段（日→中，套日繁映射）

# 3) 预检（不可编码字符 / 缺 id / 内联控制符）
python ice_text.py check proj sys_unpacked/0001.bin

# 4) 重建字符表（扫描全部译文，原地重建 0001.bin）
python ice_text.py build_charset proj sys_unpacked/0001.bin -o 0001_new.bin
#    把它替换进 sys_unpacked
copy /Y 0001_new.bin sys_unpacked\0001.bin           # Windows
# cp 0001_new.bin sys_unpacked/0001.bin              # Linux/Mac

# 5) 注入（用新表；未改动单元原样复用=最小补丁；自动重算跳转）
python ice_text.py inject proj ev_unpacked sys_unpacked/0001.bin -o ev_patched

# 6) 封包
python grp_tool.py pack ev_patched  -o Event.grp  --orig 原Event.grp
python grp_tool.py pack sys_unpacked -o System.grp --orig 原System.grp

# 7) 字体：用 FontMod 把你的中文字体 hook 进游戏（见下）
```

> 若译文**不需要任何新字**（全部命中原表），可跳过第 4 步，直接用原 `sys_unpacked/0001.bin` 注入。

---

## 三、JSON 格式（方案 B）

`proj/json/<脚本>.json`（翻译用，干净）：
```json
[
  { "id": 0, "name": "香織", "pre_jp": "「ずいぶん静かね」", "message": "「ずいぶん静かね」" },
  { "id": 2,                 "pre_jp": "もう、すべては終わって…",  "message": "もう、すべては終わって…" }
]
```
- 顺序固定 `id → name → pre_jp → message`；旁白无 `name` 键；只翻译 `message`。
- 一句被换行符切成多段时，按方案 B 拆成多条（**省略换行符**，与你的习惯一致）。
- 首尾控制符已进 meta，不在 `message` 里；若 `message` 里出现 `{C}`/`{/C}`/`{NAME}`/`{VAR}`
  等内联标签，说明该控制符夹在文本中间，**翻译时务必保留、勿改其相对位置**（`check`/`extract` 会列出这些条目）。

`proj/meta/<脚本>.json`（注入用，勿手改）：记录每个文本单元的 opcode、偏移、op69 坐标头、
清屏标记、逐行换行/重定位、首尾控制符、名字绑定等，供注入精确还原。

---

## 四、字库容量与超限处理

- 可引用索引上限 ≈ **2362**（单字节 0–230,233 + 双字节 256–2385），缓冲定长。
- `build_charset` 会打印：`译文独立字 / 已在原表 / 需新增 / 可用空槽`，并做自检。
- 若提示 **「字库不足」**（译文独立字 > ~2362）：
  1. 减少生僻字 / 异体字，合并近义字；
  2. 检查日繁映射是否把简体都映射成了 **cp932 可编码**的日系字形
     （工具会报不可编码字符，例如 `說`(繁) 不可编码，应映射为 `説`(日)）；
  3. 进阶：打 EXE 补丁扩大字符表缓冲（需要时再说，本工具暂未做）。

---

## 五、字体（FontMod）

游戏 `CreateFontA(..., SHIFTJIS_CHARSET, ...)` + `ExtTextOutA`。用 FontMod 强制换字体即可显示中文：
- 你的 `鸭神超级黑体.ttf` 已具备：OS/2 `ulCodePageRange1` **bit17(JIS) = 1**、Unicode cmap、
  覆盖全部所需字形（于/歐/這/説/凜… 均有）→ **FontMod 直接可用**。
- 用法：把 FontMod 的 dll 改名为 `winmm.dll` 或 `d3d9.dll` 放进游戏目录，配置指向该字体。
- 仅当你改用「系统字体切换」而非 FontMod 时，才需要给字体补 `name` 表 langID=2052(简中)/1041(日文)
  记录（当前字体只有 langID=1033，FontMod 模式无所谓）。

---

## 六、已验证

- opcode 模型：207/207 线性扫描对齐。
- 文本编解码：52468/52468 单元字节级完美往返。
- op69 语法：1563/1563 实例往返一致。
- **恒等注入**：未改动 → 207/207 bit-perfect。
- **变长注入**：增删字 → 207/207 重反汇编、103 跳转全对齐。
- **字库重建**：含新字（于 等）注入后 0001 正确显示中文；未改脚本 206/206 逐字不变；
  跳转 207/207 对齐；System.grp 重打包尺寸一致。

---

## 七、字库扩到 3000+ 字（EXE 补丁）

当译文独立字超过内联表上限（约 2362）时，`build_charset` 会自动把多出来的字
分配到「扩展节」，并提示需要给 EXE 打补丁。配套工具 `ice_exe_patch.py`。

### 原理（老字新字仍全部走查表，统一机制）
- 内联表 `this+4484`（索引 0~2385）**原封不动** → 原有载入/动态追加/匹配全部照常；
- 索引 ≥2386 的「扩展表」放进新增的 PE 节 `.xt`；4 个微型 code-cave 做「二级查表」：
  取字时 `if 2*idx < 4772 读内联表 else 读 .xt 节`（不动栈、寄存器全保留）；
- 把 2 字节字符判定阈值 `0xF7 → 0xEE`（`0xEE~0xF6` 是真实脚本里从未用过的颜色码），
  索引上限从 2559 提到 **4863**，可用字数约 **4840**（远超 3000）。

### 流程（在原流程第 4 步之后）
```bash
# 4) 构建字符表 → 完整表 + System.grp用的内联表
python ice_text.py build_charset proj sys_unpacked/0001.bin -o 0001_full.bin
#    输出: 0001_full.bin(完整表)  +  0001_full_sysgrp.bin(内联2386条)

# 4b) 若提示"需要 EXE 补丁"，给 EXE 打补丁(烘焙扩展表)
python ice_exe_patch.py エグゼキュート.exe 0001_full.bin -o エグゼキュート_patched.exe
#     --verify 可先只核对/反汇编补丁点，不写文件

# 5) 注入：用【完整表】
python ice_text.py inject proj ev_unpacked 0001_full.bin -o ev_patched

# 6) 封包：System.grp 的 0001.bin 用【内联表 0001_full_sysgrp.bin】
copy /Y 0001_full_sysgrp.bin sys_unpacked\0001.bin
python grp_tool.py pack ev_unpacked... (Event.grp)
python grp_tool.py pack sys_unpacked -o System.grp --orig 原System.grp

# 7) 用 エグゼキュート_patched.exe 替换原 EXE；FontMod 挂字体
```

### 重要：三者必须同源
`System.grp 的内联表`、`EXE 的扩展表`、`inject 用的完整表` 必须出自**同一次 build_charset**。
若重新翻译/改了字，三样都要重做（重跑 build_charset → 重打 EXE 补丁 → 重封 System.grp）。

### 补丁点（已逐字节核对，补丁器内置原始字节校验，版本不符会拒绝）
- 阈值 `F7→EE`：文件 `0x0A403 / 0x0A4A0 / 0x0C8BF`
- 取字→`jmp cave`：`sub_40A2C0` hi@`0xA4E0` lo@`0xA4F0`；`sub_40F390` hi@`0xC8F9` lo@`0xC904`
- cave 区：`.text` 尾部全 0 空白（VA `0x431925`，1755B）
- 新节 `.xt`：VA `0x75000`，只读数据，烘焙索引 ≥2386 的字模索引

### 风险与回滚
- 此补丁**未经实机验证**（在沙箱内无法运行游戏），已做：原始字节校验、cave 反汇编核对、
  扩展编解码全通过。请用你备份的原 EXE 测试；若异常，换回原 EXE 即可（补丁不改原节，
  只加节 + 改十几个字节，回滚无副作用）。
- 索引硬上限 4863（约 4840 字）。若某天译文独立字超过这个数，需要再扩（3 字节 token），
  到时再说。

### 已验证（EXE 补丁部分）
- 补丁器对原版 EXE 原始字节校验通过；4 个取字点正确改为 `jmp cave`、3 处阈值改为 `cmp ?,0EEh`；
  4 个 cave 反汇编正确；新节 `.xt`/SizeOfImage 正确；扩展表正确烘焙。
- 扩展编解码：内联老字 + 内联新字 + 扩展节字（索引含 >2386 及 >2559）全部编解码一致。
- 扩展不影响原表场景：恒等往返仍 207/207 bit-perfect。
