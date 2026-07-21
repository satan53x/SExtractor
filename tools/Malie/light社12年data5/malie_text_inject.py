# -*- coding: utf-8 -*-
"""
malie_text_inject.py — 将翻译回填进 EXEC 明文字节码（方案B：变长 + 重定位）
============================================================================

输入:
  原始 EXEC_decrypted.bin
  dialogue.json + dialogue.meta.json   (对话译文 + 骨架)
  choices.json  + choices.meta.json    (选择肢/角色名译文 + 段3串序)

输出:
  重建的 EXEC 明文字节码 (可再经 malie_exec_crypt.py 加密塞回 exe)

方案B 关键处理:
  1. 段5: 用译文替换每条消息的 text token, 重组段5正文
  2. 段6: 消息长度变化 → 重算 msgtab 偏移表
  3. 段3: 用译文替换选择肢/角色名串, 重建段3 (串偏移会变)
  4. 段4代码段: 若段3内串偏移变化, 重定位所有引用段3偏移的指令

★空注入(不改任何译文)必须 byte-exact 还原原文件。
"""

import argparse
import json
import struct
import sys

from malie_fmt import (
    ExecImage, parse_message, rebuild_message, split_seg3,
    OPERAND_WIDTHS, instr_len, JUMP_OPCODES,
    build_translated_message,
)


# ────────────────────────────────────────────────────────────────────────
#  段5 + 段6 重建
# ────────────────────────────────────────────────────────────────────────
def rebuild_seg5(img, dlg_meta, dlg_trans):
    """
    用译文重组段5, 并重算 msgtab。
    dlg_meta : list of {id, tokens}   tokens = 完整 token 骨架
    dlg_trans: dict id -> message(译文)
    返回 (new_seg5:bytes, new_msgtab:list[int])             — v0 格式
    　或 (new_seg5:bytes, new_msgtab_pairs:list[(int,int)])  — v1 格式

    · 无译文的消息 → 用完整骨架 rebuild_message() 逐字节还原(空注入 byte-exact)
    · 有译文的消息 → build_translated_message() 套用策略:
        语音/结构终止串保留; 中间裸特效删除, 首尾裸特效回填;
        注音退化为普通文本; 停顿删除; 单段整条回填, 多段按 '\n' 尽量逐段回填。
    """
    meta_by_id = {m['id']: m for m in dlg_meta}
    is_v1 = img._version >= 1   # v1 和 v2 都用 (off, len) pairs

    new_seg5 = bytearray()
    new_msgtab = []          # v0: [offset, ...]
    new_msgtab_pairs = []    # v1: [(offset, length), ...]

    for i in range(img.message_count()):
        msg_off = len(new_seg5)

        m = meta_by_id.get(i)
        if m is None:
            raw = img.message_raw(i)
        else:
            toks = [tuple(t) for t in m['tokens']]
            trans = dlg_trans.get(i)
            if trans is None:
                raw = rebuild_message(toks)
            else:
                new_toks = build_translated_message(toks, trans)
                raw = rebuild_message(new_toks)

        new_seg5.extend(raw)
        msg_len = len(raw)

        if is_v1:
            new_msgtab_pairs.append((msg_off, msg_len))
            # v1: 消息间 2 字节 NUL 间隔
            new_seg5.extend(b'\x00\x00')
        else:
            new_msgtab.append(msg_off)

    if is_v1:
        return bytes(new_seg5), new_msgtab_pairs
    return bytes(new_seg5), new_msgtab


# ────────────────────────────────────────────────────────────────────────
#  段3 重建 + 偏移映射
# ────────────────────────────────────────────────────────────────────────
def rebuild_seg3(ch_meta, ch_trans):
    """
    用译文重建段3。
    ch_meta : {strings:[{off,text,kind}], trailing_hex}
    ch_trans: dict seg3_off -> message(译文)
    返回 (new_seg3:bytes, off_map:dict old_off->new_off)
    """
    strings = ch_meta['strings']
    trailing = bytes.fromhex(ch_meta['trailing_hex'])

    new_seg3 = bytearray()
    off_map = {}

    for item in strings:
        old_off = item['off']
        text = item['text']
        trans = ch_trans.get(old_off)
        if trans is not None:
            text = trans
        new_off = len(new_seg3)
        off_map[old_off] = new_off
        new_seg3.extend(text.encode('utf-16le'))
        new_seg3.extend(struct.pack('<H', 0))   # NUL 分隔

    new_seg3.extend(trailing)
    return bytes(new_seg3), off_map


