#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Lazy 引擎 .VAL 剧情文本提取工具
================================

用法:
    python3 val_extract.py <input_dir> <output_dir> [--min-items N]

行为:
    遍历 <input_dir> 下所有 .VAL 文件 (无差别处理), 扫描每个文件中
    由 0xdd opcode 引用、且内容含日文/日式标点的字符串.

    判定方式 (内容驱动, 不依赖文件名):
      - 文件至少含 N 条剧情字符串 (默认 N=1) -> 输出 JSON
      - 否则跳过, 不写 JSON
    inject 阶段会把没 JSON 的 .VAL 原样拷贝过去.

    每个剧情脚本输出一份 GalTransl 兼容 JSON:
        [
          {"name": "", "message": "日文文本", "_chunks": [...]},
          ...
        ]

    JSON 顺序 = seg_A 中 dd 站点出现顺序 (= 剧情时间线).

跨条台词合并:
    引擎经常把一句 「...」 拆成多条 0xdd 显示 (分页换行的设计).
    extract 时若发现 message 含「但缺对应」, 自动向后合并直到闭合.
    被合并掉的后续条目, 其内容 + idx 记录在主条目的 _chunks 数组里;
    JSON 里只保留合并后的"主条目", 翻译时面对完整句子.

    inject 阶段: 主条目的译文写到第 1 个 chunk 的 idx, 其余 chunk 的 idx
    写空字符串 (引擎会显示空, 但分页节奏保留).

内部字段 (GalTransl 不会动, inject 用):
    _site:    seg_A 中 dd 指令的偏移 (主条目)
    _idx:     该条目对应的 seg_B 索引 (主条目, = _chunks[0]._idx)
    _chunks:  [{"_idx": int, "src": str}, ...]  原始每段的 idx 与原文 (含主条目本身)
