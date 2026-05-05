#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Softpal Lazy 引擎 VCT 容器封包工具

策略:
  - 优先读取 _vct_meta.json (解包时保存) 来 1:1 重建结构
  - 没有元信息时, 自动按文件名首字母排序并重建 ext_table
"""
import os
import sys
import struct
import json


def pad_to(s: bytes, n: int, pad=b' ') -> bytes:
    if len(s) > n:
        raise ValueError(f"field too long: {s!r} (max {n})")
    return s + pad * (n - len(s))


def pack_vct(in_dir: str, out_path: str):
    meta_path = os.path.join(in_dir, '_vct_meta.json')
    if os.path.exists(meta_path):
        with open(meta_path, 'r', encoding='utf-8') as f:
            meta = json.load(f)
        return pack_with_meta(in_dir, out_path, meta)
    else:
        return pack_auto(in_dir, out_path)


def pack_with_meta(in_dir: str, out_path: str, meta: dict):
    """带元信息: 严格按原顺序/原首字母表重建, 保证 round-trip"""
    ext_count = meta['ext_count']
    ext_table = meta['ext_table']
    entries = meta['entries']

    # === 写头部 ===
    header = bytearray()
    header.append(ext_count)
    for et in ext_table:
        header.append(ord(et['char']))
        header += struct.pack('<H', et['first_idx'])
    header += struct.pack('<I', len(entries))

    index_size = len(entries) * 0x20
    data_start = len(header) + index_size

    # === 数据块按原始物理偏移顺序排放 (保证 round-trip) ===
    # 1. 先按原 offset 排序, 给每个非空 entry 计算新偏移
    real_entries = [e for e in entries if not e['empty']]
    physical_order = sorted(real_entries, key=lambda e: e['offset'])

    new_offsets = {}  # idx -> new offset
    contents    = {}  # idx -> bytes
    cur_off = data_start
    data_blob = bytearray()
    for e in physical_order:
        full = f"{e['name']}.{e['ext']}" if e['ext'] else e['name']
        path = os.path.join(in_dir, full)
        with open(path, 'rb') as f:
            content = f.read()
        contents[e['idx']] = content
        new_offsets[e['idx']] = cur_off
        data_blob += content
        cur_off += len(content)

    # 2. 按 entry idx 顺序写 index 表
    index_records = []
    for e in entries:
        if e['empty']:
            # 空槽: 名字全空格, offset/size 保留原值
            name_field = pad_to(b'', 0x14)
            ext_field  = pad_to(b'', 0x04)
            index_records.append(name_field + ext_field +
                                 struct.pack('<II', e['offset'], e['size']))
        else:
            name_field = pad_to(e['name'].encode('ascii'), 0x14)
            ext_field  = pad_to(e['ext'].encode('ascii'),  0x04)
            new_off  = new_offsets[e['idx']]
            new_size = len(contents[e['idx']])
            index_records.append(name_field + ext_field +
                                 struct.pack('<II', new_off, new_size))

    out = bytes(header) + b''.join(index_records) + bytes(data_blob)
    with open(out_path, 'wb') as f:
        f.write(out)

    print(f"[OK] packed {len(entries)} entries -> {out_path} ({len(out)} bytes)")


def pack_auto(in_dir: str, out_path: str):
    """无元信息: 自动收集所有文件 + 按首字母排序 + 重建 ext_table"""
    files = []
    for fname in os.listdir(in_dir):
        if fname.startswith('_'):
            continue
        path = os.path.join(in_dir, fname)
        if not os.path.isfile(path):
            continue
        if '.' in fname:
            base, ext = fname.rsplit('.', 1)
        else:
            base, ext = fname, ''
        if len(base) > 0x14 or len(ext) > 0x04:
            print(f"[skip] name too long: {fname}")
            continue
        files.append((base.upper(), ext.upper(), path))

    # 按 (首字母, base) 排序 - 同首字母内部按字母序
    files.sort(key=lambda x: (x[0][:1], x[0]))

    # 构建 ext_table: 每个首字母 -> 该首字母首次出现的 entry idx
    # 注意原始格式中首字母排列顺序看似与文件无关 (是分桶顺序), 这里按出现顺序记录
    ext_table = []
    seen = {}
    for i, (base, ext, _) in enumerate(files):
        if not base:
            continue
        ch = base[0]
        if ch not in seen:
            seen[ch] = i
            ext_table.append((ch, i))

    # 写头
    ext_count = len(ext_table)
    header = bytearray()
    header.append(ext_count)
    for ch, idx in ext_table:
        header.append(ord(ch))
        header += struct.pack('<H', idx)
    header += struct.pack('<I', len(files))

    index_size = len(files) * 0x20
    data_start = len(header) + index_size

    index_records = []
    data_blob = bytearray()
    cur_off = data_start
    for base, ext, path in files:
        with open(path, 'rb') as f:
            content = f.read()
        name_field = pad_to(base.encode('ascii'), 0x14)
        ext_field  = pad_to(ext.encode('ascii'),  0x04)
        index_records.append(name_field + ext_field +
                             struct.pack('<II', cur_off, len(content)))
        data_blob += content
        cur_off += len(content)

    out = bytes(header) + b''.join(index_records) + bytes(data_blob)
    with open(out_path, 'wb') as f:
        f.write(out)

    print(f"[OK] auto-packed {len(files)} entries -> {out_path} ({len(out)} bytes)")


if __name__ == '__main__':
    if len(sys.argv) != 3:
        print("Usage: vct_pack.py <input_dir> <output.VCT>")
        sys.exit(1)
    pack_vct(sys.argv[1], sys.argv[2])
