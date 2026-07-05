# SDT 脚本 VM 分析定义文档

本文档按 `CLAUDE.md` 中“0. 前置 VM 分析与指令集建模”的要求整理，作为后续 `opcodelist.py`、`disassembler.py`、`assembler.py` 处理 SDT 文件的结构依据。

当前分析对象是 EXE 中的 `.SDT/.sdt` 剧本脚本层，不是外层 PAK 容器层。现有结论来自 `export-for-ai` 反编译文件与本目录 `mes (1)/*.SDT` 样本的交叉验证。

已确认关键反编译入口：

```text
export-for-ai/decompile/411080.c   字符串参数 -> "%s.sdt" -> 加载 SDT
export-for-ai/decompile/4110C0.c   数字参数 -> "%05d.sdt" -> 加载 SDT
export-for-ai/decompile/417C10.c   切换当前 SDT 脚本、记录当前文件名/脚本序号
export-for-ai/decompile/458FD0.c   重置当前脚本上下文、加载 SDT、从 entry 0 启动
export-for-ai/decompile/458CC0.c   SDT 容器头解析、entry 表与 body 装载
export-for-ai/decompile/458DD0.c   按 entry index 启动脚本 VM
export-for-ai/decompile/459070.c   每帧驱动脚本解释器
export-for-ai/decompile/459150.c   16-bit opcode 分发入口
export-for-ai/decompile/4101C0.c   opcode >= 0x2A 的外部命令 switch
export-for-ai/decompile/4109C0.c   外部命令参数描述表解析器
export-for-ai/decompile/410F00.c   外部命令后处理/引用参数写回
```

## 1. VM 类型识别

### 1.1 资产类型与命名

EXE 中可见两类 SDT 文件名生成入口：

- `sub_411080(a1)`：将字符串参数格式化为 `%s.sdt` 后调用 `sub_417C10`。
- `sub_4110C0(a1)`：将数字参数格式化为 `%05d.sdt` 后调用 `sub_417C10`。

`sub_417C10` 会：

1. 调用 `sub_458FD0(Source)` 加载并启动目标 SDT。
2. 将当前脚本名保存到全局 `String`。
3. 通过 `sub_45F630(String)` 从文件名前缀解析数字，并写入 `dword_742D40 = 10 * parsed_number`，后续语音编号默认值会使用该值。
4. 在静态 SDT 文件名表 `off_53C7C8` 中查找当前文件名，命中索引写入 `dword_742D44`。
5. 将 `dword_53D7CC` 复位为 `-1`。

因此 `sub_417C10` 是“切换当前剧本/场景脚本”的高层入口，而不是普通文件读取函数。

### 1.2 架构判断

SDT VM 是一个轻量级、线性 bytecode 解释器，具有如下特征：

- 文件内存在固定头与 256 项入口表。
- 正文从文件偏移 `0x408` 开始，是可变长度指令流。
- VM 内部 `ip` 使用正文内相对偏移，而不是文件绝对偏移。
- opcode 固定为 16-bit little-endian。
- opcode `< 0x2A` 属于 VM 内置控制/算术/跳转指令。
- opcode `>= 0x2A` 属于游戏脚本命令，先由参数描述表 `byte_53B080` 解析参数，再由 `sub_4101C0` 的大 switch 调用具体 handler。
- VM 有 50 个 32-bit 局部变量槽：脚本上下文 `+0xC00` 起始，`sub_458DD0` 每次启动 entry 时清零 `0xC8` 字节。
- VM 有一个简易调用/跳转栈：脚本上下文 `+0xCCC` 为栈指针；若停止时栈指针非零，`sub_458E90` 报 `Script Error : Stack Pointer Abnormal`。

后续工具应把 SDT 视为“带入口表的可变长二进制脚本 VM”，而不是纯文本脚本或固定宽度 token 流。

## 2. SDT 文件结构

### 2.1 Header

SDT 文件头固定 `0x408` 字节，小端序：

| 文件偏移 | 大小 | 字段 | 说明 |
|---:|---:|---|---|
| `0x0000` | 2 | magic0 | 必须为 `0x004C`，即宽字符式 `L` 的低字节形式 |
| `0x0002` | 2 | magic1 | 必须为 `0x0046`，即宽字符式 `F` 的低字节形式 |
| `0x0004` | 4 | file_size | SDT 总文件大小；loader 用 `file_size - 0x408` 作为 body 大小 |
| `0x0008` | 1024 | entry[256] | 256 个 `uint32le` 入口偏移 |
| `0x0408` | variable | body | SDT 指令流正文 |

证据：

- `sub_458CC0` 检查 `WORD[0] == 76`、`WORD[1] == 70`。
- `sub_458CC0` 读取 `DWORD[1]` 后减 `1032`，即 `0x408`，作为 body 字节数。
- `sub_458CC0` 将 `hMem + 0x408` 后的 body 拷贝到脚本上下文 `+0xCDC`。
- `sub_458CC0` 从 `hMem + 8` 循环复制 256 个 DWORD 到脚本上下文开头。

示例样本 `mes (1)/0100.SDT`：

```text
file_size = 0x777D = 30589
header_size = 0x408
body_size = 0x7375
entry[0] = 0x00000409
first executed ip = entry[0] - 1 = 0x408
```

### 2.2 Entry 表语义

入口表为 256 个 `uint32le`。`sub_458DD0(ctx, entry_index)` 的启动规则：

```c
if (ctx->entry[entry_index] == 0)
    return 0;
ctx->state = 1;
ctx->ip = ctx->entry[entry_index] - 1;
ctx->sp = 0;
memset(ctx + 0xC00, 0, 0xC8);
```

因此 entry 表中的非零值是 **正文 body 内 1-based 偏移**。实际执行地址需要减 1。

在 asm 表示中建议使用：

```text
; omitted .entry slots are 0
.entry 0, loc_00000408
```

反汇编输出只列非零 entry，未列出的 entry 槽位视为 0；不要输出 256 行全零/非零混合表，也不要直接输出 `0x00000409`。重汇编时再写回 `target_body_offset + 1`。

### 2.3 Body 区域

body 是可变长指令流，地址空间以 body 起点为 `0`。例如文件偏移 `0x408` 对应 body offset `0x00000000`。

解释器每次从：

```c
opcode = *(uint16_t *)(ctx->body + ctx->ip)
```

读取 16-bit little-endian opcode。

多数指令 handler 自行将 `ctx->ip` 增加指令长度；遇到跳转/调用类指令时会直接写入目标 offset。

### 2.4 脚本上下文结构

根据 `sub_458CC0`、`sub_458DD0`、`sub_459070`、`sub_458E90` 的读写，可建立高置信字段：

| 上下文偏移 | 大小 | 字段 | 说明 |
|---:|---:|---|---|
| `+0x000` | 1024 | entry[256] | 从 SDT header 复制而来，保持 1-based 原值 |
| `+0xC00` | 200 | locals[50] | 50 个 `int32` 脚本局部变量槽 |
| `+0xCC8` | 4 | ip | 当前 body offset，0-based |
| `+0xCCC` | 4 | sp | VM 调用/返回栈指针 |
| `+0xCDC` | 4 | body_ptr | 当前 SDT body 缓冲区指针 |
| `+0xCE0` | 1 | state | 解释器状态：0 停止，1 运行，2/3 等待态，4 允许重新启动 |

## 3. 文件查找与加载流程

高层调用链：

```text
sub_411080 / sub_4110C0
  -> sub_417C10
    -> sub_458FD0
      -> sub_458E30(ctx)      ; 清理旧上下文
      -> sub_458CC0(file, ctx); 加载 SDT 容器
      -> ctx->state = 4
      -> sub_458DD0(ctx, 0)   ; 从 entry 0 启动
```

`sub_458CC0` 通过 `sub_401BD0(*(char **)dword_762C94, lpFileName, &hMem)` 读取文件。`sub_401BD0` 的查找顺序：

1. 散文件：`%s\%s`
2. `patch.pak`
3. `%s.pak`
4. `pak\%s.pak`

如果 `arglist == NULL`，则直接读取 `lpFileName`。

注意：`sub_401BD0` 在尝试散文件时还会执行一次：

```text
CopyFileA("%s\%s", "%s\buf\%s", fail_if_exists=1)
```

这更像调试/缓存复制行为，不影响 SDT 格式本身。

## 4. 运行期执行流程

主循环在 `WinMain` 中空闲时反复调用：

```text
sub_440510(60)
  -> sub_440230(a1)
    -> case dword_74CE6C == 3:
       sub_459070(&unk_74BA10)
```

`sub_459070(ctx)` 的解释流程：

```c
dword_762C90 = ctx;
dword_762C8C = ctx->body_ptr;

if (ctx->state == 3)
    sub_459130();
if (ctx->state == 2)
    sub_459100();
if (ctx->state == 1)
    while (sub_459150(0))
        ;
return ctx->state;
```

`sub_459150(arglist)` 是单步分发器：

```c
opcode = u16le(ctx->body + ctx->ip);
if (opcode < 0x2A)
    dispatch_builtin(opcode);
else if (arglist != 0)
    return arglist;
else
    return sub_4101C0(opcode);
```

## 5. 指令编码总览

### 5.1 基础类型

| 类型 | 编码 | 说明 |
|---|---|---|
| `opcode` | `u16le` | 每条指令起始 2 字节，小端 |
| `u8` | 1 byte | 无符号字节 |
| `u16` | 2 bytes | 小端，部分 reader 使用低字节 + 高字节手动拼接 |
| `i16` | 2 bytes | 小端，有符号扩展 |
| `u32/i32` | 4 bytes | 小端 |
| `rel/body_offset` | 4 bytes | 目标 body offset，0-based；跳转会直接写入 `ctx->ip` |
| `local_index` | `u8` | 索引 `ctx + 0xC00 + 4*index` |
| `short_string` | `u8 len + bytes` | 长度为单字节 |
| `long_string` | `u16 len + bytes` | 长度为双字节 |

### 5.2 `sub_458EF0` 数值读取约定

`sub_458EF0(ptr, wide_flag)` 是内置 opcode 常用的二选一取值器：

| `wide_flag` | 读取方式 | 说明 |
|---:|---|---|
| `0` | `locals[*ptr]` | `ptr` 指向 1 字节局部变量索引；返回 `ctx+0xC00+4*index` 的 DWORD。 |
| `1` | `i32le(ptr)` | `ptr` 指向 4 字节立即数；返回该 DWORD。 |

因此内置 opcode 成对出现时，偶数/短格式通常是“从局部变量取右操作数”，奇数/长格式通常是“从 4 字节立即数取右操作数”。例如：

- `0x0002` 长度 4：`locals[dst] = locals[src]`。
- `0x0003` 长度 7：`locals[dst] = imm32`。
- `0x0006` 长度 9：比较 `locals[lhs]` 与 `locals[rhs]`。
- `0x0007` 长度 12：比较 `locals[lhs]` 与 `imm32`。

### 5.3 外部命令参数描述表

对于 opcode `>= 0x40`，`sub_4101C0` 首先调用：

```c
dword_66B42C = sub_4109C0(opcode);
```

`sub_4109C0` 使用：

```text
param_desc = byte_53B080 + 17 * (opcode - 64)
```

每个 opcode 最多 17 个参数描述码。描述码含义：

| 描述码 | reader | operand_schema | 说明 |
|---:|---|---|---|
| `0` | end | none | 参数结束，当前偏移即指令长度 |
| `1` | `sub_410DB0` | `u8` | 读取 1 字节参数 |
| `2` | `sub_410C00(..., 4)` | `typed_i32` | 读取 mode + 4 字节/字符串/变量引用 |
| `3` | `sub_410E20` | `short_string` | `u8 len + bytes` |
| `4` | `sub_410E80` | `long_string` | `u16 len + bytes` |
| `5` | `sub_410DB0` + writeback | `local_index_ref` | 先读局部变量索引，handler 后由 `sub_410F00` 写回结果 |
| `6` | inline comparator | `local_index, cmp_op, typed_i32` | 读取局部变量，与一个 typed_i32 比较，生成 bool |
| `7` | `sub_410DB0` | `u8` | 与 1 同 reader，语义由具体命令决定 |
| `8` | `sub_410DE0` | `u16` | 读取 2 字节参数 |
| `9` | `sub_410DE0` | `u16` | 与 8 同 reader，语义由具体命令决定 |

`typed_i32` 的 mode 规则来自 `sub_410C00`：

| mode | 后续编码 | 返回值 |
|---:|---|---|
| `0` | `i32 index` | 返回 `locals[index]` |
| `1` | `i32 value` | 返回立即数 `value` |
| `2` | `u8 len + bytes` | 读字符串后调用 `sub_410CF0(Str1)` 转数值 |
| 其它 | `i32 value` | 当前代码按立即数路径返回 |

### 5.4 外部命令长度

外部命令长度不是固定表中的常量，而是由 `sub_4109C0` 实际解析参数后返回的 `dword_66B42C` 决定。大多数 handler 最终执行：

```c
ctx->ip += dword_66B42C;
```

某些等待/显示类 handler 会在条件满足后才推进 `ip`，例如 opcode `0x00A5` 对应 `sub_411B40`，它会等待文本显示完成后再加 `dword_66B42C`。

## 6. Opcode 长度与格式表

### 6.1 内置 VM opcode：`0x0001..0x0028`

内置 opcode 由 `sub_459150` 直接 switch 分发。下表已补齐可由 handler 高置信确认的名称、长度、操作数和行为；`0x0000` 与 `0x0029` 不是有效内置 case。

