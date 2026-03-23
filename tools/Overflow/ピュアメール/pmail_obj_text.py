#!/usr/bin/env python3
"""
pmail_obj_text.py - Overflow/ピュアメール OBJ脚本 文本提取/导入工具

OBJ文件结构:
  +0x00  u16 LE  指令区偏移 (instr_offset)
  +0x02  u16 LE  字符串条目数 (n_entries)
  +0x04  字符串索引表 (n_entries × 4B: u16 data_offset + u16 size_with_null)
  [索引表后] 字符串数据区 (cp932, \0 终止)
  [instr_offset ~] 指令区 (u32 LE 字节码, 通过 0x80 mask 引用字符串索引)

提取格式: GalTransl JSON (UTF-8)
  [
    { "name": "角色名", "message": "台词", "_idx": 0 },
    ...
  ]

用法:
  python pmail_obj_text.py extract  input.obj  [output.json]
  python pmail_obj_text.py insert   input.obj  input.json  [output.obj]
  python pmail_obj_text.py batch_e  obj_dir    [json_dir]
  python pmail_obj_text.py batch_i  obj_dir    json_dir    [out_dir]
"""

import struct
import sys
import os
import re
import json


# ============================================================
# OBJ 解析 / 重建
# ============================================================
def parse_obj(data):
    """解析OBJ文件，返回 (entries, instr_offset, instr_data)"""
    instr_off = struct.unpack_from('<H', data, 0)[0]
    n_entries = struct.unpack_from('<H', data, 2)[0]

    entries = []
    for i in range(n_entries):
        base = 4 + i * 4
        str_off = struct.unpack_from('<H', data, base)[0]
        str_sz = struct.unpack_from('<H', data, base + 2)[0]
        raw = data[str_off:str_off + str_sz - 1] if str_sz > 1 else b''
        try:
            text = raw.decode('cp932')
        except:
            text = ''
        entries.append({
            'index': i,
            'offset': str_off,
            'size': str_sz,
            'raw': raw,
            'text': text,
        })

    instr_data = data[instr_off:]
    return entries, instr_off, instr_data


def build_obj(entries, instr_data):
    """从 entries + 指令区 重建 OBJ 文件"""
    n = len(entries)
    index_table_size = n * 4
    header_size = 4 + index_table_size

    str_data_parts = []
    for e in entries:
        str_data_parts.append(e['raw'] + b'\x00')
    str_data = b''.join(str_data_parts)

    data_start = header_size
    instr_off = data_start + len(str_data)
    # 4字节对齐 (指令区是u32数组)
    pad_len = (4 - (instr_off % 4)) % 4
    pad = b'\x00' * pad_len
    instr_off += pad_len

    index_buf = bytearray(index_table_size)
    cur_data_off = data_start
    for i, e in enumerate(entries):
        sz = len(e['raw']) + 1
        struct.pack_into('<H', index_buf, i * 4, cur_data_off)
        struct.pack_into('<H', index_buf, i * 4 + 2, sz)
        cur_data_off += sz

    header = struct.pack('<HH', instr_off, n)
    return header + bytes(index_buf) + str_data + pad + instr_data


# ============================================================
# 字符串分类 & 指令区分析
# ============================================================
def classify_string(raw_bytes, text_str):
    if len(raw_bytes) == 0 or text_str == '':
        return 'empty'
    if text_str.startswith('V') and text_str[1:].isdigit():
        return 'voice'
    if text_str.startswith('\u3010') and text_str.endswith('\u3011'):
        return 'name'
    if re.match(r'^[a-zA-Z0-9_.\\]+$', text_str) and not any(0x80 <= b for b in raw_bytes):
        return 'other'
    return 'text'


def extract_pairs(data, entries, instr_off):
    """从指令区执行顺序提取 name-message 配对"""
    n = len(entries)
    pos = instr_off + 4  # skip header u32
    seq = []
    while pos + 4 <= len(data):
        w = struct.unpack_from('<I', data, pos)[0]
        mid = (w >> 16) & 0xFF
        lo = w & 0xFFFF
        if mid == 0x80 and lo < n:
            e = entries[lo]
            kind = classify_string(e['raw'], e['text'])
            seq.append((lo, e['text'], kind))
        pos += 4

    current_name = ''
    pairs = []
    for idx, text, kind in seq:
        if kind == 'name':
            current_name = text[1:-1]  # 去掉【】
        elif kind == 'text':
            pairs.append({
                'name': current_name,
                'message': text,
                '_idx': idx,
            })

    return pairs


# ============================================================
# extract
# ============================================================
def cmd_extract(obj_path, json_path):
    with open(obj_path, 'rb') as f:
        data = f.read()
    entries, instr_off, _ = parse_obj(data)
    pairs = extract_pairs(data, entries, instr_off)

    output = json.dumps(pairs, ensure_ascii=False, indent=2)
    with open(json_path, 'w', encoding='utf-8') as f:
        f.write(output)

    print(f"  {os.path.basename(obj_path)}: {len(entries)} entries, "
          f"{len(pairs)} messages -> {os.path.basename(json_path)}")
    return len(pairs)


