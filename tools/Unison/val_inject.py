#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Lazy 引擎 .VAL 剧情文本注入工具
================================

用法:
    python3 val_inject.py <orig_val_dir> <translated_json_dir> <output_val_dir>
                          [--encoding cp932|gbk]

行为:
    1. 读取 <translated_json_dir>/_extract_index.json (val_extract.py 写的清单)
    2. 对清单里的每个剧情脚本:
         - 读原 .VAL, parse 出 ValFile
         - 读对应 JSON, 按每条记录的 _idx 把翻译写回 v.strings[_idx]
         - rebuild 出新字节流, 写到 <output_val_dir>
    3. 不在清单里的脚本 (系统脚本 + 任何 _vct_meta.json 等) 原样拷贝
       -> 直接喂给 vct_pack.py 即可重新封包

JSON 字段:
    每项支持 GalTransl 习惯的多种字段名:
        message  (主)
        src_msg / src / original / orig  (兜底, 翻译失败时回退)
    同时必须携带 extract 阶段写下的 _idx (= seg_B 中的字符串索引).

注入策略:
    seg_A 不动 -> 重建 seg_B 偏移表 + seg_C 字符串池.
    指令流和数据完全解耦, 变长注入零跳转风险.

编码:
    --encoding cp932 (默认): 翻译文本必须能用 CP932 编码 (即只含日文/SJIS 字符).
                              适合先做"等长性测试"或日译日.
    --encoding gbk:           按 GBK 编码 (中文汉化用); 引擎需配套 EXE 字体补丁.
