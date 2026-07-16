# Malie Scenario (.mls) VM / 格式分析

## 结论摘要

`scenario/*.mls` **不是** 定长字节码镜像，而是：

```
MalieScenario  (13 字节 ASCII magic)
+ zlib.compress(script_bytes, level=6)   # 文件内 CMF/FLG = 78 9C
```

解压后的 `script_bytes` 为 **CP932（Shift_JIS）编码的 Malie 场景源码文本**，行结束符统一为 `CRLF`（`\r\n`）。

宿主 `bokudvd.exe` 在 `sub_42E6F0` 识别 magic 后通过 `ZLibIn_OpenFromFILE` 流式解压；词法/语法在 `sub_42ED30` / `sub_423850` 等路径完成，再由 `sub_4292F0` 编译为运行时字节码缓冲。本工具按规范对 **已解密/已解压的纯净脚本流** 做语义反汇编，并在汇编阶段重新应用相同 zlib 封装，保证零突变。

## 容器层

| 字段 | 偏移 | 内容 |
|------|------|------|
| magic | 0 | `MalieScenario` |
| zlib payload | 13 | deflate，`zlib.compress(..., 6)` |

验证：对本游戏 37 个官方 `.mls`，`zlib.compress(raw, 6)` 与原文件压缩段逐字节一致。

## 脚本语义模型（源码级“指令”）

由于 onboard 数据是源码而非定长 opcode 流，工具将 **每一行** 视为一条语义单元：

| 助记符 | 识别 | 说明 |
|--------|------|------|
| `EMPTY` | 空行 | 仅 CRLF |
| `LABEL` | `name:` | 跳转标签定义 |
| `CMD` | `&name ...` | 指令/宏，保留 `MIDDLE`/`TERM` 以零突变 |
| `DIALOG` | `#channel...` | 对白行，`RAW=` 保存整行 |
| `TEXT` | 其它 | 旁白/叙述（可含内联 `$e` 翻页） |

### 命令终结符变体（TERM）

官方脚本中观察到：

- `" ;"`（绝大多数）
- `""`（无分号，如 `&charmode manual`、`&sound_ctrl loop off`）
- `" ; "`（极少数行尾空白）

反汇编用 `MIDDLE=` / `TERM=` 原样保留。

### 跳转与标签

- `&goto target ;` 等控制流命令在注释中标注 `target=`
- 定义处输出符号化标签（如 `sc_s14:`），标签前保留空行
- 重汇编时标签写回为源码 `name:` 行；跳转目标通过 `MIDDLE` 原文字段恢复，不硬编码偏移

编译器内部 `&` 命令表（`off_467BCC`，1..39）与源码宏关键字表（`off_468338`，token 101..212）完整收录于 `opcodelist.py`。

## 文本与占位符

- 默认编码：`cp932`（可用 `--encoding` / `.encoding` 覆盖）
- 不输出 `\xNN` 转义；不可打印单字节使用 `{{XX}}` / `{{XX:YY}}`
- 普通反斜杠、全角空格按文本保留
- 对白/旁白可读日文直接呈现

## 关键函数索引（bokudvd.exe）

| 地址 | 作用 |
|------|------|
| `0x42E6F0` | 打开 `.mls` / 识别 `MalieScenario` / 挂接 zlib 输入 |
| `0x42E940` | 按容器类型取下一字节 |
| `0x42EBC0` / `0x42ED30` | 取字符 / 词法 token |
| `0x42F530` | 场景源码反编译导出（`_maliescenario.txt`） |
| `0x429210` / `0x4295F0` / `0x4292F0` | 编译入口 / 语句分发 / 字节码 emit |
| `0x42A280` | `&` 命令名二分查找 |

## 零突变验证

```text
python disassembler.py bin txt
python assembler.py txt rebuild
# 37/37 官方 scenario/*.mls 与 rebuild 逐字节一致
```
