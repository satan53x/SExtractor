#!/usr/bin/env python3
"""
OBJ 脚本文本提取/导入工具 (6字节索引版)
头部: u32 指令区偏移 + u16 字符串数
索引: N × (u32 offset + u16 length)
字符串: CP932 编码, \x00 终止
指令: u32 LE, mid(bits[23:16])=0x80 时 lo(bits[15:0])=字符串索引
对话模式: 【角色名】更新当前角色 → 日文文本=对话

用法:
  python obj6_text.py extract  <obj文件> [json文件]
  python obj6_text.py insert   <obj文件> <json文件> [输出obj]
  python obj6_text.py batch_e  <obj目录> <json输出目录>
  python obj6_text.py batch_i  <obj目录> <json目录> [输出目录]
"""

import sys, os, json, struct, glob

# ─────────────────────────── 核心解析 ───────────────────────────

def parse_obj(data):
    """解析OBJ文件，返回 (strings, instr_off, n_strings)"""
    instr_off = struct.unpack_from('<I', data, 0)[0]
    n_strings = struct.unpack_from('<H', data, 4)[0]

    strings = []
    for i in range(n_strings):
        off_idx = 6 + i * 6
        s_off = struct.unpack_from('<I', data, off_idx)[0]
        s_len = struct.unpack_from('<H', data, off_idx + 4)[0]
        s_data = data[s_off:s_off + s_len]
        if s_data and s_data[-1] == 0:
            s_data = s_data[:-1]
        try:
            s = s_data.decode('cp932')
        except:
            s = s_data.decode('cp932', errors='replace')
        strings.append(s)

    return strings, instr_off, n_strings


def get_execution_order(data, strings, instr_off, n_strings):
    """按指令执行顺序获取字符串引用序列"""
    refs = []
    for pos in range(instr_off, len(data) - 3, 4):
        instr = struct.unpack_from('<I', data, pos)[0]
        mid = (instr >> 16) & 0xFF
        lo = instr & 0xFFFF
        if mid == 0x80 and lo < n_strings:
            refs.append((pos, lo, strings[lo]))
    return refs


def classify_string(s):
    """分类字符串"""
    if not s:
        return 'empty'
    if s.startswith('【') and s.endswith('】'):
        return 'name'
    if s.startswith('■'):
        return 'mark'
    if s.startswith('V') and len(s) >= 7 and all(c.isdigit() for c in s[1:]):
        return 'voice'
    if not any(c > '\x7f' for c in s) and len(s) < 15:
        return 'ctrl'
    if any(c > '\x7f' for c in s):
        return 'text'
    return 'other'


def extract_messages(data):
    """提取 name-message 配对"""
    strings, instr_off, n_strings = parse_obj(data)
    refs = get_execution_order(data, strings, instr_off, n_strings)

    messages = []
    current_name = ''

    for pos, idx, s in refs:
        cat = classify_string(s)

        if cat == 'name':
            current_name = s[1:-1]  # 去掉【】
        elif cat == 'text':
            messages.append({
                'name': current_name,
                'message': s,
                '_str_idx': idx,
            })

    return messages, strings


def rebuild_obj(data, messages):
    """将翻译导入回OBJ: 替换字符串表中的文本"""
    instr_off = struct.unpack_from('<I', data, 0)[0]
    n_strings = struct.unpack_from('<H', data, 4)[0]

    # 读取原始字符串的raw bytes
    orig_strings_raw = []
    for i in range(n_strings):
        off_idx = 6 + i * 6
        s_off = struct.unpack_from('<I', data, off_idx)[0]
        s_len = struct.unpack_from('<H', data, off_idx + 4)[0]
        orig_strings_raw.append(data[s_off:s_off + s_len])

    # 建立替换映射
    trans_map = {}
    name_map = {}
    for m in messages:
        idx = m['_str_idx']
        new_text = m.get('message_zh', m.get('message', ''))
        trans_map[idx] = new_text.encode('cp932', errors='replace') + b'\x00'
        # 角色名翻译
        if 'name_zh' in m and m['name_zh']:
            name_map[m['name']] = m['name_zh']

    # 替换字符串
    new_strings_raw = []
    for i in range(n_strings):
        if i in trans_map:
            new_strings_raw.append(trans_map[i])
        else:
            raw = orig_strings_raw[i]
            # 检查是否是需要翻译的角色名
            try:
                s = raw.rstrip(b'\x00').decode('cp932')
                if s.startswith('【') and s.endswith('】'):
                    inner = s[1:-1]
                    if inner in name_map:
                        new_s = '【' + name_map[inner] + '】'
                        new_strings_raw.append(new_s.encode('cp932') + b'\x00')
                        continue
            except:
                pass
            new_strings_raw.append(raw)

    # 重建文件: header + index + string_data + instruction_area
    string_data_start = 6 + n_strings * 6

    # 计算新的字符串数据
    new_offsets = []
    cur_off = string_data_start
    for raw in new_strings_raw:
        new_offsets.append(cur_off)
        cur_off += len(raw)

    # 对齐到4字节 (如果需要)
    string_data_end = cur_off
    padding = 0
    if string_data_end % 4 != 0:
        padding = 4 - (string_data_end % 4)

    new_instr_off = string_data_end + padding

    # 指令区数据
    instr_data = data[instr_off:]

    # 构建新文件
    out = bytearray()
    # Header
    out += struct.pack('<I', new_instr_off)
    out += struct.pack('<H', n_strings)
    # Index
    for i in range(n_strings):
        out += struct.pack('<I', new_offsets[i])
        out += struct.pack('<H', len(new_strings_raw[i]))
    # String data
    for raw in new_strings_raw:
        out += raw
    # Padding
    out += b'\x00' * padding
    # Instructions
    out += instr_data

    return bytes(out)

