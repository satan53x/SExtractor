# Malie .mls 反汇编 / 汇编工具

面向 *僕と、僕らの夏 完全版*（`bokudvd.exe`）的 `scenario/*.mls`。

## 文件

| 文件 | 说明 |
|------|------|
| `opcodelist.py` | 容器格式、关键字表、文本编解码、`{{XX}}` |
| `disassembler.py` | `.mls` → 语义 `asm.txt` |
| `assembler.py` | `asm.txt` → `.mls`（默认 zlib level 6） |
| `vm_analysis.md` | VM/格式分析真值源 |
| `asm.txt` | `s23.mls` 示例输出 |

## 用法

```bash
# 目录批处理
python disassembler.py bin txt
python assembler.py txt bin

# 单文件
python disassembler.py sample.mls -o sample.asm.txt --encoding cp932
python assembler.py sample.asm.txt -o sample.rebuild.mls --encoding cp932
```

## 验收

官方 `scenario` 下 37 个 `.mls` 反汇编再汇编后 **SHA/字节完全一致**。
