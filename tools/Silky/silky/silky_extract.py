"""silky_extract.py — Silky MES op.txt -> translate.txt 文本提取。

输入：silky_op.py 生成的 *.op.txt
输出：translate.txt（GalTransl 风格的双行格式 ◇/◆，◇ 行原文，◆ 行待翻译）

设计：
  * 不做注音特殊解析。每个对话块里所有 STR_CRYPT (0x0A) / STR_UNCRYPT (0x0B)
    字符串按出现顺序平铺，用 \\n 分隔在一个 ◇ 条目里。例如注音段：
      ◇0004◇『なあ、なんで何も言わないんだ、\\n \\nな　お　や\\n奈緒矢……』
    译者按顺序翻译这 4 段，import 时按相同顺序写回。段数必须一致。
  * 角色名 (PUSH_STR + PUSH 模式) 单独占一个 ◇/◆ 条目，标记为 ◇N◇name◇xxx。
    本游戏没用人名行，但保留逻辑兼容其他 silky 游戏。

CLI:
  python silky_extract.py <input.op.txt> <output.translate.txt>
"""

import json
import re

# ============================================================
# block 识别用的常量集合（从 silky_op 的 OP_TABLE 推导出来的标签）
# ============================================================

# 角色名块里出现的特殊 PUSH 数值（不同 silky 引擎变体可能不同）
_NAME_BLOCK_PUSH_VALS = frozenset([83886080, 167772160])

# 块内 op：扫到这些不结束当前对话块，跳过 (op + arg) 两行
_BLOCK_INTERNAL_OPCODES = frozenset([
    '#1-PUSH', '#1-PUSH_STR', '#1-RETURN',
    '#1-ff', '#1-fe', '#1-fd', '#1-fc', '#1-fb', '#1-fa',
    '#1-JUMP_2', '#1-3a', '#1-3b', '#1-3c', '#1-3d', '#1-3e', '#1-3f',
    '#1-40', '#1-41', '#1-42', '#1-43',
    '#1-34', '#1-35', '#1-37', '#1-38',
    '#1-10', '#1-11', '#1-0c', '#1-0d', '#1-0e', '#1-0f',
    '#1-02', '#1-03', '#1-04', '#1-05', '#1-06',
    '#1-17', '#1-18',
])

# 块结束 op：扫到这些当前对话块结束
_BLOCK_END_OPCODES = frozenset([
    '#1-MESSAGE', '#1-JUMP', '#1-MSG_OFSETTER', '#1-SPEC_OFSETTER',
    '#1-1a', '#1-1b',
])

# STR_CRYPT (0x0A) 和 STR_UNCRYPT (0x0B) 都承载文本。
# 本游戏里 0x0A = 对话/注音内容，0x0B = 注音分隔符 (单字节空格)。
# 提取时统一收集，1:1 对应写回，保证字节级 round-trip。
_STR_OPCODE_LINES = frozenset(['#1-STR_CRYPT', '#1-STR_UNCRYPT'])


# ============================================================
# 辅助小工具
# ============================================================

def _is_label_or_free(line: str) -> bool:
    """是否是标签或 free bytes 行（#0- #2- #3）。"""
    return line.startswith('#0-') or line.startswith('#2-') or line.startswith('#3')


def _parse_json_str(arg_line: str) -> str:
    try:
        val = json.loads(arg_line)
        if isinstance(val, list) and len(val) > 0:
            return str(val[0])
    except (json.JSONDecodeError, IndexError):
        pass
    return arg_line


def _parse_json_first_int(arg_line: str) -> int:
    try:
        val = json.loads(arg_line)
        if isinstance(val, list) and len(val) > 0:
            return int(val[0])
    except (json.JSONDecodeError, IndexError, ValueError):
        pass
    return 0


def _parse_json_first_int(arg_line: str) -> int:
    try:
        val = json.loads(arg_line)
        if isinstance(val, list) and len(val) > 0:
            return int(val[0])
    except (json.JSONDecodeError, IndexError, ValueError):
        pass
    return 0


# ============================================================
# 角色名块识别
# ============================================================

