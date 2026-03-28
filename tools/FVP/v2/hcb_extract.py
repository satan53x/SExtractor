#!/usr/bin/env python3
"""
hcb_extract.py — HCB脚本文本提取工具
引擎: アトリエかぐや/ωstar HCB字节码 (v26)
游戏: BOIN 等

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  用法
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  提取文本为JSON (推荐,可直接用于GalTransl/SE二次提取):
    python hcb_extract.py s.hcb
    python hcb_extract.py s.hcb -o s.json

  提取文本为TXT (tab分隔, 适合手动编辑):
    python hcb_extract.py s.hcb -f txt

  查看HCB文件信息 (角色表/命令表/STR统计):
    python hcb_extract.py s.hcb --info

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  输出JSON格式说明
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  每条对话包含以下字段:
    name       : 说话人名字 (旁白/内心独白为null)
    message    : 对话文本内容 (cp932编码的原文)
    message_id : 序号 (从0开始, 用于hcb_inject.py定位)
    offset     : STR opcode在HCB文件中的十六进制偏移
    max_bytes  : 原始文本最大字节数 (不含\\0终止符)

  用SE二次提取时的正则 (TXT引擎, json [{name,msgRN}] 格式):
    01_search="name": "(?P<name>.+)"
    11_search="name": null
    12_search="message": "(?P<message>.+)"

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  HCB文件结构
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  [0x00-0x03]  u32    header_offset (指向尾部header)
  [0x04-...]   bytes  bytecode区 (opcodes + 内嵌字符串)
  [header-...] bytes  header区 (entry_point, 分辨率, 标题, CMD表)

  STR opcode (0x0E) 格式:
    [0x0E][len:u8][cp932_data + \\x00]
    len = 字符串数据长度 (含\\0终止符, 最大255)
    VM执行时: 压栈(type=0x04, offset=当前PC), 然后 PC += len

  提取方法: 翻页锚点法
    遍历entry_point到header之间的bytecode:
    - CALL角色函数 → 切换当前speaker
    - STR → 加入pending队列
    - CALL翻页函数 → 将pending中的文本输出为对话行
    - CALL清屏函数 → 重置speaker为旁白
    - 其他CALL → 清空pending (防止非对话文本混入)
"""

import struct, os, argparse, json, sys
from collections import Counter


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  opcode 定义
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# 5字节指令: [opcode:1][addr:u32]
OP_SIZE_5 = {0x02, 0x06, 0x07, 0x0a}  # CALL, JMP, JZ, JNZ

# 3字节指令: [opcode:1][val:u16]
OP_SIZE_3 = {0x0b, 0x0f, 0x03, 0x15, 0x11, 0x12, 0x13}

# 2字节指令: [opcode:1][val:u8]
OP_SIZE_2 = {0x0c, 0x10, 0x16}

# 其余为1字节指令

OP_NAMES = {
    0x00: 'NOP', 0x01: 'RET', 0x02: 'CALL', 0x03: 'CMD',
    0x04: 'CALL2', 0x05: 'RET2', 0x06: 'JMP', 0x07: 'JZ',
    0x08: 'JMP2', 0x09: 'JZ2', 0x0a: 'JNZ', 0x0b: 'PUSH16',
    0x0c: 'PUSH8', 0x0d: 'PUSH_F', 0x0e: 'STR', 0x0f: 'LDVAR',
    0x10: 'LDVAR8', 0x11: 'LDGLOB', 0x12: 'LDGLOB2', 0x13: 'UNK13',
    0x14: 'UNK14', 0x15: 'STVAR', 0x16: 'STVAR8',
}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  核心解析函数
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def iter_opcodes(data, start, end):
    """遍历bytecode区的所有opcode
    
    yield: (offset, opcode, operand)
      - STR(0x0E): operand = len (字符串长度含\\0)
      - CALL/JMP/JZ/JNZ: operand = u32绝对地址
      - PUSH16等: operand = u16值
      - PUSH8等: operand = u8值
      - 其他: operand = None
    """
    i = start
    while i < end - 1:
        op = data[i]
        if op == 0x0e:  # STR: [0x0E][len:u8][data...]
            sl = data[i + 1]
            yield (i, 0x0e, sl)
            i += 2 + sl
        elif op in OP_SIZE_5:  # [op][addr:u32]
            addr = struct.unpack_from('<I', data, i + 1)[0]
            yield (i, op, addr)
            i += 5
        elif op in OP_SIZE_3:  # [op][val:u16]
            val = struct.unpack_from('<H', data, i + 1)[0]
            yield (i, op, val)
            i += 3
        elif op in OP_SIZE_2:  # [op][val:u8]
            yield (i, op, data[i + 1])
            i += 2
        else:  # 1字节指令
            yield (i, op, None)
            i += 1


