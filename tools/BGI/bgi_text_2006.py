#!/usr/bin/env python3
"""
BGI脚本文本提取/写回工具
引擎: BGI / Ethornell (あの街の恋の詩)

脚本文件结构:
  [指令区(bytecode)] + [文本数据区(null-terminated cp932 strings)]

关键opcode:
  FE 00 [line:2] 10 00 [00 00 00 00 01 00 00 00] [addr:4]  — 文本显示 (18字节固定)
  FE 00 [line:2] 85 00 [name_id\0] [14 00] [disp_name\0]   — 角色名声明 (变长)

文本引用addr是绝对偏移(相对文件头)，写回时需根据字符串长度变化修正所有addr。

用法:
  python bgi_text.py extract <input.bin> <output.txt>
  python bgi_text.py insert  <orig.bin> <input.txt> <output.bin>
  python bgi_text.py batch_extract <dir_in> <dir_out>
  python bgi_text.py batch_insert  <orig_dir> <txt_dir> <bin_dir>
  python bgi_text.py verify <input.bin>   (round-trip验证)
"""

import struct
import sys
import os

# ============================================================
# 常量
# ============================================================

OPCODE_TEXT = 0x0010
OPCODE_NAME = 0x0085
TEXT_INSTR_LEN = 18           # opcode 0x10 固定长度
TEXT_ADDR_OFFSET = 14         # addr字段在指令内的偏移
TEXT_MID_BYTES = b'\x00\x00\x00\x00\x01\x00\x00\x00'
ENCODING = 'cp932'


# ============================================================
# 解析器
# ============================================================

def find_text_refs(data):
    """
    搜索所有文本引用: [10 00] [00 00 00 00 01 00 00 00] [addr:4]
    兼容有/无 FE 00 行号前缀的两种BGI脚本格式。
    返回 [(cmd_offset, addr), ...] 其中cmd_offset指向10 00的位置。
    """
    TEXT_PATTERN = b'\x10\x00' + TEXT_MID_BYTES  # 10字节固定模式
    refs = []
    i = 0
    while i < len(data) - 14:
        if data[i] == 0x10 and data[i+1] == 0x00 and data[i+2:i+10] == TEXT_MID_BYTES:
            addr = struct.unpack_from('<I', data, i + 10)[0]
            if 0 < addr < len(data):
                refs.append((i, addr))
            i += 14
        else:
            i += 1
    return refs


def find_text_area_start(data):
    """找到文本数据区的起始偏移 = 最小的文本引用地址"""
    refs = find_text_refs(data)
    if not refs:
        return None
    return min(addr for _, addr in refs)


def parse_script(data):
    """
    解析脚本，返回:
      text_entries: [(cmd_offset, line_num, text_addr, text_bytes, 
                      name_id_or_None, disp_bytes_or_None, name_marker_offset), ...]
      text_area_start: int
    
    兼容两种BGI脚本格式:
      格式A (FE 00前缀): FE 00 [line:2] 10 00 [8B fixed] [addr:4]  (18字节)
      格式B (无前缀):     10 00 [8B fixed] [addr:4]                 (14字节)
    
    角色名检测：opcode 0x10 之前的 [14 00 disp_name\0] 标记。
    """
    text_entries = []

    # 用 find_text_refs 搜索所有 [10 00 ...] 模式（不依赖FE 00）
    refs = find_text_refs(data)
    text_area_start = min((addr for _, addr in refs), default=len(data))
    if text_area_start >= len(data):
        return [], None

    for cmd_off, addr in refs:
        # 检查是否有 FE 00 行号前缀
        line = 0
        has_fe_prefix = False
        if cmd_off >= 4:
            fe_off = cmd_off - 4
            if data[fe_off] == 0xFE and data[fe_off+1] == 0x00:
                op_check = struct.unpack_from('<H', data, fe_off + 4)[0]
                if op_check == OPCODE_TEXT:
                    has_fe_prefix = True
                    line = struct.unpack_from('<H', data, fe_off + 2)[0]

        # 读取文本
        end = data.find(0x00, addr)
        if end < 0:
            end = len(data)
        text_bytes = data[addr:end]

        name_id = None
        disp_bytes = None
        name_marker_off = None

        # 向前查找 [14 00 disp_name\0]
        # 有FE 00前缀时: ... name\0 FE 00 xx xx 10 00 ... → 从FE 00处向前找
        # 无前缀时:       ... name\0 10 00 ...             → 从10 00处向前找
        search_start = (cmd_off - 4) if has_fe_prefix else cmd_off
        if search_start >= 3 and data[search_start - 1] == 0x00:
            j = search_start - 2
            while j > 0 and data[j] != 0x00:
                j -= 1
            if j >= 1 and data[j-1] == 0x14 and data[j] == 0x00:
                disp_bytes = data[j+1:search_start-1]
                name_marker_off = j - 1

                # 检查是否有 name_id (opcode 0x85)
                k = name_marker_off - 1
                if k >= 0 and data[k] == 0x00:
                    m = k - 1
                    while m >= 0 and data[m] != 0x00 and data[m] >= 0x20 and data[m] < 0x7F:
                        m -= 1
                    m += 1
                    candidate_id = data[m:k]
                    if len(candidate_id) > 0:
                        # 验证：m前面有 85 00 (可能带FE 00前缀也可能不带)
                        found_85 = False
                        if m >= 2 and data[m-2] == 0x85 and data[m-1] == 0x00:
                            found_85 = True
                        elif m >= 6 and data[m-6] == 0xFE and data[m-6+1] == 0x00:
                            if struct.unpack_from('<H', data, m-6+4)[0] == OPCODE_NAME:
                                found_85 = True
                        if found_85:
                            try:
                                name_id = candidate_id.decode('ascii')
                            except:
                                pass

        text_entries.append((cmd_off, line, addr, text_bytes,
                             name_id, disp_bytes, name_marker_off))

    return text_entries, text_area_start