| Opcode | 命名 | byte_pattern | length / format | operand_schema | sub_opcode / variants | 精确定义与证据 |
|---:|---|---|---|---|---|---|
| `0x0001` | `END` | `01 00` | 2 bytes | none | none | `sub_458E90(ctx, 0)`：停止脚本，清 `state/ip`；若 `sp != 0` 报 `Script Error : Stack Pointer Abnormal`。 |
| `0x0002` | `MOV_LOCAL_LOCAL` | `02 00` | 4 bytes / `<op,u8 dst,u8 src>` | `dst:local_index, src:local_index` | `sub_459350(0)` | `locals[dst] = locals[src]`；`sub_458EF0(...,0)` 从局部变量取值。 |
| `0x0003` | `MOV_LOCAL_IMM32` | `03 00` | 7 bytes / `<op,u8 dst,i32 value>` | `dst:local_index, value:i32` | `sub_459350(1)` | `locals[dst] = imm32`；`sub_458EF0(...,1)` 读 4 字节立即数。 |
| `0x0004` | `SWAP_LOCAL` | `04 00` | 4 bytes / `<op,u8 a,u8 b>` | `a:local_index, b:local_index` | none | `sub_4593B0` 交换 `locals[a]` 与 `locals[b]`。 |
| `0x0005` | `RAND_LOCAL` | `05 00` | 3 bytes / `<op,u8 dst>` | `dst:local_index` | none | `sub_459410`：`locals[dst] = rand() % 0xFFFF`。 |
| `0x0006` | `JCC_LOCAL_LOCAL_SKIP` | `06 00` | 9 bytes / `<op,u8 lhs,u8 cmp,u8 rhs,u32 target>` | `lhs:local_index, cmp:cmp_op, rhs:local_index, target:body_offset` | false fallthrough | `sub_459450(0)`：比较成立则 `ip=target`，否则 `ip += 9`。 |
| `0x0007` | `JCC_LOCAL_IMM32_SKIP` | `07 00` | 12 bytes / `<op,u8 lhs,u8 cmp,i32 rhs,u32 target>` | `lhs:local_index, cmp:cmp_op, rhs:i32, target:body_offset` | false fallthrough | `sub_459450(1)`：比较成立则 `ip=target`，否则 `ip += 12`。 |
| `0x0008` | `JCC_LOCAL_LOCAL_ELSE` | `08 00` | 13 bytes / `<op,u8 lhs,u8 cmp,u8 rhs,u32 true,u32 false>` | `lhs:local_index, cmp:cmp_op, rhs:local_index, true:body_offset, false:body_offset` | two-way branch | `sub_459540(0)`：比较成立读 `+5` target，否则读 `+9` target。 |
| `0x0009` | `JCC_LOCAL_IMM32_ELSE` | `09 00` | 16 bytes / `<op,u8 lhs,u8 cmp,i32 rhs,u32 true,u32 false>` | `lhs:local_index, cmp:cmp_op, rhs:i32, true:body_offset, false:body_offset` | two-way branch | `sub_459540(1)`：比较成立读 `+8` target，否则读 `+12` target。 |
| `0x000A` | `LOOP_DEC_JNZ` | `0A 00` | 7 bytes / `<op,u8 counter,u32 target>` | `counter:local_index, target:body_offset` | none | `sub_459610`：若 `locals[counter] > 0`，先递减再跳到 target；否则 `ip += 7`。 |
| `0x000B` | `JMP` | `0B 00` | 6 bytes / `<op,u32 target>` | `target:body_offset` | none | `sub_459670`：无条件 `ip = target`。 |
| `0x000C` | `INC_LOCAL` | `0C 00` | 3 bytes / `<op,u8 local>` | `local:local_index` | none | `sub_4596A0(12)`：`locals[local]++`。 |
| `0x000D` | `DEC_LOCAL` | `0D 00` | 3 bytes / `<op,u8 local>` | `local:local_index` | none | `sub_4596A0(13)`：`locals[local]--`。 |
| `0x000E` | `BITNOT_LOCAL` | `0E 00` | 3 bytes / `<op,u8 local>` | `local:local_index` | none | `sub_4596A0(14)`：`locals[local] = ~locals[local]`。 |
| `0x000F` | `NEG_LOCAL` | `0F 00` | 3 bytes / `<op,u8 local>` | `local:local_index` | none | `sub_4596A0(15)`：`locals[local] = -locals[local]`。 |
| `0x0010` | `ADD_LOCAL_LOCAL` | `10 00` | 4 bytes / `<op,u8 dst,u8 rhs>` | `dst:local_index, rhs:local_index` | paired with `0x0011` | `sub_459720`：`locals[dst] = locals[dst] + locals[rhs]`。 |
| `0x0011` | `ADD_LOCAL_IMM32` | `11 00` | 7 bytes / `<op,u8 dst,i32 rhs>` | `dst:local_index, rhs:i32` | paired with `0x0010` | `sub_459720`：加法，右操作数为立即数。 |
| `0x0012` | `SUB_LOCAL_LOCAL` | `12 00` | 4 bytes | `dst:local_index, rhs:local_index` | paired | `locals[dst] = locals[dst] - locals[rhs]`。 |
| `0x0013` | `SUB_LOCAL_IMM32` | `13 00` | 7 bytes | `dst:local_index, rhs:i32` | paired | `locals[dst] = locals[dst] - imm32`。 |
| `0x0014` | `MUL_LOCAL_LOCAL` | `14 00` | 4 bytes | `dst:local_index, rhs:local_index` | paired | `locals[dst] = locals[dst] * locals[rhs]`。 |
| `0x0015` | `MUL_LOCAL_IMM32` | `15 00` | 7 bytes | `dst:local_index, rhs:i32` | paired | `locals[dst] = locals[dst] * imm32`。 |
| `0x0016` | `DIV_LOCAL_LOCAL` | `16 00` | 4 bytes | `dst:local_index, rhs:local_index` | paired | 整数除法；除数为 0 时结果为 0。 |
| `0x0017` | `DIV_LOCAL_IMM32` | `17 00` | 7 bytes | `dst:local_index, rhs:i32` | paired | 整数除法；除数为 0 时结果为 0。 |
| `0x0018` | `MOD_LOCAL_LOCAL` | `18 00` | 4 bytes | `dst:local_index, rhs:local_index` | paired | 取模；除数为 0 时结果为 0。 |
| `0x0019` | `MOD_LOCAL_IMM32` | `19 00` | 7 bytes | `dst:local_index, rhs:i32` | paired | 取模；除数为 0 时结果为 0。 |
| `0x001A` | `AND_LOCAL_LOCAL` | `1A 00` | 4 bytes | `dst:local_index, rhs:local_index` | paired | 按位与。 |
| `0x001B` | `AND_LOCAL_IMM32` | `1B 00` | 7 bytes | `dst:local_index, rhs:i32` | paired | 按位与。 |
| `0x001C` | `OR_LOCAL_LOCAL` | `1C 00` | 4 bytes | `dst:local_index, rhs:local_index` | paired | 按位或。 |
| `0x001D` | `OR_LOCAL_IMM32` | `1D 00` | 7 bytes | `dst:local_index, rhs:i32` | paired | 按位或。 |
| `0x001E` | `XOR_LOCAL_LOCAL` | `1E 00` | 4 bytes | `dst:local_index, rhs:local_index` | paired | 按位异或。 |
| `0x001F` | `XOR_LOCAL_IMM32` | `1F 00` | 7 bytes | `dst:local_index, rhs:i32` | paired | 按位异或。 |
| `0x0020` | `EVAL_EXPR` | `20 00` | `5 + expr_len` bytes / `<op,u8 dst,i16 expr_len,expr_packet>` | `dst:local_index, expr_len:i16, expr_packet:expr_token[]` | expression token type/value；operator `6..10` | `sub_459880` 解析表达式包并写回目标 local；详见 6.1.1。 |
| `0x0021` | `PUSH_LOCALS` | `21 00` | 2 bytes | none | stack op | `sub_459AB0` 将 50 个 local 依次压入 VM 栈，`ip += 2`。 |
| `0x0022` | `POP_LOCALS` | `22 00` | 2 bytes | none | stack op | `sub_459B00` 从 VM 栈弹回 50 个 local，`ip += 2`。 |
| `0x0023` | `CALL_ENTRY` | `23 00` | 3 bytes / `<op,u8 entry_index>` | `entry_index:u8` | call stack | `sub_459B60`：压入返回地址 `ip+3`，跳到 `entry[entry_index]-1`，若 entry 为空报 Script Call Error。 |
| `0x0024` | `RET` | `24 00` | 2 bytes | none | call stack | `sub_459BC0`：弹出返回地址到 `ip`，恢复上一 `dword_587A08`。 |
| `0x0025` | `WAIT_FRAMES` | `25 00` | 4 bytes / `<op,i16 frames>` | `frames:i16` | state=2 yield | `sub_459BE0` 设置 `state=2`，每帧 `sub_459100` 计数到 frames 后恢复运行。 |
| `0x0026` | `WAIT_TIME_MS` | `26 00` | 4 bytes / `<op,i16 ms>` | `milliseconds:i16` | state=3 yield | `sub_459C40` 设置 `wake_time=timeGetTime()+ms` 与 `state=3`，到时由 `sub_459130` 恢复运行。 |
| `0x0027` | `YIELD_NOP` | `27 00` | 2 bytes | none | frame yield | `sub_459CA0`：`ip += 2`，并让 `sub_459150` 返回 0，停止本帧连续执行。 |
| `0x0028` | `LOAD_SDT` | `28 00` | `3 + len` bytes / `<op,u8 len,bytes filename>` | `filename:byte_string` | cross-script load | `sub_459010` 读长度与文件名，调用 `sub_458FD0(filename)` 重新加载脚本。 |

#### 6.1.1 `EVAL_EXPR` (`0x0020`) 表达式 packet 子格式

`sub_459880` 给出了 `0x0020` 的完整结构化边界：

```text
<u16 opcode=0x0020>
<u8  dst_local>
<i16 expr_len>
<expr_packet: expr_len bytes>
```

解释器执行后将结果写入 `locals[dst_local]`，并执行 `ip += expr_len + 5`。因此反汇编器/汇编器的指令边界只依赖 `expr_len`，不需要猜测文本或扫描后续 opcode。

表达式 packet 由紧凑 token 串组成。`sub_459880` 先按 token 长度把 packet 展开到临时数组，再反复寻找二元运算 token 规约为单个立即数 token。当前 EXE 中可确认的 token 子格式如下：

| token kind | 长度 | token_schema | 语义 |
|---:|---:|---|---|
| `0` | 5 bytes | `imm32_token` | 立即数操作数；解释器用 `sub_458EE0` 读取 32-bit 小端值。 |
| `1` | 2 bytes | `local_token` | 局部变量操作数；后随 1 字节 `local_index`，求值时读取 `locals[local_index]`。 |
| `2` | 2 bytes | `binary_op_token` | 二元运算符；后随 1 字节 operator 子码。解释器取相邻左右 token 作为操作数并规约。 |
| `3` | 0 bytes on disk | internal sentinel | 仅由解释器在临时 token 数组末尾追加，文件中不应显式出现。 |

二元 operator 子码：

| operator | 助记名 | 计算 |
|---:|---|---|
| `6` | `EXPR_ADD` | `lhs + rhs` |
| `7` | `EXPR_SUB` | `lhs - rhs` |
| `8` | `EXPR_MUL` | `lhs * rhs` |
| `9` | `EXPR_DIV` | `lhs / rhs`；`rhs == 0` 时结果为 `0` |
| `10` | `EXPR_MOD` | `lhs % rhs`；`rhs == 0` 时结果为 `0` |

规约规则：

1. 操作数 token kind 为 `0` 时，其值直接来自 `imm32_token`。
2. 操作数 token kind 非 `0` 时，解释器把 token value 当作 `local_index` 并读取 `locals[local_index]`；官方 handler 中实际可命名为 `local_token(kind=1)`。
3. 遇到 `binary_op_token(kind=2)` 时，取其左邻 token 与右邻 token 计算，计算结果替换左邻位置为 `imm32_token(kind=0)`，随后把右侧剩余 token 左移覆盖，直到 token 串被规约到单个值。
4. 运算顺序不是常规优先级解析器，而是按 token 串扫描到的 `kind=2` 逐次规约；编译器若需要保留原脚本语义，必须逐 token 原样输出/重组，不要尝试用普通中缀表达式重排。

覆盖结论：全量官方样本统计中 `0x0020` 出现次数为 0，因此上述格式来自 `sub_459880` handler 的静态逆向，而不是样本实例。工具实现仍应支持该格式；反汇编时建议输出为显式 token 序列，例如 `EVAL_EXPR L0, [IMM32 1, OP EXPR_ADD, LOCAL L2]`，汇编时按 token 原顺序重建，以满足零突变。

### 6.2 外部命令 opcode 全表：`0x0040..0x0108`

外部命令的**清晰命名**不再依赖 handler 猜测，而是直接来自 EXE 命令名表。该表位于内存导出 `0x53AA30..0x53B070`，每项 8 字节：

```c
struct CommandNameEntry {
    char *name;
    uint32_t opcode;
};
```

因此下表的“命名”列为高置信命令原名；即使某些 opcode 在 `sub_4101C0` 中没有显式 case，也仍可由命令表和 `byte_53B080` 参数描述表获得稳定的反汇编名称与长度规则。没有显式 case 的命令在当前 EXE 运行分发中走 default 路径，仅执行通用参数后处理 `sub_410F00` 并返回对应 `return_flag`。

参数缩写：

| 缩写 | 对应描述码 | 含义 |
|---|---:|---|
| `u8` | `1` | 单字节参数 |
| `typed_i32` | `2` | `mode + i32/变量引用/字符串数值`，见 `sub_410C00` |
| `str8` | `3` | `u8 len + bytes` |
| `str16` | `4` | `u16 len + bytes` |
| `out_local` | `5` | 局部变量索引，执行后由 `sub_410F00` 写回 |
| `cmp_expr` | `6` | `local_index, cmp_op, typed_i32` 比较表达式 |
| `u8_alt` | `7` | 与 `u8` 同 reader，命令私有语义 |
| `u16` | `8` | 双字节参数 |
| `u16_alt` | `9` | 与 `u16` 同 reader，命令私有语义 |

