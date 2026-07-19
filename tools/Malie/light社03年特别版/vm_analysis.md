# sispara2 exec.dat VM 分析定义文档

> 真值源：`sispara2.exe` IDA 导出（`decompile/`、`memory/`、`strings.txt`）  
> 目标脚本：`exec.dat`（约 5.78 MB）

## 0.1 VM 类型与体系结构

| 项目 | 结论 |
|------|------|
| 架构 | 自定义脚本 VM（Malie 系 / Popotan 同源演进） |
| 执行模型 | 流式指令 + 内联表达式求值；控制流用标签表索引跳转 |
| 存储 | 哈佛式：globals 数据段 / labels / code / **string pool** 分离 |
| 端序 | Little-endian |
| 宿主加载 | `sub_42AAD0` 读 `exec.dat`；保存对称函数 `sub_42AC40` |
| 解释循环 | `sub_42BBB0`（分发表 `byte_42C274`，opcode = index+2） |

## 0.2 文件总体布局（本版本）

```
u32 global_count
Global[global_count]
u32 data_size
u32 label_count
Label[label_count]
u32 expr_count                 # 本样本为 0（AST 表达式池可为空）
ExprNode[expr_count]          # 仅当 expr_count>0；kind 仍为 u32 旧格式
u32 code_size
u8  code[code_size]
u32 pool_size                 # ★ 新版新增：尾部字符串池
u8  pool[pool_size]
```

### Global
LenString name; TypeNode type_chain; u32 flags; u32 reserved; u32 offset

### TypeNode
u32 kind; if kind!=0: u32 value; TypeNode next

### Label
LenString name; u32 code_offset  (相对 code[0])

### LenString
u32 nbytes; bytes[nbytes]   # 含结尾 NUL

## 0.3 与旧版 Popotan exec.dat 的差异

| 项目 | 旧版 | 本版（sispara2） |
|------|------|------------------|
| 表达式池 | 大量 AST ExprNode（u32 kind） | `expr_count=0`；表达式改内联到 code |
| 文本 | `text` 操作数是 **code 内 cstring** | `text` 操作数是 **pool 偏移 u32** |
| 尾部 | code 结束即 EOF | code 后还有 string pool |
| 操作码号 | text=47, eval=48, str=49, arg=50, jmp=53.. | **整体 +1**：text=48, eval=49, str=50, arg=51, jmp=54.. |
| eval 操作数 | u32 expr_index | **u16 length + 内联表达式字节码** |

实测本文件：
- globals=272, data_size=1960
- labels=29457
- exprs=0
- code_size=3095344
- pool_size=2363255
- text 指令=32702（可读日文台词约 2 万+）

## 0.4 字节码（code）

关键字 1–39 见 `opcode.py`（bgm/call/jump/image/pause/...）。

| opcode | 助记符 | 操作数 |
|-------|--------|--------|
| 41 | arg_end | none（样本未出现） |
| 43/44 | text_a/text_b | 内联 cstring |
| 45/46/47 | num_a/num_b/num_c | u32 |
| **48** | **text** | **u32 pool_offset** → `pool[offset]` 的 C 字符串 |
| **49** | **eval** | **u16 len + len 字节** 内联表达式 VM（`sub_42C410`） |
| 50 | str | 内联 cstring |
| 51 | arg | u32（关键字参数列表项，常见于 call 后） |
| 53 | fstore_imm | u32 |
| 54/55/56 | jmp/jz/jnz | u32 标签下标 |

跳转操作数是标签**下标**，不是字节偏移。

### 字符串池约定
- pool 内为连续 NUL 结尾字符串（可含 `0x07` 控制序列）。
- 常见控制：`{{07}}{{06}}` 行结束/翻页类；`{{07}}{{08}}v_xxx` 语音标记；`{{07}}{{09}}` 等演出标记。
- 并非所有 pool 条目都被 `text` 引用；未引用条目仍需原样保留（`.pool_blob`）。

### 内联表达式 VM（eval blob）要点
- 字节流由 `sub_42C410` 解释；终止于 case 4/5。
- 立即数：op 8/10 后跟 u32；op 14 后跟 u8；op 9 后跟 C 字符串。
- 典型调用：`FrameLayer_GetItem` / `FrameLayer_SetVisible` / `FrameLayer_SendMessage` / `System_TakeScreen`。

## 0.5 工具
- `opcode.py` / `disassembler.py` / `assembler.py`
- 默认编码 cp932；特殊字节 `{{XX}}`
- 反汇编输出：
  - `text <pool_off>, "..."` 保留偏移以便零突变
  - `eval "{{..}}"` 以占位符保留内联 blob
  - `.pool_blob "..."` 整池原样

## 0.6 验收要点
- `python disassembler.py exec.dat -o exec.asm.txt`
- 统计应接近：`texts=32702`，asm 中可见大量日文台词
- 代码段按指令表重编码应与原 `code` 逐字节一致


## 0.7 文本语义映射（源剧本 ↔ pool）

源 `.txt`（如 `sce_a_05a_1.txt`）与 `exec.dat` string pool 的对应关系：

