# -*- coding: utf-8 -*-
"""
AVC 引擎归档封包工具
用法:
    # 用原始 dat 提取的 key 重新封包 (推荐, 可保持二进制一致):
    python avc_inject.py <input_dir> <output.dat> --use-key <key.bin>

    # 不指定 key 时,从原 dat 复制 key (再次推荐):
    python avc_inject.py <input_dir> <output.dat> --ref <original.dat>

    # 也可指定 8 字节 hex 形式的 key:
    python avc_inject.py <input_dir> <output.dat> --key-hex 877a000083580000

文件加入顺序:
    默认按文件名字典序排序 (与原 dat 顺序通常一致)。
    也可用 --order 指定一个 .txt 文件 (每行一个文件名,按该顺序)。

注意:
    - 文件名 cp932 编码长度必须 < 0x107
    - "skipped 8 bytes" (文件 0x00..0x08) 会写为 0; 不影响读取
    - 原 dat 中可能存在 marker != 0 或空名 entry, 此处不重建这种空位
"""
import sys
import os
import struct
import argparse
from avc_codec import (
    PASSWORD, HEADER_OFFSET, KEY_OFFSET, HEADER_SIZE, ENTRY_SIZE,
    DATA_BASE, derive_key, encode_key_region, xor_with_key,
    build_header, build_entry,
)


def load_key_from_ref(ref_path: str) -> bytes:
    with open(ref_path, 'rb') as f:
        data = f.read(KEY_OFFSET + 8)
    if len(data) < KEY_OFFSET + 8:
        raise ValueError(f"参考 dat 过小: {ref_path}")
    return derive_key(data[KEY_OFFSET:KEY_OFFSET + 8])


def load_skip_bytes_from_ref(ref_path: str) -> bytes:
    """读取参考 dat 的前 8 字节 skipped 区,用于 round-trip 一致"""
    with open(ref_path, 'rb') as f:
        return f.read(8)


def load_entry_paddings_from_ref(ref_path: str):
    """从参考 dat 读取每个 entry 的明文 padding 区
    返回 dict[name] -> bytes (entry 的 0x000..0x108 明文,即整个文件名 + 后续 padding)
    封包时若文件名相同,可复用此 padding 让 entry 字节级一致
    """
    from avc_codec import (KEY_OFFSET, HEADER_OFFSET, HEADER_SIZE,
                           ENTRY_SIZE, derive_key, xor_with_key,
                           parse_header, parse_entry)
    with open(ref_path, 'rb') as f:
        data = f.read()
    key = derive_key(data[KEY_OFFSET:KEY_OFFSET + 8])
    hdr = xor_with_key(data[HEADER_OFFSET:HEADER_OFFSET + HEADER_SIZE], key, 0)
    idx_off, _, count = parse_header(hdr)
    phys = idx_off + HEADER_OFFSET
    enc = data[phys:phys + count * ENTRY_SIZE]
    dec = xor_with_key(enc, key, idx_off)
    result = {}
    for i in range(count):
        e = parse_entry(dec[i * ENTRY_SIZE:(i + 1) * ENTRY_SIZE])
        if e is None:
            continue
        name = e[0]
        # 保留 entry 0x000..0x108 区: marker + 文件名 + 填充
        result[name] = bytes(dec[i * ENTRY_SIZE:i * ENTRY_SIZE + 0x108])
    return result


def collect_files(in_dir: str, order_file: str = None):
    """返回 [(rel_name, abs_path), ...]"""
    if order_file:
        items = []
        with open(order_file, 'r', encoding='utf-8') as f:
            for line in f:
                name = line.strip()
                if not name:
                    continue
                ap = os.path.join(in_dir, name)
                if not os.path.isfile(ap):
                    raise FileNotFoundError(f"order 文件中列出的文件不存在: {ap}")
                items.append((name, ap))
        return items

    # 自动收集 (递归)
    items = []
    for root, _, files in os.walk(in_dir):
        for fn in files:
            ap = os.path.join(root, fn)
            rel = os.path.relpath(ap, in_dir).replace(os.sep, '\\')
            items.append((rel, ap))
    items.sort(key=lambda x: x[0])
    return items


