#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
nexas_disasm.py - NeXAS / 真剣演舞 引擎脚本批量反汇编器

用法:
    python nexas_disasm.py <input_dir>                 # 默认输出到 <input_dir>_disasm
    python nexas_disasm.py <input_dir> -o <output_dir>
    python nexas_disasm.py <input_dir> --no-extras     # 跳过 extras 区
    python nexas_disasm.py <input_dir> --summary-only  # 只生成 _summary.csv
"""

import os
import sys
import argparse
import glob
import time
import struct
import nexas_common as nc


def disasm_to_asm(parsed, complex_cmds, labels, choice_blocks,
                  show_extras=True, show_strings=True):
    lines = []
    n_strings = len(parsed['strings'])

    lines.append(f"; ========================================================================")
    lines.append(f"; NeXAS Script Disassembly")
    lines.append(f"; magic        = 0x{parsed['magic']:X}  ({parsed['magic']})")
    lines.append(f"; extras       = {len(parsed['extras'])} entries")
    lines.append(f"; raw_commands = {len(parsed['raw_commands'])} entries")
    lines.append(f"; folded       = {len(complex_cmds)} (op=0 prefix 已折叠)")
    lines.append(f"; strings      = {n_strings}")
    lines.append(f"; trailer      = {len(parsed['trailer'])} bytes")
    lines.append(f"; labels       = {len(labels)}")
    lines.append(f"; choice_blocks= {len(choice_blocks)}")
    lines.append(f"; ========================================================================\n")

    if show_extras:
        lines.append(f"; ---- EXTRAS ({len(parsed['extras'])} entries) ----")
        flat = []
        for op, arg in parsed['extras']:
            flat.append(f"0x{op:X}")
            flat.append(f"0x{arg:X}")
        for i in range(0, len(flat), 8):
            lines.append("\t".join(flat[i:i+8]))
        lines.append("")

    lines.append(f"; ---- COMMANDS ({len(complex_cmds)} folded entries from {len(parsed['raw_commands'])} raw) ----\n")

    cb_starts = {b['start_cmd']: b for b in choice_blocks}
    cb_ends = set(b['end_cmd'] for b in choice_blocks)

    for e in complex_cmds:
        if e['orig_idx'] in labels:
            lines.append(f"L_{e['orig_idx']}:")
        if e['idx'] in cb_starts:
            cb = cb_starts[e['idx']]
            lines.append(f"; ---- CHOICE BLOCK [{cb['kind']}] {len(cb['choices'])} options ----")

        idx_label = f"{{0x{e['orig_idx']:04X}}}"
        mnem = e['mnem']
        data = e['data']
        prefix = e['prefix']
        line_parts = [idx_label, mnem]

        if mnem == 'LOAD_STRING':
            line_parts.append(f"'{e['string']}'")
        elif mnem == 'CASE4':
            line_parts.append(f"'{e['string']}'")
        elif mnem == 'CASE4_END':
            line_parts.append(f"0x{data:X}")
        elif mnem == 'LOAD_CUSTOM_TEXT':
            line_parts.append(f"0x{data:X}")
            line_parts.append(f"'{e['string']}'")
        elif mnem == 'SET_EFFECT':
            line_parts.append(f"0x{data:X}")
            line_parts.append(f"'{e['string']}'")
        elif mnem == 'SPECIAL_TEXT':
            line_parts.append(f"0x{data:X}")
            line_parts.append(f"'{e['string']}'")
        elif mnem == 'PUSH_CUSTOM_TEXT':
            pass
        elif mnem in ('JMP', 'JNGE', 'JNLE'):
            line_parts.append(f"L_{data}")
        elif mnem == 'FUNC':
            if 'func_name' in e:
                line_parts.append(f"'{e['func_name']}'")
            else:
                line_parts.append(f"0x{data:X}")
        else:
            line_parts.append(f"0x{data:X}")

        if prefix:
            pre_str = "[" + ", ".join(f"0x{p:X}" for p in prefix) + "]"
            line_parts.append(pre_str)

        lines.append("\t".join(line_parts))

        if e['idx'] in cb_ends:
            cb = next(b for b in choice_blocks if b['end_cmd'] == e['idx'])
            recap = ", ".join(f"#{i}: '{c['string'][:20]}'" for i, c in enumerate(cb['choices']))
            lines.append(f"; ---- end choice block: {recap} ----")

    if show_strings:
        lines.append(f"\n; ---- STRINGS ({n_strings} entries) ----")
        for i, s in enumerate(parsed['strings']):
            disp = s.replace('\n', '\\n').replace('\r', '\\r')
            lines.append(f"  S[{i:4d}]  {disp!r}")

    if parsed['trailer']:
        lines.append(f"\n; ---- TRAILER ({len(parsed['trailer'])} bytes, 注入时原样保留) ----")
        try:
            t = parsed['trailer']
            if len(t) >= 4:
                tcnt = struct.unpack_from('<I', t, 0)[0]
                if 0 < tcnt < 50000:
                    lines.append(f";   header u32 = {tcnt}")
                    pos = 4
                    n_shown = 0
                    while pos < len(t) and n_shown < 30:
                        nul = t.find(b'\x00', pos)
                        if nul == -1: break
                        try:
                            s = t[pos:nul].decode('cp932')
                            lines.append(f";   T[{n_shown:4d}] {s!r}")
                            n_shown += 1
                        except:
                            pass
                        pos = nul + 1
                    if pos < len(t):
                        lines.append(f";   ... 共解析 {n_shown} 项, 略")
        except Exception:
            pass

    return "\n".join(lines) + "\n"


def process_file(src_path, out_path, show_extras=True, show_strings=True, summary_only=False):
    data = open(src_path, 'rb').read()
    parsed = nc.parse_script(data)
    complex_cmds, consumed = nc.detect_complex_ops(parsed['commands'], parsed['strings'])
    labels = nc.detect_labels(complex_cmds, parsed['raw_commands'])
    choice_blocks = nc.detect_choice_blocks(complex_cmds)

    from collections import Counter
    mnem_count = Counter(e['mnem'] for e in complex_cmds)

    info = {
        'magic': parsed['magic'],
        'n_extras': len(parsed['extras']),
        'n_raw_commands': len(parsed['raw_commands']),
        'n_folded_commands': len(complex_cmds),
        'n_strings': len(parsed['strings']),
        'n_strings_consumed': len(consumed),
        'trailer_size': len(parsed['trailer']),
        'n_labels': len(labels),
        'n_choice_blocks': len(choice_blocks),
        'n_load_string': mnem_count.get('LOAD_STRING', 0),
        'n_func': mnem_count.get('FUNC', 0),
        'n_jmp': mnem_count.get('JMP', 0),
        'n_jnge': mnem_count.get('JNGE', 0),
    }

    if not summary_only:
        asm = disasm_to_asm(parsed, complex_cmds, labels, choice_blocks,
                            show_extras=show_extras, show_strings=show_strings)
        with open(out_path, 'w', encoding='utf-8') as f:
            f.write(asm)
    return info


def main():
    ap = argparse.ArgumentParser(
        description='NeXAS 引擎脚本批量反汇编器',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''示例:
  python nexas_disasm.py mes/                          # 默认 -> mes_disasm/
  python nexas_disasm.py mes/ -o disasm/
  python nexas_disasm.py mes/ --no-extras --no-strings # 只输出 commands
  python nexas_disasm.py mes/ --summary-only           # 10秒概览全目录''')
    ap.add_argument('input_dir', help='含 .bin 脚本的目录')
    ap.add_argument('-o', '--output', default=None, help='输出目录')
    ap.add_argument('--no-extras', action='store_true', help='跳过 extras 区')
    ap.add_argument('--no-strings', action='store_true', help='跳过字符串列表区')
    ap.add_argument('--pattern', default='*.bin', help='文件匹配模式')
    ap.add_argument('--no-summary', action='store_true', help='不生成 _summary.csv')
    ap.add_argument('--summary-only', action='store_true', help='只生成 _summary.csv')
    args = ap.parse_args()

    if not os.path.isdir(args.input_dir):
        print(f"ERROR: {args.input_dir} 不是目录", file=sys.stderr)
        sys.exit(1)

    in_dir = args.input_dir.rstrip('/\\')
    out_dir = args.output or (in_dir + '_disasm')
    os.makedirs(out_dir, exist_ok=True)

    files = sorted(glob.glob(os.path.join(in_dir, args.pattern)))
    if not files:
        print(f"ERROR: {in_dir} 中没有 {args.pattern}")
        sys.exit(1)

    print(f"[Disasm] {len(files)} files: {in_dir} -> {out_dir}")
    print(f"[Disasm] no-extras={args.no_extras}, no-strings={args.no_strings}, summary-only={args.summary_only}\n")

    results = []
    t0 = time.time()
    ok = fail = 0
    for idx, src in enumerate(files, 1):
        base = os.path.splitext(os.path.basename(src))[0]
        out_path = os.path.join(out_dir, base + '.asm')
        size = os.path.getsize(src)
        try:
            info = process_file(src, out_path,
                                show_extras=not args.no_extras,
                                show_strings=not args.no_strings,
                                summary_only=args.summary_only)
            ok += 1
            out_size = 0 if args.summary_only else os.path.getsize(out_path)
            results.append({
                'file': os.path.basename(src), 'size': size, 'status': 'ok',
                'magic': f"0x{info['magic']:X}",
                'n_extras': info['n_extras'],
                'n_raw_cmds': info['n_raw_commands'],
                'n_folded': info['n_folded_commands'],
                'n_strings': info['n_strings'],
                'n_consumed': info['n_strings_consumed'],
                'n_labels': info['n_labels'],
                'n_choices': info['n_choice_blocks'],
                'n_loadstr': info['n_load_string'],
                'n_func': info['n_func'],
                'out_size': out_size,
            })
            print(f"  [{idx:3d}/{len(files)}] {os.path.basename(src):24s} "
                  f"folded={info['n_folded_commands']:6d} "
                  f"S={info['n_strings']:4d} "
                  f"LOAD_STR={info['n_load_string']:4d} "
                  f"choices={info['n_choice_blocks']:3d}")
        except Exception as e:
            fail += 1
            results.append({
                'file': os.path.basename(src), 'size': size, 'status': f'FAIL: {e}',
                'magic': '', 'n_extras': '', 'n_raw_cmds': '', 'n_folded': '',
                'n_strings': '', 'n_consumed': '', 'n_labels': '', 'n_choices': '',
                'n_loadstr': '', 'n_func': '', 'out_size': '',
            })
            print(f"  [{idx:3d}/{len(files)}] {os.path.basename(src):24s} [FAIL] {e}")

    elapsed = time.time() - t0
    print(f"\n[Done] {ok} ok, {fail} fail, {elapsed:.1f}s")

    if not args.no_summary:
        csv_path = os.path.join(out_dir, '_summary.csv')
        cols = ['file', 'size', 'status', 'magic', 'n_extras', 'n_raw_cmds',
                'n_folded', 'n_strings', 'n_consumed', 'n_labels', 'n_choices',
                'n_loadstr', 'n_func', 'out_size']
        with open(csv_path, 'w', encoding='utf-8') as f:
            f.write(','.join(cols) + '\n')
            for r in results:
                f.write(','.join(str(r[c]) for c in cols) + '\n')
        print(f"[Summary] {csv_path}")


if __name__ == '__main__':
    main()