| 源剧本 | pool 字节 | 反汇编语义 |
|--------|-----------|------------|
| `$1` | `07 0C 01` | `$1` |
| `$2` | `07 0C 02` | `$2` |
| `#雪奈 (v_yu1002)本文` 的 voice | `07 08` + `v_yu1002` | `name "雪奈"` + `voice <off>, "v_yu1002"` |
| 台词正文 | 正文 CP932 | `text <off>, "本文"` |
| 有声台词尾 | `07 09 07 06` | `tail=voiced`（.pool） |
| 旁白/普通尾 | `07 06` | `tail=plain` |
| 少数残缺尾 | 仅 `06` 或双 `07 06` 等 | `tail_hex=...` |

说明：
- **说话人姓名本身不在 pool 文本里**，是由 voice id 前缀（`v_yu/v_ak/...`）映射出来的注解字段 `name`；汇编时 `name` 不生成字节。
- **自定义主角名**才是 pool 内嵌特殊字节（`$1/$2`）。
- 尾控制符不进入语义 `text` 正文；导入时按 `tail`/`tail_hex` 还原。
- code 中 voice 与 text 是两条独立 `OP_TEXT`（各带 pool 偏移），中间常有 `ol/pause/clear`。


## 0.5 翻译/改文模型（只改 name + text）

### 你要改什么
- `name "人名"`：真实姓名窗（`FrameLayer_SendMessage` name-setter eval）。改这里就会改游戏人名。
- `text <off>, "台词"`：无语音 hard 台词（生成 `OP_TEXT`）。
- `text <off>, "台词", soft`：有语音对白正文 / 未引用 pool 正文（**不生成 code**，只更新 pool）。
- `.pool`：只作结构引用（voice id / tail），**不要**在 `.pool` 里写长台词。
- `voice <off>, "v_xxx"`：语音引用（`OP_TEXT` → voice 条目）；一般不用改。

### 为何会“挤成一团”
旧汇编器把 pool 按**原始固定偏移**写回。翻译变长后覆盖后面条目，于是 voice id 当人名、对白黏连。  
现已改为：**按原顺序紧凑重排 pool，并 remap 所有 `OP_TEXT` 偏移**。变长/缩短都安全。

### 运行时配对
```
pool:  [voice][NUL][dialogue][NUL]
code:  name "亜姫"          # eval name-setter
       voice 17, "v_ak0001" # OP_TEXT(voice)
       text 28, "...", soft # pool body only; engine shows after voice
```

### 编码注意
- 池字符串编码是 **cp932**（Shift-JIS）。
- 简体中文里不少字不在 cp932（会报 `cannot encode ... with cp932`）。
- 可选：用日文/兼容汉字、全角、或 `{{XX}}` 原始字节；若要做完整汉化需字体/码表方案。

### 命令
```bash
python disassembler.py exec.dat -o exec.asm.txt
# 编辑 name / text
python assembler.py exec.asm.txt -o exec.rebuild.dat
```
零改动 round-trip 与 `exec.dat` 字节一致。

### 行内截断 `%haato`（MLS 同源）
Malie 源剧本（`.mls` 解压后的 `.txt`）里，台词中的 `%haato` 表示心跳/截断点（继续显示下半句）。

在本 `exec.dat` 字符串池中，它被编译成 **单独的 pool 条目边界 + 尾字节 `0x06`**：
```
chunk0 ... 06 00
chunk1 ... 06 00
final  ... 07 09 07 06 00   # 或 07 06
```
反汇编合并为一条：
```text
text 1459336, "「……%haato　……%haato」", soft
```
汇编时再按 `%haato` 拆回多条 pool（保留各段 tail）。

注意：旧版 Popotan **code 内 cstr** 路径里的 `%haato` 另有一套（展开为 expr `100.68` 心形特效）；sispara2 的 pool 台词走的是上面的 `0x06` 分段语义。

## 0.8 文本控制字节（IDA `sub_434A80` / `sub_434810`，crimson 2003）

引擎在 **pool 字符串** 内用 `0x07` 作引导字节，与 code 段 VM opcode 7（`select`）无关。

| 序列 | 语义 token | IDA 行为 |
|------|------------|----------|
| `07 01` base `0A` reading `00` | `<rb "reading">base</rb>` | 递归走过 base/reading；**消费 reading 后的 NUL 并继续**外层文本 |
| `07 04` | `$e` | `sub_434810` 归一化为换行 `0x0A` |
| `07 06` | 末尾 `tail=plain`；中间 `%p` | 翻页/句末计数 |
| `07 08` id `00` | `voice` + 后续台词 | **消费 voice id 的 NUL 并继续** 对话正文 |
| `07 09` (+常跟 `07 06`) | `{{07}}{{09}}` / `tail=voiced` | 有声句结束 |
| `07 0C 01/02` | `$1` / `$2` | 主角名占位 |
| `07 02 XX` | `{{07}}{{02}}{{XX}}` | 稀有效果 |
| bare `0A` | `{{0A}}` | 布局用，多见于 `%p` 后 |

因此：
1. 注音会把物理 pool 切成多条 NUL 串，但逻辑上是一句。
2. `OP_TEXT` 指向的 offset 可能只是逻辑句的开头；后续未引用 entry 仍属同一句。
3. 本游戏 **无** name-setter eval；说话人名由 `v_xx` 前缀映射（睦月/亜梨子/姫野…）。

参考反编译：`decompile/434A80.c`、`434810.c`。

