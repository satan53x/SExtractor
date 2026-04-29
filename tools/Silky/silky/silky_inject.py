"""silky_inject.py — Silky MES translate.txt + op.txt -> 新 op.txt 译文注入。

输入：
  - 原始 *.op.txt（silky_op disasm 产物）
  - translate.txt（译者修改过的 ◆ 行）

输出：
  - 新的 *.op.txt（◆ 行的译文已替换到对应 STR_CRYPT/STR_UNCRYPT 参数行）

之后再用 silky_op asm 把新 op.txt 编回 *.MES。

关键约束：
  * translate.txt 里 ◆ 行用 \\n 分隔的"段数"必须等于原 ◇ 行的段数。
    超出的段被丢弃，缺少的段填空字符串。
  * 注入只改字符串的内容，不改 op 流结构 — 跳转/偏移由 silky_op asm 阶段重新计算。

CLI:
  python silky_inject.py <orig.op.txt> <translate.txt> <new.op.txt>
"""

import json

# 共享的对话块识别集合（与 silky_extract 完全一致）
_NAME_BLOCK_PUSH_VALS = frozenset([83886080, 167772160])

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

_BLOCK_END_OPCODES = frozenset([
    '#1-MESSAGE', '#1-JUMP', '#1-MSG_OFSETTER', '#1-SPEC_OFSETTER',
    '#1-1a', '#1-1b',
])

_STR_OPCODE_LINES = frozenset(['#1-STR_CRYPT', '#1-STR_UNCRYPT'])


def _is_label_or_free(line: str) -> bool:
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


def _try_match_ruby(lines, tns_idx, total):
    """识别 ruby 段（从 TO_NEW_STRING [1] 起）。详见 silky_extract._try_match_ruby_at_tns。"""
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
    end_idx = j + 2

    return {
        'reading_slots': inner,
        'base_arg_idx': base_arg_idx,
        'end_idx': end_idx,
    }


def _detect_name_block(lines, i, total):
    """识别角色名块，返回名字串或 None。逻辑与 silky_extract 完全一致。"""
    if i + 7 >= total:
        return None
    cl = lines[i].rstrip('\n')
    if cl != '#1-PUSH_STR':
        return None
    arg = _parse_json_str(lines[i + 1].rstrip('\n'))
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
    if (i + 6 < total and
        lines[i + 4].rstrip('\n') == '#1-PUSH' and
        lines[i + 6].rstrip('\n') == '#1-18'):
        return arg
    if (i + 10 < total and
        lines[i + 4].rstrip('\n') == '#1-PUSH' and
        lines[i + 6].rstrip('\n') == '#1-34' and
        lines[i + 8].rstrip('\n') == '#1-PUSH' and
        lines[i + 10].rstrip('\n') == '#1-18'):
        return arg
    return None


def _collect_text_block(lines, start, total):
    """收集对话块中所有 STR 字符串，注音段合并。与 silky_extract 一致。

    text_parts 元素：
      ('text', arg_line_idx, text_value)
      ('ruby', ruby_dict)
    """
    text_parts = []
    detected_name = None
    name_arg_line_idx = None
    i = start

    while i < total:
        cl = lines[i].rstrip('\n')

        name = _detect_name_block(lines, i, total)
        if name is not None:
            detected_name = name
            name_arg_line_idx = i + 1
            i += 2
            continue

        if cl == '#1-TO_NEW_STRING':
            arg_val = _parse_json_first_int(lines[i + 1].rstrip('\n')) if i + 1 < total else -1
            if arg_val == 1:
                ruby = _try_match_ruby(lines, i, total)
                if ruby is not None:
                    text_parts.append(('ruby', ruby))
                    i = ruby['end_idx']
                    continue
            elif arg_val == 0:
                text_parts.append(('newline',))
                i += 2
                continue
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