# ============================================================
# 提取
# ============================================================

def extract(bin_path, txt_path):
    with open(bin_path, 'rb') as f:
        data = f.read()

    text_entries, text_area_start = parse_script(data)

    if not text_entries:
        print(f"  [SKIP] {bin_path}: 无文本条目")
        return 0

    name_count = sum(1 for e in text_entries if e[5] is not None)

    lines_out = []
    lines_out.append(f"# BGI Script Text - {os.path.basename(bin_path)}")
    lines_out.append(f"# text_area_start=0x{text_area_start:X}")
    lines_out.append(f"# texts={len(text_entries)} named={name_count}")
    lines_out.append(f"#")
    lines_out.append(f"# 格式:")
    lines_out.append(f"#   ●name_id|显示名|序号|台词  = 角色对话(有voice标记)")
    lines_out.append(f"#   ◆显示名|序号|台词          = 角色对话(无voice标记)")
    lines_out.append(f"#   ○序号|文本                  = 旁白/独白")
    lines_out.append("")

    for idx, entry in enumerate(text_entries):
        cmd_off, line, addr, text_bytes, name_id, disp_bytes, _ = entry
        text = text_bytes.decode(ENCODING, errors='replace')
        # 转义嵌入的换行符，防止TXT行截断
        text = text.replace('\n', '\\n').replace('\r', '\\r')
        if disp_bytes is not None:
            disp = disp_bytes.decode(ENCODING, errors='replace')
            if name_id:
                lines_out.append(f"●{name_id}|{disp}|{idx:04d}|{text}")
            else:
                lines_out.append(f"◆{disp}|{idx:04d}|{text}")
        else:
            lines_out.append(f"○{idx:04d}|{text}")

    with open(txt_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines_out) + '\n')

    print(f"  [OK] {os.path.basename(bin_path)}: "
          f"{len(text_entries)} texts, {name_count} named")
    return len(text_entries)


# ============================================================
# 写回
# ============================================================

def _unescape_text(s):
    """还原提取时转义的控制字符"""
    return s.replace('\\r', '\r').replace('\\n', '\n')