def _detect_name_block(lines, i, total):
    """检查 line i 是否是角色名块的 PUSH_STR。

    Pattern A: PUSH_STR[name] -> PUSH[83886080]  -> PUSH[...] -> 18[]
    Pattern B: PUSH_STR[name] -> PUSH[167772160] -> PUSH[...] -> 34[] -> PUSH[...] -> 18[]

    返回角色名字符串，或 None。
    """
    if i + 7 >= total:
        return None
    cl = lines[i].rstrip('\n')
    if cl != '#1-PUSH_STR':
        return None

    arg = _parse_json_str(lines[i + 1].rstrip('\n'))
    # 角色名必须是非 ASCII (避免误判路径字符串)
    try:
        arg.encode('ascii')
        return None
    except UnicodeEncodeError:
        pass

    if lines[i + 2].rstrip('\n') != '#1-PUSH':
        return None
    try:
        push_val = json.loads(lines[i + 3].rstrip('\n'))
        if not (isinstance(push_val, list) and push_val[0] in _NAME_BLOCK_PUSH_VALS):
            return None
    except (json.JSONDecodeError, IndexError, KeyError):
        return None

    # Pattern A
    if (i + 6 < total and
        lines[i + 4].rstrip('\n') == '#1-PUSH' and
        lines[i + 6].rstrip('\n') == '#1-18'):
        return arg

    # Pattern B
    if (i + 10 < total and
        lines[i + 4].rstrip('\n') == '#1-PUSH' and
        lines[i + 6].rstrip('\n') == '#1-34' and
        lines[i + 8].rstrip('\n') == '#1-PUSH' and
        lines[i + 10].rstrip('\n') == '#1-18'):
        return arg

    return None


# ============================================================
# 对话块收集
# ============================================================

def _try_match_ruby_at_tns(lines, tns_idx, total):
    """检查 tns_idx (一个 #1-TO_NEW_STRING 行) 是否启动一个 ruby 段。

    通用 ruby 结构（从 TNS[1] 开始；不假设前文存在）：
      tns_idx + 0:  #1-TO_NEW_STRING
      tns_idx + 1:  [1]                       ← arg=1 是 ruby 信号
      ── ruby 内部，任意条 STR_CRYPT/STR_UNCRYPT ──
        STR_UNCRYPT [" "]   → sep
        STR_CRYPT  ["　"]   → sep（单全角空格）
        STR_CRYPT  ["abc"]  → reading
      ── ruby 结束 ──
      #1-RETURN []
      #1-STR_CRYPT ["base"]

    返回 dict 含：base_arg_idx, reading_slots, end_idx，或 None。
    """
    if tns_idx + 1 >= total:
        return None
    if lines[tns_idx].rstrip('\n') != '#1-TO_NEW_STRING':
        return None
    if _parse_json_first_int(lines[tns_idx + 1].rstrip('\n')) != 1:
        return None

    j = tns_idx + 2
    inner = []
    while j < total:
        op = lines[j].rstrip('\n')
        if op == '#1-RETURN':
            break
        if op not in ('#1-STR_CRYPT', '#1-STR_UNCRYPT'):
            return None
        if j + 1 >= total:
            return None
        val = _parse_json_str(lines[j + 1].rstrip('\n'))
        if op == '#1-STR_UNCRYPT':
            kind = 'sep_uncrypt'
        elif val == '\u3000':
            kind = 'sep_full'
        else:
            kind = 'reading'
        inner.append((j + 1, val, kind))
        j += 2

    if not inner:
        return None
    if j >= total or lines[j].rstrip('\n') != '#1-RETURN':
        return None
    j += 2
    if j + 1 >= total or lines[j].rstrip('\n') != '#1-STR_CRYPT':
        return None
    base_arg_idx = j + 1
    base = _parse_json_str(lines[base_arg_idx].rstrip('\n'))
    end_idx = j + 2

    return {
        'reading_slots': inner,
        'base_arg_idx': base_arg_idx,
        'base': base,
        'end_idx': end_idx,
    }


def _collect_text_block(lines, start, total):
    """收集对话块所有 STR_CRYPT/STR_UNCRYPT 字符串，注音段合并为一条。

    text_parts 里每个元素：
      ('text', arg_line_idx, text_value)  - 普通字符串
      ('ruby', ruby_dict)                 - 注音整段 (含 4 个 arg 位置 + 3 个文本)
    """
    text_parts = []
    detected_name = None
    name_arg_line_idx = None
    i = start

    while i < total:
        cl = lines[i].rstrip('\n')

        # 角色名块？
        name = _detect_name_block(lines, i, total)
        if name is not None:
            detected_name = name
            name_arg_line_idx = i + 1
            i += 2
            continue

        # ruby 段：以 TO_NEW_STRING [1] 起始
        if cl == '#1-TO_NEW_STRING':
            arg_val = _parse_json_first_int(lines[i + 1].rstrip('\n')) if i + 1 < total else -1
            if arg_val == 1:
                ruby = _try_match_ruby_at_tns(lines, i, total)
                if ruby is not None:
                    text_parts.append(('ruby', ruby))
                    i = ruby['end_idx']
                    continue
            elif arg_val == 0:
                # 真正的换段信号 → 输出 \n
                text_parts.append(('newline',))
                i += 2
                continue
            # 异常 arg 值（不是 0 也不是 1），跳过
            i += 2
            continue

        if cl in _STR_OPCODE_LINES:
            arg_line = lines[i + 1].rstrip('\n') if i + 1 < total else '[]'
            text_val = _parse_json_str(arg_line)
            text_parts.append(('text', i + 1, text_val))
            i += 2

        elif cl in _BLOCK_END_OPCODES:
            break

        elif cl in _BLOCK_INTERNAL_OPCODES:
            i += 2

        elif _is_label_or_free(cl):
            i += 1

        elif cl.startswith('#1-'):
            i += 2

        elif cl.startswith('$'):
            i += 1

        else:
            i += 1

    return text_parts, i, detected_name, name_arg_line_idx


