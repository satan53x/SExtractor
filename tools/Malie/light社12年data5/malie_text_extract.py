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
    VOICE_PREFIX_TO_CHARA, split_message_struct, clean_body_text,
    classify_body_effects, EFFECT_TOKENS,
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
    段5 每条消息 -> (records, metas)

    ★核心变更: 含 \n 的消息按行拆分成多条独立记录, \n 存入 meta。
      译者看到的每条 record 都是纯净单行, 不含 \n。
      注入时按 meta 里的 msg_idx + line_seps 重组回完整消息。

    record: 给译者   {id, msg_idx, speaker, voice, pre_jp, message}
    meta  : 注入用   {id(=msg_idx), tokens, line_ids, line_seps}
            line_ids  = 属于本消息的 record id 列表
            line_seps = 相邻行之间的 \n 分隔符列表 (长度 = len(line_ids)-1)
    """
    from collections import defaultdict
    from malie_fmt import voice_prefix

    records = []
    metas = []
    prefix_stats = defaultdict(lambda: {'count': 0, 'samples': []})

    n_effect_msgs = 0
    n_multiseg = 0
    rec_id = 0   # 全局递增 id

    for i in range(img.message_count()):
        raw = img.message_raw(i)
        toks = parse_message(raw)

        voice_name, body, tail = split_message_struct(toks)
        speaker = voice_to_chara(voice_name, extra_map) if voice_name else ''

        # 译者可读的纯净正文(含 \n)
        clean = clean_body_text(body)

        # 统计
        if any(t[0] in EFFECT_TOKENS for t in body):
            n_effect_msgs += 1
        if any(t[0] == 'page' for t in body):
            n_multiseg += 1

        # meta: 完整 token 骨架(无损)
        meta = {'id': i, 'tokens': [list(t) for t in toks]}

        has_text = any(t[0] in ('text', 'ruby') for t in body) and clean.strip('\n ')
        if has_text:
            # ── 按 \n 拆分成独立行 ──
            parts = clean.split('\n')
            non_empty = [(j, p) for j, p in enumerate(parts) if p]

            if len(non_empty) == 0:
                meta['line_ids'] = []
                meta['line_seps'] = []
                metas.append(meta)
                continue

            line_ids = []
            line_seps = []

            for k, (idx_in_parts, text_line) in enumerate(non_empty):
                rid = rec_id
                rec_id += 1
                line_ids.append(rid)

                records.append({
                    'id': rid,
                    'msg_idx': i,
                    'speaker': speaker if k == 0 else '',
                    'voice': voice_name if k == 0 else '',
                    'pre_jp': text_line,
                    'message': text_line,
                })

                # 计算与下一非空行之间的 \n 分隔符
                if k + 1 < len(non_empty):
                    next_idx = non_empty[k + 1][0]
                    n_breaks = next_idx - idx_in_parts
                    line_seps.append('\n' * n_breaks)

            meta['line_ids'] = line_ids
            meta['line_seps'] = line_seps

            # speaker_map 统计
            if voice_name:
                pfx = voice_prefix(voice_name)
                st = prefix_stats[pfx]
                st['count'] += 1
                if len(st['samples']) < 3 and clean:
                    st['samples'].append(clean.replace('\n', ' ')[:30])
        else:
            meta['line_ids'] = []
            meta['line_seps'] = []

        metas.append(meta)

    return records, metas, dict(prefix_stats), {'effect_msgs': n_effect_msgs,
                                                'multiseg_msgs': n_multiseg}


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

    if img._parsed_end != img._total and not img._trailing:
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
    dlg_recs, dlg_meta, prefix_stats, dlg_stats = extract_dialogue(img, extra_map)

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
    print(f'    · 含裸特效(变色/样式/表情)的消息 {dlg_stats["effect_msgs"]} 条 '
          f'→ 译者只见干净正文, 中间特效注入时删除、首尾特效回填')
    print(f'    · 含内部换页(多屏叙述)的消息 {dlg_stats["multiseg_msgs"]} 条 '
          f'→ message 里以换行呈现, 注入按行尽量回填')
    print(f'  选择肢+角色名 choices.json : {len(ch_recs)} 条 (选择肢 {n_choice} / 角色名 {n_chara})')
    print(f'  说话人对照 speaker_map.json : {len(speaker_table)} 个语音前缀 (已知角色 {n_known})')
    print(f'    → 未知前缀的 speaker 暂用前缀原样(如 v_hrm); 可在 speaker_map.json')
    print(f'      填 chara 后加 --speaker-map speaker_map.json 重跑, 说话人即更新')
    print(f'  meta 已输出 (注入用, 勿改)')
    print(f'  输出目录: {os.path.abspath(args.outdir)}')


if __name__ == '__main__':
    main()