| Opcode | 命名 | byte_pattern | length / format | operand_schema | sub_opcode / variants | 精确定义与证据 |
|---:|---|---|---|---|---|---|
| `0x0040` | `LoadMap` | `40 00` | dynamic / `<u16 opcode> + typed_i32 + typed_i32` | arg0:typed_i32, arg1:typed_i32 | handler=sub_411220; return_flag=1; aux=0 | 命令名来自命令表 `0x53AA30: 0x53C5E4 -> LoadMap, opcode=64`；参数描述表 `0x53B080`；运行分发见 `sub_4101C0`。 |
| `0x0041` | `ReleaseMap` | `41 00` | 2 bytes / `<u16 opcode>` | none | handler=sub_411250; return_flag=1; aux=0 | 命令名来自命令表 `0x53AA38: 0x53C5D8 -> ReleaseMap, opcode=65`；参数描述表 `0x53B091`；运行分发见 `sub_4101C0`。 |
| `0x0042` | `SetMapObj` | `42 00` | dynamic / `<u16 opcode> + typed_i32 + typed_i32 + typed_i32 + typed_i32 + typed_i32 + typed_i32 + typed_i32` | arg0:typed_i32, arg1:typed_i32, arg2:typed_i32, arg3:typed_i32, arg4:typed_i32, arg5:typed_i32, arg6:typed_i32 | handler=sub_411270; return_flag=1; aux=2 | 命令名来自命令表 `0x53AA40: 0x53C5CC -> SetMapObj, opcode=66`；参数描述表 `0x53B0A2`；运行分发见 `sub_4101C0`。 |
| `0x0043` | `SetMapObjEx` | `43 00` | dynamic / `<u16 opcode> + typed_i32 + str8 + str8 + typed_i32 + typed_i32 + typed_i32 + typed_i32` | arg0:typed_i32, arg1:str8, arg2:str8, arg3:typed_i32, arg4:typed_i32, arg5:typed_i32, arg6:typed_i32 | handler=sub_4112E0; return_flag=1; aux=2 | 命令名来自命令表 `0x53AA48: 0x53C5C0 -> SetMapObjEx, opcode=67`；参数描述表 `0x53B0B3`；运行分发见 `sub_4101C0`。 |
| `0x0044` | `SetMapObjNoLoad` | `44 00` | dynamic / `<u16 opcode> + typed_i32 + typed_i32 + typed_i32 + typed_i32 + typed_i32 + typed_i32 + typed_i32` | arg0:typed_i32, arg1:typed_i32, arg2:typed_i32, arg3:typed_i32, arg4:typed_i32, arg5:typed_i32, arg6:typed_i32 | handler=sub_411340; return_flag=1; aux=2 | 命令名来自命令表 `0x53AA50: 0x53C5B0 -> SetMapObjNoLoad, opcode=68`；参数描述表 `0x53B0C4`；运行分发见 `sub_4101C0`。 |
| `0x0045` | `SetMapObjRev` | `45 00` | dynamic / `<u16 opcode> + typed_i32 + typed_i32` | arg0:typed_i32, arg1:typed_i32 | handler=sub_4113B0; return_flag=1; aux=0 | 命令名来自命令表 `0x53AA58: 0x53C5A0 -> SetMapObjRev, opcode=69`；参数描述表 `0x53B0D5`；运行分发见 `sub_4101C0`。 |
| `0x0046` | `SetMapObjLayer` | `46 00` | dynamic / `<u16 opcode> + typed_i32 + typed_i32` | arg0:typed_i32, arg1:typed_i32 | handler=sub_4113E0; return_flag=1; aux=0 | 命令名来自命令表 `0x53AA60: 0x53C590 -> SetMapObjLayer, opcode=70`；参数描述表 `0x53B0E6`；运行分发见 `sub_4101C0`。 |
| `0x0047` | `SetMapObjMove` | `47 00` | dynamic / `<u16 opcode> + typed_i32 + typed_i32 + typed_i32 + typed_i32 + typed_i32` | arg0:typed_i32, arg1:typed_i32, arg2:typed_i32, arg3:typed_i32, arg4:typed_i32 | handler=sub_411410; return_flag=1; aux=0 | 命令名来自命令表 `0x53AA68: 0x53C580 -> SetMapObjMove, opcode=71`；参数描述表 `0x53B0F7`；运行分发见 `sub_4101C0`。 |
| `0x0048` | `SetMapObjZoom` | `48 00` | dynamic / `<u16 opcode> + typed_i32 + typed_i32` | arg0:typed_i32, arg1:typed_i32 | handler=sub_411450; return_flag=1; aux=0 | 命令名来自命令表 `0x53AA70: 0x53C570 -> SetMapObjZoom, opcode=72`；参数描述表 `0x53B108`；运行分发见 `sub_4101C0`。 |
| `0x0049` | `SetMapObjParam` | `49 00` | dynamic / `<u16 opcode> + typed_i32 + typed_i32 + typed_i32` | arg0:typed_i32, arg1:typed_i32, arg2:typed_i32 | handler=sub_411480; return_flag=1; aux=0 | 命令名来自命令表 `0x53AA78: 0x53C560 -> SetMapObjParam, opcode=73`；参数描述表 `0x53B119`；运行分发见 `sub_4101C0`。 |
| `0x004A` | `PlayMapObj` | `4A 00` | dynamic / `<u16 opcode> + typed_i32 + typed_i32 + typed_i32 + typed_i32` | arg0:typed_i32, arg1:typed_i32, arg2:typed_i32, arg3:typed_i32 | handler=sub_4114B0; return_flag=1; aux=0 | 命令名来自命令表 `0x53AA80: 0x53C554 -> PlayMapObj, opcode=74`；参数描述表 `0x53B12A`；运行分发见 `sub_4101C0`。 |
| `0x004B` | `ResetMapObj` | `4B 00` | dynamic / `<u16 opcode> + typed_i32 + typed_i32` | arg0:typed_i32, arg1:typed_i32 | handler=sub_4114F0; return_flag=1; aux=1 | 命令名来自命令表 `0x53AA88: 0x53C548 -> ResetMapObj, opcode=75`；参数描述表 `0x53B13B`；运行分发见 `sub_4101C0`。 |
| `0x004C` | `SetBrightMap` | `4C 00` | dynamic / `<u16 opcode> + typed_i32 + typed_i32 + typed_i32 + typed_i32 + typed_i32` | arg0:typed_i32, arg1:typed_i32, arg2:typed_i32, arg3:typed_i32, arg4:typed_i32 | handler=sub_411530; return_flag=1; aux=2 | 命令名来自命令表 `0x53AA90: 0x53C538 -> SetBrightMap, opcode=76`；参数描述表 `0x53B14C`；运行分发见 `sub_4101C0`。 |
| `0x004D` | `SetScrollMap` | `4D 00` | dynamic / `<u16 opcode> + typed_i32 + typed_i32 + typed_i32 + typed_i32 + typed_i32` | arg0:typed_i32, arg1:typed_i32, arg2:typed_i32, arg3:typed_i32, arg4:typed_i32 | handler=sub_411590; return_flag=1; aux=3 | 命令名来自命令表 `0x53AA98: 0x53C528 -> SetScrollMap, opcode=77`；参数描述表 `0x53B15D`；运行分发见 `sub_4101C0`。 |
| `0x004E` | `SetScrollMapChar` | `4E 00` | dynamic / `<u16 opcode> + typed_i32 + typed_i32 + typed_i32 + typed_i32` | arg0:typed_i32, arg1:typed_i32, arg2:typed_i32, arg3:typed_i32 | handler=sub_411600; return_flag=1; aux=3 | 命令名来自命令表 `0x53AAA0: 0x53C514 -> SetScrollMapChar, opcode=78`；参数描述表 `0x53B16E`；运行分发见 `sub_4101C0`。 |
| `0x004F` | `WaitMap` | `4F 00` | dynamic / `<u16 opcode> + typed_i32` | arg0:typed_i32 | handler=sub_411660; return_flag=0; aux=1 | 命令名来自命令表 `0x53AAA8: 0x53C50C -> WaitMap, opcode=79`；参数描述表 `0x53B17F`；运行分发见 `sub_4101C0`。 |
| `0x0050` | `StartBattle` | `50 00` | dynamic / `<u16 opcode> + typed_i32 + typed_i32 + typed_i32 + typed_i32 + typed_i32 + typed_i32 + typed_i32` | arg0:typed_i32, arg1:typed_i32, arg2:typed_i32, arg3:typed_i32, arg4:typed_i32, arg5:typed_i32, arg6:typed_i32 | handler=sub_4116B0; return_flag=1; aux=5 | 命令名来自命令表 `0x53AAB0: 0x53C500 -> StartBattle, opcode=80`；参数描述表 `0x53B190`；运行分发见 `sub_4101C0`。 |
| `0x0051` | `WaitBattleEnd` | `51 00` | 2 bytes / `<u16 opcode>` | none | handler=sub_411750; return_flag=0; aux=0 | 命令名来自命令表 `0x53AAB8: 0x53C4F0 -> WaitBattleEnd, opcode=81`；参数描述表 `0x53B1A1`；运行分发见 `sub_4101C0`。 |
| `0x0052` | `WaitBattleEndEx` | `52 00` | dynamic / `<u16 opcode> + out_local` | arg0:out_local | handler=sub_411790; return_flag=0; aux=0 | 命令名来自命令表 `0x53AAC0: 0x53C4E0 -> WaitBattleEndEx, opcode=82`；参数描述表 `0x53B1B2`；运行分发见 `sub_4101C0`。 |
| `0x0053` | `SetMapCharPlayer` | `53 00` | dynamic / `<u16 opcode> + typed_i32 + typed_i32 + typed_i32 + typed_i32 + typed_i32` | arg0:typed_i32, arg1:typed_i32, arg2:typed_i32, arg3:typed_i32, arg4:typed_i32 | handler=sub_4117E0; return_flag=1; aux=1 | 命令名来自命令表 `0x53AAC8: 0x53C4CC -> SetMapCharPlayer, opcode=83`；参数描述表 `0x53B1C3`；运行分发见 `sub_4101C0`。 |
| `0x0054` | `SetMapChar` | `54 00` | dynamic / `<u16 opcode> + typed_i32 + typed_i32 + typed_i32 + typed_i32 + typed_i32 + typed_i32 + typed_i32 + typed_i32 + typed_i32` | arg0:typed_i32, arg1:typed_i32, arg2:typed_i32, arg3:typed_i32, arg4:typed_i32, arg5:typed_i32, arg6:typed_i32, arg7:typed_i32, arg8:typed_i32 | handler=sub_411830; return_flag=1; aux=3 | 命令名来自命令表 `0x53AAD0: 0x53C4C0 -> SetMapChar, opcode=84`；参数描述表 `0x53B1D4`；运行分发见 `sub_4101C0`。 |
| `0x0055` | `SetMapCharEngun` | `55 00` | dynamic / `<u16 opcode> + typed_i32 + typed_i32 + typed_i32 + typed_i32` | arg0:typed_i32, arg1:typed_i32, arg2:typed_i32, arg3:typed_i32 | handler=sub_4118E0; return_flag=1; aux=1 | 命令名来自命令表 `0x53AAD8: 0x53C4B0 -> SetMapCharEngun, opcode=85`；参数描述表 `0x53B1E5`；运行分发见 `sub_4101C0`。 |
| `0x0056` | `SetMapCharItem` | `56 00` | dynamic / `<u16 opcode> + typed_i32 + typed_i32 + typed_i32` | arg0:typed_i32, arg1:typed_i32, arg2:typed_i32 | handler=sub_411920; return_flag=1; aux=0 | 命令名来自命令表 `0x53AAE0: 0x53C4A0 -> SetMapCharItem, opcode=86`；参数描述表 `0x53B1F6`；运行分发见 `sub_4101C0`。 |
| `0x0057` | `SetMapCharThink` | `57 00` | dynamic / `<u16 opcode> + typed_i32 + typed_i32 + typed_i32 + typed_i32 + typed_i32 + typed_i32` | arg0:typed_i32, arg1:typed_i32, arg2:typed_i32, arg3:typed_i32, arg4:typed_i32, arg5:typed_i32 | handler=sub_411950; return_flag=1; aux=3 | 命令名来自命令表 `0x53AAE8: 0x53C490 -> SetMapCharThink, opcode=87`；参数描述表 `0x53B207`；运行分发见 `sub_4101C0`。 |
| `0x0058` | `ResetMapChar` | `58 00` | dynamic / `<u16 opcode> + typed_i32` | arg0:typed_i32 | handler=sub_4119A0; return_flag=1; aux=0 | 命令名来自命令表 `0x53AAF0: 0x53C480 -> ResetMapChar, opcode=88`；参数描述表 `0x53B218`；运行分发见 `sub_4101C0`。 |
| `0x0059` | `ResetMapCharAll` | `59 00` | 2 bytes / `<u16 opcode>` | none | handler=sub_4119D0; return_flag=1; aux=0 | 命令名来自命令表 `0x53AAF8: 0x53C470 -> ResetMapCharAll, opcode=89`；参数描述表 `0x53B229`；运行分发见 `sub_4101C0`。 |
| `0x005A` | `SetMapCharEvent` | `5A 00` | dynamic / `<u16 opcode> + typed_i32 + typed_i32 + typed_i32 + typed_i32` | arg0:typed_i32, arg1:typed_i32, arg2:typed_i32, arg3:typed_i32 | handler=sub_4119F0; return_flag=1; aux=2 | 命令名来自命令表 `0x53AB00: 0x53C460 -> SetMapCharEvent, opcode=90`；参数描述表 `0x53B23A`；运行分发见 `sub_4101C0`。 |
| `0x005B` | `WaitMapCharEvent` | `5B 00` | dynamic / `<u16 opcode> + typed_i32` | arg0:typed_i32 | handler=sub_411A40; return_flag=0; aux=0 | 命令名来自命令表 `0x53AB08: 0x53C44C -> WaitMapCharEvent, opcode=91`；参数描述表 `0x53B24B`；运行分发见 `sub_4101C0`。 |
| `0x005C` | `SetMapCharMove` | `5C 00` | dynamic / `<u16 opcode> + typed_i32 + typed_i32 + typed_i32 + typed_i32 + typed_i32 + typed_i32` | arg0:typed_i32, arg1:typed_i32, arg2:typed_i32, arg3:typed_i32, arg4:typed_i32, arg5:typed_i32 | handler=sub_411A70; return_flag=1; aux=3 | 命令名来自命令表 `0x53AB10: 0x53C43C -> SetMapCharMove, opcode=92`；参数描述表 `0x53B25C`；运行分发见 `sub_4101C0`。 |
| `0x005D` | `WaitMapCharMove` | `5D 00` | dynamic / `<u16 opcode> + typed_i32` | arg0:typed_i32 | handler=sub_411AE0; return_flag=0; aux=0 | 命令名来自命令表 `0x53AB18: 0x53C42C -> WaitMapCharMove, opcode=93`；参数描述表 `0x53B26D`；运行分发见 `sub_4101C0`。 |
| `0x005E` | `SetMapCharDisp` | `5E 00` | dynamic / `<u16 opcode> + typed_i32 + typed_i32` | arg0:typed_i32, arg1:typed_i32 | handler=sub_411B10; return_flag=1; aux=0 | 命令名来自命令表 `0x53AB20: 0x53C41C -> SetMapCharDisp, opcode=94`；参数描述表 `0x53B27E`；运行分发见 `sub_4101C0`。 |
| `0x005F` | `B` | `5F 00` | dynamic / `<u16 opcode> + typed_i32 + typed_i32 + typed_i32 + typed_i32 + typed_i32 + typed_i32 + typed_i32 + typed_i32 + typed_i32` | arg0:typed_i32, arg1:typed_i32, arg2:typed_i32, arg3:typed_i32, arg4:typed_i32, arg5:typed_i32, arg6:typed_i32, arg7:typed_i32, arg8:typed_i32 | handler=sub_411BF0; return_flag=0; aux=7 | 命令名来自命令表 `0x53AB28: 0x53C418 -> B, opcode=95`；参数描述表 `0x53B28F`；运行分发见 `sub_4101C0`。 |
| `0x0060` | `BT` | `60 00` | dynamic / `<u16 opcode> + typed_i32 + typed_i32 + typed_i32 + typed_i32 + typed_i32 + typed_i32 + typed_i32 + typed_i32 + typed_i32` | arg0:typed_i32, arg1:typed_i32, arg2:typed_i32, arg3:typed_i32, arg4:typed_i32, arg5:typed_i32, arg6:typed_i32, arg7:typed_i32, arg8:typed_i32 | handler=nullsub_1; return_flag=0; aux=7 | 命令名来自命令表 `0x53AB30: 0x53C414 -> BT, opcode=96`；参数描述表 `0x53B2A0`；运行分发见 `sub_4101C0`。 |
| `0x0061` | `BC` | `61 00` | dynamic / `<u16 opcode> + typed_i32 + typed_i32 + typed_i32 + typed_i32 + typed_i32 + typed_i32 + typed_i32 + typed_i32 + typed_i32` | arg0:typed_i32, arg1:typed_i32, arg2:typed_i32, arg3:typed_i32, arg4:typed_i32, arg5:typed_i32, arg6:typed_i32, arg7:typed_i32, arg8:typed_i32 | handler=sub_411CF0; return_flag=0; aux=7 | 命令名来自命令表 `0x53AB38: 0x53C410 -> BC, opcode=97`；参数描述表 `0x53B2B1`；运行分发见 `sub_4101C0`。 |
| `0x0062` | `BCT` | `62 00` | dynamic / `<u16 opcode> + typed_i32 + typed_i32 + typed_i32 + typed_i32 + typed_i32 + typed_i32 + typed_i32 + typed_i32 + typed_i32` | arg0:typed_i32, arg1:typed_i32, arg2:typed_i32, arg3:typed_i32, arg4:typed_i32, arg5:typed_i32, arg6:typed_i32, arg7:typed_i32, arg8:typed_i32 | handler=nullsub_2; return_flag=0; aux=7 | 命令名来自命令表 `0x53AB40: 0x53C40C -> BCT, opcode=98`；参数描述表 `0x53B2C2`；运行分发见 `sub_4101C0`。 |
| `0x0063` | `V` | `63 00` | dynamic / `<u16 opcode> + typed_i32 + typed_i32 + typed_i32 + typed_i32 + typed_i32 + typed_i32 + typed_i32 + typed_i32 + typed_i32` | arg0:typed_i32, arg1:typed_i32, arg2:typed_i32, arg3:typed_i32, arg4:typed_i32, arg5:typed_i32, arg6:typed_i32, arg7:typed_i32, arg8:typed_i32 | handler=sub_411DF0; return_flag=0; aux=7 | 命令名来自命令表 `0x53AB48: 0x53C408 -> V, opcode=99`；参数描述表 `0x53B2D3`；运行分发见 `sub_4101C0`。 |
| `0x0064` | `VT` | `64 00` | dynamic / `<u16 opcode> + typed_i32 + typed_i32 + typed_i32 + typed_i32 + typed_i32 + typed_i32 + typed_i32 + typed_i32 + typed_i32` | arg0:typed_i32, arg1:typed_i32, arg2:typed_i32, arg3:typed_i32, arg4:typed_i32, arg5:typed_i32, arg6:typed_i32, arg7:typed_i32, arg8:typed_i32 | handler=nullsub_3; return_flag=0; aux=7 | 命令名来自命令表 `0x53AB50: 0x53C404 -> VT, opcode=100`；参数描述表 `0x53B2E4`；运行分发见 `sub_4101C0`。 |
| `0x0065` | `H` | `65 00` | dynamic / `<u16 opcode> + typed_i32 + typed_i32 + typed_i32 + typed_i32 + typed_i32 + typed_i32 + typed_i32 + typed_i32 + typed_i32` | arg0:typed_i32, arg1:typed_i32, arg2:typed_i32, arg3:typed_i32, arg4:typed_i32, arg5:typed_i32, arg6:typed_i32, arg7:typed_i32, arg8:typed_i32 | handler=sub_411EF0; return_flag=0; aux=7 | 命令名来自命令表 `0x53AB58: 0x53C400 -> H, opcode=101`；参数描述表 `0x53B2F5`；运行分发见 `sub_4101C0`。 |
| `0x0066` | `HT` | `66 00` | dynamic / `<u16 opcode> + typed_i32 + typed_i32 + typed_i32 + typed_i32 + typed_i32 + typed_i32 + typed_i32 + typed_i32 + typed_i32` | arg0:typed_i32, arg1:typed_i32, arg2:typed_i32, arg3:typed_i32, arg4:typed_i32, arg5:typed_i32, arg6:typed_i32, arg7:typed_i32, arg8:typed_i32 | handler=nullsub_4; return_flag=0; aux=7 | 命令名来自命令表 `0x53AB60: 0x53C3FC -> HT, opcode=102`；参数描述表 `0x53B306`；运行分发见 `sub_4101C0`。 |
| `0x0067` | `S` | `67 00` | dynamic / `<u16 opcode> + typed_i32 + typed_i32 + typed_i32 + typed_i32` | arg0:typed_i32, arg1:typed_i32, arg2:typed_i32, arg3:typed_i32 | handler=nullsub_5; return_flag=0; aux=0 | 命令名来自命令表 `0x53AB68: 0x53C3F8 -> S, opcode=103`；参数描述表 `0x53B317`；运行分发见 `sub_4101C0`。 |
| `0x0068` | `Z` | `68 00` | dynamic / `<u16 opcode> + typed_i32 + typed_i32 + typed_i32 + typed_i32 + typed_i32 + typed_i32` | arg0:typed_i32, arg1:typed_i32, arg2:typed_i32, arg3:typed_i32, arg4:typed_i32, arg5:typed_i32 | handler=nullsub_6; return_flag=0; aux=0 | 命令名来自命令表 `0x53AB70: 0x53C3F4 -> Z, opcode=104`；参数描述表 `0x53B328`；运行分发见 `sub_4101C0`。 |
| `0x0069` | `FI` | `69 00` | 2 bytes / `<u16 opcode>` | none | handler=default/no explicit handler; return_flag=0; aux=0 | 命令名来自命令表 `0x53AB78: 0x53C3F0 -> FI, opcode=105`；参数描述表 `0x53B339`；运行分发见 `sub_4101C0`。 |
| `0x006A` | `FIF` | `6A 00` | dynamic / `<u16 opcode> + typed_i32` | arg0:typed_i32 | handler=default/no explicit handler; return_flag=0; aux=0 | 命令名来自命令表 `0x53AB80: 0x53C3EC -> FIF, opcode=106`；参数描述表 `0x53B34A`；运行分发见 `sub_4101C0`。 |
| `0x006B` | `FO` | `6B 00` | 2 bytes / `<u16 opcode>` | none | handler=default/no explicit handler; return_flag=0; aux=0 | 命令名来自命令表 `0x53AB88: 0x53C3E8 -> FO, opcode=107`；参数描述表 `0x53B35B`；运行分发见 `sub_4101C0`。 |
| `0x006C` | `FOF` | `6C 00` | dynamic / `<u16 opcode> + typed_i32` | arg0:typed_i32 | handler=default/no explicit handler; return_flag=0; aux=0 | 命令名来自命令表 `0x53AB90: 0x53C3E4 -> FOF, opcode=108`；参数描述表 `0x53B36C`；运行分发见 `sub_4101C0`。 |
| `0x006D` | `FB` | `6D 00` | dynamic / `<u16 opcode> + typed_i32 + typed_i32 + typed_i32 + typed_i32` | arg0:typed_i32, arg1:typed_i32, arg2:typed_i32, arg3:typed_i32 | handler=default/no explicit handler; return_flag=0; aux=0 | 命令名来自命令表 `0x53AB98: 0x53C3E0 -> FB, opcode=109`；参数描述表 `0x53B37D`；运行分发见 `sub_4101C0`。 |
| `0x006E` | `PFI` | `6E 00` | dynamic / `<u16 opcode> + typed_i32 + typed_i32 + typed_i32 + typed_i32 + typed_i32 + typed_i32` | arg0:typed_i32, arg1:typed_i32, arg2:typed_i32, arg3:typed_i32, arg4:typed_i32, arg5:typed_i32 | handler=default/no explicit handler; return_flag=0; aux=2 | 命令名来自命令表 `0x53ABA0: 0x53C3DC -> PFI, opcode=110`；参数描述表 `0x53B38E`；运行分发见 `sub_4101C0`。 |
| `0x006F` | `PFO` | `6F 00` | dynamic / `<u16 opcode> + typed_i32 + typed_i32 + typed_i32 + typed_i32 + typed_i32 + typed_i32` | arg0:typed_i32, arg1:typed_i32, arg2:typed_i32, arg3:typed_i32, arg4:typed_i32, arg5:typed_i32 | handler=default/no explicit handler; return_flag=0; aux=2 | 命令名来自命令表 `0x53ABA8: 0x53C3D8 -> PFO, opcode=111`；参数描述表 `0x53B39F`；运行分发见 `sub_4101C0`。 |
| `0x0070` | `PWI` | `70 00` | dynamic / `<u16 opcode> + typed_i32 + typed_i32 + typed_i32 + typed_i32 + typed_i32 + typed_i32` | arg0:typed_i32, arg1:typed_i32, arg2:typed_i32, arg3:typed_i32, arg4:typed_i32, arg5:typed_i32 | handler=default/no explicit handler; return_flag=0; aux=2 | 命令名来自命令表 `0x53ABB0: 0x53C3D4 -> PWI, opcode=112`；参数描述表 `0x53B3B0`；运行分发见 `sub_4101C0`。 |
| `0x0071` | `PWO` | `71 00` | dynamic / `<u16 opcode> + typed_i32 + typed_i32 + typed_i32 + typed_i32 + typed_i32 + typed_i32` | arg0:typed_i32, arg1:typed_i32, arg2:typed_i32, arg3:typed_i32, arg4:typed_i32, arg5:typed_i32 | handler=default/no explicit handler; return_flag=0; aux=2 | 命令名来自命令表 `0x53ABB8: 0x53C3D0 -> PWO, opcode=113`；参数描述表 `0x53B3C1`；运行分发见 `sub_4101C0`。 |
| `0x0072` | `Q` | `72 00` | dynamic / `<u16 opcode> + typed_i32 + typed_i32 + typed_i32 + typed_i32 + typed_i32` | arg0:typed_i32, arg1:typed_i32, arg2:typed_i32, arg3:typed_i32, arg4:typed_i32 | handler=sub_412030; return_flag=0; aux=0 | 命令名来自命令表 `0x53ABC0: 0x53C3CC -> Q, opcode=114`；参数描述表 `0x53B3D2`；运行分发见 `sub_4101C0`。 |
| `0x0073` | `F` | `73 00` | dynamic / `<u16 opcode> + typed_i32 + typed_i32 + typed_i32 + typed_i32 + typed_i32` | arg0:typed_i32, arg1:typed_i32, arg2:typed_i32, arg3:typed_i32, arg4:typed_i32 | handler=default/no explicit handler; return_flag=0; aux=0 | 命令名来自命令表 `0x53ABC8: 0x53C3C8 -> F, opcode=115`；参数描述表 `0x53B3E3`；运行分发见 `sub_4101C0`。 |
| `0x0074` | `C` | `74 00` | dynamic / `<u16 opcode> + typed_i32 + typed_i32 + typed_i32 + typed_i32 + typed_i32 + typed_i32 + typed_i32 + typed_i32` | arg0:typed_i32, arg1:typed_i32, arg2:typed_i32, arg3:typed_i32, arg4:typed_i32, arg5:typed_i32, arg6:typed_i32, arg7:typed_i32 | handler=sub_412090; return_flag=0; aux=7 | 命令名来自命令表 `0x53ABD0: 0x53C3C4 -> C, opcode=116`；参数描述表 `0x53B3F4`；运行分发见 `sub_4101C0`。 |
| `0x0075` | `CR` | `75 00` | dynamic / `<u16 opcode> + typed_i32 + typed_i32 + typed_i32` | arg0:typed_i32, arg1:typed_i32, arg2:typed_i32 | handler=sub_412150; return_flag=0; aux=2 | 命令名来自命令表 `0x53ABD8: 0x53C3C0 -> CR, opcode=117`；参数描述表 `0x53B405`；运行分发见 `sub_4101C0`。 |
| `0x0076` | `CP` | `76 00` | dynamic / `<u16 opcode> + typed_i32 + typed_i32 + typed_i32` | arg0:typed_i32, arg1:typed_i32, arg2:typed_i32 | handler=sub_4121F0; return_flag=0; aux=1 | 命令名来自命令表 `0x53ABE0: 0x53C3BC -> CP, opcode=118`；参数描述表 `0x53B416`；运行分发见 `sub_4101C0`。 |
| `0x0077` | `CL` | `77 00` | dynamic / `<u16 opcode> + typed_i32 + typed_i32 + typed_i32` | arg0:typed_i32, arg1:typed_i32, arg2:typed_i32 | handler=sub_412260; return_flag=0; aux=1 | 命令名来自命令表 `0x53ABE8: 0x53C3B8 -> CL, opcode=119`；参数描述表 `0x53B427`；运行分发见 `sub_4101C0`。 |
| `0x0078` | `CY` | `78 00` | dynamic / `<u16 opcode> + typed_i32 + typed_i32` | arg0:typed_i32, arg1:typed_i32 | handler=sub_4122D0; return_flag=0; aux=0 | 命令名来自命令表 `0x53ABF0: 0x53C3B4 -> CY, opcode=120`；参数描述表 `0x53B438`；运行分发见 `sub_4101C0`。 |
| `0x0079` | `CB` | `79 00` | dynamic / `<u16 opcode> + typed_i32 + typed_i32 + typed_i32 + typed_i32 + typed_i32` | arg0:typed_i32, arg1:typed_i32, arg2:typed_i32, arg3:typed_i32, arg4:typed_i32 | handler=sub_412320; return_flag=0; aux=0 | 命令名来自命令表 `0x53ABF8: 0x53C3B0 -> CB, opcode=121`；参数描述表 `0x53B449`；运行分发见 `sub_4101C0`。 |
| `0x007A` | `CA` | `7A 00` | dynamic / `<u16 opcode> + typed_i32 + typed_i32 + typed_i32` | arg0:typed_i32, arg1:typed_i32, arg2:typed_i32 | handler=sub_412390; return_flag=0; aux=0 | 命令名来自命令表 `0x53AC00: 0x53C3AC -> CA, opcode=122`；参数描述表 `0x53B45A`；运行分发见 `sub_4101C0`。 |
| `0x007B` | `CW` | `7B 00` | dynamic / `<u16 opcode> + typed_i32` | arg0:typed_i32 | handler=sub_4123F0; return_flag=0; aux=0 | 命令名来自命令表 `0x53AC08: 0x53C3A8 -> CW, opcode=123`；参数描述表 `0x53B46B`；运行分发见 `sub_4101C0`。 |
| `0x007C` | `W` | `7C 00` | dynamic / `<u16 opcode> + typed_i32 + typed_i32` | arg0:typed_i32, arg1:typed_i32 | handler=sub_412430; return_flag=1; aux=2 | 命令名来自命令表 `0x53AC10: 0x53C3A4 -> W, opcode=124`；参数描述表 `0x53B47C`；运行分发见 `sub_4101C0`。 |
| `0x007D` | `WR` | `7D 00` | dynamic / `<u16 opcode> + typed_i32 + typed_i32` | arg0:typed_i32, arg1:typed_i32 | handler=sub_4124B0; return_flag=1; aux=2 | 命令名来自命令表 `0x53AC18: 0x53C3A0 -> WR, opcode=125`；参数描述表 `0x53B48D`；运行分发见 `sub_4101C0`。 |
| `0x007E` | `WN` | `7E 00` | dynamic / `<u16 opcode> + str8` | arg0:str8 | handler=sub_412510; return_flag=1; aux=1 | 命令名来自命令表 `0x53AC20: 0x53C39C -> WN, opcode=126`；参数描述表 `0x53B49E`；运行分发见 `sub_4101C0`。 |
| `0x007F` | `KW` | `7F 00` | dynamic / `<u16 opcode> + typed_i32` | arg0:typed_i32 | handler=default/no explicit handler; return_flag=1; aux=0 | 命令名来自命令表 `0x53AC28: 0x53C398 -> KW, opcode=127`；参数描述表 `0x53B4AF`；运行分发见 `sub_4101C0`。 |
| `0x0080` | `K` | `80 00` | 2 bytes / `<u16 opcode>` | none | handler=sub_412530; return_flag=0; aux=0 | 命令名来自命令表 `0x53AC30: 0x53C394 -> K, opcode=128`；参数描述表 `0x53B4C0`；运行分发见 `sub_4101C0`。 |
| `0x0081` | `M` | `81 00` | dynamic / `<u16 opcode> + typed_i32 + typed_i32 + typed_i32 + typed_i32` | arg0:typed_i32, arg1:typed_i32, arg2:typed_i32, arg3:typed_i32 | handler=sub_412550; return_flag=1; aux=3 | 命令名来自命令表 `0x53AC38: 0x53C390 -> M, opcode=129`；参数描述表 `0x53B4D1`；运行分发见 `sub_4101C0`。 |
| `0x0082` | `MS` | `82 00` | dynamic / `<u16 opcode> + typed_i32` | arg0:typed_i32 | handler=sub_4125C0; return_flag=1; aux=1 | 命令名来自命令表 `0x53AC40: 0x53C38C -> MS, opcode=130`；参数描述表 `0x53B4E2`；运行分发见 `sub_4101C0`。 |
| `0x0083` | `MP` | `83 00` | dynamic / `<u16 opcode> + typed_i32` | arg0:typed_i32 | handler=sub_4125F0; return_flag=1; aux=0 | 命令名来自命令表 `0x53AC48: 0x53C388 -> MP, opcode=131`；参数描述表 `0x53B4F3`；运行分发见 `sub_4101C0`。 |
| `0x0084` | `MV` | `84 00` | dynamic / `<u16 opcode> + typed_i32 + typed_i32` | arg0:typed_i32, arg1:typed_i32 | handler=sub_412610; return_flag=1; aux=0 | 命令名来自命令表 `0x53AC50: 0x53C384 -> MV, opcode=132`；参数描述表 `0x53B504`；运行分发见 `sub_4101C0`。 |
| `0x0085` | `MW` | `85 00` | 2 bytes / `<u16 opcode>` | none | handler=sub_412640; return_flag=0; aux=0 | 命令名来自命令表 `0x53AC58: 0x53C380 -> MW, opcode=133`；参数描述表 `0x53B515`；运行分发见 `sub_4101C0`。 |
| `0x0086` | `SE` | `86 00` | dynamic / `<u16 opcode> + typed_i32 + typed_i32` | arg0:typed_i32, arg1:typed_i32 | handler=sub_412680; return_flag=1; aux=1 | 命令名来自命令表 `0x53AC60: 0x53C37C -> SE, opcode=134`；参数描述表 `0x53B526`；运行分发见 `sub_4101C0`。 |
| `0x0087` | `SEP` | `87 00` | dynamic / `<u16 opcode> + typed_i32 + typed_i32 + typed_i32 + typed_i32 + typed_i32` | arg0:typed_i32, arg1:typed_i32, arg2:typed_i32, arg3:typed_i32, arg4:typed_i32 | handler=sub_4126C0; return_flag=1; aux=3 | 命令名来自命令表 `0x53AC68: 0x53C378 -> SEP, opcode=135`；参数描述表 `0x53B537`；运行分发见 `sub_4101C0`。 |
| `0x0088` | `SES` | `88 00` | dynamic / `<u16 opcode> + typed_i32 + typed_i32` | arg0:typed_i32, arg1:typed_i32 | handler=sub_412730; return_flag=1; aux=1 | 命令名来自命令表 `0x53AC70: 0x53C374 -> SES, opcode=136`；参数描述表 `0x53B548`；运行分发见 `sub_4101C0`。 |
| `0x0089` | `SEW` | `89 00` | dynamic / `<u16 opcode> + typed_i32` | arg0:typed_i32 | handler=sub_412790; return_flag=0; aux=0 | 命令名来自命令表 `0x53AC78: 0x53C370 -> SEW, opcode=137`；参数描述表 `0x53B559`；运行分发见 `sub_4101C0`。 |
| `0x008A` | `SEV` | `8A 00` | dynamic / `<u16 opcode> + typed_i32 + typed_i32 + typed_i32` | arg0:typed_i32, arg1:typed_i32, arg2:typed_i32 | handler=sub_412760; return_flag=1; aux=0 | 命令名来自命令表 `0x53AC80: 0x53C36C -> SEV, opcode=138`；参数描述表 `0x53B56A`；运行分发见 `sub_4101C0`。 |
| `0x008B` | `SEVW` | `8B 00` | dynamic / `<u16 opcode> + typed_i32` | arg0:typed_i32 | handler=sub_4127C0; return_flag=0; aux=0 | 命令名来自命令表 `0x53AC88: 0x53C364 -> SEVW, opcode=139`；参数描述表 `0x53B57B`；运行分发见 `sub_4101C0`。 |
| `0x008C` | `VV` | `8C 00` | dynamic / `<u16 opcode> + typed_i32 + typed_i32 + typed_i32 + typed_i32 + u16_alt` | arg0:typed_i32, arg1:typed_i32, arg2:typed_i32, arg3:typed_i32, arg4:u16_alt | handler=sub_4127F0; return_flag=1; aux=5 | 命令名来自命令表 `0x53AC90: 0x53C360 -> VV, opcode=140`；参数描述表 `0x53B58C`；运行分发见 `sub_4101C0`。 |
| `0x008D` | `VA` | `8D 00` | dynamic / `<u16 opcode> + typed_i32 + typed_i32 + typed_i32 + typed_i32 + u16_alt` | arg0:typed_i32, arg1:typed_i32, arg2:typed_i32, arg3:typed_i32, arg4:u16_alt | handler=sub_412860; return_flag=1; aux=5 | 命令名来自命令表 `0x53AC98: 0x53C35C -> VA, opcode=141`；参数描述表 `0x53B59D`；运行分发见 `sub_4101C0`。 |
| `0x008E` | `VB` | `8E 00` | dynamic / `<u16 opcode> + typed_i32 + typed_i32 + typed_i32 + typed_i32 + u16_alt` | arg0:typed_i32, arg1:typed_i32, arg2:typed_i32, arg3:typed_i32, arg4:u16_alt | handler=sub_4128D0; return_flag=1; aux=5 | 命令名来自命令表 `0x53ACA0: 0x53C358 -> VB, opcode=142`；参数描述表 `0x53B5AE`；运行分发见 `sub_4101C0`。 |
| `0x008F` | `VC` | `8F 00` | dynamic / `<u16 opcode> + typed_i32 + typed_i32 + typed_i32 + typed_i32 + u16_alt` | arg0:typed_i32, arg1:typed_i32, arg2:typed_i32, arg3:typed_i32, arg4:u16_alt | handler=sub_412940; return_flag=1; aux=5 | 命令名来自命令表 `0x53ACA8: 0x53C354 -> VC, opcode=143`；参数描述表 `0x53B5BF`；运行分发见 `sub_4101C0`。 |
| `0x0090` | `VX` | `90 00` | dynamic / `<u16 opcode> + typed_i32 + typed_i32 + typed_i32 + typed_i32 + typed_i32 + typed_i32` | arg0:typed_i32, arg1:typed_i32, arg2:typed_i32, arg3:typed_i32, arg4:typed_i32, arg5:typed_i32 | handler=sub_4129B0; return_flag=1; aux=3 | 命令名来自命令表 `0x53ACB0: 0x53C350 -> VX, opcode=144`；参数描述表 `0x53B5D0`；运行分发见 `sub_4101C0`。 |
| `0x0091` | `VW` | `91 00` | 2 bytes / `<u16 opcode>` | none | handler=sub_412A20; return_flag=0; aux=1 | 命令名来自命令表 `0x53ACB8: 0x53C34C -> VW, opcode=145`；参数描述表 `0x53B5E1`；运行分发见 `sub_4101C0`。 |
| `0x0092` | `VS` | `92 00` | dynamic / `<u16 opcode> + typed_i32 + typed_i32` | arg0:typed_i32, arg1:typed_i32 | handler=sub_412A50; return_flag=1; aux=1 | 命令名来自命令表 `0x53ACC0: 0x53C348 -> VS, opcode=146`；参数描述表 `0x53B5F2`；运行分发见 `sub_4101C0`。 |
| `0x0093` | `VI` | `93 00` | dynamic / `<u16 opcode> + u16_alt + typed_i32` | arg0:u16_alt, arg1:typed_i32 | handler=sub_412AB0; return_flag=1; aux=2 | 命令名来自命令表 `0x53ACC8: 0x53C344 -> VI, opcode=147`；参数描述表 `0x53B603`；运行分发见 `sub_4101C0`。 |
| `0x0094` | `R` | `94 00` | dynamic / `<u16 opcode> + typed_i32 + typed_i32 + typed_i32` | arg0:typed_i32, arg1:typed_i32, arg2:typed_i32 | handler=default/no explicit handler; return_flag=0; aux=0 | 命令名来自命令表 `0x53ACD0: 0x53C340 -> R, opcode=148`；参数描述表 `0x53B614`；运行分发见 `sub_4101C0`。 |
| `0x0095` | `RC` | `95 00` | dynamic / `<u16 opcode> + typed_i32 + typed_i32 + typed_i32` | arg0:typed_i32, arg1:typed_i32, arg2:typed_i32 | handler=default/no explicit handler; return_flag=0; aux=0 | 命令名来自命令表 `0x53ACD8: 0x53C33C -> RC, opcode=149`；参数描述表 `0x53B625`；运行分发见 `sub_4101C0`。 |
| `0x0096` | `RR` | `96 00` | 2 bytes / `<u16 opcode>` | none | handler=default/no explicit handler; return_flag=0; aux=0 | 命令名来自命令表 `0x53ACE0: 0x53C338 -> RR, opcode=150`；参数描述表 `0x53B636`；运行分发见 `sub_4101C0`。 |
| `0x0097` | `LF` | `97 00` | dynamic / `<u16 opcode> + typed_i32 + typed_i32 + typed_i32` | arg0:typed_i32, arg1:typed_i32, arg2:typed_i32 | handler=default/no explicit handler; return_flag=1; aux=0 | 命令名来自命令表 `0x53ACE8: 0x53C334 -> LF, opcode=151`；参数描述表 `0x53B647`；运行分发见 `sub_4101C0`。 |
| `0x0098` | `WE` | `98 00` | dynamic / `<u16 opcode> + typed_i32 + typed_i32 + typed_i32` | arg0:typed_i32, arg1:typed_i32, arg2:typed_i32 | handler=default/no explicit handler; return_flag=0; aux=1 | 命令名来自命令表 `0x53ACF0: 0x53C330 -> WE, opcode=152`；参数描述表 `0x53B658`；运行分发见 `sub_4101C0`。 |
| `0x0099` | `WER` | `99 00` | 2 bytes / `<u16 opcode>` | none | handler=default/no explicit handler; return_flag=1; aux=0 | 命令名来自命令表 `0x53ACF8: 0x53C32C -> WER, opcode=153`；参数描述表 `0x53B669`；运行分发见 `sub_4101C0`。 |
| `0x009A` | `SetFlag` | `9A 00` | dynamic / `<u16 opcode> + typed_i32 + typed_i32` | arg0:typed_i32, arg1:typed_i32 | handler=sub_410FB0; return_flag=1; aux=0 | 命令名来自命令表 `0x53AD00: 0x53C324 -> SetFlag, opcode=154`；参数描述表 `0x53B67A`；运行分发见 `sub_4101C0`。 |
| `0x009B` | `GetFlag` | `9B 00` | dynamic / `<u16 opcode> + typed_i32 + out_local` | arg0:typed_i32, arg1:out_local | handler=sub_410FE0; return_flag=1; aux=0 | 命令名来自命令表 `0x53AD08: 0x53C31C -> GetFlag, opcode=155`；参数描述表 `0x53B68B`；运行分发见 `sub_4101C0`。 |
| `0x009C` | `SetGameFlag` | `9C 00` | dynamic / `<u16 opcode> + typed_i32 + typed_i32` | arg0:typed_i32, arg1:typed_i32 | handler=sub_411010; return_flag=1; aux=0 | 命令名来自命令表 `0x53AD10: 0x53C310 -> SetGameFlag, opcode=156`；参数描述表 `0x53B69C`；运行分发见 `sub_4101C0`。 |
| `0x009D` | `GetGameFlag` | `9D 00` | dynamic / `<u16 opcode> + typed_i32 + out_local` | arg0:typed_i32, arg1:out_local | handler=sub_411040; return_flag=1; aux=0 | 命令名来自命令表 `0x53AD18: 0x53C304 -> GetGameFlag, opcode=157`；参数描述表 `0x53B6AD`；运行分发见 `sub_4101C0`。 |
| `0x009E` | `LoadScript` | `9E 00` | dynamic / `<u16 opcode> + str8` | arg0:str8 | handler=sub_411070; return_flag=0; aux=0 | 命令名来自命令表 `0x53AD20: 0x53C2F8 -> LoadScript, opcode=158`；参数描述表 `0x53B6BE`；运行分发见 `sub_4101C0`。 |
| `0x009F` | `GameEnd` | `9F 00` | dynamic / `<u16 opcode> + typed_i32` | arg0:typed_i32 | handler=default/no explicit handler; return_flag=0; aux=1 | 命令名来自命令表 `0x53AD28: 0x53C2F0 -> GameEnd, opcode=159`；参数描述表 `0x53B6CF`；运行分发见 `sub_4101C0`。 |
| `0x00A0` | `CallFunc` | `A0 00` | dynamic / `<u16 opcode> + typed_i32 + typed_i32 + typed_i32 + typed_i32 + typed_i32 + typed_i32 + typed_i32 + typed_i32 + typed_i32 + typed_i32 + typed_i32 + typed_i32 + typed_i32 + typed_i32 + typed_i32` | arg0:typed_i32, arg1:typed_i32, arg2:typed_i32, arg3:typed_i32, arg4:typed_i32, arg5:typed_i32, arg6:typed_i32, arg7:typed_i32, arg8:typed_i32, arg9:typed_i32, arg10:typed_i32, arg11:typed_i32, arg12:typed_i32, arg13:typed_i32, arg14:typed_i32 | handler=sub_4110F0; return_flag=1; aux=14 | 命令名来自命令表 `0x53AD30: 0x53C2E4 -> CallFunc, opcode=160`；参数描述表 `0x53B6E0`；运行分发见 `sub_4101C0`。 |
| `0x00A1` | `SetTimeMode` | `A1 00` | dynamic / `<u16 opcode> + typed_i32` | arg0:typed_i32 | handler=sub_411160; return_flag=1; aux=1 | 命令名来自命令表 `0x53AD38: 0x53C2D8 -> SetTimeMode, opcode=161`；参数描述表 `0x53B6F1`；运行分发见 `sub_4101C0`。 |
| `0x00A2` | `SetChromaMode` | `A2 00` | dynamic / `<u16 opcode> + typed_i32 + typed_i32` | arg0:typed_i32, arg1:typed_i32 | handler=sub_411190; return_flag=1; aux=2 | 命令名来自命令表 `0x53AD40: 0x53C2C8 -> SetChromaMode, opcode=162`；参数描述表 `0x53B702`；运行分发见 `sub_4101C0`。 |
| `0x00A3` | `SetEffctMode` | `A3 00` | dynamic / `<u16 opcode> + str8 + typed_i32` | arg0:str8, arg1:typed_i32 | handler=sub_4111E0; return_flag=1; aux=2 | 命令名来自命令表 `0x53AD48: 0x53C2B8 -> SetEffctMode, opcode=163`；参数描述表 `0x53B713`；运行分发见 `sub_4101C0`。 |
| `0x00A4` | `SetMessage` | `A4 00` | dynamic / `<u16 opcode> + typed_i32 + str8 + u16` | arg0:typed_i32, arg1:str8, arg2:u16 | handler=default/no explicit handler; return_flag=0; aux=0 | 命令名来自命令表 `0x53AD50: 0x53C2AC -> SetMessage, opcode=164`；参数描述表 `0x53B724`；运行分发见 `sub_4101C0`。 |
| `0x00A5` | `SetMessage2` | `A5 00` | dynamic / `<u16 opcode> + str16 + u8_alt + u16` | arg0:str16, arg1:u8_alt, arg2:u16 | handler=sub_411B40; return_flag=0; aux=0 | 命令名来自命令表 `0x53AD58: 0x53C2A0 -> SetMessage2, opcode=165`；参数描述表 `0x53B735`；运行分发见 `sub_4101C0`。 |
| `0x00A6` | `SetMessageEx` | `A6 00` | dynamic / `<u16 opcode> + typed_i32 + typed_i32 + str8 + typed_i32 + u16` | arg0:typed_i32, arg1:typed_i32, arg2:str8, arg3:typed_i32, arg4:u16 | handler=default/no explicit handler; return_flag=0; aux=0 | 命令名来自命令表 `0x53AD60: 0x53C290 -> SetMessageEx, opcode=166`；参数描述表 `0x53B746`；运行分发见 `sub_4101C0`。 |
| `0x00A7` | `SetChipMessage` | `A7 00` | dynamic / `<u16 opcode> + str8 + u16` | arg0:str8, arg1:u16 | handler=default/no explicit handler; return_flag=1; aux=0 | 命令名来自命令表 `0x53AD68: 0x53C280 -> SetChipMessage, opcode=167`；参数描述表 `0x53B757`；运行分发见 `sub_4101C0`。 |
| `0x00A8` | `AddMessage` | `A8 00` | dynamic / `<u16 opcode> + typed_i32 + str8` | arg0:typed_i32, arg1:str8 | handler=default/no explicit handler; return_flag=0; aux=0 | 命令名来自命令表 `0x53AD70: 0x53C274 -> AddMessage, opcode=168`；参数描述表 `0x53B768`；运行分发见 `sub_4101C0`。 |
| `0x00A9` | `AddMessage2` | `A9 00` | dynamic / `<u16 opcode> + str16 + u8_alt` | arg0:str16, arg1:u8_alt | handler=sub_411BA0; return_flag=0; aux=0 | 命令名来自命令表 `0x53AD78: 0x53C268 -> AddMessage2, opcode=169`；参数描述表 `0x53B779`；运行分发见 `sub_4101C0`。 |
| `0x00AA` | `SetMessageWait` | `AA 00` | dynamic / `<u16 opcode> + typed_i32` | arg0:typed_i32 | handler=default/no explicit handler; return_flag=0; aux=0 | 命令名来自命令表 `0x53AD80: 0x53C258 -> SetMessageWait, opcode=170`；参数描述表 `0x53B78A`；运行分发见 `sub_4101C0`。 |
| `0x00AB` | `ResetMessage` | `AB 00` | 2 bytes / `<u16 opcode>` | none | handler=default/no explicit handler; return_flag=0; aux=0 | 命令名来自命令表 `0x53AD88: 0x53C248 -> ResetMessage, opcode=171`；参数描述表 `0x53B79B`；运行分发见 `sub_4101C0`。 |
| `0x00AC` | `WaitKey` | `AC 00` | 2 bytes / `<u16 opcode>` | none | handler=default/no explicit handler; return_flag=0; aux=0 | 命令名来自命令表 `0x53AD90: 0x53C240 -> WaitKey, opcode=172`；参数描述表 `0x53B7AC`；运行分发见 `sub_4101C0`。 |
| `0x00AD` | `SetSelectMes` | `AD 00` | dynamic / `<u16 opcode> + str8 + typed_i32 + typed_i32` | arg0:str8, arg1:typed_i32, arg2:typed_i32 | handler=sub_412C00; return_flag=1; aux=3 | 命令名来自命令表 `0x53AD98: 0x53C230 -> SetSelectMes, opcode=173`；参数描述表 `0x53B7BD`；运行分发见 `sub_4101C0`。 |
| `0x00AE` | `SetSelectMesEx` | `AE 00` | dynamic / `<u16 opcode> + str8 + str8 + typed_i32 + typed_i32` | arg0:str8, arg1:str8, arg2:typed_i32, arg3:typed_i32 | handler=default/no explicit handler; return_flag=1; aux=2 | 命令名来自命令表 `0x53ADA0: 0x53C220 -> SetSelectMesEx, opcode=174`；参数描述表 `0x53B7CE`；运行分发见 `sub_4101C0`。 |
| `0x00AF` | `SetSelect` | `AF 00` | dynamic / `<u16 opcode> + out_local + typed_i32` | arg0:out_local, arg1:typed_i32 | handler=sub_412C50; return_flag=0; aux=1 | 命令名来自命令表 `0x53ADA8: 0x53C214 -> SetSelect, opcode=175`；参数描述表 `0x53B7DF`；运行分发见 `sub_4101C0`。 |
| `0x00B0` | `SetSelectEx` | `B0 00` | 2 bytes / `<u16 opcode>` | none | handler=default/no explicit handler; return_flag=0; aux=0 | 命令名来自命令表 `0x53ADB0: 0x53C208 -> SetSelectEx, opcode=176`；参数描述表 `0x53B7F0`；运行分发见 `sub_4101C0`。 |
| `0x00B1` | `PlayBgm` | `B1 00` | dynamic / `<u16 opcode> + typed_i32 + typed_i32` | arg0:typed_i32, arg1:typed_i32 | handler=default/no explicit handler; return_flag=1; aux=0 | 命令名来自命令表 `0x53ADB8: 0x53C200 -> PlayBgm, opcode=177`；参数描述表 `0x53B801`；运行分发见 `sub_4101C0`。 |
| `0x00B2` | `PlayBgmEx` | `B2 00` | dynamic / `<u16 opcode> + typed_i32 + typed_i32 + typed_i32 + typed_i32 + typed_i32` | arg0:typed_i32, arg1:typed_i32, arg2:typed_i32, arg3:typed_i32, arg4:typed_i32 | handler=default/no explicit handler; return_flag=1; aux=0 | 命令名来自命令表 `0x53ADC0: 0x53C1F4 -> PlayBgmEx, opcode=178`；参数描述表 `0x53B812`；运行分发见 `sub_4101C0`。 |
| `0x00B3` | `StopBgm` | `B3 00` | dynamic / `<u16 opcode> + typed_i32` | arg0:typed_i32 | handler=default/no explicit handler; return_flag=1; aux=0 | 命令名来自命令表 `0x53ADC8: 0x53C1EC -> StopBgm, opcode=179`；参数描述表 `0x53B823`；运行分发见 `sub_4101C0`。 |
| `0x00B4` | `StopBgmEx` | `B4 00` | dynamic / `<u16 opcode> + typed_i32 + typed_i32` | arg0:typed_i32, arg1:typed_i32 | handler=default/no explicit handler; return_flag=1; aux=0 | 命令名来自命令表 `0x53ADD0: 0x53C1E0 -> StopBgmEx, opcode=180`；参数描述表 `0x53B834`；运行分发见 `sub_4101C0`。 |
| `0x00B5` | `SetVolumeBgm` | `B5 00` | dynamic / `<u16 opcode> + typed_i32 + typed_i32` | arg0:typed_i32, arg1:typed_i32 | handler=default/no explicit handler; return_flag=1; aux=0 | 命令名来自命令表 `0x53ADD8: 0x53C1D0 -> SetVolumeBgm, opcode=181`；参数描述表 `0x53B845`；运行分发见 `sub_4101C0`。 |
| `0x00B6` | `SetVolumeBgmEx` | `B6 00` | dynamic / `<u16 opcode> + typed_i32 + typed_i32 + typed_i32` | arg0:typed_i32, arg1:typed_i32, arg2:typed_i32 | handler=default/no explicit handler; return_flag=1; aux=0 | 命令名来自命令表 `0x53ADE0: 0x53C1C0 -> SetVolumeBgmEx, opcode=182`；参数描述表 `0x53B856`；运行分发见 `sub_4101C0`。 |
| `0x00B7` | `PlaySe` | `B7 00` | dynamic / `<u16 opcode> + typed_i32` | arg0:typed_i32 | handler=default/no explicit handler; return_flag=1; aux=0 | 命令名来自命令表 `0x53ADE8: 0x53C1B8 -> PlaySe, opcode=183`；参数描述表 `0x53B867`；运行分发见 `sub_4101C0`。 |
| `0x00B8` | `PlaySeEx` | `B8 00` | dynamic / `<u16 opcode> + typed_i32 + typed_i32 + typed_i32 + typed_i32 + typed_i32` | arg0:typed_i32, arg1:typed_i32, arg2:typed_i32, arg3:typed_i32, arg4:typed_i32 | handler=default/no explicit handler; return_flag=1; aux=0 | 命令名来自命令表 `0x53ADF0: 0x53C1AC -> PlaySeEx, opcode=184`；参数描述表 `0x53B878`；运行分发见 `sub_4101C0`。 |
| `0x00B9` | `StopSeEx` | `B9 00` | dynamic / `<u16 opcode> + typed_i32 + typed_i32` | arg0:typed_i32, arg1:typed_i32 | handler=default/no explicit handler; return_flag=1; aux=0 | 命令名来自命令表 `0x53ADF8: 0x53C1A0 -> StopSeEx, opcode=185`；参数描述表 `0x53B889`；运行分发见 `sub_4101C0`。 |
| `0x00BA` | `SetVolumeSe` | `BA 00` | dynamic / `<u16 opcode> + typed_i32 + typed_i32 + typed_i32` | arg0:typed_i32, arg1:typed_i32, arg2:typed_i32 | handler=default/no explicit handler; return_flag=1; aux=0 | 命令名来自命令表 `0x53AE00: 0x53C194 -> SetVolumeSe, opcode=186`；参数描述表 `0x53B89A`；运行分发见 `sub_4101C0`。 |
| `0x00BB` | `SetWeather` | `BB 00` | dynamic / `<u16 opcode> + typed_i32 + typed_i32 + typed_i32 + typed_i32 + typed_i32` | arg0:typed_i32, arg1:typed_i32, arg2:typed_i32, arg3:typed_i32, arg4:typed_i32 | handler=sub_412B10; return_flag=1; aux=1 | 命令名来自命令表 `0x53AE08: 0x53C188 -> SetWeather, opcode=187`；参数描述表 `0x53B8AB`；运行分发见 `sub_4101C0`。 |
| `0x00BC` | `ChangeWeather` | `BC 00` | dynamic / `<u16 opcode> + typed_i32 + typed_i32 + typed_i32 + typed_i32` | arg0:typed_i32, arg1:typed_i32, arg2:typed_i32, arg3:typed_i32 | handler=sub_412B60; return_flag=1; aux=1 | 命令名来自命令表 `0x53AE10: 0x53C178 -> ChangeWeather, opcode=188`；参数描述表 `0x53B8BC`；运行分发见 `sub_4101C0`。 |
| `0x00BD` | `ResetWeather` | `BD 00` | 2 bytes / `<u16 opcode>` | none | handler=sub_412BC0; return_flag=0; aux=0 | 命令名来自命令表 `0x53AE18: 0x53C168 -> ResetWeather, opcode=189`；参数描述表 `0x53B8CD`；运行分发见 `sub_4101C0`。 |
| `0x00BE` | `SetLensFrea` | `BE 00` | dynamic / `<u16 opcode> + typed_i32 + typed_i32 + typed_i32` | arg0:typed_i32, arg1:typed_i32, arg2:typed_i32 | handler=default/no explicit handler; return_flag=1; aux=0 | 命令名来自命令表 `0x53AE20: 0x53C15C -> SetLensFrea, opcode=190`；参数描述表 `0x53B8DE`；运行分发见 `sub_4101C0`。 |
| `0x00BF` | `SetWavEffect` | `BF 00` | dynamic / `<u16 opcode> + typed_i32 + typed_i32 + typed_i32` | arg0:typed_i32, arg1:typed_i32, arg2:typed_i32 | handler=default/no explicit handler; return_flag=0; aux=3 | 命令名来自命令表 `0x53AE28: 0x53C14C -> SetWavEffect, opcode=191`；参数描述表 `0x53B8EF`；运行分发见 `sub_4101C0`。 |
| `0x00C0` | `ResetWavEffect` | `C0 00` | 2 bytes / `<u16 opcode>` | none | handler=default/no explicit handler; return_flag=1; aux=0 | 命令名来自命令表 `0x53AE30: 0x53C13C -> ResetWavEffect, opcode=192`；参数描述表 `0x53B900`；运行分发见 `sub_4101C0`。 |
| `0x00C1` | `SetWarp` | `C1 00` | dynamic / `<u16 opcode> + typed_i32 + typed_i32 + typed_i32 + typed_i32 + typed_i32 + typed_i32 + typed_i32 + typed_i32` | arg0:typed_i32, arg1:typed_i32, arg2:typed_i32, arg3:typed_i32, arg4:typed_i32, arg5:typed_i32, arg6:typed_i32, arg7:typed_i32 | handler=default/no explicit handler; return_flag=0; aux=8 | 命令名来自命令表 `0x53AE38: 0x53C134 -> SetWarp, opcode=193`；参数描述表 `0x53B911`；运行分发见 `sub_4101C0`。 |
| `0x00C2` | `ResetWarp` | `C2 00` | dynamic / `<u16 opcode> + typed_i32` | arg0:typed_i32 | handler=default/no explicit handler; return_flag=0; aux=1 | 命令名来自命令表 `0x53AE40: 0x53C128 -> ResetWarp, opcode=194`；参数描述表 `0x53B922`；运行分发见 `sub_4101C0`。 |
| `0x00C3` | `WaitFrame` | `C3 00` | dynamic / `<u16 opcode> + typed_i32` | arg0:typed_i32 | handler=sub_412CB0; return_flag=0; aux=0 | 命令名来自命令表 `0x53AE48: 0x53C11C -> WaitFrame, opcode=195`；参数描述表 `0x53B933`；运行分发见 `sub_4101C0`。 |
| `0x00C4` | `SetBmp` | `C4 00` | dynamic / `<u16 opcode> + typed_i32 + str8 + typed_i32 + typed_i32 + typed_i32 + str8 + typed_i32 + str8` | arg0:typed_i32, arg1:str8, arg2:typed_i32, arg3:typed_i32, arg4:typed_i32, arg5:str8, arg6:typed_i32, arg7:str8 | handler=sub_412D00; return_flag=1; aux=5 | 命令名来自命令表 `0x53AE50: 0x53C114 -> SetBmp, opcode=196`；参数描述表 `0x53B944`；运行分发见 `sub_4101C0`。 |
| `0x00C5` | `SetBmpEx` | `C5 00` | dynamic / `<u16 opcode> + typed_i32 + typed_i32 + str8 + typed_i32 + typed_i32 + typed_i32 + str8` | arg0:typed_i32, arg1:typed_i32, arg2:str8, arg3:typed_i32, arg4:typed_i32, arg5:typed_i32, arg6:str8 | handler=default/no explicit handler; return_flag=1; aux=2 | 命令名来自命令表 `0x53AE58: 0x53C108 -> SetBmpEx, opcode=197`；参数描述表 `0x53B955`；运行分发见 `sub_4101C0`。 |
| `0x00C6` | `SetBmp4Bmp` | `C6 00` | dynamic / `<u16 opcode> + typed_i32 + typed_i32 + typed_i32 + typed_i32` | arg0:typed_i32, arg1:typed_i32, arg2:typed_i32, arg3:typed_i32 | handler=default/no explicit handler; return_flag=1; aux=0 | 命令名来自命令表 `0x53AE60: 0x53C0FC -> SetBmp4Bmp, opcode=198`；参数描述表 `0x53B966`；运行分发见 `sub_4101C0`。 |
| `0x00C7` | `SetBmpPrim` | `C7 00` | dynamic / `<u16 opcode> + typed_i32 + typed_i32 + typed_i32 + typed_i32` | arg0:typed_i32, arg1:typed_i32, arg2:typed_i32, arg3:typed_i32 | handler=default/no explicit handler; return_flag=1; aux=0 | 命令名来自命令表 `0x53AE68: 0x53C0F0 -> SetBmpPrim, opcode=199`；参数描述表 `0x53B977`；运行分发见 `sub_4101C0`。 |
| `0x00C8` | `ResetBmp` | `C8 00` | dynamic / `<u16 opcode> + typed_i32` | arg0:typed_i32 | handler=sub_412D80; return_flag=1; aux=0 | 命令名来自命令表 `0x53AE70: 0x53C0E4 -> ResetBmp, opcode=200`；参数描述表 `0x53B988`；运行分发见 `sub_4101C0`。 |
| `0x00C9` | `ResetBmpAll` | `C9 00` | 2 bytes / `<u16 opcode>` | none | handler=sub_412DA0; return_flag=1; aux=0 | 命令名来自命令表 `0x53AE78: 0x53C0D8 -> ResetBmpAll, opcode=201`；参数描述表 `0x53B999`；运行分发见 `sub_4101C0`。 |
| `0x00CA` | `SetBmpAnime` | `CA 00` | dynamic / `<u16 opcode> + typed_i32 + str8 + typed_i32 + str8 + typed_i32 + str8` | arg0:typed_i32, arg1:str8, arg2:typed_i32, arg3:str8, arg4:typed_i32, arg5:str8 | handler=sub_412DD0; return_flag=1; aux=3 | 命令名来自命令表 `0x53AE80: 0x53C0CC -> SetBmpAnime, opcode=202`；参数描述表 `0x53B9AA`；运行分发见 `sub_4101C0`。 |
| `0x00CB` | `ResetBmpAnime` | `CB 00` | dynamic / `<u16 opcode> + typed_i32` | arg0:typed_i32 | handler=sub_412E70; return_flag=1; aux=0 | 命令名来自命令表 `0x53AE88: 0x53C0BC -> ResetBmpAnime, opcode=203`；参数描述表 `0x53B9BB`；运行分发见 `sub_4101C0`。 |
| `0x00CC` | `WaitBmpAnime` | `CC 00` | dynamic / `<u16 opcode> + typed_i32` | arg0:typed_i32 | handler=sub_412E40; return_flag=0; aux=0 | 命令名来自命令表 `0x53AE90: 0x53C0AC -> WaitBmpAnime, opcode=204`；参数描述表 `0x53B9CC`；运行分发见 `sub_4101C0`。 |
| `0x00CD` | `SetBmpAnimePlay` | `CD 00` | dynamic / `<u16 opcode> + typed_i32 + typed_i32 + typed_i32 + typed_i32` | arg0:typed_i32, arg1:typed_i32, arg2:typed_i32, arg3:typed_i32 | handler=sub_412E90; return_flag=1; aux=3 | 命令名来自命令表 `0x53AE98: 0x53C09C -> SetBmpAnimePlay, opcode=205`；参数描述表 `0x53B9DD`；运行分发见 `sub_4101C0`。 |
| `0x00CE` | `SetAvi` | `CE 00` | dynamic / `<u16 opcode> + typed_i32 + str8 + typed_i32` | arg0:typed_i32, arg1:str8, arg2:typed_i32 | handler=sub_413170; return_flag=1; aux=0 | 命令名来自命令表 `0x53AEA0: 0x53C094 -> SetAvi, opcode=206`；参数描述表 `0x53B9EE`；运行分发见 `sub_4101C0`。 |
| `0x00CF` | `ResetAvi` | `CF 00` | dynamic / `<u16 opcode> + typed_i32` | arg0:typed_i32 | handler=default/no explicit handler; return_flag=1; aux=0 | 命令名来自命令表 `0x53AEA8: 0x53C088 -> ResetAvi, opcode=207`；参数描述表 `0x53B9FF`；运行分发见 `sub_4101C0`。 |
| `0x00D0` | `WaitAvi` | `D0 00` | dynamic / `<u16 opcode> + typed_i32` | arg0:typed_i32 | handler=sub_4131A0; return_flag=0; aux=0 | 命令名来自命令表 `0x53AEB0: 0x53C080 -> WaitAvi, opcode=208`；参数描述表 `0x53BA10`；运行分发见 `sub_4101C0`。 |
| `0x00D1` | `SetAviFull` | `D1 00` | dynamic / `<u16 opcode> + typed_i32` | arg0:typed_i32 | handler=sub_4131D0; return_flag=1; aux=1 | 命令名来自命令表 `0x53AEB8: 0x53C074 -> SetAviFull, opcode=209`；参数描述表 `0x53BA21`；运行分发见 `sub_4101C0`。 |
| `0x00D2` | `WaitAviFull` | `D2 00` | 2 bytes / `<u16 opcode>` | none | handler=sub_413200; return_flag=0; aux=0 | 命令名来自命令表 `0x53AEC0: 0x53C068 -> WaitAviFull, opcode=210`；参数描述表 `0x53BA32`；运行分发见 `sub_4101C0`。 |
| `0x00D3` | `SetBmpDisp` | `D3 00` | dynamic / `<u16 opcode> + typed_i32 + typed_i32` | arg0:typed_i32, arg1:typed_i32 | handler=sub_412EF0; return_flag=1; aux=0 | 命令名来自命令表 `0x53AEC8: 0x53C05C -> SetBmpDisp, opcode=211`；参数描述表 `0x53BA43`；运行分发见 `sub_4101C0`。 |
| `0x00D4` | `SetBmpLayer` | `D4 00` | dynamic / `<u16 opcode> + typed_i32 + typed_i32` | arg0:typed_i32, arg1:typed_i32 | handler=sub_412F20; return_flag=1; aux=0 | 命令名来自命令表 `0x53AED0: 0x53C050 -> SetBmpLayer, opcode=212`；参数描述表 `0x53BA54`；运行分发见 `sub_4101C0`。 |
| `0x00D5` | `SetBmpParam` | `D5 00` | dynamic / `<u16 opcode> + typed_i32 + typed_i32 + typed_i32` | arg0:typed_i32, arg1:typed_i32, arg2:typed_i32 | handler=sub_412F50; return_flag=1; aux=1 | 命令名来自命令表 `0x53AED8: 0x53C044 -> SetBmpParam, opcode=213`；参数描述表 `0x53BA65`；运行分发见 `sub_4101C0`。 |
| `0x00D6` | `SetBmpRevParam` | `D6 00` | dynamic / `<u16 opcode> + typed_i32 + typed_i32` | arg0:typed_i32, arg1:typed_i32 | handler=sub_412F90; return_flag=1; aux=0 | 命令名来自命令表 `0x53AEE0: 0x53C034 -> SetBmpRevParam, opcode=214`；参数描述表 `0x53BA76`；运行分发见 `sub_4101C0`。 |
| `0x00D7` | `SetBmpBright` | `D7 00` | dynamic / `<u16 opcode> + typed_i32 + typed_i32 + typed_i32 + typed_i32` | arg0:typed_i32, arg1:typed_i32, arg2:typed_i32, arg3:typed_i32 | handler=sub_412FC0; return_flag=1; aux=2 | 命令名来自命令表 `0x53AEE8: 0x53C024 -> SetBmpBright, opcode=215`；参数描述表 `0x53BA87`；运行分发见 `sub_4101C0`。 |
| `0x00D8` | `SetBmpMove` | `D8 00` | dynamic / `<u16 opcode> + typed_i32 + typed_i32 + typed_i32` | arg0:typed_i32, arg1:typed_i32, arg2:typed_i32 | handler=sub_413030; return_flag=1; aux=0 | 命令名来自命令表 `0x53AEF0: 0x53C018 -> SetBmpMove, opcode=216`；参数描述表 `0x53BA98`；运行分发见 `sub_4101C0`。 |
| `0x00D9` | `SetBmpPos` | `D9 00` | dynamic / `<u16 opcode> + typed_i32 + typed_i32 + typed_i32 + typed_i32 + typed_i32 + typed_i32 + typed_i32` | arg0:typed_i32, arg1:typed_i32, arg2:typed_i32, arg3:typed_i32, arg4:typed_i32, arg5:typed_i32, arg6:typed_i32 | handler=sub_413060; return_flag=1; aux=0 | 命令名来自命令表 `0x53AEF8: 0x53C00C -> SetBmpPos, opcode=217`；参数描述表 `0x53BAA9`；运行分发见 `sub_4101C0`。 |
| `0x00DA` | `SetBmpZoom` | `DA 00` | dynamic / `<u16 opcode> + typed_i32 + typed_i32 + typed_i32 + typed_i32 + typed_i32` | arg0:typed_i32, arg1:typed_i32, arg2:typed_i32, arg3:typed_i32, arg4:typed_i32 | handler=sub_4130B0; return_flag=1; aux=0 | 命令名来自命令表 `0x53AF00: 0x53C000 -> SetBmpZoom, opcode=218`；参数描述表 `0x53BABA`；运行分发见 `sub_4101C0`。 |
| `0x00DB` | `SetBmpZoom2` | `DB 00` | dynamic / `<u16 opcode> + typed_i32 + typed_i32 + typed_i32 + typed_i32` | arg0:typed_i32, arg1:typed_i32, arg2:typed_i32, arg3:typed_i32 | handler=sub_4130F0; return_flag=1; aux=0 | 命令名来自命令表 `0x53AF08: 0x53BFF4 -> SetBmpZoom2, opcode=219`；参数描述表 `0x53BACB`；运行分发见 `sub_4101C0`。 |
| `0x00DC` | `SetTitle` | `DC 00` | 2 bytes / `<u16 opcode>` | none | handler=default/no explicit handler; return_flag=0; aux=0 | 命令名来自命令表 `0x53AF10: 0x53BFE8 -> SetTitle, opcode=220`；参数描述表 `0x53BADC`；运行分发见 `sub_4101C0`。 |
| `0x00DD` | `SetEnding` | `DD 00` | dynamic / `<u16 opcode> + typed_i32 + typed_i32` | arg0:typed_i32, arg1:typed_i32 | handler=default/no explicit handler; return_flag=0; aux=0 | 命令名来自命令表 `0x53AF18: 0x53BFDC -> SetEnding, opcode=221`；参数描述表 `0x53BAED`；运行分发见 `sub_4101C0`。 |
| `0x00DE` | `NextGameStep` | `DE 00` | dynamic / `<u16 opcode> + typed_i32 + str8` | arg0:typed_i32, arg1:str8 | handler=sub_411130; return_flag=1; aux=1 | 命令名来自命令表 `0x53AF20: 0x53BFCC -> NextGameStep, opcode=222`；参数描述表 `0x53BAFE`；运行分发见 `sub_4101C0`。 |
| `0x00DF` | `SetDemoFlag` | `DF 00` | dynamic / `<u16 opcode> + typed_i32 + typed_i32` | arg0:typed_i32, arg1:typed_i32 | handler=sub_413220; return_flag=1; aux=0 | 命令名来自命令表 `0x53AF28: 0x53BFC0 -> SetDemoFlag, opcode=223`；参数描述表 `0x53BB0F`；运行分发见 `sub_4101C0`。 |
| `0x00E0` | `SetSceneNo` | `E0 00` | dynamic / `<u16 opcode> + typed_i32` | arg0:typed_i32 | handler=default/no explicit handler; return_flag=1; aux=0 | 命令名来自命令表 `0x53AF30: 0x53BFB4 -> SetSceneNo, opcode=224`；参数描述表 `0x53BB20`；运行分发见 `sub_4101C0`。 |
| `0x00E1` | `SetEndingNo` | `E1 00` | dynamic / `<u16 opcode> + typed_i32` | arg0:typed_i32 | handler=default/no explicit handler; return_flag=1; aux=0 | 命令名来自命令表 `0x53AF38: 0x53BFA8 -> SetEndingNo, opcode=225`；参数描述表 `0x53BB31`；运行分发见 `sub_4101C0`。 |
| `0x00E2` | `SetReplayNo` | `E2 00` | dynamic / `<u16 opcode> + typed_i32` | arg0:typed_i32 | handler=default/no explicit handler; return_flag=1; aux=0 | 命令名来自命令表 `0x53AF40: 0x53BF9C -> SetReplayNo, opcode=226`；参数描述表 `0x53BB42`；运行分发见 `sub_4101C0`。 |
| `0x00E3` | `SetSoundEvent` | `E3 00` | dynamic / `<u16 opcode> + typed_i32 + typed_i32 + typed_i32 + typed_i32 + typed_i32 + typed_i32 + typed_i32` | arg0:typed_i32, arg1:typed_i32, arg2:typed_i32, arg3:typed_i32, arg4:typed_i32, arg5:typed_i32, arg6:typed_i32 | handler=default/no explicit handler; return_flag=1; aux=5 | 命令名来自命令表 `0x53AF48: 0x53BF8C -> SetSoundEvent, opcode=227`；参数描述表 `0x53BB53`；运行分发见 `sub_4101C0`。 |
| `0x00E4` | `SetSoundEventVolume` | `E4 00` | dynamic / `<u16 opcode> + typed_i32 + typed_i32 + typed_i32 + typed_i32` | arg0:typed_i32, arg1:typed_i32, arg2:typed_i32, arg3:typed_i32 | handler=default/no explicit handler; return_flag=1; aux=2 | 命令名来自命令表 `0x53AF50: 0x53BF78 -> SetSoundEventVolume, opcode=228`；参数描述表 `0x53BB64`；运行分发见 `sub_4101C0`。 |
| `0x00E5` | `SetPotaPota` | `E5 00` | dynamic / `<u16 opcode> + typed_i32 + typed_i32 + typed_i32` | arg0:typed_i32, arg1:typed_i32, arg2:typed_i32 | handler=default/no explicit handler; return_flag=0; aux=3 | 命令名来自命令表 `0x53AF58: 0x53BF6C -> SetPotaPota, opcode=229`；参数描述表 `0x53BB75`；运行分发见 `sub_4101C0`。 |
| `0x00E6` | `GetTime` | `E6 00` | dynamic / `<u16 opcode> + out_local` | arg0:out_local | handler=sub_413250; return_flag=1; aux=0 | 命令名来自命令表 `0x53AF60: 0x53BF64 -> GetTime, opcode=230`；参数描述表 `0x53BB86`；运行分发见 `sub_4101C0`。 |
| `0x00E7` | `WaitTime` | `E7 00` | dynamic / `<u16 opcode> + typed_i32` | arg0:typed_i32 | handler=sub_413270; return_flag=0; aux=0 | 命令名来自命令表 `0x53AF68: 0x53BF58 -> WaitTime, opcode=231`；参数描述表 `0x53BB97`；运行分发见 `sub_4101C0`。 |
| `0x00E8` | `SetTextFormat` | `E8 00` | dynamic / `<u16 opcode> + typed_i32 + typed_i32 + typed_i32 + typed_i32 + typed_i32 + typed_i32 + typed_i32 + typed_i32 + typed_i32 + typed_i32 + typed_i32` | arg0:typed_i32, arg1:typed_i32, arg2:typed_i32, arg3:typed_i32, arg4:typed_i32, arg5:typed_i32, arg6:typed_i32, arg7:typed_i32, arg8:typed_i32, arg9:typed_i32, arg10:typed_i32 | handler=default/no explicit handler; return_flag=1; aux=10 | 命令名来自命令表 `0x53AF70: 0x53BF48 -> SetTextFormat, opcode=232`；参数描述表 `0x53BBA8`；运行分发见 `sub_4101C0`。 |
| `0x00E9` | `SetTextSync` | `E9 00` | dynamic / `<u16 opcode> + typed_i32 + typed_i32` | arg0:typed_i32, arg1:typed_i32 | handler=default/no explicit handler; return_flag=1; aux=0 | 命令名来自命令表 `0x53AF78: 0x53BF3C -> SetTextSync, opcode=233`；参数描述表 `0x53BBB9`；运行分发见 `sub_4101C0`。 |
| `0x00EA` | `SetText` | `EA 00` | dynamic / `<u16 opcode> + typed_i32 + str8` | arg0:typed_i32, arg1:str8 | handler=default/no explicit handler; return_flag=0; aux=0 | 命令名来自命令表 `0x53AF80: 0x53BF34 -> SetText, opcode=234`；参数描述表 `0x53BBCA`；运行分发见 `sub_4101C0`。 |
| `0x00EB` | `SetTextEx` | `EB 00` | dynamic / `<u16 opcode> + str8` | arg0:str8 | handler=default/no explicit handler; return_flag=0; aux=0 | 命令名来自命令表 `0x53AF88: 0x53BF28 -> SetTextEx, opcode=235`；参数描述表 `0x53BBDB`；运行分发见 `sub_4101C0`。 |
| `0x00EC` | `ResetText` | `EC 00` | dynamic / `<u16 opcode> + typed_i32` | arg0:typed_i32 | handler=default/no explicit handler; return_flag=1; aux=0 | 命令名来自命令表 `0x53AF90: 0x53BF1C -> ResetText, opcode=236`；参数描述表 `0x53BBEC`；运行分发见 `sub_4101C0`。 |
| `0x00ED` | `WaitText` | `ED 00` | dynamic / `<u16 opcode> + typed_i32` | arg0:typed_i32 | handler=default/no explicit handler; return_flag=0; aux=0 | 命令名来自命令表 `0x53AF98: 0x53BF10 -> WaitText, opcode=237`；参数描述表 `0x53BBFD`；运行分发见 `sub_4101C0`。 |
| `0x00EE` | `ResetTextAll` | `EE 00` | 2 bytes / `<u16 opcode>` | none | handler=default/no explicit handler; return_flag=1; aux=0 | 命令名来自命令表 `0x53AFA0: 0x53BF00 -> ResetTextAll, opcode=238`；参数描述表 `0x53BC0E`；运行分发见 `sub_4101C0`。 |
| `0x00EF` | `SetDemoFadeFlag` | `EF 00` | dynamic / `<u16 opcode> + typed_i32` | arg0:typed_i32 | handler=default/no explicit handler; return_flag=1; aux=0 | 命令名来自命令表 `0x53AFA8: 0x53BEF0 -> SetDemoFadeFlag, opcode=239`；参数描述表 `0x53BC1F`；运行分发见 `sub_4101C0`。 |
| `0x00F0` | `Mov2` | `F0 00` | dynamic / `<u16 opcode> + out_local + typed_i32` | arg0:out_local, arg1:typed_i32 | handler=sub_413290; return_flag=1; aux=0 | 命令名来自命令表 `0x53AFB0: 0x53BEE8 -> Mov2, opcode=240`；参数描述表 `0x53BC30`；运行分发见 `sub_4101C0`。 |
| `0x00F1` | `Sin` | `F1 00` | dynamic / `<u16 opcode> + out_local + typed_i32 + typed_i32` | arg0:out_local, arg1:typed_i32, arg2:typed_i32 | handler=sub_4132B0; return_flag=1; aux=1 | 命令名来自命令表 `0x53AFB8: 0x53BEE4 -> Sin, opcode=241`；参数描述表 `0x53BC41`；运行分发见 `sub_4101C0`。 |
| `0x00F2` | `Cos` | `F2 00` | dynamic / `<u16 opcode> + out_local + typed_i32 + typed_i32` | arg0:out_local, arg1:typed_i32, arg2:typed_i32 | handler=sub_413320; return_flag=1; aux=1 | 命令名来自命令表 `0x53AFC0: 0x53BEE0 -> Cos, opcode=242`；参数描述表 `0x53BC52`；运行分发见 `sub_4101C0`。 |
| `0x00F3` | `Abs` | `F3 00` | dynamic / `<u16 opcode> + out_local + typed_i32` | arg0:out_local, arg1:typed_i32 | handler=sub_413390; return_flag=1; aux=0 | 命令名来自命令表 `0x53AFC8: 0x53BEDC -> Abs, opcode=243`；参数描述表 `0x53BC63`；运行分发见 `sub_4101C0`。 |
| `0x00F4` | `TestSetParam` | `F4 00` | dynamic / `<u16 opcode> + typed_i32` | arg0:typed_i32 | handler=sub_4133F0; return_flag=1; aux=0 | 命令名来自命令表 `0x53AFD0: 0x53BECC -> TestSetParam, opcode=244`；参数描述表 `0x53BC74`；运行分发见 `sub_4101C0`。 |
| `0x00F5` | `SetPartyChar` | `F5 00` | dynamic / `<u16 opcode> + typed_i32 + typed_i32 + typed_i32 + typed_i32` | arg0:typed_i32, arg1:typed_i32, arg2:typed_i32, arg3:typed_i32 | handler=sub_413410; return_flag=1; aux=2 | 命令名来自命令表 `0x53AFD8: 0x53BEBC -> SetPartyChar, opcode=245`；参数描述表 `0x53BC85`；运行分发见 `sub_4101C0`。 |
| `0x00F6` | `GetPartyLevel` | `F6 00` | dynamic / `<u16 opcode> + typed_i32 + out_local` | arg0:typed_i32, arg1:out_local | handler=sub_413460; return_flag=1; aux=0 | 命令名来自命令表 `0x53AFE0: 0x53BEAC -> GetPartyLevel, opcode=246`；参数描述表 `0x53BC96`；运行分发见 `sub_4101C0`。 |
| `0x00F7` | `SetMapBox` | `F7 00` | dynamic / `<u16 opcode> + typed_i32 + typed_i32 + typed_i32 + typed_i32 + typed_i32` | arg0:typed_i32, arg1:typed_i32, arg2:typed_i32, arg3:typed_i32, arg4:typed_i32 | handler=nullsub_7; return_flag=1; aux=1 | 命令名来自命令表 `0x53AFE8: 0x53BEA0 -> SetMapBox, opcode=247`；参数描述表 `0x53BCA7`；运行分发见 `sub_4101C0`。 |
| `0x00F8` | `SetCutCut` | `F8 00` | dynamic / `<u16 opcode> + typed_i32` | arg0:typed_i32 | handler=default/no explicit handler; return_flag=1; aux=0 | 命令名来自命令表 `0x53AFF0: 0x53BE94 -> SetCutCut, opcode=248`；参数描述表 `0x53BCB8`；运行分发见 `sub_4101C0`。 |
| `0x00F9` | `SetNoise` | `F9 00` | dynamic / `<u16 opcode> + typed_i32 + typed_i32 + typed_i32` | arg0:typed_i32, arg1:typed_i32, arg2:typed_i32 | handler=default/no explicit handler; return_flag=0; aux=2 | 命令名来自命令表 `0x53AFF8: 0x53BE88 -> SetNoise, opcode=249`；参数描述表 `0x53BCC9`；运行分发见 `sub_4101C0`。 |
| `0x00FA` | `T` | `FA 00` | dynamic / `<u16 opcode> + typed_i32 + typed_i32` | arg0:typed_i32, arg1:typed_i32 | handler=default/no explicit handler; return_flag=1; aux=1 | 命令名来自命令表 `0x53B000: 0x53BE84 -> T, opcode=250`；参数描述表 `0x53BCDA`；运行分发见 `sub_4101C0`。 |
| `0x00FB` | `SetUsoErr` | `FB 00` | 2 bytes / `<u16 opcode>` | none | handler=default/no explicit handler; return_flag=1; aux=0 | 命令名来自命令表 `0x53B008: 0x53BE78 -> SetUsoErr, opcode=251`；参数描述表 `0x53BCEB`；运行分发见 `sub_4101C0`。 |
| `0x00FC` | `LoadScriptNum` | `FC 00` | dynamic / `<u16 opcode> + typed_i32` | arg0:typed_i32 | handler=sub_4110B0; return_flag=0; aux=0 | 命令名来自命令表 `0x53B010: 0x53BE68 -> LoadScriptNum, opcode=252`；参数描述表 `0x53BCFC`；运行分发见 `sub_4101C0`。 |
| `0x00FD` | `SetRipple` | `FD 00` | dynamic / `<u16 opcode> + typed_i32 + typed_i32 + typed_i32` | arg0:typed_i32, arg1:typed_i32, arg2:typed_i32 | handler=default/no explicit handler; return_flag=1; aux=0 | 命令名来自命令表 `0x53B018: 0x53BE5C -> SetRipple, opcode=253`；参数描述表 `0x53BD0D`；运行分发见 `sub_4101C0`。 |
| `0x00FE` | `SetRippleSet` | `FE 00` | dynamic / `<u16 opcode> + typed_i32 + typed_i32 + typed_i32` | arg0:typed_i32, arg1:typed_i32, arg2:typed_i32 | handler=default/no explicit handler; return_flag=1; aux=1 | 命令名来自命令表 `0x53B020: 0x53BE4C -> SetRippleSet, opcode=254`；参数描述表 `0x53BD1E`；运行分发见 `sub_4101C0`。 |
| `0x00FF` | `WaitRipple` | `FF 00` | 2 bytes / `<u16 opcode>` | none | handler=default/no explicit handler; return_flag=0; aux=0 | 命令名来自命令表 `0x53B028: 0x53BE40 -> WaitRipple, opcode=255`；参数描述表 `0x53BD2F`；运行分发见 `sub_4101C0`。 |
| `0x0100` | `SetRippleLost` | `00 01` | 2 bytes / `<u16 opcode>` | none | handler=default/no explicit handler; return_flag=0; aux=0 | 命令名来自命令表 `0x53B030: 0x53BE30 -> SetRippleLost, opcode=256`；参数描述表 `0x53BD40`；运行分发见 `sub_4101C0`。 |
| `0x0101` | `MLW` | `01 01` | 2 bytes / `<u16 opcode>` | none | handler=sub_412660; return_flag=0; aux=0 | 命令名来自命令表 `0x53B038: 0x53BE2C -> MLW, opcode=257`；参数描述表 `0x53BD51`；运行分发见 `sub_4101C0`。 |
| `0x0102` | `GetItem` | `02 01` | dynamic / `<u16 opcode> + typed_i32 + typed_i32` | arg0:typed_i32, arg1:typed_i32 | handler=sub_4134A0; return_flag=1; aux=0 | 命令名来自命令表 `0x53B040: 0x53BE24 -> GetItem, opcode=258`；参数描述表 `0x53BD62`；运行分发见 `sub_4101C0`。 |
| `0x0103` | `CheckItem` | `03 01` | dynamic / `<u16 opcode> + typed_i32 + out_local` | arg0:typed_i32, arg1:out_local | handler=sub_4134D0; return_flag=1; aux=0 | 命令名来自命令表 `0x53B048: 0x53BE18 -> CheckItem, opcode=259`；参数描述表 `0x53BD73`；运行分发见 `sub_4101C0`。 |
| `0x0104` | `SetMapCharName` | `04 01` | dynamic / `<u16 opcode> + typed_i32 + str8` | arg0:typed_i32, arg1:str8 | handler=sub_4118B0; return_flag=1; aux=0 | 命令名来自命令表 `0x53B050: 0x53BE08 -> SetMapCharName, opcode=260`；参数描述表 `0x53BD84`；运行分发见 `sub_4101C0`。 |
| `0x0105` | `SetBmpRoll` | `05 01` | dynamic / `<u16 opcode> + typed_i32 + typed_i32 + typed_i32 + typed_i32` | arg0:typed_i32, arg1:typed_i32, arg2:typed_i32, arg3:typed_i32 | handler=sub_413130; return_flag=1; aux=0 | 命令名来自命令表 `0x53B058: 0x53BDFC -> SetBmpRoll, opcode=261`；参数描述表 `0x53BD95`；运行分发见 `sub_4101C0`。 |
| `0x0106` | `SetMovie` | `06 01` | 2 bytes / `<u16 opcode>` | none | handler=default/no explicit handler; return_flag=0; aux=0 | 命令名来自命令表 `0x53B060: 0x53BDF0 -> SetMovie, opcode=262`；参数描述表 `0x53BDA6`；运行分发见 `sub_4101C0`。 |
| `0x0107` | `DebugBox` | `07 01` | dynamic / `<u16 opcode> + typed_i32 + str8` | arg0:typed_i32, arg1:str8 | handler=sub_4133C0; return_flag=1; aux=1 | 命令名来自命令表 `0x53B068: 0x53BDE4 -> DebugBox, opcode=263`；参数描述表 `0x53BDB7`；运行分发见 `sub_4101C0`。 |
| `0x0108` | `VHFlag` | `08 01` | dynamic / `<u16 opcode> + typed_i32 + typed_i32` | arg0:typed_i32, arg1:typed_i32 | handler=sub_411FF0; return_flag=1; aux=0 | 命令名来自命令表 `0x53B070: 0x53BDDC -> VHFlag, opcode=264`；参数描述表 `0x53BDC8`；运行分发见 `sub_4101C0`。 |