"""
import os
import sys
import json
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lazy_common import (
    ValFile, collect_story_refs, decode_sjis,
)


# 用于"未闭合台词"判定的成对符号 (开 -> 闭)
_PAIRS = [('「', '」'), ('『', '』')]
_OPENS  = ''.join(o for o, _ in _PAIRS)
_CLOSES = ''.join(c for _, c in _PAIRS)


def _balance(s: str) -> int:
    """返回 s 中开括号数 - 闭括号数; > 0 说明有未闭合的开括号."""
    return (sum(s.count(o) for o in _OPENS)
            - sum(s.count(c) for c in _CLOSES))


def _merge_unclosed(records: list) -> list:
    """
    把"开了 quote 但本条未闭"的记录与后续条合并,
    直到整体平衡 (或耗尽前瞻).
    输入: [{name, message, _site, _idx}, ...]   (extract 阶段构造的原子记录)
    输出: [{name, message, _site, _idx, _chunks: [...]}, ...]
    """
    MAX_LOOKAHEAD = 8   # 最多向后吸收 8 条; 防止异常情况无限合并
    out = []
    i = 0
    n = len(records)
    while i < n:
        cur = records[i]
        chunks = [{'_idx': cur['_idx'], 'src': cur['message']}]
        msg = cur['message']
        bal = _balance(msg)
        j = i + 1
        steps = 0
        while bal > 0 and j < n and steps < MAX_LOOKAHEAD:
            nx = records[j]
            chunks.append({'_idx': nx['_idx'], 'src': nx['message']})
            msg += nx['message']
            bal = _balance(msg)
            j += 1
            steps += 1
        out.append({
            'name':    cur['name'],
            'message': msg,
            '_site':   cur['_site'],
            '_idx':    cur['_idx'],
            '_chunks': chunks,
        })
        i = j  # 跳过被吸收的条目
    return out



def _dedupe_refs_by_idx(refs: list) -> tuple:
    """
    同一个 seg_B idx 被多个 0xdd 站点引用时, 只保留第一次。

    对注入来说 idx 才是实际写回目标；同 idx 多次出现只需要翻译一次。
    这不会合并“文本相同但 idx 不同”的句子, 避免误伤不同上下文。
    返回: (去重后的 refs, 跳过数量)
    """
    seen = set()
    out = []
    skipped = 0
    for site, idx in refs:
        if idx in seen:
            skipped += 1
            continue
        seen.add(idx)
        out.append((site, idx))
    return out, skipped


def extract_one(val_path: str, out_json_path: str) -> dict:
    with open(val_path, 'rb') as f:
        data = f.read()
    v = ValFile.parse(data)
    refs_raw = collect_story_refs(v)
    refs, duplicate_idx_skipped = _dedupe_refs_by_idx(refs_raw)

    # 原子记录 (每个有效 seg_B idx 一条；同 idx 多站点引用只提一次)
    atoms = []
    for site, idx in refs:
        atoms.append({
            'name':    '',
            'message': decode_sjis(v.strings[idx]),
            '_site':   site,
            '_idx':    idx,
        })

    # 合并未闭合台词
    items = _merge_unclosed(atoms)

    return {
        'val':           os.path.basename(val_path),
        'json':          os.path.basename(out_json_path),
        'ref_count':     len(refs),
        'raw_ref_count': len(refs_raw),
        'item_count':    len(items),
        'merged_count':  len(refs) - len(items),
        'duplicate_idx_skipped': duplicate_idx_skipped,
        'distinct_idx':  len({idx for _, idx in refs}),
        'string_count':  len(v.strings),
        'seg_a_size':    len(v.seg_a),
        '_items':        items,   # 内部传出, main 决定是否落盘
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('input_dir',  help='解包后的 .VAL 目录 (包含 _vct_meta.json)')
    ap.add_argument('output_dir', help='输出 JSON 目录')
    ap.add_argument('--min-items', type=int, default=1,
                    help='文件至少有这么多条剧情才输出 JSON (默认 1, 即只要有剧情就输出)')
    args = ap.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)

    summary = {'story': [], 'no_story_skipped': []}
    total_refs = 0
    total_items = 0
    total_merged = 0
    total_dup_idx = 0

    for fname in sorted(os.listdir(args.input_dir)):
        if fname.startswith('_'):
            continue
        path = os.path.join(args.input_dir, fname)
        if not os.path.isfile(path) or not fname.upper().endswith('.VAL'):
            continue

        name_no_ext = os.path.splitext(fname)[0]
        out_json = os.path.join(args.output_dir, name_no_ext + '.json')
        try:
            info = extract_one(path, out_json)
        except Exception as e:
            print(f"  [ERR] {fname}: {e}")
            continue

        # 没剧情条目就不写 JSON, inject 时这类文件会被原样拷贝
        items = info.pop('_items')
        if len(items) < args.min_items:
            summary['no_story_skipped'].append(fname)
            continue

        with open(out_json, 'w', encoding='utf-8') as f:
            json.dump(items, f, ensure_ascii=False, indent=2)
        summary['story'].append(info)
        total_refs    += info['ref_count']
        total_items   += info['item_count']
        total_merged  += info['merged_count']
        total_dup_idx += info.get('duplicate_idx_skipped', 0)

    summary['totals'] = {
        'story_files':       len(summary['story']),
        'no_story_skipped':  len(summary['no_story_skipped']),
        'total_text_refs':   total_refs,
        'total_items':       total_items,
        'total_merged':      total_merged,
        'total_duplicate_idx_skipped': total_dup_idx,
    }
    with open(os.path.join(args.output_dir, '_extract_index.json'), 'w', encoding='utf-8') as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    print(f"[OK] story={len(summary['story'])}, "
          f"no_story={len(summary['no_story_skipped'])}, "
          f"refs={total_refs}, items={total_items} "
          f"(merged {total_merged}, dup-idx skipped {total_dup_idx})")
    print(f"     output -> {args.output_dir}")


if __name__ == '__main__':
    main()

