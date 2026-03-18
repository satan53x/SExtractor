# BunBun / DigitalWorks 引擎汉化工具技术要点
# 游戏：保健室～マジカルピュアレッスン♪～

## 一、封包系统 (pac_tool.py)

### 索引结构
- 索引存储在exe的.data段，**不在BIN文件内**
- 每条目12字节：`offset(u32) + size(u32) + is_packed(u16) + id(u16)`
- `id=0` 为终止符
- GARbro定位方式：用BIN文件大小构造`[size, size]`8字节在exe中搜索

### 5种BIN封包

| 封包 | 内容 | exe硬编码偏移 | 条目数 |
|------|------|-------------|--------|
| TAK.BIN | 脚本 | 0x44748 | 167 |
| VIS.BIN | 图像 | 0x44F28 | 765 |
| STR.BIN | 音乐 | 0x47310 | 39 |
| _SE.BIN | 音效 | 0x474F0 | 77 |
| VCE.BIN | 语音 | 0x47898 | 8429 |

### is_packed 字段（重要！）
- `1` = LZS压缩，`0` = raw数据
- **解压后存raw时必须把flags改成0，否则引擎尝试解压raw数据会卡死**
- pac_tool.py的pack命令自动检测文件头是否LZS来设置flags

### LZS压缩
- 头：`'LZS\x00' + decomp_size(u32)`
- LZSS：4KB ring buffer，0x20填充，写入起始0xFEE
- 12位ring offset + 4位length(+3)
- 引擎检查`LZS`头，不是则直接使用raw数据 → 封包时可不压缩

### 数据对齐
- BIN内子文件按0x800(2048)字节对齐

---

## 二、TAK脚本字节码 (tak_text.py)

### 指令格式
- **通用opcode**：固定4字节 `[opcode, byte1, byte2, byte3]`
- **全部4字节对齐**（包括文本块的总长度）

### 文本指令

| opcode | 含义 | 格式 |
|--------|------|------|
| 0xAA | 消息文本开始 | `AA 00 id_lo id_hi` + SJIS文本 [+ 00 00] |
| 0xAB | 消息文本结束 | `AB 00 00 00` (固定4字节) |
| 0xA8 | 说话者名开始 | `A8 00 id_lo id_hi` + SJIS文本 [+ 00 00] |
| 0xA9 | 说话者名结束 | `A9 00 00 00` (固定4字节) |

### 文本终止规则（最关键的坑）
引擎文本扫描**每次+2字节**，所以：
- 文本字节长度**总是偶数**（SJIS双字节字符）
- 扫描遇到 `0x00`、`0xA9`、`0xAB` 时终止
- **4字节对齐padding规则**：
  - `(4 + text_len) % 4 == 0` → 不加null，下一条AB/A9直接终止
  - `(4 + text_len) % 4 == 2` → 加2字节`00 00`
  - 此规则经40191个文本块验证零违规

### 文件末尾
- 每个脚本文件末尾固定4字节 `00 00 00 00`

### AC跳转指令
- 格式：`AC offset_lo offset_hi 00` (4字节)
- `offset = u16LE(byte[1:3])`，是**绝对偏移**（从脚本开头算起）
- byte[3]固定为0x00
- **文本长度改变时必须自动修正所有AC的跳转目标**
- tak_text.py用 old_to_new 偏移映射表自动修正

### 选择支结构
```
CMD 33 0000     ← 选择支开始
MSG xxxx text   ← 选择支标题
MSG_END
CMD 02 0001     ← 选项1标记
JUMP @target1   ← 选项1跳转
MSG xxxx text   ← 选项1文本
MSG_END
CMD 02 0002     ← 选项2标记  
JUMP @target2   ← 选项2跳转
MSG xxxx text   ← 选项2文本
MSG_END
CMD 2A 0000     ← 选择支结束
```

### txt格式
```
@0000 CMD 33 0000
@0004 MSG 0025 いきなり究極の選択
@0004 TL  0025                        ← 翻译填这行，空则用原文
@0018 MSG_END 00 0000
@001C JUMP @0258
```

### 解析txt时的坑
- `\s` 在Python regex中匹配Unicode全角空格`\u3000` → 用`[ \t]`
- `.rstrip()` 会吃掉全角空格 → 用`.rstrip('\n\r')`
- TL行为空时（未翻译），使用MSG行原文

---

## 三、font32.dat 字体 (font_tool.py)

### 格式
- 89页 × 256×256像素 × BGRA32 = 23,330,816字节
- 每页0x40000(262,144)字节
- 每页10列×10行 = 100个字符
- 每字符24×24像素有效区域
- 白色(RGB=255,255,255) + Alpha通道抗锯齿

### JIS索引计算
```
线性索引 = jis_hi * 94 + jis_lo - 3135
页号 = index / 100
页内位置 = index % 100
X = (pos % 10) * 24
Y = (pos // 10) * 24
文件偏移 = page * 0x40000 + (Y * 256 + X) * 4
```

### SJIS → 槽位（引擎算法 FUN_00406aa0）
```python
def sjis_to_slot(s1, s2):
    if 0x81 <= s1 <= 0x9F: hi = s1 - 0x81
    elif 0xE0 <= s1 <= 0xEF: hi = s1 - 0xC1
    if 0x40 <= s2 <= 0x7E: jis = hi*0x200 + s2 + 0x20E1
    elif 0x80 <= s2 <= 0x9E: jis = hi*0x200 + s2 + 0x20E0
    elif 0x9F <= s2 <= 0xFC: jis = (hi*2+1)*0x100 + 0x2121 + (s2-0x9F)
    return ((jis & 0xFF) - 0xC3F) + (jis >> 8) * 0x5E
```

### 占位符白点
- JIS未定义码位有固定6像素pattern：`(8,11,132)(9,11,132)(8,12,252)(9,12,252)(8,13,180)(9,13,180)`
- dump时用精确pattern匹配排除，不能用像素数阈值

### 汉化方案：字形重绘（无需DLL hook）
1. `subs_cn_jp.json`：中文简体→日文繁体 映射表（2999条）
2. 反转为 日文→中文，用SJIS编码算出JIS槽位
3. 从原始font32.dat复制作为基础
4. 只替换映射表中的字符：用TTF渲染中文字形写入对应槽位
5. 未映射的字符（假名/标点/数字/字母）保留原始字形

---

## 四、完整汉化流程

```bash
# 1. 解包脚本
python pac_tool.py unpack hoken.exe PAC/TAK.BIN tak/ -d

# 2. 提取文本（分文件反汇编）
python tak_text.py extract hoken.exe PAC/TAK.BIN texts/

# 3. 翻译（填写TL行）+ AI翻译

# 4. 重绘字体
python font_tool.py build font32.dat subs_cn_jp.json font.ttf font32_new.dat --size 22

# 5. 写回脚本（自动修正跳转偏移）
python tak_text.py build hoken.exe PAC/TAK.BIN texts/ PAC/TAK.BIN hoken.exe

# 6. 替换文件
#    - PAC\TAK.BIN (脚本)
#    - hoken.exe (索引+flags)
#    - data\ETC\font32.dat (字体)
```

## 五、round-trip验证结果
- disassemble → assemble：167/167 ✅
- disassemble → text → parse → assemble：167/167 ✅
- extract → build (file pipeline)：167/167 ✅
- flags全部正确设为0 ✅
- 580个跳转偏移自动修正 ✅
