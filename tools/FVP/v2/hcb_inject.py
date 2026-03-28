#!/usr/bin/env python3
"""
hcb_inject.py — HCB脚本文本注入工具
引擎: アトリエかぐや/ωstar HCB字节码 (v26)
游戏: BOIN 等

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  用法
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  注入翻译 (JSON格式):
    python hcb_inject.py 原始.hcb 翻译.json
    python hcb_inject.py 原始.hcb 翻译.json -o 输出.hcb

  注入翻译 (TXT格式):
    python hcb_inject.py 原始.hcb 翻译.txt -o 输出.hcb

  指定编码 (默认cp932):
    python hcb_inject.py 原始.hcb 翻译.json -e cp932

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  完整汉化工作流
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  1. 备份原始HCB:
       copy s.hcb 留档\\s.hcb

  2. 提取文本 (用hcb_extract.py):
       python hcb_extract.py 留档\\s.hcb -o s.json

  3. 翻译 (GalTransl / 手动编辑s.json的message字段)

  4. 注入翻译:
       python hcb_inject.py 留档\\s.hcb s_translated.json -o s.hcb

  5. 将生成的s.hcb放入游戏目录,启动游戏验证

  ⚠ 注意: 始终用留档的原始HCB作为inject的第一个参数!
          不要用已注入过的HCB再次注入!

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  翻译JSON格式说明
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  输入JSON必须是数组, 每个元素至少包含以下字段之一:

  方式A — 按message_id定位 (推荐):
    {"message_id": 29, "message": "翻译后的文本"}

  方式B — 按offset定位:
    {"offset": "0x02E20A", "translation": "翻译后的文本"}

  未修改的条目 (message==原文) 会自动跳过, 不会影响输出。

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  注入策略
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  短文本 (翻译后字节数 ≤ 原文字节数):
    → 就地替换: 在原STR数据区内覆写, 剩余空间填\\x00
    → 不改变文件大小, 不影响任何偏移

  长文本 (翻译后字节数 > 原文字节数):
    → Trampoline跳板法:
      原位: 整个STR区域替换为 [JMP trampoline地址] + NOP填充
      文件末尾追加: [STR 新文本] + [JMP 返回地址]
    → 不移动任何现有bytecode, 所有绝对偏移天然正确
    → 单条文本上限: 254字节 (cp932编码后, 不含\\0)

  限制:
    - 原STR区域 < 5字节时无法放置JMP跳板, 会截断处理 (极罕见)
    - 单条cp932编码 > 254字节时自动截断 (约127个全角字符, 正常不会触及)
"""

import struct, os, argparse, json, sys
from collections import Counter


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  从 hcb_extract.py 复用的核心函数
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

OP_SIZE_5 = {0x02, 0x06, 0x07, 0x0a}
OP_SIZE_3 = {0x0b, 0x0f, 0x03, 0x15, 0x11, 0x12, 0x13}
OP_SIZE_2 = {0x0c, 0x10, 0x16}
STVAR_CHR_ID = 0x00AD


def iter_opcodes(data, start, end):
    """遍历bytecode区的所有opcode"""
    i = start
    while i < end - 1:
        op = data[i]
        if op == 0x0e:
            sl = data[i + 1]
            yield (i, 0x0e, sl)
            i += 2 + sl
        elif op in OP_SIZE_5:
            addr = struct.unpack_from('<I', data, i + 1)[0]
            yield (i, op, addr)
            i += 5
        elif op in OP_SIZE_3:
            val = struct.unpack_from('<H', data, i + 1)[0]
            yield (i, op, val)
            i += 3
        elif op in OP_SIZE_2:
            yield (i, op, data[i + 1])
            i += 2
        else:
            yield (i, op, None)
            i += 1


def parse_header(data):
    """解析HCB尾部header"""
    hdr_off = struct.unpack_from('<I', data, 0)[0]
    pos = hdr_off
    info = {'header_offset': hdr_off}
    info['entry_point'] = struct.unpack_from('<I', data, pos)[0]; pos += 4
    info['count_a'] = struct.unpack_from('<h', data, pos)[0]; pos += 2
    info['count_b'] = struct.unpack_from('<h', data, pos)[0]; pos += 2
    res_table = [
        (640,480),(800,600),(1024,768),(1280,960),(1600,1200),(640,480),
        (1024,576),(1024,640),(1280,720),(1280,800),(1440,810),(1440,900),
        (1680,945),(1680,1050),(1920,1080),(1920,1200)
    ]
    res_idx = data[pos]; pos += 1
    info['resolution'] = res_table[res_idx] if res_idx < 16 else (0, 0)
    pos += 1
    title_len = data[pos]; pos += 1
    info['title'] = data[pos:pos + title_len].rstrip(b'\x00').decode('cp932', errors='replace') if title_len else ''
    pos += title_len
    cmd_count = struct.unpack_from('<h', data, pos)[0]; pos += 2
    commands = []
    for _ in range(cmd_count):
        typ = struct.unpack_from('<b', data, pos)[0]
        nl = data[pos + 1]
        name = data[pos + 2:pos + 2 + nl].rstrip(b'\x00').decode('ascii', errors='replace')
        commands.append((typ, name))
        pos += 2 + nl
    info['commands'] = commands
    return info