def parse_header(data):
    """解析HCB尾部header, 返回包含以下字段的dict:
      header_offset, entry_point, count_a, count_b,
      resolution, title, commands
    """
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
    pos += 1  # padding
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
    """读取offset处的STR opcode, 返回 (decoded_text, len字段值)
    
    在第一个\\0处截断 (支持就地替换后的\\0 padding),
    解码失败返回 (None, len)
    """
    sl = data[offset + 1]
    if sl < 2:
        return None, sl
    sb = data[offset + 2:offset + 2 + sl]
    if not sb or sb[-1] != 0:
        return None, sl
    # 在第一个\0处截断
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


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  角色系统解析
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

STVAR_CHR_ID = 0x00AD  # 角色ID的变量槽位


def build_chr_funcs(data, bytecode_end, scan_limit=0x800):
    """扫描bytecode开头的角色函数定义区
    
    模式: [RET(0x01)] ... [PUSH8(0x0C) chr_id] [STVAR(0x15) 0x00AD]
    返回: {函数地址: chr_id}
    """
    funcs = {}
    limit = min(scan_limit, bytecode_end)
    i = 4
    while i < limit:
        if data[i] == 0x01:  # RET = 函数边界
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
    """解析entry_point处的ChrAdd调用序列
    
    模式: [STR name] [PUSH8 game_id] [PUSH8 vol] [STR voice] [CMD ChrAdd_idx]
    返回: [(game_id, name), ...]
    """
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
    """构建完整的角色映射
    返回: (func_to_name, id_to_name, chr_adds)
    """
    info = parse_header(data)
    chr_funcs = build_chr_funcs(data, bytecode_end)
    chr_adds = parse_chr_add(data, info['entry_point'], bytecode_end, commands)
    id_to_name = {idx: name for idx, (gid, name) in enumerate(chr_adds, 1)}
    func_to_name = {a: id_to_name.get(c, f'chr_{c}') for a, c in chr_funcs.items()}
    return func_to_name, id_to_name, chr_adds


def detect_page_clear_funcs(data, bytecode_end):
    """自动检测翻页函数和清屏函数
    
    原理: 统计CALL目标的出现频率,
    翻页函数 = 最频繁被调用的函数 (每句对话结尾都会调用)
    清屏函数 = 第二频繁的函数 (场景切换/角色变更时调用)
    """
    call_targets = Counter()
    for off, op, addr in iter_opcodes(data, 4, bytecode_end):
        if op == 0x02 and addr < bytecode_end:
            call_targets[addr] += 1
    candidates = [(addr, cnt) for addr, cnt in call_targets.most_common(20)
                  if addr > 0x800 and addr < bytecode_end]
    page_func = candidates[0][0] if len(candidates) > 0 else None
    clear_func = candidates[1][0] if len(candidates) > 1 else None
    return page_func, clear_func


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  文本提取
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def extract_dialogues(data):
    """翻页锚点法提取对话文本
    
    返回: [(offset, str_len, text, speaker, page_group), ...]
    page_group: 翻页分组编号, 同一翻页内的多条STR共享同一编号
    """
    info = parse_header(data)
    bytecode_end = info['header_offset']
    func_to_name, id_to_name, chr_adds = build_speaker_map(
        data, bytecode_end, info['commands'])
    page_func, clear_func = detect_page_clear_funcs(data, bytecode_end)
    if not page_func or not clear_func:
        print(f"[WARN] 未能自动检测翻页/清屏函数", file=sys.stderr)
        return []

    default_speaker = None  # 无角色函数CALL时 = 旁白(name=null)
    results = []
    speaker = default_speaker
    pending = []
    page_id = 0  # 翻页分组编号

    # 从entry_point开始遍历, 跳过角色函数定义区
    for off, op, operand in iter_opcodes(data, info['entry_point'], bytecode_end):
        if op == 0x02:  # CALL
            addr = operand
            if addr in func_to_name:
                speaker = func_to_name[addr]
                pending = []
            elif addr == page_func:
                # 翻页 → 输出pending中的文本, 共享同一page_group
                for p_off, p_sl, p_text in pending:
                    results.append((p_off, p_sl, p_text, speaker, page_id))
                if pending:
                    page_id += 1
                pending = []
            elif addr == clear_func:
                # 清屏 → 重置speaker为旁白
                speaker = default_speaker
                pending = []
            else:
                # 其他函数调用 → 清空pending防混入
                pending = []
        elif op == 0x0e:  # STR
            text, sl = read_str(data, off)
            if text is not None and len(text) >= 1:
                pending.append((off, sl, text))

    return results


