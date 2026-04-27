# -*- coding: utf-8 -*-
"""
AVC 引擎 (Adv.exe / SETSUEI 系列) 归档格式 codec

格式布局 (基于 Adv.exe 反编译 + 参考 GARbro ArcAVC.cs):

  偏移         大小      内容
  --------------------------------------------------------------
  0x00..0x08   8         skipped (引擎读两次4*2但被覆盖,内容无关)
  0x08..0x10   8         key 推导区: file_bytes ^ "SETSUEI-" => key
  0x10..0x34   0x24      header (用 key 异或加密)
                         [0x00..0x08] = "ARCHIVE\0"
                         [0x08..0x0c] = 0
                         [0x0c..0x10] = 0x24 (header 大小)
                         [0x10..0x14] = index_offset (相对 0x10)
                         [0x14..0x18] = entry_size (固定 0x114)
                         [0x18..0x20] = 0
                         [0x20..0x24] = entry_count
  0x34..        ...       数据区 (用 key 异或, i = phys - 0x10)
  index_off+0x10..        index 表 (count * 0x114, 用 key 异或, i 同上)

每个 entry (0x114 字节):
  [0x000]      = 0  (marker)
  [0x001..0x108] = 文件名 cp932 + NUL 填充 (0x107 字节)
  [0x108..0x10c] = offset (相对 0x10)
  [0x10c..0x110] = size
  [0x110..0x114] = extra (恒为 0)

注意: entry.offset 是相对偏移, 物理偏移 = entry.offset + 0x10
"""
import struct

PASSWORD       = b"SETSUEI-"      # 8 字节固定密码
HEADER_OFFSET  = 0x10             # header 在文件中的物理偏移
KEY_OFFSET     = 0x08             # key 推导区在文件中的物理偏移
HEADER_SIZE    = 0x24             # header 区大小
ENTRY_SIZE     = 0x114            # 每个 index entry 大小
NAME_AREA      = 0x107            # 文件名区大小 (含 NUL 终止)
DATA_BASE      = HEADER_OFFSET + HEADER_SIZE   # 0x34, 数据区起始物理偏移
ARCHIVE_MAGIC  = b"ARCHIVE\0"


def derive_key(file_bytes_at_8: bytes) -> bytes:
    """从文件 0x08..0x10 处的 8 字节 ⊕ password 得到 key"""
    assert len(file_bytes_at_8) == 8
    return bytes(file_bytes_at_8[i] ^ PASSWORD[i] for i in range(8))


def encode_key_region(key: bytes) -> bytes:
    """反向: 从 key 得到要写入文件 0x08..0x10 处的 8 字节"""
    assert len(key) == 8
    return bytes(key[i] ^ PASSWORD[i] for i in range(8))


def xor_with_key(data: bytes, key: bytes, start_index: int) -> bytes:
    """用 key 异或一段数据, start_index 决定 key 循环起点 ((start+i)&7)"""
    out = bytearray(data)
    for i in range(len(out)):
        out[i] ^= key[(start_index + i) & 7]
    return bytes(out)


def parse_header(decrypted_header: bytes):
    """解析已解密的 0x24 字节 header, 返回 (index_offset, entry_size, count)"""
    if decrypted_header[:8] != ARCHIVE_MAGIC:
        raise ValueError(f"Header magic 校验失败, 得到: {decrypted_header[:8]!r}")
    index_offset = struct.unpack_from('<I', decrypted_header, 0x10)[0]
    entry_size   = struct.unpack_from('<I', decrypted_header, 0x14)[0]
    count        = struct.unpack_from('<I', decrypted_header, 0x20)[0]
    if entry_size != ENTRY_SIZE:
        raise ValueError(f"entry_size 异常: 0x{entry_size:x}, 期望 0x{ENTRY_SIZE:x}")
    return index_offset, entry_size, count


def build_header(index_offset: int, count: int) -> bytes:
    """构建明文 header (0x24 字节)"""
    h = bytearray(HEADER_SIZE)
    h[0:8] = ARCHIVE_MAGIC
    # 0x08..0x0c 留 0
    struct.pack_into('<I', h, 0x0c, HEADER_SIZE)   # 0x24, header 大小标记
    struct.pack_into('<I', h, 0x10, index_offset)
    struct.pack_into('<I', h, 0x14, ENTRY_SIZE)
    # 0x18, 0x1c 留 0
    struct.pack_into('<I', h, 0x20, count)
    return bytes(h)


def parse_entry(entry_bytes: bytes):
    """解析 0x114 字节的 entry, 返回 (name, offset, size) 或 None (空 entry)"""
    if entry_bytes[0] != 0:
        return None  # marker 异常
    name_bytes = bytearray()
    for i in range(NAME_AREA - 1):  # 最多 0x106 个名字字符 + 1 终止
        b = entry_bytes[1 + i]
        if b == 0:
            break
        name_bytes.append(b)
    if len(name_bytes) == 0:
        return None  # 空 entry
    try:
        name = bytes(name_bytes).decode('cp932')
    except UnicodeDecodeError:
        name = bytes(name_bytes).decode('cp932', errors='replace')
    offset = struct.unpack_from('<I', entry_bytes, 0x108)[0]
    size   = struct.unpack_from('<I', entry_bytes, 0x10c)[0]
    return name, offset, size


def build_entry(name: str, offset: int, size: int) -> bytes:
    """构建 0x114 字节的 entry"""
    name_bytes = name.encode('cp932')
    if len(name_bytes) >= NAME_AREA:
        raise ValueError(f"文件名 cp932 编码后过长 (>= 0x{NAME_AREA:x}): {name}")
    e = bytearray(ENTRY_SIZE)
    # [0] marker = 0 (默认)
    # [1..1+len] 文件名
    e[1:1 + len(name_bytes)] = name_bytes
    # 后续 NUL 填充已默认
    struct.pack_into('<I', e, 0x108, offset)
    struct.pack_into('<I', e, 0x10c, size)
    # 0x110..0x114 留 0
    return bytes(e)