def read_str(data, offset):
    """读取STR opcode, 在第一个\\0处截断"""
    sl = data[offset + 1]
    if sl < 2:
        return None, sl
    sb = data[offset + 2:offset + 2 + sl]
    if not sb or sb[-1] != 0:
        return None, sl
    nul = sb.index(0)
    sb_trimmed = sb[:nul]
    if not sb_trimmed:
        return None, sl
    try:
        t = sb_trimmed.decode('cp932')
        return t, sl
    except:
        pass
    return None, sl


def build_chr_funcs(data, bytecode_end, scan_limit=0x800):
    """扫描角色函数定义区"""
    funcs = {}
    limit = min(scan_limit, bytecode_end)
    i = 4
    while i < limit:
        if data[i] == 0x01:
            for j in range(i + 1, min(i + 30, limit)):
                if (data[j] == 0x0c and j + 4 < limit and
                    data[j + 2] == 0x15 and
                    struct.unpack_from('<H', data, j + 3)[0] == STVAR_CHR_ID):
                    if i not in funcs:
                        funcs[i] = data[j + 1]
                    break
        i += 1
    return funcs


def parse_chr_add(data, entry_point, bytecode_end, commands):
    """解析ChrAdd调用序列"""
    chr_add_idx = None
    for idx, (_, name) in enumerate(commands):
        if name == 'ChrAdd':
            chr_add_idx = idx
            break
    if chr_add_idx is None:
        return []
    tokens = []
    limit = min(entry_point + 0x400, bytecode_end)
    for off, op, operand in iter_opcodes(data, entry_point, limit):
        if op == 0x0e:
            sl = operand
            sb = data[off + 2:off + 2 + sl]
            if sb and sb[-1] == 0:
                try:
                    t = sb[:-1].decode('cp932')
                    tokens.append(('STR', t, off))
                except:
                    tokens.append(('STR_BAD', None, off))
            else:
                tokens.append(('STR_BAD', None, off))
        elif op == 0x0c:
            tokens.append(('PUSH8', operand, off))
        elif op == 0x03:
            tokens.append(('CMD', operand, off))
        elif op == 0x02:
            tokens.append(('CALL', operand, off))
    result = []
    j = 0
    while j < len(tokens) - 4:
        if (tokens[j][0] == 'STR' and tokens[j][1] is not None and
            tokens[j+1][0] == 'PUSH8' and tokens[j+2][0] == 'PUSH8' and
            tokens[j+3][0] == 'STR' and
            tokens[j+4][0] == 'CMD' and tokens[j+4][1] == chr_add_idx):
            result.append((tokens[j+1][1], tokens[j][1]))
            j += 5
        else:
            j += 1
    return result


def build_speaker_map(data, bytecode_end, commands):
    """构建角色映射"""
    info = parse_header(data)
    chr_funcs = build_chr_funcs(data, bytecode_end)
    chr_adds = parse_chr_add(data, info['entry_point'], bytecode_end, commands)
    id_to_name = {idx: name for idx, (gid, name) in enumerate(chr_adds, 1)}
    func_to_name = {a: id_to_name.get(c, f'chr_{c}') for a, c in chr_funcs.items()}
    return func_to_name, id_to_name, chr_adds


def detect_page_clear_funcs(data, bytecode_end):
    """自动检测翻页/清屏函数"""
    call_targets = Counter()
    for off, op, addr in iter_opcodes(data, 4, bytecode_end):
        if op == 0x02 and addr < bytecode_end:
            call_targets[addr] += 1
    candidates = [(addr, cnt) for addr, cnt in call_targets.most_common(20)
                  if addr > 0x800 and addr < bytecode_end]
    page_func = candidates[0][0] if len(candidates) > 0 else None
    clear_func = candidates[1][0] if len(candidates) > 1 else None
    return page_func, clear_func