"""
import os
import sys
import json
import shutil
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lazy_common import ValFile


# 翻译条目里"译文"字段的优先级
_TEXT_KEYS_PRIMARY = ('message',)
_TEXT_KEYS_FALLBACK = ('src_msg', 'src', 'original', 'orig')


def pick_text(item: dict) -> str:
    for k in _TEXT_KEYS_PRIMARY:
        v = item.get(k)
        if v:
            return v
    for k in _TEXT_KEYS_FALLBACK:
        v = item.get(k)
        if v:
            return v
    return ''


def inject_one(val_path: str, json_path: str, out_path: str,
               encoding: str) -> tuple:
    with open(val_path, 'rb') as f:
        data = f.read()
    v = ValFile.parse(data)

    with open(json_path, 'r', encoding='utf-8') as f:
        items = json.load(f)

    # 注入策略 (兼容三种条目形态):
    #   形态 A: 旧版扁平条目 (无 _chunks). 直接按 _idx 写.
    #   形态 B: 合并条目 (有 _chunks). 主译文写到 _chunks[0]._idx,
    #           其余 chunk 的 _idx 写空字符串 (引擎执行那条 0xdd 时显示空,
    #           分页节奏保留).
    #   形态 C: 用户手动改了 _chunks[k].src (作为译文). 此时 src != orig,
    #           按 chunk 各自的译文分别写, 不再用主 message 的整段.
    #
    # 所有写入按"首次为准 + 冲突警告"原则.
    first_text = {}    # idx -> 已写文本 (用 str 存, 编码留到 build)
    conflicts = []     # (idx, first_text, later_text)
    written = 0

    def _write(idx: int, text: str):
        """单点写入, 处理冲突检测."""
        if not (0 <= idx < len(v.strings)):
            raise ValueError(f"{os.path.basename(json_path)}: _idx {idx} out of range "
                             f"(strings={len(v.strings)})")
        if idx in first_text:
            if first_text[idx] != text:
                conflicts.append((idx, first_text[idx], text))
            return False
        first_text[idx] = text
        try:
            v.strings[idx] = text.encode(encoding)
        except UnicodeEncodeError as e:
            raise ValueError(
                f"{os.path.basename(json_path)} idx={idx}: "
                f"{encoding} encode failed: {text!r} ({e})"
            )
        return True

    for item in items:
        chunks = item.get('_chunks')
        if chunks:
            # 形态 B/C: 用 chunk 决定写到哪个 idx
            translated = pick_text(item)
            chunk_translations = []
            for c in chunks:
                # 如果 chunk.src 被用户手改 (与原文不同), 当作显式译文
                # (这里没有"原文"参考列, 只能用 src 是否为空来判断)
                cs = c.get('src', '')
                chunk_translations.append(cs if cs else None)

            # 决定主译文走哪种分配
            user_edited_chunks = any(t is not None and t != '' for t in chunk_translations)
            # 简化: 若主 message (translated) 非空, 第一段写整段, 其余写空
            #       否则按 chunk.src 各自写 (兼容用户手动模式)
            if translated:
                for k, c in enumerate(chunks):
                    if _write(c['_idx'], translated if k == 0 else ''):
                        written += 1
            else:
                # 没主译文 -> 用 chunk.src 各自写
                for c in chunks:
                    src = c.get('src', '')
                    if src and _write(c['_idx'], src):
                        written += 1
        else:
            # 形态 A: 扁平
            idx = item.get('_idx')
            if idx is None:
                continue
            text = pick_text(item)
            if not text:
                continue
            if _write(idx, text):
                written += 1

    warnings = []
    if conflicts:
        warnings.append(f"  [WARN] {os.path.basename(json_path)}: "
                        f"{len(conflicts)} idx-conflicts (kept first); "
                        f"e.g. idx={conflicts[0][0]}: {conflicts[0][1]!r} vs {conflicts[0][2]!r}")

    out_data = v.build()
    with open(out_path, 'wb') as f:
        f.write(out_data)
    return written, len(out_data) - len(data), warnings


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('orig_dir',     help='原始 .VAL 目录')
    ap.add_argument('json_dir',     help='翻译后的 JSON 目录 (含 _extract_index.json)')
    ap.add_argument('output_dir',   help='注入后的 .VAL 输出目录')
    ap.add_argument('--encoding',   default='cp932', choices=['cp932', 'gbk'],
                    help='文本编码 (默认 cp932)')
    args = ap.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)

    index_path = os.path.join(args.json_dir, '_extract_index.json')
    if not os.path.exists(index_path):
        print(f"[ERR] {index_path} not found - run val_extract.py first")
        sys.exit(1)
    with open(index_path, 'r', encoding='utf-8') as f:
        index = json.load(f)

    handled = set()      # 已处理 (注入 / 拷贝) 的文件名
    injected_count = 0
    total_written = 0
    total_delta = 0
    failures = []

    # 1) 注入剧情脚本
    for info in index.get('story', []):
        val_name = info['val']
        json_name = info['json']
        val_path  = os.path.join(args.orig_dir,   val_name)
        json_path = os.path.join(args.json_dir,   json_name)
        out_path  = os.path.join(args.output_dir, val_name)

        if not os.path.exists(val_path):
            print(f"  [skip] missing orig: {val_name}")
            continue
        if not os.path.exists(json_path):
            # 没翻译就照搬原文
            shutil.copy(val_path, out_path)
            handled.add(val_name)
            continue
        try:
            n, dsize, warns = inject_one(val_path, json_path, out_path, args.encoding)
            injected_count += 1
            total_written  += n
            total_delta    += dsize
            print(f"  {val_name:20} <- {n:5} items   size {dsize:+d}")
            for w in warns:
                print(w)
            handled.add(val_name)
        except Exception as e:
            print(f"  [ERR] {val_name}: {e}")
            failures.append((val_name, str(e)))

    # 2) 系统脚本 / 其他文件原样拷贝 (含 _vct_meta.json)
    copied = 0
    for fname in sorted(os.listdir(args.orig_dir)):
        if fname in handled:
            continue
        src = os.path.join(args.orig_dir, fname)
        if not os.path.isfile(src):
            continue
        shutil.copy(src, os.path.join(args.output_dir, fname))
        copied += 1

    print()
    print(f"[OK] injected   {injected_count} story scripts "
          f"({total_written} items written, total size {total_delta:+d} bytes)")
    print(f"     copied     {copied} other files (system scripts / metadata)")
    if failures:
        print(f"     {len(failures)} FAILURES:")
        for fn, err in failures:
            print(f"       {fn}: {err}")
        sys.exit(2)


if __name__ == '__main__':
    main()