# ============================================================
# 主入口
# ============================================================

def extract_text(opcode_txt_path: str, text_txt_path: str) -> int:
    """从 op.txt 提取所有需要翻译的字符串，写出 GalTransl 双行格式 translate.txt。

    一个对话块（MESSAGE 起点 → 块结束 op）的多个 STR 用 \\n 拼成一条，让译者
    看到完整句子上下文。注音 reading 不暴露（注入时填全角空格占位），但 ruby
    的 base 与同块其他 STR 一起进入 \\n 拼接。

    输出格式：
      ◇0000◇句1\\n句2\\n句3
      ◆0000◆句1\\n句2\\n句3
                              <- 空行分隔
      ◇0001◇下一块
      ...

    角色名条目独立占一条：
      ◇0001◇name◇角色名
      ◆0001◆name◆角色名

    返回总条目数。
    """
    with open(opcode_txt_path, 'r', encoding='utf-8-sig') as f:
        lines = f.readlines()

    total = len(lines)
    entries = []  # ('name', name_str) 或 ('text', joined_str)
    i = 0

    def _join_parts(parts):
        """按 newline 标记决定 \\n 位置；普通 STR 之间和 ruby 段内部都直接相邻拼接。"""
        out = []
        for p in parts:
            if p[0] == 'text':
                out.append(p[2])
            elif p[0] == 'ruby':
                out.append(p[1]['base'])
            elif p[0] == 'newline':
                out.append('\\n')
        return ''.join(out)

    while i < total:
        line = lines[i].rstrip('\n')

        if line == '#1-MESSAGE':
            i += 2
            text_parts, i, block_name, _ = _collect_text_block(lines, i, total)
            if block_name is not None:
                entries.append(('name', block_name))
            joined = _join_parts(text_parts)
            if joined:
                entries.append(('text', joined))

        elif line in _STR_OPCODE_LINES or line == '#1-TO_NEW_STRING':
            text_parts, i, block_name, _ = _collect_text_block(lines, i, total)
            if block_name is not None:
                entries.append(('name', block_name))
            joined = _join_parts(text_parts)
            if joined:
                entries.append(('text', joined))
        else:
            i += 1

    # 写出 ◇/◆ 双行格式
    with open(text_txt_path, 'w', encoding='utf-8-sig') as out:
        for seq, (kind, val) in enumerate(entries):
            if kind == 'name':
                out.write(f'\u25c7{seq:04d}\u25c7name\u25c7{val}\n')
                out.write(f'\u25c6{seq:04d}\u25c6name\u25c6{val}\n')
            else:
                out.write(f'\u25c7{seq:04d}\u25c7{val}\n')
                out.write(f'\u25c6{seq:04d}\u25c6{val}\n')
            out.write('\n')

    return len(entries)


if __name__ == "__main__":
    import argparse, os, glob

    ap = argparse.ArgumentParser(
        description="Silky MES op.txt -> translate.txt (单文件 或 目录批处理)"
    )
    ap.add_argument("input", help="单个 *.op.txt 文件，或包含 *.op.txt 的目录")
    ap.add_argument("output", help="单文件输出路径，或输出目录")
    ap.add_argument("--pattern", default="*.op.txt",
                    help="目录模式下的 glob 通配符 (default: *.op.txt)")
    args = ap.parse_args()

    def _strip_ext(name, exts):
        for e in exts:
            if name.lower().endswith(e.lower()):
                return name[:-len(e)]
        return os.path.splitext(name)[0]

    if os.path.isdir(args.input):
        os.makedirs(args.output, exist_ok=True)
        files = sorted(glob.glob(os.path.join(args.input, args.pattern)))
        print(f"[batch] {len(files)} 个 op.txt -> {args.output}")
        total_entries = 0
        for f in files:
            base = _strip_ext(os.path.basename(f), ['.op.txt'])
            out = os.path.join(args.output, base + '.translate.txt')
            n = extract_text(f, out)
            total_entries += n
            print(f"  [+] {os.path.basename(f)}: {n} entries -> {os.path.basename(out)}")
        print(f"[batch] 完成 {len(files)} 个文件, 共 {total_entries} 条")
    else:
        n = extract_text(args.input, args.output)
        print(f"[+] extracted {n} entries: {args.input} -> {args.output}")