def extract_dialogues(data):
    """翻页锚点法提取对话文本 (注入时内部使用)"""
    info = parse_header(data)
    bytecode_end = info['header_offset']
    func_to_name, _, _ = build_speaker_map(data, bytecode_end, info['commands'])
    page_func, clear_func = detect_page_clear_funcs(data, bytecode_end)
    if not page_func or not clear_func:
        return []
    default_speaker = None
    results = []
    speaker = default_speaker
    pending = []
    page_id = 0
    for off, op, operand in iter_opcodes(data, info['entry_point'], bytecode_end):
        if op == 0x02:
            addr = operand
            if addr in func_to_name:
                speaker = func_to_name[addr]
                pending = []
            elif addr == page_func:
                for p_off, p_sl, p_text in pending:
                    results.append((p_off, p_sl, p_text, speaker, page_id))
                if pending:
                    page_id += 1
                pending = []
            elif addr == clear_func:
                speaker = default_speaker
                pending = []
            else:
                pending = []
        elif op == 0x0e:
            text, sl = read_str(data, off)
            if text is not None and len(text) >= 1:
                pending.append((off, sl, text))
    return results


def filter_jp_text(results):
    """过滤日文文本"""
    filtered = []
    for off, sl, text, speaker, page_group in results:
        has_kana = any(0x3040 <= ord(c) <= 0x30FF for c in text)
        has_kanji = any(0x4E00 <= ord(c) <= 0x9FFF for c in text)
        if has_kana or has_kanji or text.startswith('「'):
            filtered.append((off, sl, text, speaker, page_group))
    return filtered


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  注入核心逻辑
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def inject_texts(orig_data, translations, encoding='cp932'):
    """将翻译文本注入HCB字节码
    
    参数:
      orig_data:     原始HCB文件的bytes
      translations:  翻译条目列表, 支持两种格式:
                     - [{"message_id": N, "message": "..."}]
                     - [{"offset": "0xNNNNNN", "translation": "..."}]
      encoding:      目标编码 (默认cp932)
    
    返回: 修改后的完整HCB数据 (bytes)
    """
    data = bytearray(orig_data)
    info = parse_header(data)
    bytecode_end = info['header_offset']

    # ── Step 1: 提取原始对话, 构建定位映射 ──
    all_lines = extract_dialogues(data)
    jp_lines = filter_jp_text(all_lines)

    # message_id → (offset, orig_len, orig_text)
    id_to_loc = {}
    for idx, (off, sl, text, spk, _pg) in enumerate(jp_lines):
        id_to_loc[idx] = (off, sl, text)

    # offset → (offset, orig_len, orig_text)
    off_to_loc = {}
    for off, sl, text, spk, _pg in jp_lines:
        off_to_loc[off] = (off, sl, text)

    # ── Step 2: 解析翻译条目, 生成patch列表 ──
    patches = []  # [(offset, orig_len, new_cp932_bytes), ...]

    for entry in translations:
        if 'parts' in entry and 'message' in entry:
            # ── 合并格式: message用\n连接, parts记录各子行 ──
            parts = entry['parts']
            orig_message = entry.get('_orig_message', '')
            new_message = entry['message']
            if new_message == orig_message:
                continue  # 未翻译
            
            new_lines = new_message.replace('\r\n', '\n').split('\n')
            
            # 对齐: 翻译行数可能与原始不同
            # 策略: 按顺序填充parts, 多余的行追加到最后一个part,
            #        不足的part填空字符串(保留原文)
            for pi, part in enumerate(parts):
                off_val = part['offset']
                if isinstance(off_val, str):
                    p_off = int(off_val, 16) if off_val.startswith('0x') else int(off_val)
                else:
                    p_off = int(off_val)
                p_orig_len = part['max_bytes'] + 1  # 含\0
                
                if p_off not in off_to_loc:
                    continue
                _, _, p_orig_text = off_to_loc[p_off]
                
                if pi < len(new_lines):
                    if pi == len(parts) - 1 and len(new_lines) > len(parts):
                        # 最后一个part: 合并剩余所有翻译行
                        p_new_text = '\n'.join(new_lines[pi:])
                    else:
                        p_new_text = new_lines[pi]
                else:
                    p_new_text = p_orig_text  # 不足时保留原文
                
                if p_new_text == p_orig_text:
                    continue
                
                try:
                    new_bytes = p_new_text.encode(encoding) + b'\x00'
                except UnicodeEncodeError:
                    print(f"[WARN] 编码失败 @ 0x{p_off:X}: {p_new_text[:30]}...",
                          file=sys.stderr)
                    continue
                patches.append((p_off, p_orig_len, new_bytes))
        
        elif 'message_id' in entry:
            # ── 旧格式: 按message_id定位 ──
            mid = entry['message_id']
            if mid not in id_to_loc:
                print(f"[WARN] message_id {mid} not found, skipping", file=sys.stderr)
                continue
            off, orig_len, orig_text = id_to_loc[mid]
            new_text = entry.get('message', entry.get('translation', orig_text))
            if new_text == orig_text:
                continue
            try:
                new_bytes = new_text.encode(encoding) + b'\x00'
            except UnicodeEncodeError:
                print(f"[WARN] 编码失败 @ 0x{off:X}: {new_text[:30]}...", file=sys.stderr)
                continue
            patches.append((off, orig_len, new_bytes))

        elif 'offset' in entry:
            # ── 旧格式: 按offset定位 ──
            off_val = entry['offset']
            if isinstance(off_val, str):
                off = int(off_val, 16) if off_val.startswith('0x') else int(off_val)
            else:
                off = int(off_val)
            if off not in off_to_loc:
                print(f"[WARN] offset 0x{off:X} not found, skipping", file=sys.stderr)
                continue
            _, orig_len, orig_text = off_to_loc[off]
            new_text = entry.get('translation', orig_text)
            if new_text == orig_text:
                continue
            try:
                new_bytes = new_text.encode(encoding) + b'\x00'
            except UnicodeEncodeError:
                print(f"[WARN] 编码失败 @ 0x{off:X}: {new_text[:30]}...", file=sys.stderr)
                continue
            patches.append((off, orig_len, new_bytes))

    if not patches:
        print("[INFO] 无需注入的文本", file=sys.stderr)
        return bytes(data)

    # ── Step 3: 分类 ──
    inplace = []   # 可就地替换
    relocate = []  # 需要trampoline跳板

    for off, orig_len, new_bytes in patches:
        if len(new_bytes) <= orig_len:
            inplace.append((off, orig_len, new_bytes))
        else:
            relocate.append((off, orig_len, new_bytes))

    print(f"[INFO] 就地替换: {len(inplace)} | 重定位: {len(relocate)}", file=sys.stderr)

    # ── Step 4: 就地替换 ──
    for off, orig_len, new_bytes in inplace:
        # data[off]   = 0x0E (不变)
        # data[off+1] = orig_len (不变, 控制VM的PC跳过距离)
        # data[off+2 : off+2+orig_len] = 新数据 + \0填充
        padded = new_bytes + b'\x00' * (orig_len - len(new_bytes))
        data[off + 2:off + 2 + orig_len] = padded

    # ── Step 5: Trampoline跳板法 (长文本重定位) ──
    #
    # 原理: 不移动任何现有bytecode, 避免修正全局绝对偏移
    #
    # 原位 (2+orig_len 字节):
    #   替换为: [0x06(JMP)][trampoline_addr:u32] + [0x00填充...]
    #
    # 文件末尾追加 (trampoline区):
    #   [0x0E(STR)][new_len:u8][new_data + \0]
    #   [0x06(JMP)][resume_addr:u32]
    #
    #   resume_addr = 原STR之后的下一条指令 = off + 2 + orig_len
    #
    # 要求: 原STR总大小(2+orig_len) ≥ 5字节, 即 orig_len ≥ 3
    #
    if relocate:
        append_buf = bytearray()
        trampoline_count = 0
        truncate_count = 0

        for off, orig_len, new_bytes in relocate:
            total_orig = 2 + orig_len  # [0x0E][len][data...]
            new_len = len(new_bytes)

            if new_len > 255:
                print(f"[WARN] 文本过长({new_len}B > 255B) @ 0x{off:X}, 截断",
                      file=sys.stderr)
                new_bytes = new_bytes[:254] + b'\x00'
                new_len = 255

            if total_orig < 5:
                # 原区域放不下JMP(5字节), 强制截断
                truncated = new_bytes[:orig_len - 1] + b'\x00'
                padded = truncated + b'\x00' * (orig_len - len(truncated))
                data[off + 2:off + 2 + orig_len] = padded
                truncate_count += 1
                continue

            # trampoline地址 = 当前bytecode末尾 + 已追加的数据长度
            trampoline_addr = bytecode_end + len(append_buf)
            resume_addr = off + 2 + orig_len  # 原STR后的下一条指令

            # 原位: [JMP trampoline_addr] + NOP填充
            patch = bytearray(total_orig)
            patch[0] = 0x06  # JMP opcode
            struct.pack_into('<I', patch, 1, trampoline_addr)
            data[off:off + total_orig] = patch

            # trampoline: [STR new_text] + [JMP resume]
            trampoline = bytearray()
            trampoline.append(0x0e)       # STR opcode
            trampoline.append(new_len)    # len
            trampoline.extend(new_bytes)  # data (含\0)
            trampoline.append(0x06)       # JMP opcode
            trampoline.extend(struct.pack('<I', resume_addr))
            append_buf.extend(trampoline)
            trampoline_count += 1

        if truncate_count:
            print(f"[WARN] {truncate_count} 条文本因原区域过小被截断",
                  file=sys.stderr)

        if append_buf:
            new_bytecode_end = bytecode_end + len(append_buf)
            struct.pack_into('<I', data, 0, new_bytecode_end)  # 更新header_offset
            data[bytecode_end:bytecode_end] = append_buf        # 插入trampoline区
            print(f"[INFO] trampoline跳板: {trampoline_count} 条, "
                  f"追加 {len(append_buf)} bytes", file=sys.stderr)

    return bytes(data)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  验证与辅助
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def verify_output(path):
    """验证输出HCB文件的完整性"""
    with open(path, 'rb') as f:
        data = f.read()
    try:
        info = parse_header(data)
        bytecode_end = info['header_offset']
        count = 0
        for _ in iter_opcodes(data, 4, bytecode_end):
            count += 1
        print(f"[VERIFY] OK: {count} opcodes, entry=0x{info['entry_point']:X}, "
              f"title={info['title']}")
    except Exception as e:
        print(f"[VERIFY] FAILED: {e}", file=sys.stderr)