def filter_jp_text(results):
    """过滤出包含日文的文本行 (去除纯ASCII控制字符串)"""
    filtered = []
    for off, sl, text, speaker, page_group in results:
        has_kana = any(0x3040 <= ord(c) <= 0x30FF for c in text)
        has_kanji = any(0x4E00 <= ord(c) <= 0x9FFF for c in text)
        if has_kana or has_kanji or text.startswith('「'):
            filtered.append((off, sl, text, speaker, page_group))
    return filtered


def _merge_lines(jp_lines):
    """合并同一speaker连续的多行为一条
    
    用\\r\\n连接同一speaker的连续文本行。
    speaker切换时断开为新条目。
    
    例如:
      id=27 一条大介 「ご、ごめん。...あわててたん
      id=28 一条大介 だ。悪かった。よっ、と……」
    合并为:
      message = 「ご、ごめん。...あわててたん\\r\\nだ。悪かった。...」
      parts = [{"offset":"0x...", "max_bytes":50}, {"offset":"0x...", "max_bytes":28}]
    
    注入时根据parts按\\r\\n拆回各子行
    """
    if not jp_lines:
        return []
    
    merged = []
    cur_name = jp_lines[0][3]   # speaker
    cur_texts = [jp_lines[0][2]]
    cur_parts = [{"offset": f"0x{jp_lines[0][0]:06X}", "max_bytes": jp_lines[0][1] - 1}]
    
    for off, sl, text, spk, _pg in jp_lines[1:]:
        if spk == cur_name:
            # 同speaker → 追加
            cur_texts.append(text)
            cur_parts.append({"offset": f"0x{off:06X}", "max_bytes": sl - 1})
        else:
            # speaker切换 → 输出当前组
            merged.append({
                "name": cur_name if cur_name else None,
                "message": "\r\n".join(cur_texts),
                "parts": cur_parts,
            })
            cur_name = spk
            cur_texts = [text]
            cur_parts = [{"offset": f"0x{off:06X}", "max_bytes": sl - 1}]
    
    # 最后一组
    merged.append({
        "name": cur_name if cur_name else None,
        "message": "\r\n".join(cur_texts),
        "parts": cur_parts,
    })
    
    return merged


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  CLI
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def cmd_extract(args):
    """提取HCB脚本中的对话文本"""
    with open(args.input, 'rb') as f:
        data = f.read()
    info = parse_header(data)
    bytecode_end = info['header_offset']
    func_to_name, id_to_name, chr_adds = build_speaker_map(
        data, bytecode_end, info['commands'])
    page_func, clear_func = detect_page_clear_funcs(data, bytecode_end)

    print(f"文件: {len(data)} bytes | 标题: {info['title']} | "
          f"分辨率: {info['resolution'][0]}x{info['resolution'][1]}")
    print(f"角色: {len(chr_adds)} | 角色函数: {len(func_to_name)} | "
          f"翻页: 0x{page_func:X} | 清屏: 0x{clear_func:X}")
    for gid, name in chr_adds:
        print(f"  {name} (id=0x{gid:02X})")

    all_lines = extract_dialogues(data)
    jp_lines = filter_jp_text(all_lines)
    print(f"翻页关联文本: {len(all_lines)} | 日文对话: {len(jp_lines)}")
    spk_cnt = Counter(sp for _, _, _, sp, _ in jp_lines)
    for name, cnt in spk_cnt.most_common():
        print(f"  {name}: {cnt}")

    fmt = getattr(args, 'format', 'json')
    if fmt == 'txt':
        out = args.output or os.path.splitext(args.input)[0] + '_text.txt'
        with open(out, 'w', encoding='utf-8') as f:
            f.write(f"# HCB Text Export | {os.path.basename(args.input)} | "
                    f"{info['title']} | {len(jp_lines)} lines\n")
            f.write(f"# offset\torig_len\tspeaker\toriginal\ttranslation\n#\n")
            for off, sl, text, spk, pg in jp_lines:
                s = spk or ''
                e = text.replace('\\', '\\\\').replace('\n', '\\n').replace('\r', '\\r').replace('\t', '\\t')
                f.write(f"0x{off:06X}\t{sl}\t{s}\t{e}\t{e}\n")
    else:
        out = args.output or os.path.splitext(args.input)[0] + '.json'
        if not out.endswith('.json'):
            out += '.json'
        # 合并同一speaker连续的多行为一条 (用\n连接)
        # 翻译时更自然, 注入时自动拆回
        merged = _merge_lines(jp_lines)
        entries = []
        for idx, item in enumerate(merged):
            entries.append({
                "name": item['name'],
                "message": item['message'],
                "message_id": idx,
                "parts": item['parts'],  # 各子行的offset和max_bytes
            })
        with open(out, 'w', encoding='utf-8') as f:
            json.dump(entries, f, ensure_ascii=False, indent=2)
        print(f"  合并后: {len(merged)} 条 (原始 {len(jp_lines)} 行)")

    print(f"输出: {out}")