## 7. 跳转与标签策略

### 7.1 地址空间

所有 VM 跳转目标都应表示为 body offset，即文件偏移减 `0x408`。

```text
file_offset = 0x408 + body_offset
entry_file_value = body_offset + 1
```

### 7.2 标签来源

反汇编器必须至少为以下目标生成标签：

1. `entry[i] != 0` 的入口：`entry[i] - 1`。
2. 内置条件跳转/无条件跳转读取的 `u32 target`。
3. 调用/返回栈相关 handler 中读取的目标 offset。
4. `LOAD_SDT` 等跨脚本切换指令的文件名使用语义操作数，不作为本文件内 label。

建议标签命名：

```text
loc_00000000
entry_000_loc_00000000
```

若一个地址同时是入口和普通跳转目标，asm 中只定义一个标签，但 `.entry` 表可引用它。`.entry` 只需要列出非零槽位，未列出的 0 槽位由汇编器自动补齐。

### 7.3 重定位规则

若字符串或指令重写导致 body 长度变化：

- asm 中指令必须引用 label，而不是硬编码 `u32 target`。
- 汇编器第一遍计算 label body offset。
- 第二遍将跳转目标写为新的 body offset。
- entry 表写回 `label_offset + 1`。

这可以避免文本长度变化后跳转仍指向旧地址导致游戏执行异常。

