#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Softpal Lazy 引擎 VCT 容器解包工具
格式:
  u8  ext_count
  {char letter, u16 first_entry_idx}[ext_count]   (首字母索引加速表)
  u32 entry_count
  {char name[0x14], char ext[0x04], u32 offset, u32 size}[entry_count]
  raw data...
"""
import os
import sys
import struct
import json


def extract_vct(vct_path: str, out_dir: str):
    with open(vct_path, 'rb') as f:
        data = f.read()

    pos = 0
    ext_count = data[pos]; pos += 1

    ext_table = []
    for i in range(ext_count):
        ch = chr(data[pos])
        idx = data[pos+1] | (data[pos+2] << 8)
        ext_table.append({'char': ch, 'first_idx': idx})
        pos += 3

    entry_count = struct.unpack_from('<I', data, pos)[0]; pos += 4
    index_start = pos

    os.makedirs(out_dir, exist_ok=True)
    entries = []
    skipped = 0
    for i in range(entry_count):
        off = index_start + i * 0x20
        rec = data[off:off+0x20]
        name_raw = rec[:0x14]
        ext_raw = rec[0x14:0x18]
        file_off, file_size = struct.unpack_from('<II', rec, 0x18)

        # 名字采用 ASCII 解码; 空格 strip
        name = name_raw.decode('ascii', errors='replace').rstrip(' \x00')
        ext  = ext_raw.decode('ascii', errors='replace').rstrip(' \x00')

        if not name:
            # 空槽 - 引擎逻辑里全空格被视为占位
            skipped += 1
            entries.append({'idx': i, 'name': '', 'ext': '', 'offset': file_off, 'size': file_size, 'empty': True})
            continue

        # 写文件
        full = f"{name}.{ext}" if ext else name
        out_path = os.path.join(out_dir, full)
        with open(out_path, 'wb') as g:
            g.write(data[file_off:file_off+file_size])

        entries.append({
            'idx': i,
            'name': name,
            'ext': ext,
            'offset': file_off,
            'size': file_size,
            'empty': False,
        })

    # 保存元信息以便完美回包
    meta = {
        'ext_count': ext_count,
        'ext_table': ext_table,
        'entry_count': entry_count,
        'entries': entries,
    }
    with open(os.path.join(out_dir, '_vct_meta.json'), 'w', encoding='utf-8') as g:
        json.dump(meta, g, indent=2, ensure_ascii=False)

    print(f"[OK] extracted {entry_count - skipped} files (+ {skipped} empty slots) -> {out_dir}")


if __name__ == '__main__':
    if len(sys.argv) != 3:
        print("Usage: vct_extract.py <input.VCT> <output_dir>")
        sys.exit(1)
    extract_vct(sys.argv[1], sys.argv[2])
