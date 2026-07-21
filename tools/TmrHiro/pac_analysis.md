# srp.pac 格式分析

来源：`FCS.exe` 中的 `sub_40E2E0`（`decompile/40E2E0.c`）。  
样本：`srp.pac`（724784 bytes，27 个条目）。

## 容器结构

小端序，无魔数，无压缩，无容器层加密。

```
offset  size  field
0x00    2     entry_count   (u16)
0x02    1     name_len      (u8)  固定宽文件名字段长度
0x03    4     data_base     (u32) 第一个文件数据的绝对偏移
0x07    N     directory     entry_count * (name_len + 4)
data_base ... payload 顺序拼接
```

### 目录项

```
name[name_len]   ASCII，0 填充；引擎用 sub_40E430 转小写后 strcmp
rel_offset (u32) 绝对偏移 = data_base + rel_offset
```

### 大小

目录不存 size。用相邻条目的绝对偏移差得到 size；最后一项到 EOF。

`srp.pac` 中：`name_len=8`，`data_base == index_end == 0x14B`（无目录/数据间隙）。

## 查找逻辑（游戏内）

1. 读 `entry_count`、`name_len`、`data_base`
2. 查询名转小写
3. 逐项读 name + rel_offset，name 转小写后比较
4. 命中则返回 `data_base + rel_offset`

相关调用：

- `sub_4150D0`：按资源类型选择 loose 文件或 `*.pac` / `*_2.pac`
- `sub_409F10`：加载脚本（类型 9 → `srp.pac` / `script/%s.txt` / `script/%s.sct`）

## 脚本载荷（下一阶段，非 PAC 层）

PAC 解出的每个文件不是裸文本，而是：

```
u32 line_count
line_1 + 0x0A
line_2 + 0x0A
...
line_N + 0x0A
```

每行正文在 `sub_40E1E0` 中按字节解密（直到 `0x0A`）：

```
x = b ^ 0x0A
b' = ((x << 4) | ((x >> 4) & 0x0F)) & 0xFF   # 即 nibble swap(x)
```

解密后仍是脚本字节码/文本行（如含 `0xA0` 前缀等），完整指令集反汇编属于下一步。

## 工具用法

依赖标准库，Python 3.10+。

```text
# 列出并解包
python pac_unpack.py srp.pac
python pac_unpack.py srp.pac srp_extracted
python pac_unpack.py srp.pac -l

# 从解包目录封包（读取 _pac_index.txt 保序/保名字段）
python pac_pack.py srp_extracted srp_repack.pac

# 直接从原包恒等重建
python pac_pack.py --from-pac srp.pac srp_rebuild.pac
```

## 验收

对 `srp.pac`：

- `pac_pack.py --from-pac` 输出与原文件 **逐字节一致**
- `unpack → pack_from_dir` 输出与原文件 **逐字节一致**

## 交付文件

| 文件 | 作用 |
|------|------|
| `pac_format.py` | 解析 / 构建核心库 |
| `pac_unpack.py` | 解包 / 列表 CLI |
| `pac_pack.py` | 封包 / 恒等重建 CLI |
| `pac_analysis.md` | 本格式说明 |

解包目录会生成 `_pac_index.txt`，记录顺序、`name_len`、`name_raw` 十六进制，保证可 round-trip。