## 8. 字符串与文本数据策略

SDT 正文中的文本不是独立字符串池，而是嵌入在指令参数中，长度由 opcode handler 或参数描述表决定：

- `sub_410E20`：`u8 len + bytes`。
- `sub_410E80`：`u16 len + bytes`。
- `sub_410C00` mode `2`：`u8 len + bytes`，读出后转数值。
- `sub_459010`：`u8 len + filename bytes`。

反汇编器不得用正则扫描整个 SDT 抓文本，必须通过指令/参数结构到达这些字节。对于无法结构化识别但仍位于 body 内的字节段，必须用 `.byte` 或 `.raw` 语义伪指令完整覆盖，保证零突变。

asm 输出字符串规范：

- 默认编码建议 `cp932`。
- 可打印文本按编码解码输出，普通反斜杠按脚本文本直接保留。
- 控制字节、解码失败字节、无法安全显示字节必须输出为 `{{XX}}` 占位符；Unicode 私用区字符按原始编码字节成组输出，如 CP932 `F0 41` 输出为 `{{F0:41}}`。
- asm 不把 `\xNN` 作为十六进制字节转义；需要指定原始字节时使用 `{{XX}}` / `{{XX:XX}}`。
- 不允许在注释中写原始十六进制转储。

示例：

```text
.encoding "cp932"

loc_00000030:
    CMD_00A5    .str8 "東京へようこそ{{00}}"
```

