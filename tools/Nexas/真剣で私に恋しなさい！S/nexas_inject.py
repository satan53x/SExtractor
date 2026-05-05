#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
nexas_inject.py - NeXAS 脚本批量文本注入

读原始 .bin + 翻译后的 .json (GalTransl 格式)，输出注入后的新 .bin。

用法:
    python nexas_inject.py <bin_dir> --json <json_dir> -o <output_dir>
    python nexas_inject.py mes/ --json text_zh/ -o mes_zh/ --encoding gbk

JSON 格式 (与 nexas_extract.py 输出兼容):
    [
      {"name": "...", "message": "...", "_msg_sid": N, "_name_sid": N, "_site": N, "_idx": N},
      {"name": "", "message": "选项A", "_msg_sid": N, "_choice": true, ...},
      ...
    ]

注入逻辑:
    1. 读原 .bin 获取 strings 表 (字符串数组)
    2. 读 .json,按 _msg_sid 把 message 写回 strings[_msg_sid]
       按 _name_sid 把 name 写回 strings[_name_sid] (如果 _name_sid >= 0)
    3. 重新打包 .bin (commands 完全保留)
    4. cp932 优先编码,失败时 GBK 兜底
    5. 未修改的字符串保留原始字节 (避免 cp932 双向映射问题)
