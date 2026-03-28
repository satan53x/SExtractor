#!/usr/bin/env python3
"""
hcb_inject.py — HCB 引擎文本注入工具 (重建模式)

功能：
  1. 替换 0x0E 文本，自动修正 len 字节
  2. 线性反汇编遍历字节码，修正所有 02/06/07 的绝对地址
  3. 修正文件头 header_offset 和头部表 entry_point

用法：
  python hcb_inject.py <原文件.hcb> <翻译.json> <输出.hcb>
"""

import sys
import struct
import json
import re


# ============================================================
# Opcode 大小表（已修正: 0x01 PROLOGUE = 3字节）
# ============================================================

def get_opcode_size(data, pos):
    op = data[pos]
    if op == 0x0E:
        return 2 + data[pos + 1]
    elif op in (0x02, 0x06, 0x07, 0x0A):
        return 5
    elif op in (0x01, 0x03, 0x0B, 0x0F, 0x11, 0x12, 0x13, 0x15):
        return 3
    elif op in (0x0C, 0x10, 0x16):
        return 2
    else:
        return 1


# ============================================================
# hcb_text.py 兼容的过滤逻辑
# ============================================================

def _classify(text):
    if text.startswith('【') and '】' in text:
        return 'name'
    has_jp = any(ord(c) > 0x3000 for c in text)
    if '/' in text and not has_jp:
        return 'resource'
    hk = any(0x3040 <= ord(c) <= 0x30FF for c in text)
    hj = any(0x4E00 <= ord(c) <= 0x9FFF for c in text)
    if any(c in text for c in '。？！') and len(text) > 3:
        return 'dialogue'
    if (hk or hj) and len(text) > 2:
        if text[0] in '「『（' or any(c in text for c in '…～♪、') or len(text) > 5:
            return 'dialogue'
        return 'scene'
    if text.replace('_', '').replace('-', '').isalnum():
        return 'label'
    return 'other'


def _is_dialogue_text(text, offset, cat):
    if offset < 0x0C0000:
        return False
    if cat in ('label', 'resource'):
        return False
    if text.startswith('_'):
        return False
    if '_吹出' in text:
        return False
    if any(ord(c) < 0x20 and c not in '\n\r\t' for c in text):
        return False
    has_jp = any(ord(c) > 0x3000 for c in text)
    has_kana = any(0x3040 <= ord(c) <= 0x30FF for c in text)
    has_kanji = any(0x4E00 <= ord(c) <= 0x9FFF for c in text)
    if not (has_jp or has_kana or has_kanji or text.startswith('「')):
        return False
    return True


# ============================================================
# 线性反汇编遍历
# ============================================================

def disassemble_scan(data):
    header_offset = struct.unpack_from('<I', data, 0)[0]
    all_0e = []
    addr_offsets = []

    pc = 4
    end = header_offset
    while pc < end:
        op = data[pc]
        size = get_opcode_size(data, pc)

        if op in (0x02, 0x06, 0x07):
            addr = struct.unpack_from('<I', data, pc + 1)[0]
            if addr < header_offset:
                addr_offsets.append(pc + 1)

        elif op == 0x0E:
            length = data[pc + 1]
            text_end = pc + 2 + length
            if length >= 2 and text_end <= end and data[text_end - 1] == 0x00:
                text_bytes = data[pc + 2 : text_end - 1]
                try:
                    text = text_bytes.decode('cp932')
                    if text.encode('cp932') + b'\x00' == data[pc + 2 : text_end]:
                        if len(text) >= 1:
                            cat = _classify(text)
                            all_0e.append((pc, length, text, cat))
                except (UnicodeDecodeError, ValueError):
                    pass

        pc += size

    assert pc == end, f"遍历未对齐: pc=0x{pc:X}, end=0x{end:X}"
    return all_0e, addr_offsets, header_offset


def build_dialogue_map(all_0e):
    seen = set()
    dialogue_entries = []
    for offset, length, text, cat in all_0e:
        if offset in seen:
            continue
        if _is_dialogue_text(text, offset, cat):
            seen.add(offset)
            dialogue_entries.append((offset, length, text))
    return dialogue_entries


# ============================================================
# 构建替换列表
# ============================================================

def build_replacements(dialogue_entries, translations, encoding='cp932'):
    replacements = []

    for msg_id, (offset, orig_len, orig_text) in enumerate(dialogue_entries):
        if msg_id not in translations:
            continue

        trans_text = translations[msg_id]
        if trans_text == orig_text:
            continue

        try:
            encoded = trans_text.encode(encoding)
        except UnicodeEncodeError:
            print(f"  警告: message_id={msg_id} 编码失败，保留原文")
            continue

        new_len = len(encoded) + 1

        if new_len > 255:
            print(f"  警告: message_id={msg_id} 编码后 {new_len} 字节超过255限制，截断")
            encoded = encoded[:254]
            try:
                encoded.decode(encoding)
            except UnicodeDecodeError:
                encoded = encoded[:-1]
            new_len = len(encoded) + 1

        new_block = bytes([0x0E, new_len]) + encoded + b'\x00'
        orig_total = 2 + orig_len
        replacements.append((offset, orig_total, new_block))

    return replacements


# ============================================================
# 应用替换并修正所有地址
# ============================================================