## 9. 未定义 opcode 的发现与校正流程

实现反汇编器时，一旦遇到当前表无法解析的 opcode，必须按以下顺序排查：

1. 检查上一条指令长度是否错误。SDT 为可变长指令流，长度误判会造成连锁错位。
2. 若 opcode `< 0x2A`，回看 `sub_459150` 对应 case 与具体 handler，例如 `sub_4593B0`、`sub_459410` 等。
3. 若 opcode `>= 0x40`，从 `byte_53B080 + 17*(opcode-64)` 导出参数描述，检查是否是外部命令。
4. 若 opcode 在 `0x2A..0x3F`，当前 `sub_4109C0` 会报告 `<64` 异常，需确认是否前序长度错误。
5. 将新确认的 opcode、长度规则、operand_schema、handler 证据回写到本文档。
6. 对全部样本重新执行反汇编，确认地址空间无空洞、无重叠、无未识别段。

## 10. 后续工具实现建议

### 10.1 `opcodelist.py`

应至少包含：

- SDT header 常量：magic、header size、entry count。
- 内置 opcode 表：opcode、mnemonic、handler、length 规则、operand_schema、jump target 字段。
- 外部命令表：从 `byte_53B080` 提取的 17 字节参数描述表、handler 名称、返回/等待策略。
- 参数 reader 定义：desc code `0..9` 到 parser 的映射。
- 比较操作码定义：`0:<, 1:<=, 2:>, 3:>=, 4:==, 5:!=`。