"""

import os
import sys
import argparse
import glob
import json
import time
import hashlib
import nexas_common as nc


def inject_file(bin_path, json_path, out_path, encoding='cp932'):
    bin_data = open(bin_path, 'rb').read()
    parsed = nc.parse_script(bin_data)

    with open(json_path, 'r', encoding='utf-8') as f:
        items = json.load(f)
    if not isinstance(items, list):
        raise ValueError("JSON 必须是数组 [{name, message, ...}, ...]")

    # 拷贝 strings,按 _msg_sid / _name_sid 写回
    new_strings = list(parsed['strings'])
    n_strings = len(new_strings)
    n_msg_changed = 0
    n_name_changed = 0
    skipped = 0

    for i, it in enumerate(items):
        if not isinstance(it, dict):
            raise ValueError(f"item[{i}] 不是 object")

        msg_sid = it.get('_msg_sid', -1)
        name_sid = it.get('_name_sid', -1)
        msg = it.get('message', '')
        name = it.get('name', '')
        tags = it.get('_tags', None)
        cont_sid = it.get('_continuation_sid', None)
        cont_tags = it.get('_continuation_tags', None)

        # 处理续接合并: 按 CONTINUATION_MARKER 拆回两段
        if cont_sid is not None:
            part1, part2 = nc.split_continuation(msg)
            if part2 is None:
                # translator 把 marker 删了, 退化为单段处理 (整段写入 cur sid)
                part1 = msg
                part2 = ''
            # 还原各自的 control tags
            if tags:
                part1 = nc.restore_control_tags(part1, tags)
            if cont_tags:
                part2 = nc.restore_control_tags(part2, cont_tags)
            # 写两个 sid
            if 0 <= msg_sid < n_strings:
                if new_strings[msg_sid] != part1:
                    new_strings[msg_sid] = part1
                    n_msg_changed += 1
            if 0 <= cont_sid < n_strings and part2:
                if new_strings[cont_sid] != part2:
                    new_strings[cont_sid] = part2
                    n_msg_changed += 1
        else:
            # 普通: 还原 control tags
            if tags:
                msg = nc.restore_control_tags(msg, tags)
            # 写 message
            if 0 <= msg_sid < n_strings:
                if new_strings[msg_sid] != msg:
                    new_strings[msg_sid] = msg
                    n_msg_changed += 1
            else:
                skipped += 1

        # 写 name
        if 0 <= name_sid < n_strings:
            if new_strings[name_sid] != name:
                new_strings[name_sid] = name
                n_name_changed += 1

    rebuilt = nc.rebuild_script(parsed, new_strings, encoding=encoding)
    with open(out_path, 'wb') as f:
        f.write(rebuilt)

    return {
        'original_md5': hashlib.md5(bin_data).hexdigest(),
        'new_md5': hashlib.md5(rebuilt).hexdigest(),
        'n_items': len(items),
        'n_msg_changed': n_msg_changed,
        'n_name_changed': n_name_changed,
        'skipped': skipped,
        'orig_size': len(bin_data),
        'new_size': len(rebuilt),
    }


def main():
    ap = argparse.ArgumentParser(
        description='NeXAS 脚本批量文本注入 (GalTransl 格式)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''示例:
  # 标准: GBK 编码 (中文)
  python nexas_inject.py mes\\ --json text_zh\\ -o mes_zh\\ --encoding gbk

  # round-trip 验证: extract 不修改直接 inject, MD5 应 100% 一致
  python nexas_extract.py mes\\ -o /tmp/jp\\
  python nexas_inject.py mes\\ --json /tmp/jp\\ -o /tmp/rebuilt\\
  # 然后比对 mes\\ 和 /tmp/rebuilt\\ 的 MD5''')
    ap.add_argument('bin_dir', help='原始 .bin 目录')
    ap.add_argument('--json', dest='json_dir', required=True, help='翻译后 .json 目录')
    ap.add_argument('-o', '--output', required=True, help='输出 .bin 目录')
    ap.add_argument('--encoding', default='cp932', choices=['cp932', 'gbk'],
                    help='字符串编码 (默认 cp932,中文用 gbk)')
    ap.add_argument('--pattern', default='*.bin')
    ap.add_argument('--strict', action='store_true', help='缺少 .json 时报错 (默认跳过)')
    args = ap.parse_args()

    for d in (args.bin_dir, args.json_dir):
        if not os.path.isdir(d):
            print(f"ERROR: {d} 不是目录", file=sys.stderr)
            sys.exit(1)

    bin_dir = args.bin_dir.rstrip('/\\')
    out_dir = args.output.rstrip('/\\')
    os.makedirs(out_dir, exist_ok=True)

    files = sorted(glob.glob(os.path.join(bin_dir, args.pattern)))
    if not files:
        print(f"ERROR: {bin_dir} 中没有 {args.pattern}")
        sys.exit(1)

    print(f"[Inject] {len(files)} files")
    print(f"[Inject] bin={bin_dir}  json={args.json_dir}  out={out_dir}")
    print(f"[Inject] encoding={args.encoding}\n")

    t0 = time.time()
    ok = skipped = fail = 0
    rt_match = 0
    total_msg = total_name = 0

    for idx, src in enumerate(files, 1):
        base = os.path.splitext(os.path.basename(src))[0]
        json_path = os.path.join(args.json_dir, base + '.json')
        out_path = os.path.join(out_dir, base + '.bin')

        if not os.path.isfile(json_path):
            if args.strict:
                fail += 1
                print(f"  [{idx:3d}/{len(files)}] {base:24s} [FAIL] 无 JSON")
            else:
                skipped += 1
                print(f"  [{idx:3d}/{len(files)}] {base:24s} [SKIP] 无 JSON")
            continue

        try:
            info = inject_file(src, json_path, out_path, encoding=args.encoding)
            ok += 1
            total_msg += info['n_msg_changed']
            total_name += info['n_name_changed']
            md5_match = info['original_md5'] == info['new_md5']
            if md5_match:
                rt_match += 1
                tag = '[RT-MATCH]'
            else:
                tag = f"[CHG msg={info['n_msg_changed']} name={info['n_name_changed']}]"
            print(f"  [{idx:3d}/{len(files)}] {base:24s} "
                  f"orig={info['orig_size']:>7d} new={info['new_size']:>7d} {tag}")
        except Exception as e:
            fail += 1
            print(f"  [{idx:3d}/{len(files)}] {base:24s} [FAIL] {e}")

    elapsed = time.time() - t0
    print(f"\n[Done] {ok} ok ({rt_match} round-trip 匹配), {skipped} skip, {fail} fail, {elapsed:.1f}s")
    print(f"[Total] 修改 message={total_msg}, name={total_name}")


if __name__ == '__main__':
    main()