# ============================================================
# insert
# ============================================================
def cmd_insert(obj_path, json_path, out_path):
    with open(obj_path, 'rb') as f:
        data = f.read()
    entries, instr_off, instr_data = parse_obj(data)

    with open(json_path, 'r', encoding='utf-8') as f:
        pairs = json.load(f)

    changed = 0
    for p in pairs:
        idx = p.get('_idx')
        new_msg = p.get('message', '')
        if idx is None or idx >= len(entries):
            continue
        e = entries[idx]
        if new_msg != e['text']:
            try:
                e['raw'] = new_msg.encode('cp932')
            except UnicodeEncodeError:
                e['raw'] = new_msg.encode('cp932', errors='replace')
            e['text'] = new_msg
            changed += 1

        # 更新角色名
        new_name = p.get('name', '')
        if new_name:
            name_full = '\u3010' + new_name + '\u3011'
            _update_name_entry(data, entries, instr_off, idx, name_full)

    output = build_obj(entries, instr_data)
    with open(out_path, 'wb') as f:
        f.write(output)

    print(f"  {os.path.basename(obj_path)}: {changed} lines changed -> "
          f"{os.path.basename(out_path)}")


def _update_name_entry(data, entries, instr_off, text_idx, name_full):
    """在指令序列中找到text_idx之前最近的name entry并更新"""
    n = len(entries)
    pos = instr_off + 4
    refs = []
    while pos + 4 <= len(data):
        w = struct.unpack_from('<I', data, pos)[0]
        mid = (w >> 16) & 0xFF
        lo = w & 0xFFFF
        if mid == 0x80 and lo < n:
            refs.append(lo)
        pos += 4

    for i, ref_idx in enumerate(refs):
        if ref_idx == text_idx:
            for j in range(i - 1, -1, -1):
                e = entries[refs[j]]
                kind = classify_string(e['raw'], e['text'])
                if kind == 'name':
                    if e['text'] != name_full:
                        try:
                            e['raw'] = name_full.encode('cp932')
                        except:
                            e['raw'] = name_full.encode('cp932', errors='replace')
                        e['text'] = name_full
                    return
                elif kind == 'text':
                    break
            return


# ============================================================
# batch
# ============================================================
def cmd_batch_extract(obj_dir, json_dir):
    os.makedirs(json_dir, exist_ok=True)
    obj_files = sorted([
        os.path.join(obj_dir, f) for f in os.listdir(obj_dir)
        if os.path.isfile(os.path.join(obj_dir, f))
        and not f.startswith('_')
        and f.lower().endswith('.obj')
    ])
    if not obj_files:
        obj_files = sorted([
            os.path.join(obj_dir, f) for f in os.listdir(obj_dir)
            if os.path.isfile(os.path.join(obj_dir, f))
            and not f.startswith('_')
            and not f.endswith(('.txt', '.json', '.py'))
        ])
    total = 0
    extracted = 0
    for obj_path in obj_files:
        base = os.path.splitext(os.path.basename(obj_path))[0]
        json_path = os.path.join(json_dir, base + '.json')
        try:
            with open(obj_path, 'rb') as f:
                d = f.read()
            entries, io, _ = parse_obj(d)
            pairs = extract_pairs(d, entries, io)
            if not pairs:
                continue
            n = cmd_extract(obj_path, json_path)
            total += n
            extracted += 1
        except Exception as ex:
            print(f"  ERROR: {obj_path}: {ex}")

    print(f"\nBatch extract: {len(obj_files)} files scanned, "
          f"{extracted} extracted, {total} messages total")


def cmd_batch_insert(obj_dir, json_dir, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    json_files = sorted([
        os.path.join(json_dir, f) for f in os.listdir(json_dir)
        if f.lower().endswith('.json') and os.path.isfile(os.path.join(json_dir, f))
    ])
    obj_map = {}
    for f in os.listdir(obj_dir):
        obj_map[f.lower()] = f
    for json_path in json_files:
        base = os.path.splitext(os.path.basename(json_path))[0]
        obj_name = obj_map.get(base.lower() + '.obj')
        if obj_name is None:
            print(f"  SKIP: no obj for {os.path.basename(json_path)}")
            continue
        obj_path = os.path.join(obj_dir, obj_name)
        out_path = os.path.join(out_dir, obj_name)
        try:
            cmd_insert(obj_path, json_path, out_path)
        except Exception as ex:
            print(f"  ERROR: {obj_path}: {ex}")

    print(f"\nBatch insert done.")


# ============================================================
# main
# ============================================================
def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)

    cmd = sys.argv[1].lower()

    if cmd in ('extract', 'e'):
        obj_path = sys.argv[2]
        out = sys.argv[3] if len(sys.argv) > 3 else \
            os.path.splitext(obj_path)[0] + '.json'
        cmd_extract(obj_path, out)

    elif cmd in ('insert', 'i'):
        if len(sys.argv) < 4:
            print("Usage: insert input.obj input.json [output.obj]")
            sys.exit(1)
        obj_path = sys.argv[2]
        json_path = sys.argv[3]
        out_path = sys.argv[4] if len(sys.argv) > 4 else \
            os.path.splitext(obj_path)[0] + '_cn.obj'
        cmd_insert(obj_path, json_path, out_path)

    elif cmd in ('batch_e', 'be'):
        obj_dir = sys.argv[2]
        out_dir = sys.argv[3] if len(sys.argv) > 3 else obj_dir + '_json'
        cmd_batch_extract(obj_dir, out_dir)

    elif cmd in ('batch_i', 'bi'):
        if len(sys.argv) < 4:
            print("Usage: batch_i obj_dir json_dir [out_dir]")
            sys.exit(1)
        obj_dir = sys.argv[2]
        json_dir = sys.argv[3]
        out_dir = sys.argv[4] if len(sys.argv) > 4 else obj_dir + '_cn'
        cmd_batch_insert(obj_dir, json_dir, out_dir)

    else:
        print(f"Unknown command: {cmd}")
        print(__doc__)
        sys.exit(1)


if __name__ == '__main__':
    main()