def cmd_info(args):
    """显示HCB文件的详细信息"""
    with open(args.input, 'rb') as f:
        data = f.read()
    info = parse_header(data)
    bytecode_end = info['header_offset']
    func_to_name, id_to_name, chr_adds = build_speaker_map(
        data, bytecode_end, info['commands'])
    page_func, clear_func = detect_page_clear_funcs(data, bytecode_end)

    print(f"文件: {len(data)} bytes | 标题: {info['title']} | "
          f"分辨率: {info['resolution'][0]}x{info['resolution'][1]}")
    print(f"入口: 0x{info['entry_point']:X} | "
          f"labels: {info['count_a']}+{info['count_b']} | "
          f"命令: {len(info['commands'])}")
    print(f"\n翻页函数: 0x{page_func:X}")
    print(f"清屏函数: 0x{clear_func:X}")
    print(f"\nChrAdd角色注册 ({len(chr_adds)}):")
    for idx, (gid, name) in enumerate(chr_adds, 1):
        print(f"  chr_id={idx} game_id=0x{gid:02X} → {name}")
    print(f"\n角色函数映射 ({len(func_to_name)}):")
    for addr in sorted(func_to_name):
        print(f"  func@0x{addr:04X} → {func_to_name[addr]}")
    print(f"\n命令表 ({len(info['commands'])}):")
    for i, (t, n) in enumerate(info['commands']):
        print(f"  [{i:3d}] p={t} {n}")

    lens = []
    for off, op, operand in iter_opcodes(data, 4, bytecode_end):
        if op == 0x0e:
            lens.append(operand)
    if lens:
        print(f"\nSTR长度统计: total={len(lens)} min={min(lens)} max={max(lens)} "
              f"avg={sum(lens)/len(lens):.1f}")


def main():
    p = argparse.ArgumentParser(
        description='HCB脚本文本提取工具 — アトリエかぐや/ωstar引擎',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""示例:
  python hcb_extract.py s.hcb                  提取为JSON
  python hcb_extract.py s.hcb -o out.json      指定输出路径
  python hcb_extract.py s.hcb -f txt            提取为TXT
  python hcb_extract.py s.hcb --info            查看文件信息

注意:
  - 提取结果中前若干条可能是开发者测试文本,游戏正常流程不执行
  - 注入时请使用 hcb_inject.py, 始终基于原始HCB文件操作""")

    p.add_argument('input', help='输入HCB文件路径')
    p.add_argument('-o', '--output', help='输出文件路径 (默认: 同名.json/.txt)')
    p.add_argument('-f', '--format', choices=['json', 'txt'], default='json',
                   help='输出格式: json(默认) 或 txt(tab分隔)')
    p.add_argument('--info', action='store_true',
                   help='仅显示文件信息,不提取文本')

    args = p.parse_args()
    if args.info:
        cmd_info(args)
    else:
        cmd_extract(args)


if __name__ == '__main__':
    main()