def parse_txt_translations(path):
    """解析TXT格式的翻译文件 (tab分隔5列)
    
    格式: offset<TAB>orig_len<TAB>speaker<TAB>original<TAB>translation
    以#开头的行为注释
    """
    entries = []
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.rstrip('\n').rstrip('\r')
            if line.startswith('#') or not line.strip():
                continue
            parts = line.split('\t')
            if len(parts) < 5:
                continue
            offset_str, orig_len_str, speaker, original, translation = parts[:5]
            for old, new in [('\\\\', '\x00'), ('\\n', '\n'), ('\\r', '\r'), ('\\t', '\t')]:
                original = original.replace(old, new)
                translation = translation.replace(old, new)
            original = original.replace('\x00', '\\')
            translation = translation.replace('\x00', '\\')
            entries.append({
                'offset': offset_str,
                'original': original,
                'translation': translation,
            })
    return entries


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  CLI
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def main():
    p = argparse.ArgumentParser(
        description='HCB脚本文本注入工具 — アトリエかぐや/ωstar引擎',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""示例:
  python hcb_inject.py 留档\\s.hcb s_translated.json
  python hcb_inject.py 留档\\s.hcb s_translated.json -o s.hcb
  python hcb_inject.py 留档\\s.hcb s_translated.txt -o s.hcb -e cp932

注意:
  - 第一个参数必须是原始(未修改过的)HCB文件
  - 翻译文件支持JSON和TXT两种格式
  - 翻译后文本可以超过原文长度,工具会自动处理重定位
  - 单条文本上限254字节(cp932编码后), 约127个全角字符""")

    p.add_argument('input', help='原始HCB文件路径 (必须是未修改过的原版)')
    p.add_argument('translation', help='翻译文件路径 (.json 或 .txt)')
    p.add_argument('-o', '--output', help='输出HCB文件路径 (默认: 原文件名_cn.hcb)')
    p.add_argument('-e', '--encoding', default='cp932',
                   help='目标编码 (默认: cp932)')

    args = p.parse_args()

    # 读取原始HCB
    with open(args.input, 'rb') as f:
        orig_data = f.read()

    # 读取翻译文件
    trans_file = args.translation
    if trans_file.endswith('.json'):
        with open(trans_file, 'r', encoding='utf-8') as f:
            translations = json.load(f)
    elif trans_file.endswith('.txt'):
        translations = parse_txt_translations(trans_file)
    else:
        print(f"[ERROR] 不支持的翻译文件格式: {trans_file}", file=sys.stderr)
        sys.exit(1)

    print(f"[INFO] 加载翻译条目: {len(translations)}")

    # 注入
    result = inject_texts(orig_data, translations, encoding=args.encoding)

    # 输出
    out = args.output or os.path.splitext(args.input)[0] + '_cn.hcb'
    with open(out, 'wb') as f:
        f.write(result)
    print(f"[INFO] 输出: {out} ({len(result)} bytes)")

    # 验证
    verify_output(out)


if __name__ == '__main__':
    main()