# ────────────────────────────────────────────────────────────────────────
#  段4 代码段: 段3 偏移重定位
# ────────────────────────────────────────────────────────────────────────
def _disasm_code(code):
    """
    线性反汇编代码段为指令列表。
    返回 list of dict: {ip, op, operands:[(type, value), ...], length}
    opcode 表已全覆盖, 不会遇到未知 op。
    """
    ins = []
    n = len(code)
    ip = 0
    while ip < n:
        op = code[ip]
        w = OPERAND_WIDTHS.get(op)
        if w is None:
            raise ValueError(f'代码段 0x{ip:X} 处未知 opcode {op}(0x{op:02X})')
        p = ip + 1
        operands = []
        for t in w:
            if t == 'U':
                operands.append(['U', struct.unpack_from('<I', code, p)[0]]); p += 4
            elif t == 'W':
                operands.append(['W', struct.unpack_from('<H', code, p)[0]]); p += 2
            else:
                operands.append(['B', code[p]]); p += 1
        ins.append({'ip': ip, 'op': op, 'operands': operands, 'length': p - ip})
        ip = p
    return ins


def relocate_code(code, labels, off_map):
    """
    段3 变长后重定位代码段。分两阶段:

    阶段1 (段3引用更新, 定长):
      op9/op10/op12 的立即数 = 旧段3偏移 → off_map[旧偏移]。
      若 op10(u16) 的新偏移 > 0xFFFF, 标记该指令需升级为 op12(u32)。
      若 op9(u8)  的新偏移 > 0xFF,   标记升级为 op12。

    阶段2 (指令升级, 变长):
      被标记的 op10/op9 升级为 op12(+2/+3 字节)。这改变后续所有指令的 ip,
      因此需重新计算:
        - 每条 JMP(op0/1/2) 的目标偏移
        - CALL_SUB(op45) 的目标(经 labels 索引, label.type 需更新)
        - labels 表的 type 字段(标签入口偏移)

    返回 (new_code:bytes, new_labels:list, stats:dict)

    注: 段3恒等映射(空注入)时零改动, 直接返回。
    """
    identity = all(k == v for k, v in off_map.items())

    # 段3偏移未变(仅对话注入/空注入) → 代码段零改动, 无需反汇编, 直接返回。
    # 这样对话注入不受代码段任何 opcode 细节影响, 最稳。
    if identity:
        return code, list(labels), {'reloc': 0, 'upgrade': 0}

    ins = _disasm_code(code)

    # ── 阶段1: 更新段3引用, 标记需升级的指令 ──
    n_reloc = 0
    n_upgrade = 0
    for e in ins:
        op = e['op']
        if op == 12 and e['operands'] and e['operands'][0][0] == 'U':
            v = e['operands'][0][1]
            if v in off_map:
                nv = off_map[v]
                if nv != v:
                    e['operands'][0][1] = nv; n_reloc += 1
        elif op == 10 and e['operands'] and e['operands'][0][0] == 'W':
            v = e['operands'][0][1]
            if v in off_map:
                nv = off_map[v]
                if nv > 0xFFFF:
                    # 升级为 op12
                    e['op'] = 12
                    e['operands'][0] = ['U', nv]
                    e['_upgraded'] = True
                    n_upgrade += 1
                elif nv != v:
                    e['operands'][0][1] = nv; n_reloc += 1
        elif op == 9 and e['operands'] and e['operands'][0][0] == 'B':
            v = e['operands'][0][1]
            if v in off_map:
                nv = off_map[v]
                if nv > 0xFF:
                    e['op'] = 12
                    e['operands'][0] = ['U', nv]
                    e['_upgraded'] = True
                    n_upgrade += 1
                elif nv != v:
                    e['operands'][0][1] = nv; n_reloc += 1

    if identity and n_upgrade == 0:
        return code, list(labels), {'reloc': 0, 'upgrade': 0}

    # 若无升级, 段3引用是定长改写, 无需重排 → 直接回填
    if n_upgrade == 0:
        out = bytearray(code)
        for e in ins:
            p = e['ip'] + 1
            for t, v in e['operands']:
                if t == 'U':
                    struct.pack_into('<I', out, p, v); p += 4
                elif t == 'W':
                    struct.pack_into('<H', out, p, v); p += 2
                else:
                    out[p] = v; p += 1
        return bytes(out), list(labels), {'reloc': n_reloc, 'upgrade': 0}

    # ── 阶段2: 有升级 → 指令流长度变化, 需重排 + 重定位 ──
    # 1. 计算每条指令的新长度与旧→新 ip 映射
    def op_len(op, operands):
        n = 1
        for t, _ in operands:
            n += {'U': 4, 'W': 2, 'B': 1}[t]
        return n

    old_to_new = {}
    new_ip = 0
    for e in ins:
        old_to_new[e['ip']] = new_ip
        e['_newlen'] = op_len(e['op'], e['operands'])
        new_ip += e['_newlen']
    new_code_len = new_ip
    # 代码段末尾对齐字节(若有), 记录尾部残留
    # _disasm_code 精确覆盖到段长, 故无残留

    # 2. 更新 labels.type (标签入口偏移)
    new_labels = []
    for name, typ in labels:
        if typ in old_to_new:
            new_labels.append((name, old_to_new[typ]))
        elif typ == len(code):        # 指向段末的标签
            new_labels.append((name, new_code_len))
        else:
            # 落在指令中间(不应发生) → 保守保留, 但告警
            new_labels.append((name, old_to_new.get(typ, typ)))

    # label 索引 → 新偏移(供 CALL_SUB 用, 其实 CALL_SUB 存的是索引不是偏移, 不需改)

    # 3. 更新 JMP(op0/1/2) 目标 = old_to_new[旧目标]
    for e in ins:
        if e['op'] in JUMP_OPCODES and e['operands'] and e['operands'][0][0] == 'U':
            tgt = e['operands'][0][1]
            if tgt in old_to_new:
                e['operands'][0][1] = old_to_new[tgt]
            elif tgt == len(code):
                e['operands'][0][1] = new_code_len
            # 否则目标在开头数据区/不可达, 保留原值(这些是死代码)

    # 4. 生成新代码字节
    out = bytearray()
    for e in ins:
        out.append(e['op'])
        for t, v in e['operands']:
            if t == 'U':
                out.extend(struct.pack('<I', v))
            elif t == 'W':
                out.extend(struct.pack('<H', v))
            else:
                out.append(v)

    return bytes(out), new_labels, {'reloc': n_reloc, 'upgrade': n_upgrade}