### 10.2 `disassembler.py`

核心流程：

1. 读取 SDT，校验 `LF` header。
2. 解析 `file_size`，确认等于实际文件大小。
3. 解析 entry[256]，非零 entry 转换为 label target `entry-1`；asm 只输出这些非零 entry。
4. 从 body offset 0 开始线性解析指令。
5. 按 opcode 表确定长度；外部命令使用参数描述表动态解析。
6. 收集跳转目标并生成 label。
7. 对每个结构化字符串参数使用指定编码输出，并用 `{{XX}}` 保护特殊字节。
8. 对未覆盖数据段输出伪指令，确保逐字节覆盖。

### 10.3 `assembler.py`

核心流程：

1. 读取 `.encoding`，默认 `cp932`。
2. 第一遍解析 label、显式 `.entry`、指令和伪指令，计算 body offset；未显式列出的 entry 槽位为 0。
3. 第二遍编码 opcode 和参数，解析 label relocation。
4. 字符串编码时保留 `{{XX}}` 占位符为原始字节。
5. 写出 header：`magic`、`file_size`、entry 表。
6. 拼接 body。
7. 与原文件执行 `sha256sum` 或 `diff` 验证零突变。

## 11. 全量官方 SDT 样本覆盖统计

按本文档的内置 opcode 长度规则、`update_sdt_md.py` 已抽取的 EXE 命令名表、`byte_53B080` 参数描述表和 `byte_53B08F` `return_flag` 表，对 `mes (1)/*.SDT` 执行线性结构化解析统计。

