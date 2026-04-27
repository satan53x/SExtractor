# -*- coding: utf-8 -*-
"""
AVC 引擎归档解包工具
用法:
    python avc_extract.py <input.dat> <output_dir>
    python avc_extract.py <input.dat> <output_dir> --save-key <key.bin>

输出:
    将归档内每个文件释放到 output_dir;
    可选 --save-key 保存 key (8字节二进制),
    封包时使用 --use-key 即可保持二进制一致。
"""
import sys
import os
import struct
import argparse
from avc_codec import (
    PASSWORD, HEADER_OFFSET, KEY_OFFSET, HEADER_SIZE, ENTRY_SIZE,
    DATA_BASE, derive_key, xor_with_key, parse_header, parse_entry,
)


def extract(arc_path: str, out_dir: str, key_save_path: str = None,
            verbose: bool = True) -> int:
    with open(arc_path, 'rb') as f:
        data = f.read()

    if len(data) < DATA_BASE:
        raise ValueError(f"文件过小: 0x{len(data):x}")

    # 1. 推导 key
    key = derive_key(data[KEY_OFFSET:KEY_OFFSET + 8])
    if verbose:
        print(f"[KEY] {key.hex()}")

    # 2. 解密 & 解析 header
    enc_hdr = data[HEADER_OFFSET:HEADER_OFFSET + HEADER_SIZE]
    dec_hdr = xor_with_key(enc_hdr, key, start_index=0)  # header 起始位置 i=0
    index_offset_rel, entry_size, count = parse_header(dec_hdr)
    if verbose:
        print(f"[HDR] index_offset(rel)=0x{index_offset_rel:x}  "
              f"entry_size=0x{entry_size:x}  count={count}")

    # 3. 解密 index 区
    index_phys = index_offset_rel + HEADER_OFFSET
    index_total = count * ENTRY_SIZE
    if index_phys + index_total > len(data):
        raise ValueError(
            f"index 区超出文件: 起点 0x{index_phys:x}, 大小 0x{index_total:x}, "
            f"文件大小 0x{len(data):x}")
    enc_idx = data[index_phys:index_phys + index_total]
    # XOR 起始 i = index_offset_rel (相对 header 偏移)
    dec_idx = xor_with_key(enc_idx, key, start_index=index_offset_rel)

    # 4. 遍历 entry
    os.makedirs(out_dir, exist_ok=True)
    extracted = 0
    skipped = 0
    for i in range(count):
        e = parse_entry(dec_idx[i * ENTRY_SIZE:(i + 1) * ENTRY_SIZE])
        if e is None:
            skipped += 1
            if verbose:
                print(f"  [{i:3}] (空 entry, 跳过)")
            continue
        name, off_rel, size = e
        phys = off_rel + HEADER_OFFSET
        if phys + size > len(data):
            raise ValueError(
                f"entry [{i}] {name} 越界: phys=0x{phys:x} size=0x{size:x}")

        enc = data[phys:phys + size]
        # XOR 起始 i = off_rel
        dec = xor_with_key(enc, key, start_index=off_rel)

        # 处理可能的子目录 (本游戏无, 但保险)
        safe_name = name.replace('\\', os.sep).replace('/', os.sep)
        out_path = os.path.join(out_dir, safe_name)
        os.makedirs(os.path.dirname(out_path) or '.', exist_ok=True)
        with open(out_path, 'wb') as wf:
            wf.write(dec)

        if verbose:
            print(f"  [{i:3}] {name:<35s} off=0x{off_rel:08x} size=0x{size:08x} -> {out_path}")
        extracted += 1

    if key_save_path:
        with open(key_save_path, 'wb') as kf:
            kf.write(key)
        if verbose:
            print(f"\n[KEY] 已保存到 {key_save_path}")

    if verbose:
        print(f"\n完成: 解出 {extracted} 个, 跳过空项 {skipped} 个")
    return extracted


def main():
    ap = argparse.ArgumentParser(description="AVC 引擎归档解包")
    ap.add_argument("input", help="输入 .dat 文件")
    ap.add_argument("output_dir", help="输出目录")
    ap.add_argument("--save-key", help="将 8 字节 key 保存到该路径", default=None)
    ap.add_argument("-q", "--quiet", action="store_true", help="静默模式")
    args = ap.parse_args()

    extract(args.input, args.output_dir, args.save_key, verbose=not args.quiet)


if __name__ == "__main__":
    main()
