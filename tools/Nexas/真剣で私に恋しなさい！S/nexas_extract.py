#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
nexas_extract.py - NeXAS 脚本批量文本提取 (GalTransl 兼容格式)

把每个 .bin 中的对话和选项提取为 GalTransl/SExtractor 标准格式的 JSON。

用法:
    python nexas_extract.py <input_dir>                  # 默认 -> <input_dir>_json/
    python nexas_extract.py <input_dir> -o text_jp/

输出 JSON 格式:
    [
      {
        "name": "",
        "message": "生徒会長選挙が、いよいよ来週となった。",
        "_site": 1079,
        "_idx": 0
      },
      {
        "name": "大和",
        "message": "@vS016_B1_0003「もぐもぐ。あー、カレー美味しかった」",
        "_site": 3128,
        "_idx": 3
      },
      {
        "name": "",
        "message": "キスする",
        "_site": 42517,
        "_idx": 110,
        "_choice": true
      },
      ...
    ]

字段说明:
    name      : 角色名 (空字符串 = 旁白)
    message   : 对话/选项文本 (可能含 @v 语音 tag, 「」括号等)
    _site     : 引擎中该消息的 entry index (调试参考)
    _idx      : 数组中的索引 (与位置一致)
    _choice   : true = 选项菜单项, 缺失/false = 对话
    _msg_sid  : (内部使用,注入时按此回写) string 表索引

翻译流程:
    1. 此工具提取 .json (含日文)
    2. 翻译: 修改每个 entry 的 "message" (可选: 也修改 "name")
    3. 用 nexas_inject.py 注入回 .bin
"""

import os
import sys
import argparse
import glob
import json
import time
import nexas_common as nc


def extract_file(src_path, out_path):
    data = open(src_path, 'rb').read()
    parsed = nc.parse_script(data)
    complex_cmds, _ = nc.detect_complex_ops(parsed['commands'], parsed['strings'])

    dialogues = nc.detect_dialogues(complex_cmds, parsed['strings'])
    choices = nc.detect_choices(complex_cmds)

    # 合并 dialogues + choices,按 _site 排序
    items = []
    for d in dialogues:
        # 剥离控制符 tag (如 @vS050_A1_0005)
        cleaned, tags = nc.strip_control_tags(d['message'])
        rec = {
            'name': d['name'],
            'message': cleaned,
            '_site': d['_site'],
            '_msg_sid': d['_msg_sid'],
            '_name_sid': d['_name_sid'],
        }
        if tags:
            rec['_tags'] = tags
        items.append(rec)

    for c in choices:
        # 选项跟对话可能引用同一 sid? 避免重复
        if any(it['_msg_sid'] == c['_msg_sid'] for it in items):
            continue
        cleaned, tags = nc.strip_control_tags(c['message'])
        rec = {
            'name': '',
            'message': cleaned,
            '_site': c['_site'],
            '_msg_sid': c['_msg_sid'],
            '_name_sid': -1,
            '_choice': True,
        }
        if tags:
            rec['_tags'] = tags
        items.append(rec)

    # 按 _site 排序 (=按剧本时间顺序)
    items.sort(key=lambda x: x['_site'])

    # 合并被引擎拆成两段的连续对话 (开括号未闭合 + 下一句同 name 闭合)
    items = nc.merge_continuations(items)

    # 重新分配 _idx
    for i, it in enumerate(items):
        it['_idx'] = i

    # 重新组织字段顺序: name, message 在前
    out = []
    for it in items:
        rec = {
            'name': it['name'],
            'message': it['message'],
            '_site': it['_site'],
            '_idx': it['_idx'],
            '_msg_sid': it['_msg_sid'],
            '_name_sid': it['_name_sid'],
        }
        if it.get('_choice'):
            rec['_choice'] = True
        if it.get('_tags'):
            rec['_tags'] = it['_tags']
        if it.get('_continuation_sid') is not None:
            rec['_continuation_sid'] = it['_continuation_sid']
        if it.get('_continuation_tags'):
            rec['_continuation_tags'] = it['_continuation_tags']
        out.append(rec)

    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    return {
        'n_dialogues': len(dialogues),
        'n_choices': len(choices),
        'n_total': len(items),
    }


def main():
    ap = argparse.ArgumentParser(
        description='NeXAS 脚本批量文本提取 (GalTransl 格式)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''输出 JSON 格式 (标准 GalTransl):
  [{ "name": "...", "message": "...", "_site": N, "_idx": N }, ...]

  选项额外有 "_choice": true 字段,翻译时与对话同等对待。
  _msg_sid / _name_sid 是内部注入索引,翻译者不要改动。

工作流:
  1. python nexas_extract.py mes\\ -o text_jp\\
  2. GalTransl / 人工翻译 修改 message (和 name) -> text_zh\\
  3. python nexas_inject.py mes\\ --json text_zh\\ -o mes_zh\\ --encoding gbk''')
    ap.add_argument('input_dir', help='含 .bin 的目录')
    ap.add_argument('-o', '--output', default=None, help='输出 .json 目录')
    ap.add_argument('--pattern', default='*.bin')
    args = ap.parse_args()

    if not os.path.isdir(args.input_dir):
        print(f"ERROR: {args.input_dir} 不是目录", file=sys.stderr)
        sys.exit(1)

    in_dir = args.input_dir.rstrip('/\\')
    out_dir = args.output or (in_dir + '_json')
    os.makedirs(out_dir, exist_ok=True)

    files = sorted(glob.glob(os.path.join(in_dir, args.pattern)))
    if not files:
        print(f"ERROR: {in_dir} 中没有 {args.pattern}")
        sys.exit(1)

    print(f"[Extract] {len(files)} files: {in_dir} -> {out_dir}\n")

    t0 = time.time()
    ok = fail = 0
    total_d = total_c = 0
    for idx, src in enumerate(files, 1):
        base = os.path.splitext(os.path.basename(src))[0]
        out_path = os.path.join(out_dir, base + '.json')
        try:
            info = extract_file(src, out_path)
            ok += 1
            total_d += info['n_dialogues']
            total_c += info['n_choices']
            print(f"  [{idx:3d}/{len(files)}] {os.path.basename(src):24s} "
                  f"对话={info['n_dialogues']:5d}  选项={info['n_choices']:3d}  "
                  f"合计={info['n_total']:5d}")
        except Exception as e:
            fail += 1
            print(f"  [{idx:3d}/{len(files)}] {os.path.basename(src):24s} [FAIL] {e}")

    elapsed = time.time() - t0
    print(f"\n[Done] {ok} ok, {fail} fail, {elapsed:.1f}s")
    print(f"[Total] 对话={total_d}, 选项={total_c}")


if __name__ == '__main__':
    main()