### 11.1 总体结果

- 扫描 `.SDT` 文件数：469 个。
- 成功完整解析：468 个。
- 未参与解析：1 个，`06003ymz.SDT` 为 0 字节空文件，无法通过 SDT header 校验。
- 成功解析样本 body 总字节数：2,770,699 字节。
- 非零 entry 数：468；所有非零 entry 均在对应 body 范围内，无越界 entry。
- 总指令数：100,753 条。
  - 内置 VM opcode：2,455 条。
  - 外部命令 opcode：98,298 条。
- 已观察到 opcode 种类：112 种。
- 已知 opcode 总数：241 种，包括内置 `0x0001..0x0028` 与外部命令 `0x0040..0x0108`。
- 未出现 opcode：129 种。
- 未识别 opcode：0 种。
- 解析错位/越界：0 处；除空文件外，所有样本均可按当前 opcode/参数表逐字节推进到 body 末尾。

出现次数最高的 opcode：

| opcode | 次数 | 覆盖文件数 | 名称 |
|---:|---:|---:|---|
| `0x008C` | 17,963 | 256 | `VV` |
| `0x00A5` | 15,501 | 283 | `SetMessage2` |
| `0x007C` | 9,845 | 277 | `W` |
| `0x00F0` | 7,071 | 257 | `Mov2` |
| `0x00A9` | 6,355 | 250 | `AddMessage2` |
| `0x0074` | 6,042 | 258 | `C` |
| `0x0054` | 3,748 | 275 | `SetMapChar` |
| `0x00C3` | 2,952 | 379 | `WaitFrame` |
| `0x007E` | 2,944 | 171 | `WN` |
| `0x0075` | 2,672 | 234 | `CR` |

### 11.2 内置 opcode 覆盖

已出现内置 opcode：

```text
0x0001(470) 0x0002(4) 0x0003(77) 0x0005(75) 0x0006(237)
0x0007(595) 0x000B(195) 0x000C(259) 0x0010(1) 0x0011(3)
0x0013(2) 0x0017(2) 0x0019(10) 0x0025(57) 0x0027(468)
```

未出现内置 opcode：

```text
0x0004 0x0008 0x0009 0x000A 0x000D 0x000E 0x000F 0x0012
0x0014 0x0015 0x0016 0x0018 0x001A 0x001B 0x001C 0x001D
0x001E 0x001F 0x0020 0x0021 0x0022 0x0023 0x0024 0x0026 0x0028
```

`EVAL_EXPR(0x0020)` 在官方样本中未出现，但其结构和子 opcode 已由 `sub_459880` 静态确认，见 6.1.1。

### 11.3 外部命令覆盖

已出现外部命令 opcode：

```text
0x0040(366) 0x0041(206) 0x0042(408) 0x0043(122) 0x0045(2)
0x0046(31) 0x0047(26) 0x0048(10) 0x0049(121) 0x004A(119)
0x004B(54) 0x004C(1126) 0x004D(772) 0x004E(87) 0x004F(1291)
0x0050(156) 0x0051(154) 0x0052(2) 0x0053(7) 0x0054(3748)
0x0055(183) 0x0056(48) 0x0057(1668) 0x0058(133) 0x0059(443)
0x005A(1344) 0x005B(104) 0x005C(1717) 0x005D(426) 0x005E(220)
0x005F(1252) 0x0061(154) 0x0063(255) 0x0065(321) 0x0072(154)
0x0074(6042) 0x0075(2672) 0x0076(49) 0x007C(9845) 0x007D(1325)
0x007E(2944) 0x0080(16) 0x0081(627) 0x0082(509) 0x0084(16)
0x0085(1) 0x0086(435) 0x0087(440) 0x0088(297) 0x0089(107)
0x008A(29) 0x008C(17963) 0x0092(4) 0x0093(428) 0x009A(1898)
0x009B(272) 0x009C(54) 0x009E(216) 0x00A1(173) 0x00A2(34)
0x00A3(39) 0x00A5(15501) 0x00A9(6355) 0x00AD(44) 0x00AF(10)
0x00BB(31) 0x00BC(12) 0x00BD(19) 0x00C3(2952) 0x00C4(93)
0x00C8(199) 0x00CA(106) 0x00CC(37) 0x00CD(111) 0x00CE(12)
0x00D0(10) 0x00D1(2) 0x00D2(2) 0x00D3(282) 0x00D5(243)
0x00D6(8) 0x00D7(65) 0x00D8(177) 0x00D9(1) 0x00DA(15)
0x00DB(169) 0x00DE(295) 0x00DF(10) 0x00F0(7071) 0x00F1(26)
0x00F2(12) 0x00F5(704) 0x00F6(12) 0x0102(14) 0x0103(1)
0x0104(28) 0x0105(4)
```

未出现外部命令 opcode：

```text
0x0044 0x0060 0x0062 0x0064 0x0066 0x0067 0x0068 0x0069
0x006A 0x006B 0x006C 0x006D 0x006E 0x006F 0x0070 0x0071
0x0073 0x0077 0x0078 0x0079 0x007A 0x007B 0x007F 0x0083
0x008B 0x008D 0x008E 0x008F 0x0090 0x0091 0x0094 0x0095
0x0096 0x0097 0x0098 0x0099 0x009D 0x009F 0x00A0 0x00A4
0x00A6 0x00A7 0x00A8 0x00AA 0x00AB 0x00AC 0x00AE 0x00B0
0x00B1 0x00B2 0x00B3 0x00B4 0x00B5 0x00B6 0x00B7 0x00B8
0x00B9 0x00BA 0x00BE 0x00BF 0x00C0 0x00C1 0x00C2 0x00C5
0x00C6 0x00C7 0x00C9 0x00CB 0x00CF 0x00D4 0x00DC 0x00DD
0x00E0 0x00E1 0x00E2 0x00E3 0x00E4 0x00E5 0x00E6 0x00E7
0x00E8 0x00E9 0x00EA 0x00EB 0x00EC 0x00ED 0x00EE 0x00EF
0x00F3 0x00F4 0x00F7 0x00F8 0x00F9 0x00FA 0x00FB 0x00FC
0x00FD 0x00FE 0x00FF 0x0100 0x0101 0x0106 0x0107 0x0108
```

`default/no explicit handler` 覆盖结果：

- EXE 命令表中 `handler=default/no explicit handler` 的外部命令共有 71 个。
- 全量官方样本中实际出现数量：0 个。
- 因此官方样本未覆盖任何 default/no explicit handler 命令；这些命令仍可由命令名表和参数描述表解析长度，运行语义按 `sub_4101C0` default 路径理解：不调用专用 handler，仅执行通用 `sub_410F00` 后处理并返回 `byte_53B08F` 对应 `return_flag`。

`nullsub_*` handler 覆盖结果：

- 样本中实际出现 `nullsub_*` 命令数量：0 个。
- 未出现的 `nullsub_*` 命令为：`BT(0x0060)`、`BCT(0x0062)`、`VT(0x0064)`、`HT(0x0066)`、`S(0x0067)`、`Z(0x0068)`、`SetMapBox(0x00F7)`。

### 11.4 `return_flag/aux` 运行期影响

外部命令 `return_flag` 分布：

| return_flag | 指令数 |
|---:|---:|
| `0` | 38,102 |
| `1` | 60,196 |

外部命令 `aux` 分布：

| aux | 指令数 |
|---:|---:|
| `0` | 38,053 |
| `1` | 6,577 |
| `2` | 18,112 |
| `3` | 9,320 |
| `5` | 18,212 |
| `7` | 8,024 |

`return_flag/aux` 联合分布：

| return_flag | aux | 指令数 |
|---:|---:|---:|
| `0` | `0` | 26,056 |
| `0` | `1` | 1,350 |
| `0` | `2` | 2,672 |
| `0` | `7` | 8,024 |
| `1` | `0` | 11,997 |
| `1` | `1` | 5,227 |
| `1` | `2` | 15,440 |
| `1` | `3` | 9,320 |
| `1` | `5` | 18,212 |

结论：

- 外部命令的静态长度完全由 `byte_53B080` 参数描述表和实际参数编码决定，统计中未发现 `return_flag` 或 `aux` 改变指令切分长度的情况。
- `return_flag` 是 `sub_4101C0` 返回给 `sub_459150` 的继续执行标志，影响 VM 是否在当前帧继续 `while (sub_459150(0))` 循环；不参与参数长度计算。
- `aux` 在当前解析层面不影响指令长度或线性推进；相同 `aux` 下仍可能出现多种长度，长度差异来自 `typed_i32` mode、`str8/str16` 字符串长度等变长参数。
- 具体 `ip` 推进仍由各 handler 根据 `dword_66B42C` 执行；多数外部命令推进 `ip += dword_66B42C`，等待/显示类 handler 可延迟推进，但其结构长度仍为 `dword_66B42C`。

## 12. 当前置信边界

高置信：

- SDT header 与 entry 表结构。
- body 起点 `0x408`。
- entry 表 1-based 偏移规则。
- opcode 为 16-bit little-endian。
- `opcode < 0x2A` 与 `opcode >= 0x2A` 的分发边界。
- 内置 opcode `0x0001..0x0028` 的长度、操作数字段与跳转字段。
- `EVAL_EXPR(0x0020)` 的表达式 packet 边界、token 子格式和 operator 子码。
- 外部命令 `0x0040..0x0108` 的命令名表、参数描述表、handler/default/nullsub 分类。
- 外部命令参数描述表基址 `0x53B080` 与 17 字节 stride。
- 参数描述码 `0..9` 的 reader 行为。
- `return_flag` 影响当前帧 VM 连续执行，`aux` 不参与结构长度计算。
- 局部变量区 `+0xC00` 与 50 个 DWORD 的清零范围。
- 对 468 个非空官方 SDT 样本的线性解析无未识别 opcode、无错位、无越界。

工具实现可以基于本文档进入 `opcodelist.py`、`disassembler.py`、`assembler.py` 阶段：未出现或未覆盖运行期专用 handler 的命令保持 EXE 命令原名/handler/default 标注即可，但长度、操作数、标签重定位和字符串占位符必须按本文档精确实现。
