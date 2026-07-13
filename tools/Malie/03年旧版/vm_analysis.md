# Popotan exec.dat VM 分析定义文档

> 真值源：`popotandvd.exe` IDA 导出（`decompile/`、`memory/`、`strings.txt`）  
> 目标脚本：`bin/exec.dat`（约 9.65 MB）

## 0.1 VM 类型与体系结构

| 项目 | 结论 |
|------|------|
| 架构 | 自定义脚本 VM（非 x86 字节码） |
| 执行模型 | **流式指令 + 表达式求值**；控制流用标签表索引跳转 |
| 存储 | 哈佛式：数据段（全局变量）与代码段分离；另有只读表达式池 |
| 端序 | Little-endian |
| 编码 | 定长操作码 1 字节 + 按操作码决定的定长/变长操作数 |
| 宿主 | `popotandvd.exe`，启动时 `WinMain` → `sub_410460` → `sub_410FC0` → `sub_451B20` 加载 `.\data\exec.dat` |

核心函数：

- **加载** `sub_451B20`：按节解析 globals / labels / exprs / code
- **保存** `sub_451C40`：对称写回
- **发射** `sub_44FAA0`：编译器将源语言语句写成 code 字节流
- **解释** `sub_452910`：主调度循环
- **关键字表** `off_4759E8`（`sub_450A50` 二分查找，39 项）

## 0.2 文件总体布局

```
u32 global_count
Global[global_count]
u32 data_size
u32 label_count
Label[label_count]
u32 expr_count
ExprNode[expr_count]
u32 code_size
u8  code[code_size]
```

### Global
LenString name; TypeNode type_chain; u32 flags; u32 reserved; u32 offset

### TypeNode
u32 kind; if kind!=0: u32 value; TypeNode next

### Label
LenString name; u32 code_offset  (相对 code[0])

### ExprNode
- 84 T null
- 85 U identifier (LenString)
- 86 V int (u32)
- 87 W string (LenString)
- else binary (left, right)

常用: 88 CALL, 89 ARG, 101-105 算术, 108-113 比较, 120 ASSIGN

## 0.3 字节码

关键字 1-39 见 opcode.py（bgm/call/jump/image/pause/...）。

操作数型：
- 41 arg_end
- 42/43/47 text_* + cstring
- 44/45/46 num_* + u32
- 48 eval + expr_index
- 49 str + cstring
- 50 arg + label_index
- 52 fstore_imm + u32
- 53/54/55 jmp/jz/jnz + label_index

跳转操作数是标签**下标**，不是偏移。

## 0.4 样例实测 (bin/exec.dat)
- globals=327 data_size=2460
- labels=8780
- exprs=99784
- code_size=2103352
- 无加密

## 0.5 工具
- opcode.py / disassembler.py / assembler.py
- 默认编码 cp932；特殊字节 {{XX}}