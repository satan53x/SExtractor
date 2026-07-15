# -*- coding: utf-8 -*-
"""
malie_text_extract.py — 从解密的 EXEC 明文字节码提取待翻译文本
==============================================================

输出两个 JSON:
  dialogue.json  对话(段5), 每条: {id, speaker, pre_jp, message} + 独立 meta
  choices.json   选择肢+角色名(段3), 每条: {id, seg3_off, pre_jp, message} + 独立 meta

给译者的字段:
  pre_jp  : 原始日文纯净正文(参考, 只读)
  message : 待翻译正文(译者在此填中文)。已去除: 语音标记 / 停顿符 / 换页 / 串结束 / 注音包裹(留汉字)

meta(不给译者, 注入时还原用):
  dialogue: 每条的完整 token 骨架 tokens(含控制符占位), 使注入能无损重组段5
  choices : 每串在段3的字节偏移与原始文本, 使注入能重建段3

用法:
  python malie_text_extract.py EXEC_decrypted.bin -o OUTDIR
"""

import argparse
import json
import os
import sys

from malie_fmt import (
    ExecImage, parse_message, split_seg3, voice_to_chara,
    VOICE_PREFIX_TO_CHARA,
)


# ────────────────────────────────────────────────────────────────────────
#  段3 分类：判断一个串是否是"要给译者的文本"
# ────────────────────────────────────────────────────────────────────────
def _has_jp(s):
    for ch in s:
        o = ord(ch)
        if (0x3040 <= o <= 0x30ff or   # 假名
                0x4e00 <= o <= 0x9fff or  # 汉字
                0xff00 <= o <= 0xffef):   # 全角/半角形
            return True
    return False


def _is_markup(s):
    return s.startswith('<') and s.endswith('>')


def _is_voice_name(s):
    # 语音名: v_ 开头, 或纯 ASCII 且含下划线的脚本标签
    return s.startswith('v_')


def _is_script_label(s):
    # 脚本标签如 s01_a01_s1a1_b1 / s02_a06_s2a6_a1
    import re
    return bool(re.match(r'^[a-zA-Z]\w*$', s)) and not _has_jp(s)


def _is_debug_string(s):
    # 调试/系统串: 含换行占位、"処理"、"シナリオ"、■ 前缀
    return ('\n' in s or '処理' in s or 'シナリオ' in s or s.startswith('■')
            or 'chapter' in s)


def classify_seg3(s):
    """
    返回该串的类别:
      'choice'   选择肢(要译)
      'chara'    角色名(要译, 作说话人参考)
      'skip'     不译(markup/语音名/脚本标签/调试串/纯ASCII)
    """
    if not s.strip():
        return 'skip'
    if not _has_jp(s):
        return 'skip'                 # 纯 ASCII / 数字 / 符号
    if _is_markup(s):
        return 'skip'                 # <chapter>/<layer>/<cg> 等
    if _is_debug_string(s):
        return 'skip'                 # 调试/系统/章节标记

    # 角色名: 短(<=6字符), 去掉全角空格后仍是纯假名/汉字
    core = s.replace('\u3000', '')
    if len(core) <= 5 and len(s) <= 8:
        import re
        if re.match(r'^[\u3040-\u30ff\u4e00-\u9fff]+$', core):
            return 'chara'

    # 其余含日文的 -> 选择肢
    return 'choice'


# ────────────────────────────────────────────────────────────────────────
#  对话消息 -> 提取记录
# ────────────────────────────────────────────────────────────────────────
def extract_dialogue(img, extra_map=None):
    """
    段5 每条消息 -> (record, meta)
    record: 给译者   {id, speaker, pre_jp, message}
    meta  : 注入用   {id, tokens}   tokens 是可 JSON 化的 token 骨架
    另返回 prefix_stats: {前缀: {count, samples}} 用于生成 speaker_map 对照表
    """
    from collections import defaultdict
    from malie_fmt import voice_prefix

    records = []
    metas = []
    prefix_stats = defaultdict(lambda: {'count': 0, 'samples': []})

    for i in range(img.message_count()):
        raw = img.message_raw(i)
        toks = parse_message(raw)

        # 说话人: 取该消息第一个 voice token 的前缀映射
        speaker = None
        voice_name = None
        for t in toks:
            if t[0] == 'voice':
                voice_name = t[1]
                speaker = voice_to_chara(t[1], extra_map)
                break

        # 纯净正文: text token 原样 + ruby 只取汉字; 丢弃控制符
        # 多个正文段(被 pause/page 分隔)用可见分隔标出, 便于译者对照
        pieces = []
        for t in toks:
            if t[0] == 'text':
                pieces.append(t[1])
            elif t[0] == 'ruby':
                pieces.append(t[1])   # 只留汉字
        pre_jp = ''.join(pieces)

        # 空消息(无正文, 纯控制)跳过, 但仍要记 meta 保证注入完整
        has_text = any(t[0] in ('text', 'ruby') for t in toks)

        # token 骨架 JSON 化
        jtoks = []
        for t in toks:
            jtoks.append(list(t))

        meta = {'id': i, 'tokens': jtoks}
        metas.append(meta)

        if has_text:
            rec = {
                'id': i,
                'speaker': speaker or '',
                'voice': voice_name or '',
                'pre_jp': pre_jp,
                'message': pre_jp,   # 译者在此改中文; 默认填原文
            }
            records.append(rec)

            # 收集前缀 -> 台词样本 对照
            if voice_name:
                pfx = voice_prefix(voice_name)
                st = prefix_stats[pfx]
                st['count'] += 1
                if len(st['samples']) < 3 and pre_jp:
                    st['samples'].append(pre_jp[:30])

    return records, metas, dict(prefix_stats)