def parse_txt(txt_path):
    """
    解析TXT，返回 (texts: dict[int,str], names: dict[str,str])
    格式:
      ●name_id|disp|序号|台词  = 角色对话(有voice)
      ◆disp|序号|台词          = 角色对话(无voice)
      ○序号|文本               = 旁白/独白
    """
    texts = {}
    names = {}

    with open(txt_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.rstrip('\n').rstrip('\r')
            if not line or line.startswith('#'):
                continue

            if line.startswith('○'):
                body = line[len('○'):]
                pipe = body.find('|')
                if pipe < 0:
                    continue
                idx = int(body[:pipe])
                text = _unescape_text(body[pipe+1:])
                texts[idx] = text

            elif line.startswith('●'):
                body = line[len('●'):]
                parts = body.split('|', 3)
                if len(parts) < 4:
                    continue
                name_id = parts[0]
                disp = parts[1]
                idx = int(parts[2])
                text = _unescape_text(parts[3])
                texts[idx] = text
                if disp:
                    names[name_id] = disp

            elif line.startswith('◆'):
                body = line[len('◆'):]
                parts = body.split('|', 2)
                if len(parts) < 3:
                    continue
                idx = int(parts[1])
                text = _unescape_text(parts[2])
                texts[idx] = text
                # ◆的disp_name在14 00标记中，写回时不修改指令区

    return texts, names


def insert(orig_bin_path, txt_path, out_bin_path):
    with open(orig_bin_path, 'rb') as f:
        orig_data = bytearray(f.read())

    text_entries, text_area_start = parse_script(orig_data)

    if text_area_start is None:
        with open(out_bin_path, 'wb') as f:
            f.write(orig_data)
        print(f"  [SKIP] {orig_bin_path}: 无文本区，直接复制")
        return

    translated_texts, translated_names = parse_txt(txt_path)

    # ---- 步骤1: 在指令区中应用 opcode 0x85 的 disp_name 补丁 ----
    code_area = bytearray(orig_data[:text_area_start])

    # 收集需要补丁的 0x85 name 指令（含 name_id 和 disp）
    # 从 text_entries 中找出有 name_id 的条目
    name_patches = []  # [(marker_off, old_disp_bytes, new_disp_bytes), ...]
    for entry in text_entries:
        _, _, _, _, name_id, disp_bytes, name_marker_off = entry
        if name_id and disp_bytes is not None and name_id in translated_names:
            new_disp = translated_names[name_id]
            new_disp_bytes = new_disp.encode(ENCODING, errors='replace')
            # 补丁位置：name_marker_off 指向 0x14，后面是 00 + disp + 00
            # 即 [14] [00] [old_disp] [00] -> [14] [00] [new_disp] [00]
            old_start = name_marker_off + 2  # 跳过 14 00
            old_end = old_start + len(disp_bytes) + 1  # 含 \0
            name_patches.append((old_start, old_end, new_disp_bytes + b'\x00'))

    # 从后往前打补丁
    name_patches.sort(key=lambda x: x[0], reverse=True)
    for start, end, new_bytes in name_patches:
        if start < len(code_area):
            code_area[start:end] = new_bytes

    # ---- 步骤2: 构建新文本数据区 ----
    new_text_area_start = len(code_area)
    new_text_area = bytearray()
    new_addrs = []

    for idx, entry in enumerate(text_entries):
        _, _, _, orig_text_bytes, _, _, _ = entry
        if idx in translated_texts:
            new_bytes = translated_texts[idx].encode(ENCODING, errors='replace')
        else:
            new_bytes = orig_text_bytes

        addr = new_text_area_start + len(new_text_area)
        new_addrs.append(addr)
        new_text_area += new_bytes + b'\x00'

    # ---- 步骤3: 修正指令区中所有文本引用的地址 ----
    # 直接搜索 [10 00] [8B fixed] 模式，不依赖FE 00前缀
    i = 0
    ref_idx = 0
    while i < len(code_area) - 14:
        if (code_area[i] == 0x10 and code_area[i+1] == 0x00 and
            code_area[i+2:i+10] == TEXT_MID_BYTES):
            if ref_idx < len(new_addrs):
                struct.pack_into('<I', code_area, i + 10, new_addrs[ref_idx])
            ref_idx += 1
            i += 14
        else:
            i += 1

    if ref_idx != len(text_entries):
        print(f"  [WARN] 修正了 {ref_idx} 个地址，但原始有 {len(text_entries)} 个文本引用")

    # ---- 步骤4: 拼合输出 ----
    out_data = bytes(code_area) + bytes(new_text_area)

    with open(out_bin_path, 'wb') as f:
        f.write(out_data)

    delta = len(out_data) - len(orig_data)
    print(f"  [OK] {os.path.basename(orig_bin_path)}: "
          f"{len(text_entries)} texts, {len(name_patches)} name_patches | "
          f"size {len(orig_data)} -> {len(out_data)} ({'+' if delta >= 0 else ''}{delta})")


# ============================================================
# 批量操作
# ============================================================

def batch_extract(dir_in, dir_out):
    os.makedirs(dir_out, exist_ok=True)
    total = 0
    for fname in sorted(os.listdir(dir_in)):
        path_in = os.path.join(dir_in, fname)
        if not os.path.isfile(path_in):
            continue
        # 跳过明显非脚本的文件（有常见扩展名的）
        lower = fname.lower()
        if any(lower.endswith(ext) for ext in
               ['.txt', '.py', '.png', '.jpg', '.bmp', '.ogg', '.wav', '.mp3', '.arc']):
            continue
        path_out = os.path.join(dir_out, fname + '.txt')
        n = extract(path_in, path_out)
        total += n
    print(f"\n总计提取 {total} 条")


def batch_insert(orig_dir, txt_dir, bin_dir):
    os.makedirs(bin_dir, exist_ok=True)
    count = 0
    for fname in sorted(os.listdir(txt_dir)):
        if not fname.endswith('.txt'):
            continue
        base = fname[:-4]
        orig_path = os.path.join(orig_dir, base)
        if not os.path.isfile(orig_path):
            print(f"  [SKIP] 原始文件不存在: {orig_path}")
            continue
        txt_path = os.path.join(txt_dir, fname)
        out_path = os.path.join(bin_dir, base)
        insert(orig_path, txt_path, out_path)
        count += 1
    print(f"\n总计写回 {count} 个文件")


# ============================================================
# Round-trip验证
# ============================================================

def verify(orig_bin_path):
    """提取原文再写回，验证输出bin与原始完全一致"""
    import tempfile
    with open(orig_bin_path, 'rb') as f:
        orig_data = f.read()

    txt_path = tempfile.mktemp(suffix='.txt')
    out_path = tempfile.mktemp(suffix='.bin')

    try:
        extract(orig_bin_path, txt_path)
        insert(orig_bin_path, txt_path, out_path)

        with open(out_path, 'rb') as f:
            new_data = f.read()

        if orig_data == new_data:
            print(f"  [PASS] Round-trip 完全一致: {os.path.basename(orig_bin_path)}")
            return True
        else:
            print(f"  [FAIL] Round-trip 不一致! "
                  f"orig={len(orig_data)} new={len(new_data)}")
            for i in range(min(len(orig_data), len(new_data))):
                if orig_data[i] != new_data[i]:
                    print(f"    首个差异 @0x{i:04X}: "
                          f"orig=0x{orig_data[i]:02X} new=0x{new_data[i]:02X}")
                    # 打印上下文
                    s = max(0, i-8)
                    print(f"    orig: {' '.join(f'{b:02X}' for b in orig_data[s:i+8])}")
                    print(f"    new:  {' '.join(f'{b:02X}' for b in new_data[s:i+8])}")
                    break
            return False
    finally:
        for p in [txt_path, out_path]:
            if os.path.exists(p):
                os.unlink(p)


# ============================================================
# Main
# ============================================================

def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == 'extract' and len(sys.argv) == 4:
        extract(sys.argv[2], sys.argv[3])
    elif cmd == 'insert' and len(sys.argv) == 5:
        insert(sys.argv[2], sys.argv[3], sys.argv[4])
    elif cmd == 'batch_extract' and len(sys.argv) == 4:
        batch_extract(sys.argv[2], sys.argv[3])
    elif cmd == 'batch_insert' and len(sys.argv) == 5:
        batch_insert(sys.argv[2], sys.argv[3], sys.argv[4])
    elif cmd == 'verify' and len(sys.argv) == 3:
        verify(sys.argv[2])
    elif cmd == 'verify_all' and len(sys.argv) == 3:
        # 批量验证目录下所有脚本
        d = sys.argv[2]
        ok = fail = skip = 0
        for fname in sorted(os.listdir(d)):
            path = os.path.join(d, fname)
            if not os.path.isfile(path):
                continue
            lower = fname.lower()
            if any(lower.endswith(ext) for ext in
                   ['.txt', '.py', '.png', '.jpg', '.bmp', '.ogg', '.wav', '.mp3', '.arc']):
                continue
            if verify(path):
                ok += 1
            else:
                fail += 1
        print(f"\n验证结果: {ok} PASS, {fail} FAIL")
    else:
        print(__doc__)
        sys.exit(1)


if __name__ == '__main__':
    main()
