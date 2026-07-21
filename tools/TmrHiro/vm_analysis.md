# FCS 剧本 VM 分析文档（vm_analysis.md）

本文档是 `srp.pac` 解包后脚本文件反汇编/汇编的唯一真值源。  
引擎入口：`sub_409F10`（加载）→ `sub_40A270`（取当前行）→ `sub_40A4D0`（解释）。

## 0. VM 类型

| 项目 | 结论 |
|------|------|
| 体系结构 | **行寻址**脚本机（非字节流 PC） |
| 指令边界 | 解密后每一行 = 一条指令 |
| 操作码 | 行首 1 字节 |
| 操作数 | 行内剩余全部字节（可变长） |
| 端序 | 立即数多以 ASCII 十进制/十六进制存储；少量 raw `u8` |
| 字符集 | CP932（Shift-JIS） |
| 跳转 | 标签名字符串（`LABEL`/`!name`），非数值偏移 |
| 调用 | 可跨脚本加载（`CALL_OR_JUMP` mode=2） |

### 0.1 文件容器

```
u32le line_count
repeat line_count:
    encrypt(instruction_bytes) + 0x0A
```

解密（`sub_40E1E0`）：对 `0x0A` 之前每个字节  
`plain = nibble_swap(enc ^ 0x0A)`  
`nibble_swap(x) = ((x & 0x0F)<<4) | ((x>>4)&0x0F)`  

加密（逆变换）：  
`enc = nibble_swap(plain) ^ 0x0A`

### 0.2 指令解码流程

1. 读当前行指针 `PC = this+1712`
2. 取 `line = lines[PC]`（已解密、无尾 `0x0A`）
3. `opcode = line[0]`，`payload = line[1:]`
4. `switch(opcode)` 进入 `sub_40A4D0`
5. 字段分隔：主分隔符 `','(0x2C)`（`sub_40E040`）；部分复杂指令用 `' '(0x20)` 分组

### 0.3 跳转与标签

- **定义**：`opcode == 0x21`（`LABEL`），payload 为标签名（ASCII）
- **引用**：`0x1E`/`0x1F` 的名字字段；`0x22` 条件目标；`0x23` 选项目标；`0x25`/`0xC8` UI 按钮目标
- **基准**：标签为**符号名**，不依赖行号绝对地址。改写文本导致行内容变长不影响跳转语义（行索引仍由标签扫描决定）

加载时若首条/任意行 opcode 为 `0xA0`，payload 经 `atoi` 写入 `word_445044`（脚本 ID）。

## 1. Opcode 全表

长度规则：所有指令 `length = 1 + len(payload)`，payload 为整行余下字节（变长，以 `0x0A` 定界）。

| opcode | mnemonic | 语义摘要 | operand_schema |
|-------:|----------|----------|----------------|
| 0x14 | TEXT | 旁白/正文 | text(cp932) |
| 0x15 | VOICE_TEXT | 语音+正文 | voice,text |
| 0x16 | NAME_TEXT | 立绘名+正文 | name,text |
| 0x17 | VOICE_NAME_TEXT | 语音+角色名+正文 | voice,name,text |
| 0x18-0x1B | TEXT_ALTx | 文本变体族 | text_fields |
| 0x1E | CALL_OR_JUMP | 跳转/调用 | u8 mode; u8 flag; name[,ret] |
| 0x1F | CALL_SAVEPOS | 保存返回点后跳转/调用 | 同 0x1E |
| 0x20 | RETURN | 脚本调用返回 | — |
| 0x21 | LABEL | 标签定义 | name |
| 0x22 | IF | 条件分支 | cmp/var fields + target |
| 0x23 | SELECT | 选项菜单 | count_enc + entries |
| 0x24-0x25 | CGMODE_SETUPx | CG/菜单布局 | complex |
| 0x26-0x28 | WAIT_CLICKx | 等待点击/推进 | — |
| 0x32-0x3D | BG_* | 背景 load/pos/move/rect | effect + name/hex |
| 0x46-0x49 | LAYER_IMG* | 图层图片 | fade/layer/name/pos |
| 0x50-0x51 | CHR_SET* | 角色立绘（最多 4） | mode + names |
| 0x5A | EFFECT_STR | 命名特效 | string |
| 0x5B | FADE_COLOR | 颜色淡入淡出 | hex params |
| 0x5C | FADE_MODE | 淡入模式 | u8 |
| 0x5D-0x5F,0x75 | LABEL_ALTx | 标签类标记（解释器空操作） | name? |
| 0x64 | BGM_PLAY | 播放 BGM | vol; param; name |
| 0x65 | BGM_VOL | BGM 音量 | vol_enc |
| 0x66 | BGM_STOP | 停止 BGM | — |
| 0x69/0x6A | SE_PLAY* | 音效 | ch[;vol]; name |
| 0x6B | SE_STOP | 停 SE | — |
| 0x6E | VOICE_PLAY | 播放语音资源 | name |
| 0x6F | VOICE_STOP | 停语音 | — |
| 0x73/0x74 | SND_PLAY* | 其它声音 | — |
| 0x76 | SND_STOP | 停声音 | — |
| 0x78 | AUDIO_STOP_ALL | 停全部音频 | — |
| 0x82 | VAR_SET | 变量赋值 | op; modes; lhs,rhs |
| 0x83 | VAR_SYNC | 变量同步 | — |
| 0x8C-0x8F | FLAG_* / SKIP_FLAG | 系统开关 | u8(1/2) |
| 0x90 | SYS_CALL | 系统调用 | — |
| 0x96-0x98 | WAIT_HEXx | 延时（hex 时长） | hex_digits |
| 0x99-0x9C | WAIT_MODEx | 延时模式 | — |
| 0xA0 | SCRIPT_ID | 脚本数字 ID | decimal ASCII |
| 0xA1 | SCRIPT_TITLE | 脚本标题 | text |
| 0xA2-0xA5 | MODE_* | 内部模式/调用 | — |
| 0xC8 | CG_GALLERY | CG 鉴赏页 | complex |
| 0xD2 | RAND_GLO | 随机 $glo000 | — |