def import_text(opcode_txt_path: str, text_txt_path: str, output_txt_path: str) -> int:
    """把 translate.txt 的 ◆ 行注入回 op.txt 的 STR 参数行。

    每个 ◆ 条目对应一个 STR (text 或 ruby base) 或一个 name。1:1 严格对应，
    顺序与 extract_text 完全一致。注音 reading 不在译文里，注入时按原 reading
    去 \\u3000 后的字符数填全角空格占位。

    translate.txt 行格式：
      ◆0001◆name◆角色译名     (角色名条目)
      ◆0002◆译文一句          (普通文本 / ruby base)

    返回成功扫描的条目数。
    """
    # 1. 读 translate.txt，把所有 ◆ 行按 seq 索引存
    translations = {}      # seq -> 文本译文
    name_translations = {} # seq -> 角色名译文
    with open(text_txt_path, 'r', encoding='utf-8-sig') as f:
        for tline in f:
            tline = tline.rstrip('\n')
            if not tline.startswith('\u25c6'):
                continue
            rest = tline[1:]
            parts = rest.split('\u25c6')
            if len(parts) >= 3 and parts[1] == 'name':
                try:
                    name_translations[int(parts[0])] = parts[2]
                except ValueError:
                    pass
            elif len(parts) >= 2:
                try:
                    translations[int(parts[0])] = parts[1]
                except ValueError:
                    pass

    # 2. 读原 op.txt
    with open(opcode_txt_path, 'r', encoding='utf-8-sig') as f:
        lines = f.readlines()

    seq = 0
    i = 0
    total = len(lines)

    def _flush_block(text_parts):
        """整块写回。

        extract 时的拼接规则：text + ruby_base 直接相邻，TNS[0] 处插字面 \\n。
        所以一个 trans_part（按 \\n 拆出来的一段）可能对应**多个**连续的 text/ruby 槽位。

        写回策略：把 text_parts 按 newline 切成"段组"，每个段组对应一个 trans_part。
        段组内的所有 text/ruby 槽位**共享**同一段译文 — 但段组内通常只有 1 或 2 个槽位
        （比如 [text("「"), ruby{...}] = "「" + base，或单个 text）。
        多槽位段组的写回方式：第一个槽位拿整段译文，其余清空。
        译者要保持原文的 text 边界，最简单的做法是不拆分 — 一段译文直接整段塞给段组首个槽位。
        """
        nonlocal seq
        # 计算块内是否有"翻译槽位"
        n_slots = sum(1 for p in text_parts if p[0] in ('text', 'ruby'))
        if n_slots == 0:
            return

        # 按 newline 切分 text_parts 成"段组"
        groups = [[]]
        for p in text_parts:
            if p[0] == 'newline':
                groups.append([])
            else:
                groups[-1].append(p)
        # 去掉空段组（理论上不该有）
        groups = [g for g in groups if g]

        trans = translations.get(seq, '')
        trans_parts = trans.split('\\n') if trans else []

        for gi, group in enumerate(groups):
            seg_text = trans_parts[gi] if gi < len(trans_parts) else ''
            # 段组内多个槽位：第一个 text/ruby base 拿整段译文，其余清空
            assigned = False
            for p in group:
                if p[0] == 'text':
                    arg_idx = p[1]
                    if seq in translations:
                        new_val = seg_text if not assigned else ''
                        lines[arg_idx] = json.dumps([new_val], ensure_ascii=False) + '\n'
                        assigned = True
                elif p[0] == 'ruby':
                    r = p[1]
                    # ruby 内部 reading 槽位填全角空格占位，sep 保留
                    for arg_idx, orig_val, kind in r['reading_slots']:
                        if kind == 'reading':
                            n_chars = len(orig_val.replace('\u3000', ''))
                            filler = '\u3000' * n_chars
                            lines[arg_idx] = json.dumps([filler], ensure_ascii=False) + '\n'
                    # base
                    if seq in translations:
                        new_val = seg_text if not assigned else ''
                        lines[r['base_arg_idx']] = json.dumps([new_val], ensure_ascii=False) + '\n'
                        assigned = True
        seq += 1

    while i < total:
        line = lines[i].rstrip('\n')

        is_message_block = (line == '#1-MESSAGE')
        is_str_or_tns = (line in _STR_OPCODE_LINES) or (line == '#1-TO_NEW_STRING')

        if is_message_block:
            i += 2

        if is_message_block or is_str_or_tns:
            text_parts, i, block_name, name_line_idx = _collect_text_block(lines, i, total)
            if block_name is not None:
                if name_line_idx is not None and seq in name_translations:
                    trans_name = name_translations[seq]
                    lines[name_line_idx] = json.dumps([trans_name], ensure_ascii=False) + '\n'
                seq += 1
            _flush_block(text_parts)
        else:
            i += 1

    # 3. 写出新 op.txt
    with open(output_txt_path, 'w', encoding='utf-8-sig') as out:
        out.writelines(lines)

    return seq


if __name__ == "__main__":
    import argparse, os, glob

    ap = argparse.ArgumentParser(
        description="Silky MES translate.txt + op.txt -> 新 op.txt (单文件 或 目录批处理)"
    )
    ap.add_argument("op_txt", help="原始 *.op.txt (单文件 或 目录)")
    ap.add_argument("translate_txt", help="译文 translate.txt (单文件 或 目录)")
    ap.add_argument("output_op_txt", help="新 op.txt (单文件 或 输出目录)")
    ap.add_argument("--pattern", default="*.op.txt",
                    help="目录模式下匹配 op.txt 的通配 (default: *.op.txt)")
    args = ap.parse_args()

    def _strip_ext(name, exts):
        for e in exts:
            if name.lower().endswith(e.lower()):
                return name[:-len(e)]
        return os.path.splitext(name)[0]

    if os.path.isdir(args.op_txt):
        if not os.path.isdir(args.translate_txt):
            raise SystemExit("批处理模式下 translate_txt 也必须是目录")
        os.makedirs(args.output_op_txt, exist_ok=True)
        files = sorted(glob.glob(os.path.join(args.op_txt, args.pattern)))
        print(f"[batch] {len(files)} 个 op.txt 注入 -> {args.output_op_txt}")
        total_entries = 0
        missing = []
        for f in files:
            base = _strip_ext(os.path.basename(f), ['.op.txt'])
            tr = os.path.join(args.translate_txt, base + '.translate.txt')
            if not os.path.isfile(tr):
                missing.append(base)
                continue
            out = os.path.join(args.output_op_txt, base + '.op.txt')
            n = import_text(f, tr, out)
            total_entries += n
            print(f"  [+] {base}: {n} entries injected")
        if missing:
            print(f"[!] {len(missing)} 个文件缺失对应 translate.txt: {missing[:5]}{'...' if len(missing)>5 else ''}")
        print(f"[batch] 完成 {len(files) - len(missing)} 个文件, 共 {total_entries} 条")
    else:
        n = import_text(args.op_txt, args.translate_txt, args.output_op_txt)
        print(f"[+] injected {n} entries: {args.translate_txt} -> {args.output_op_txt}")