# ────────────────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser(description='Malie EXEC 文本注入(方案B)')
    ap.add_argument('input', help='原始 EXEC_decrypted.bin')
    ap.add_argument('-d', '--dialogue', help='dialogue.json 译文')
    ap.add_argument('--dialogue-meta', help='dialogue.meta.json')
    ap.add_argument('-c', '--choices', help='choices.json 译文')
    ap.add_argument('--choices-meta', help='choices.meta.json')
    ap.add_argument('-o', '--output', required=True, help='输出重建的 EXEC 明文')
    ap.add_argument('--empty', action='store_true',
                    help='空注入模式: 忽略译文, 仅测试 byte-exact 重建')
    args = ap.parse_args()

    data = open(args.input, 'rb').read()
    img = ExecImage(data)

    # 载入 meta 与译文
    dlg_meta = json.load(open(args.dialogue_meta, encoding='utf-8')) if args.dialogue_meta else \
        _extract_meta_dialogue(img)
    ch_meta = json.load(open(args.choices_meta, encoding='utf-8')) if args.choices_meta else \
        _extract_meta_choices(img)

    dlg_trans = {}
    ch_trans = {}
    if not args.empty:
        if args.dialogue and args.dialogue_meta:
            # ── 新格式: 按 msg_idx + line_seps 重组多行消息 ──
            dlg_recs = json.load(open(args.dialogue, encoding='utf-8'))
            dlg_meta_list = json.load(open(args.dialogue_meta, encoding='utf-8'))

            # 建立 record id -> record 映射
            rec_by_id = {r['id']: r for r in dlg_recs}

            for m in dlg_meta_list:
                msg_idx = m['id']
                line_ids = m.get('line_ids', [])
                line_seps = m.get('line_seps', [])

                if not line_ids:
                    continue  # 无文本行的消息, 跳过

                # 收集各行的翻译文本
                parts = []
                any_changed = False
                for lid in line_ids:
                    rec = rec_by_id.get(lid)
                    if rec is None:
                        parts.append('')
                        continue
                    msg = rec.get('message', '')
                    pre = rec.get('pre_jp', '')
                    parts.append(msg)
                    if msg != pre:
                        any_changed = True

                if any_changed:
                    # 用 line_seps 拼回完整翻译文本
                    full = parts[0]
                    for k in range(1, len(parts)):
                        sep = line_seps[k - 1] if k - 1 < len(line_seps) else '\n'
                        full += sep + parts[k]
                    dlg_trans[msg_idx] = full

        elif args.dialogue:
            # ── 兼容旧格式(无 msg_idx 字段) ──
            for r in json.load(open(args.dialogue, encoding='utf-8')):
                if r.get('message') is not None and r['message'] != r.get('pre_jp'):
                    rid = r.get('msg_idx', r['id'])
                    dlg_trans[rid] = r['message']

        if args.choices:
            for r in json.load(open(args.choices, encoding='utf-8')):
                if r.get('message') is not None and r['message'] != r.get('pre_jp'):
                    ch_trans[r['seg3_off']] = r['message']

    # 重建段5 + 段6
    new_seg5, new_msgtab = rebuild_seg5(img, dlg_meta, dlg_trans)
    img.seg5 = new_seg5
    if img._version >= 1:
        img._msgtab_pairs = new_msgtab  # v1/v2: list of (off, len)
        img.msgtab = [off for off, _ in new_msgtab]
    else:
        img.msgtab = new_msgtab          # v0: list of offsets

    # 重建段3 + 重定位段4(含 op10→op12 升级与跳转/标签重定位)
    new_seg3, off_map = rebuild_seg3(ch_meta, ch_trans)
    img.seg3 = new_seg3
    new_code, new_labels, stats = relocate_code(img.code, img.labels, off_map)
    img.code = new_code
    img.labels = new_labels

    out = img.build()
    with open(args.output, 'wb') as f:
        f.write(out)

    print('注入完成:')
    print(f'  对话译文应用: {len(dlg_trans)} 条')
    print(f'  段3译文应用: {len(ch_trans)} 条')
    print(f'  段4重定位: {stats["reloc"]} 处段3引用更新')
    if stats['upgrade']:
        print(f'  段4指令升级: {stats["upgrade"]} 处 op10→op12 (偏移超u16), 已重排跳转/标签')
    print(f'  输出: {args.output}  ({len(out)} 字节)')

    if args.empty:
        same = (out == data)
        print(f'  空注入 byte-exact: {"✅ 完全一致" if same else "❌ 有差异"}')
        if not same:
            for k in range(min(len(out), len(data))):
                if out[k] != data[k]:
                    print(f'    首差异@0x{k:X}: 原{data[k:k+8].hex()} 新{out[k:k+8].hex()}')
                    break
            sys.exit(1)


# 无 meta 文件时, 从原 img 现算(便于独立测试)
def _extract_meta_dialogue(img):
    metas = []
    for i in range(img.message_count()):
        toks = parse_message(img.message_raw(i))
        metas.append({'id': i, 'tokens': [list(t) for t in toks]})
    return metas


def _extract_meta_choices(img):
    items, trailing = split_seg3(img.seg3)
    from malie_text_extract import classify_seg3
    strings = [{'off': o, 'text': s, 'kind': classify_seg3(s)} for o, s in items]
    return {'strings': strings, 'trailing_hex': trailing.hex()}


if __name__ == '__main__':
    main()