def apply_replacements(data, replacements, addr_offsets, header_offset):
    replacements.sort(key=lambda x: x[0])

    delta_table = []
    cumulative = 0
    for orig_off, orig_size, new_block in replacements:
        delta = len(new_block) - orig_size
        if delta != 0:
            cumulative += delta
            delta_table.append((orig_off + orig_size, cumulative))

    def translate_addr(old_addr):
        lo, hi = 0, len(delta_table)
        while lo < hi:
            mid = (lo + hi) // 2
            if delta_table[mid][0] <= old_addr:
                lo = mid + 1
            else:
                hi = mid
        if lo == 0:
            return old_addr
        return old_addr + delta_table[lo - 1][1]

    # 拼接新文件
    parts = []
    prev_end = 0
    for orig_off, orig_size, new_block in replacements:
        parts.append(data[prev_end:orig_off])
        parts.append(new_block)
        prev_end = orig_off + orig_size
    parts.append(data[prev_end:])
    new_data = bytearray(b''.join(parts))

    total_delta = cumulative
    print(f"  文件大小变化: {len(data)} → {len(new_data)} (delta={total_delta:+d})")

    if total_delta == 0:
        return bytes(new_data)

    # 修正所有 02/06/07 绝对地址（已排除超范围）
    fixed_count = 0
    for old_field_offset in addr_offsets:
        new_field_offset = translate_addr(old_field_offset)
        if new_field_offset + 4 > len(new_data):
            continue
        old_value = struct.unpack_from('<I', new_data, new_field_offset)[0]
        new_value = translate_addr(old_value)
        if new_value != old_value:
            struct.pack_into('<I', new_data, new_field_offset, new_value)
            fixed_count += 1
    print(f"  修正 02/06/07 地址: {fixed_count} / {len(addr_offsets)}")

    # 修正 header_offset
    new_header_off = translate_addr(header_offset)
    struct.pack_into('<I', new_data, 0, new_header_off)
    print(f"  header_offset: 0x{header_offset:X} → 0x{new_header_off:X}")

    # 修正 entry_point
    old_entry = struct.unpack_from('<I', data, header_offset)[0]
    new_entry = translate_addr(old_entry)
    struct.pack_into('<I', new_data, new_header_off, new_entry)
    print(f"  entry_point: 0x{old_entry:X} → 0x{new_entry:X}")

    return bytes(new_data)


# ============================================================
# 主函数
# ============================================================

def main():
    if len(sys.argv) != 4:
        print(f"用法: {sys.argv[0]} <原文件.hcb> <翻译.json> <输出.hcb>")
        print()
        print("功能:")
        print("  1. 替换 0x0E 文本 (修正 len 字节)")
        print("  2. 修正所有 02(CALL)/06(JUMP)/07(JUMP_IF) 绝对地址")
        print("  3. 修正 header_offset 和 entry_point")
        sys.exit(1)

    orig_path = sys.argv[1]
    json_path = sys.argv[2]
    out_path  = sys.argv[3]

    with open(orig_path, 'rb') as f:
        data = f.read()
    print(f"原文件: {orig_path} ({len(data)} bytes)")

    with open(json_path, 'r', encoding='utf-8') as f:
        raw = f.read()
    try:
        json_data = json.loads(raw)
    except json.JSONDecodeError:
        fixed = re.sub(
            r'("message"\s*:\s*")(.*?)(",\s*\n)',
            lambda m: m.group(1) + m.group(2).replace('"', '\\"') + m.group(3),
            raw
        )
        try:
            json_data = json.loads(fixed)
            print(f"翻译文件: {json_path} ({len(json_data)} 条) [已自动修复JSON格式]")
        except json.JSONDecodeError as e:
            print(f"JSON格式错误且无法自动修复: {e}")
            sys.exit(1)
    else:
        print(f"翻译文件: {json_path} ({len(json_data)} 条)")

    translations = {}
    for entry in json_data:
        mid = entry.get('message_id')
        msg = entry.get('message')
        if mid is not None and msg is not None:
            translations[mid] = msg

    print("\n[1/4] 线性反汇编遍历字节码...")
    all_0e, addr_offsets, header_offset = disassemble_scan(data)
    print(f"  指令区: [0x04, 0x{header_offset:X})")
    print(f"  全部 0E 文本: {len(all_0e)} 个")
    print(f"  02/06/07 地址引用: {len(addr_offsets)} 个")

    print("\n[2/4] 过滤对话文本 (与 hcb_text.py 一致)...")
    dialogue_entries = build_dialogue_map(all_0e)
    print(f"  有效对话: {len(dialogue_entries)} 个")

    print("\n[3/4] 构建替换列表...")
    replacements = build_replacements(dialogue_entries, translations)
    print(f"  {len(replacements)} / {len(dialogue_entries)} 条文本有变化")

    if not replacements:
        print("\n无文本变化，直接复制原文件")
        with open(out_path, 'wb') as f:
            f.write(data)
        return

    print("\n[4/4] 应用替换 + 修正地址...")
    new_data = apply_replacements(data, replacements, addr_offsets, header_offset)

    with open(out_path, 'wb') as f:
        f.write(new_data)
    print(f"\n输出: {out_path} ({len(new_data)} bytes)")
    print("完成!")


if __name__ == '__main__':
    main()