def pack(in_dir: str, out_path: str, key: bytes,
         order_file: str = None, ref_dat: str = None,
         verbose: bool = True) -> int:
    items = collect_files(in_dir, order_file)
    if not items:
        raise ValueError(f"在 {in_dir} 下没找到任何文件")
    count = len(items)

    if verbose:
        print(f"[KEY]  {key.hex()}")
        print(f"[FILES] {count} 个")

    # 如有 ref, 尝试加载 padding 与 skip 区
    ref_paddings = {}
    ref_skip = None
    if ref_dat:
        ref_paddings = load_entry_paddings_from_ref(ref_dat)
        ref_skip = load_skip_bytes_from_ref(ref_dat)
        if verbose:
            print(f"[REF]  {ref_dat}: 加载到 {len(ref_paddings)} 个 entry padding")

    # 阶段 1: 准备每个 entry 的 (name, raw_data)
    raw_entries = []
    for name, ap in items:
        with open(ap, 'rb') as f:
            raw_entries.append((name, f.read()))

    # 阶段 2: 计算物理布局
    cursor_phys = DATA_BASE
    entry_meta = []
    for name, raw in raw_entries:
        off_rel = cursor_phys - HEADER_OFFSET
        sz = len(raw)
        entry_meta.append((name, off_rel, sz, raw))
        cursor_phys += sz

    index_phys = cursor_phys
    index_offset_rel = index_phys - HEADER_OFFSET
    total_size = index_phys + count * ENTRY_SIZE

    if verbose:
        print(f"[LAY]  data: 0x{DATA_BASE:x} .. 0x{index_phys:x}  "
              f"index: 0x{index_phys:x} .. 0x{total_size:x}")

    # 阶段 3: 构建并加密各部分
    out = bytearray(total_size)

    # 3.1 file 0x00..0x08: skipped (引擎不读)
    if ref_skip is not None:
        out[0:8] = ref_skip

    # 3.2 file 0x08..0x10: key 推导区
    out[KEY_OFFSET:KEY_OFFSET + 8] = encode_key_region(key)

    # 3.3 file 0x10..0x34: 加密 header
    plain_hdr = build_header(index_offset_rel, count)
    enc_hdr = xor_with_key(plain_hdr, key, start_index=0)
    out[HEADER_OFFSET:HEADER_OFFSET + HEADER_SIZE] = enc_hdr

    # 3.4 数据区
    for name, off_rel, sz, raw in entry_meta:
        phys = off_rel + HEADER_OFFSET
        enc = xor_with_key(raw, key, start_index=off_rel)
        out[phys:phys + sz] = enc

    # 3.5 index 表
    plain_idx = bytearray(count * ENTRY_SIZE)
    matched_pad = 0
    for i, (name, off_rel, sz, _) in enumerate(entry_meta):
        e = bytearray(ENTRY_SIZE)
        if name in ref_paddings:
            # 复用原 dat 的整个 0x108 区 (含 marker / name / padding)
            e[0:0x108] = ref_paddings[name]
            matched_pad += 1
        else:
            built = build_entry(name, 0, 0)  # offset/size 后面再填
            e[0:0x108] = built[0:0x108]
        # 写 offset/size (覆盖 0x108..0x114)
        struct.pack_into('<I', e, 0x108, off_rel)
        struct.pack_into('<I', e, 0x10c, sz)
        # [0x110..0x114] = 0 默认
        plain_idx[i * ENTRY_SIZE:(i + 1) * ENTRY_SIZE] = e
    enc_idx = xor_with_key(bytes(plain_idx), key, start_index=index_offset_rel)
    out[index_phys:index_phys + count * ENTRY_SIZE] = enc_idx

    if verbose and ref_paddings:
        print(f"[PAD]  从参考 dat 复用了 {matched_pad}/{count} 个 entry 的 padding")

    with open(out_path, 'wb') as f:
        f.write(out)

    if verbose:
        for name, off_rel, sz, _ in entry_meta:
            print(f"  + {name:<35s} off=0x{off_rel:08x} size=0x{sz:08x}")
        print(f"\n完成: {out_path}  总大小 0x{total_size:x}")
    return total_size


def main():
    ap = argparse.ArgumentParser(description="AVC 引擎归档封包")
    ap.add_argument("input_dir", help="输入目录 (含要打包的文件)")
    ap.add_argument("output", help="输出 .dat 路径")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--use-key", help="从二进制文件读 8 字节 key")
    g.add_argument("--ref", help="从一个原始 dat 提取并复用 key/skip-bytes/padding (推荐: 严格 round-trip)")
    g.add_argument("--key-hex", help="直接给定 8 字节 key 的 hex 串 (16 字符)")
    ap.add_argument("--order", help="可选: 指定文件加入顺序的 .txt", default=None)
    ap.add_argument("-q", "--quiet", action="store_true", help="静默模式")
    args = ap.parse_args()

    ref_dat = None
    if args.use_key:
        with open(args.use_key, 'rb') as f:
            key = f.read(8)
        if len(key) != 8:
            sys.exit("key 文件大小不是 8 字节")
    elif args.ref:
        key = load_key_from_ref(args.ref)
        ref_dat = args.ref
    else:
        h = args.key_hex.strip()
        if len(h) != 16:
            sys.exit("--key-hex 必须是 16 个 hex 字符")
        key = bytes.fromhex(h)

    pack(args.input_dir, args.output, key, args.order, ref_dat,
         verbose=not args.quiet)


if __name__ == "__main__":
    main()