# ────────────────────────────────────────────────────────────────────────
#  段3 -> 选择肢/角色名 提取
# ────────────────────────────────────────────────────────────────────────
def extract_choices(img):
    """
    段3 -> (records, meta)
    records: 给译者  choice + chara, {id, kind, seg3_off, pre_jp, message}
    meta   : 注入用  段3完整串序(offset, text, kind) + trailing
    """
    items, trailing = split_seg3(img.seg3)

    records = []
    all_strings = []   # 注入需要完整串序

    cid = 0
    for off, s in items:
        kind = classify_seg3(s)
        all_strings.append({'off': off, 'text': s, 'kind': kind})
        if kind in ('choice', 'chara'):
            records.append({
                'id': cid,
                'kind': kind,
                'seg3_off': off,
                'pre_jp': s,
                'message': s,   # 译者改中文
            })
            cid += 1

    meta = {
        'strings': all_strings,
        'trailing_hex': trailing.hex(),
    }
    return records, meta


# ────────────────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser(description='Malie EXEC 文本提取')
    ap.add_argument('input', help='解密后的 EXEC 明文字节码 (如 EXEC_decrypted.bin)')
    ap.add_argument('-o', '--outdir', default='.', help='输出目录')
    ap.add_argument('--speaker-map', help='人工填写的 前缀->角色名 映射 JSON (可选)')
    args = ap.parse_args()

    data = open(args.input, 'rb').read()
    img = ExecImage(data)

    if img._parsed_end != img._total:
        print('警告: 结构解析未到 EOF，可能格式不符', file=sys.stderr)

    os.makedirs(args.outdir, exist_ok=True)

    # 可选的人工说话人映射
    extra_map = None
    if args.speaker_map:
        sm = json.load(open(args.speaker_map, encoding='utf-8'))
        # 支持两种格式: 直接 {前缀:角色} 或 对照表 {前缀:{chara:..}}
        extra_map = {}
        for k, v in sm.items():
            extra_map[k] = v if isinstance(v, str) else v.get('chara', k)

    # 对话
    dlg_recs, dlg_meta, prefix_stats = extract_dialogue(img, extra_map)

    # 输出说话人对照表(前缀 + 出现次数 + 台词样本 + 待填角色名)
    from malie_fmt import VOICE_PREFIX_TO_CHARA
    speaker_table = {}
    for pfx in sorted(prefix_stats, key=lambda p: -prefix_stats[p]['count']):
        known = (extra_map or {}).get(pfx) or VOICE_PREFIX_TO_CHARA.get(pfx, '')
        speaker_table[pfx] = {
            'chara': known,           # 已知则填, 否则空待人工填
            'count': prefix_stats[pfx]['count'],
            'samples': prefix_stats[pfx]['samples'],
        }
    with open(os.path.join(args.outdir, 'speaker_map.json'), 'w', encoding='utf-8') as f:
        json.dump(speaker_table, f, ensure_ascii=False, indent=1)
    with open(os.path.join(args.outdir, 'dialogue.json'), 'w', encoding='utf-8') as f:
        json.dump(dlg_recs, f, ensure_ascii=False, indent=1)
    with open(os.path.join(args.outdir, 'dialogue.meta.json'), 'w', encoding='utf-8') as f:
        json.dump(dlg_meta, f, ensure_ascii=False)

    # 选择肢
    ch_recs, ch_meta = extract_choices(img)
    with open(os.path.join(args.outdir, 'choices.json'), 'w', encoding='utf-8') as f:
        json.dump(ch_recs, f, ensure_ascii=False, indent=1)
    with open(os.path.join(args.outdir, 'choices.meta.json'), 'w', encoding='utf-8') as f:
        json.dump(ch_meta, f, ensure_ascii=False)

    # 统计
    n_choice = sum(1 for r in ch_recs if r['kind'] == 'choice')
    n_chara = sum(1 for r in ch_recs if r['kind'] == 'chara')
    n_known = sum(1 for v in speaker_table.values() if v['chara'])
    print('提取完成:')
    print(f'  对话 dialogue.json : {len(dlg_recs)} 条 (共 {img.message_count()} 消息槽)')
    print(f'  选择肢+角色名 choices.json : {len(ch_recs)} 条 (选择肢 {n_choice} / 角色名 {n_chara})')
    print(f'  说话人对照 speaker_map.json : {len(speaker_table)} 个语音前缀 (已知角色 {n_known})')
    print(f'    → 未知前缀的 speaker 暂用前缀原样(如 v_hrm); 可在 speaker_map.json')
    print(f'      填 chara 后加 --speaker-map speaker_map.json 重跑, 说话人即更新')
    print(f'  meta 已输出 (注入用, 勿改)')
    print(f'  输出目录: {os.path.abspath(args.outdir)}')


if __name__ == '__main__':
    main()