# ─────────────────────────── 命令实现 ───────────────────────────

def cmd_extract(obj_path, json_path=None):
    data = open(obj_path, 'rb').read()
    messages, _ = extract_messages(data)

    output = [{
        "name": m["name"],
        "message": m["message"],
        "_str_idx": m["_str_idx"],
    } for m in messages]

    if json_path is None:
        json_path = os.path.splitext(obj_path)[0] + '.json'

    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"  {os.path.basename(obj_path)}: {len(output)} messages → {os.path.basename(json_path)}")
    return output


def cmd_insert(obj_path, json_path, out_path=None):
    data = open(obj_path, 'rb').read()

    with open(json_path, 'r', encoding='utf-8') as f:
        messages = json.load(f)

    new_data = rebuild_obj(data, messages)

    if out_path is None:
        out_path = obj_path

    with open(out_path, 'wb') as f:
        f.write(new_data)

    print(f"  {os.path.basename(obj_path)}: {len(messages)} messages → {os.path.basename(out_path)}")


def cmd_batch_extract(obj_dir, json_dir):
    os.makedirs(json_dir, exist_ok=True)

    obj_files = sorted([
        os.path.join(obj_dir, f) for f in os.listdir(obj_dir)
        if f.lower().endswith('.obj')
    ])

    total_msgs = 0
    total_files = 0

    for obj_path in obj_files:
        basename = os.path.splitext(os.path.basename(obj_path))[0]
        json_path = os.path.join(json_dir, basename + '.json')

        try:
            data = open(obj_path, 'rb').read()
            messages, _ = extract_messages(data)

            if not messages:
                continue

            output = [{
                "name": m["name"],
                "message": m["message"],
                "_str_idx": m["_str_idx"],
            } for m in messages]

            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(output, f, ensure_ascii=False, indent=2)

            total_msgs += len(output)
            total_files += 1
            print(f"  {basename}.obj: {len(output)} messages")

        except Exception as e:
            print(f"  {basename}.obj: ERROR - {e}")

    print(f"\nTotal: {total_files} files, {total_msgs} messages")


def cmd_batch_insert(obj_dir, json_dir, out_dir=None):
    if out_dir is None:
        out_dir = obj_dir
    os.makedirs(out_dir, exist_ok=True)

    json_files = sorted([
        f for f in os.listdir(json_dir) if f.lower().endswith('.json')
    ])

    total = 0
    ok = 0
    fail = 0

    for jf in json_files:
        basename = os.path.splitext(jf)[0]
        json_path = os.path.join(json_dir, jf)

        obj_path = None
        for f in os.listdir(obj_dir):
            if f.lower() == basename.lower() + '.obj':
                obj_path = os.path.join(obj_dir, f)
                break

        if obj_path is None:
            print(f"  {basename}: obj not found, skip")
            fail += 1
            continue

        try:
            data = open(obj_path, 'rb').read()
            with open(json_path, 'r', encoding='utf-8') as f:
                messages = json.load(f)

            new_data = rebuild_obj(data, messages)

            out_name = os.path.basename(obj_path)
            out_path = os.path.join(out_dir, out_name)
            with open(out_path, 'wb') as f:
                f.write(new_data)

            ok += 1
            total += len(messages)
            print(f"  {basename}: {len(messages)} messages")

        except Exception as e:
            print(f"  {basename}: ERROR - {e}")
            fail += 1

    print(f"\nTotal: {ok} files, {total} messages, {fail} errors")

# ─────────────────────────── 入口 ───────────────────────────

def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)

    cmd = sys.argv[1].lower()

    if cmd in ('extract', 'e'):
        cmd_extract(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else None)
    elif cmd in ('insert', 'i'):
        if len(sys.argv) < 4:
            print("Usage: insert <obj> <json> [output_obj]")
            sys.exit(1)
        cmd_insert(sys.argv[2], sys.argv[3], sys.argv[4] if len(sys.argv) > 4 else None)
    elif cmd in ('batch_e', 'be'):
        cmd_batch_extract(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else os.path.join(sys.argv[2], 'json_out'))
    elif cmd in ('batch_i', 'bi'):
        if len(sys.argv) < 4:
            print("Usage: batch_i <obj_dir> <json_dir> [out_dir]")
            sys.exit(1)
        cmd_batch_insert(sys.argv[2], sys.argv[3], sys.argv[4] if len(sys.argv) > 4 else None)
    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)

if __name__ == '__main__':
    main()