未在样例中出现、但 switch 已列出的 opcode 同样按 raw 保留（`OP_XX`）。

### 1.1 重要子码 / 变体

**0x1E / 0x1F**
- `payload[0] == 1`：脚本内跳到标签 `payload[2:]`（`sub_40A390`）
- `payload[0] == 2`：卸载当前脚本并 `sub_409F10` 加载新脚本名
- `payload[1]` 附加标志（=2 时还可带返回标签第二字段）

**0x22 IF**
- `payload[0]`：比较模式 1..6（`== != > < >= <=`，见 `sub_40D670` mode 3）
- 后续字段空格/` ` 与变量名、`$glo`/`$tmp` 等混排，最后字段为目标

**0x23 SELECT**
- `payload[0]`：选项数相关编码（运行时 `*buf_3`，显示层 `n168 = payload[1]`）
- 每项：`sub_40E040` 按空格取条目，再按逗号拆 text/label

**0x32 BG_LOAD**
- `payload[0]`：效果/通道编码
- `payload[1:]`：背景资源名（如 `bg30`）

**0x50 CHR_SET**
- `payload[0]`：角色槽模式
- 随后为空格分隔的角色立绘名；`mode==1` 可清槽

**0x64 BGM_PLAY**
- `payload[0]`：音量编码（运行时 `vol_enc - 20` 一类换算）
- `payload[1]`：参数字节
- `payload[2:]`：曲名

**数值**
- `sub_40D670(..., 99)`：`atoi` 十进制
- `sub_40D670(..., 100)`：十六进制 ASCII（`0-9a-f`）

## 2. 反汇编文本约定

- 头部注释：`# encoding: cp932`、源文件名、行数
- 每行：`L####: MNEMONIC operand_display`
- 标签定义行前有空行；`LABEL name` 本身仍输出以保真
- 操作数：CP932 可逆显示；不可打印/不可逆字节 `{{XX}}`
- `{`/`}` 字面量用 `{{7B}}`/`{{7D}}`，避免与占位符冲突
- 注释 `  ; def/ref ...` 仅供阅读，汇编时丢弃

## 3. 工具链

| 文件 | 作用 |
|------|------|
| `script_codec.py` | 行加解密 + 容器编解码 |
| `opcodelist.py` | opcode 字典与显示编解码 |
| `disassembler.py` | bin → asm.txt |
| `assembler.py` | asm.txt → bin |
| `pac_*.py` | srp.pac 解包/封包 |

```text
python pac_unpack.py srp.pac srp_extracted
python disassembler.py srp_extracted srp_asm
python assembler.py srp_asm srp_rebuild
# srp_rebuild/* 应与 srp_extracted/* 逐字节一致
python pac_pack.py srp_extracted srp_repack.pac
```

## 4. 验收

- 全部 27 个官方脚本：`disassemble → assemble` **逐字节一致**
- `asm` 中正文为可读日文（CP932），无 `\x` 转义
- 标签以符号名呈现；跳转注释标注 `ref NAME -> L####`

## 5. 样例（start）

```
L0000: SCRIPT_ID 1
L0001: BG_LOAD [17]logo
L0002: WAIT_HEX 000007d0
L0003: RAND_GLO
L0004: IF [01][02][01]$GLO000 1 YUI
...
L0010: LABEL YUI
```

（实际输出以工具生成为准；方括号为 `{{XX}}` 占位。）
