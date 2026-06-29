# -*- coding: utf-8 -*-
"""
text_inject.py  ——  方案B 注入：把翻译写回 .SD，文本变长，所有跳转/调用偏移自动重定位

用法:
    python text_inject.py MOPN.SD MOPN.json [out.SD] [--linebytes=62]

原理:
  * 重新反汇编原始 .SD，按与 text_extract 完全一致的顺序定位每条 op74 消息 / op75 选项。
  * 用译文(message 字段)替换对应文本：
      - 消息(op74)：游戏【无自动换行】，故把整句按 <=62 字节（默认）贪心折行，
        每行写成一个独立正文段（与原版"一行一段"完全一致，引擎逐段换行）；
        该 op74 的段数(count)随之更新。折行只在字符边界断，绝不切断双字节字。
      - 选项(op75)：逐条 1:1 替换。
      - message 与原文相同(或该 id 未翻译/缺失/为空) -> 原样字节回写，未译部分 byte-exact。
  * 重新计算每条指令的新偏移，并据此把 op32(GOSUB)/op33,op60(JMP)/op153,op154(跳转表)
    里存的相对偏移全部改写为新值（目标必落在指令边界，已验证）。
  * 译文必须能通过 cp932 编码（含自制 JIS 字形映射）；不能编码会列出并中止。

每行字节上限可用 --linebytes=N 调整（原版每行最多 52 字节，默认 62）。
不改任何内容时（原样回写），输出应与原文件 byte-identical（零突变）。
"""
import sys, os, json
import mop_sd as M


# 每行最大字节数（游戏无自动换行，必须手动折行；原版每行最多 52 字节，留余量取 62）
MAX_LINE_BYTES = 62


def _u16(v): return bytes((v & 0xFF, (v >> 8) & 0xFF))
def _u32(v): return bytes((v & 0xFF, (v >> 8) & 0xFF, (v >> 16) & 0xFF, (v >> 24) & 0xFF))


def encode_cp932(s, where, errs):
    try:
        return s.encode('cp932')
    except UnicodeEncodeError as e:
        bad = s[e.start:e.end]
        errs.append((where, bad, s))
        return None


def wrap_cp932(s, where, errs, limit=MAX_LINE_BYTES):
    """把一句译文按 cp932 字节数贪心折行（在字符边界处断，绝不切断双字节字）。
    返回每行的 cp932 字节串列表（每行 <= limit 字节）；遇到无法编码的字符记入 errs 并返回 None。"""
    lines = []
    cur = bytearray()
    for ch in s:
        try:
            b = ch.encode('cp932')
        except UnicodeEncodeError:
            errs.append((where, ch, s))
            return None
        if cur and len(cur) + len(b) > limit:
            lines.append(bytes(cur))
            cur = bytearray()
        cur += b
    if cur:
        lines.append(bytes(cur))
    return lines


def build_op74(inst, id_of_run, trans, errs, limit=MAX_LINE_BYTES):
    """重建一条 op74 指令字节。id_of_run: {run_start_seg_index: 全局id}。"""
    segs = inst.segs
    # 标记每个 text-run（消息）的起始与覆盖范围
    runs = {}                 # start_idx -> [indices...]
    for (idx_list, joined, _name) in M.iter_messages(inst):
        runs[idx_list[0]] = idx_list
    consumed = set()
    new_segs = []   # [(raw_bytes, extra_bytes)]
    for idx, (raw, extra) in enumerate(segs):
        if idx in consumed:
            continue
        if idx in runs:
            run = runs[idx]
            consumed.update(run)
            orig = b''.join(segs[i][0] for i in run)
            mid = id_of_run.get(idx)            # 该消息对应的全局 id
            wrapped = None
            if mid is not None and mid in trans:
                cand = trans[mid]
                if cand is not None and cand != '' and cand != M.decode_cp932(orig):
                    lines = wrap_cp932(cand, "msg id=%d" % mid, errs, limit)
                    if lines:                    # 折行成功（非空）
                        wrapped = lines
            if wrapped is not None:
                for line in wrapped:             # 每行=一个独立正文段（引擎逐段换行）
                    new_segs.append((line, b''))
            else:
                for i in run:                    # 未改/空 -> 原样保留原始分段，保证 byte-exact
                    new_segs.append(segs[i])
        else:
            new_segs.append((raw, extra))         # N/M/V/W/@ 命令段，原样

    body = bytearray()
    body += _u16(inst.op)              # 用本指令自身的文本opcode（MOP/EXD=74, KLH=72）
    body += _u16(len(new_segs))
    for raw, extra in new_segs:
        body += raw + b'\x00' + extra
    return bytes(body)


def build_op75(inst, ids, trans, errs):
    opts = inst.opts
    body = bytearray()
    body += _u16(inst.op)             # 用本指令自身的选择肢opcode（MOP/EXD=75, KLH=73）
    body += _u16(len(opts))
    for oi, raw in enumerate(opts):
        mid = ids[oi]
        out = raw
        if mid in trans:
            cand = trans[mid]
            if cand is not None and cand != M.decode_cp932(raw):
                enc = encode_cp932(cand, "opt id=%d" % mid, errs)
                if enc is not None:
                    out = enc
        body += out + b'\x00'
    return bytes(body)


def inject(sd_path, json_path, out_path, limit=MAX_LINE_BYTES):
    data = open(sd_path, 'rb').read()
    insts, boundaries = M.disassemble(data)
    entries = json.load(open(json_path, encoding='utf-8'))
    trans = {}
    for x in entries:
        if 'id' in x and 'message' in x:
            trans[x['id']] = x['message']

    errs = []
    # 第一遍：按提取顺序分配 id，并生成每条指令的新字节
    new_bytes = [None] * len(insts)
    nid = 0
    for ii, inst in enumerate(insts):
        if inst.kind == 'text':
            id_of_run = {}
            for (idx_list, joined, _name) in M.iter_messages(inst):
                id_of_run[idx_list[0]] = nid
                nid += 1
            new_bytes[ii] = build_op74(inst, id_of_run, trans, errs, limit)
        elif inst.kind == 'choice':
            ids = []
            for _ in inst.opts:
                ids.append(nid); nid += 1
            new_bytes[ii] = build_op75(inst, ids, trans, errs)
        else:
            new_bytes[ii] = data[inst.off:inst.off + inst.length]

    if errs:
        print("!! 以下译文无法用 cp932 编码（需检查字库/字形映射），已中止：")
        for where, bad, full in errs[:40]:
            print("   [%s] 非法字符 %r  于句: %s" % (where, bad, full[:40]))
        if len(errs) > 40:
            print("   ... 共 %d 处" % len(errs))
        raise SystemExit(2)

    # 计算新偏移 + 旧->新 映射
    new_off = []
    acc = 0
    for b in new_bytes:
        new_off.append(acc); acc += len(b)
    old_to_new = {insts[i].off: new_off[i] for i in range(len(insts))}

    # 第二遍：重定位所有内联偏移（op32/33/60/153/154）
    relocs = 0
    for ii, inst in enumerate(insts):
        if not inst.reloc:
            continue
        b = bytearray(new_bytes[ii])
        for (field_abs, old_tgt) in inst.reloc:
            if old_tgt not in old_to_new:
                raise ValueError("跳转目标 0x%x 不在指令边界（来自指令 @0x%x op=%d），中止以免损坏脚本"
                                 % (old_tgt, inst.off, inst.op))
            rel = field_abs - inst.off       # 字段在本指令内的相对位置（指令长度不变）
            b[rel:rel + 4] = _u32(old_to_new[old_tgt])
            relocs += 1
        new_bytes[ii] = bytes(b)

    out = b''.join(new_bytes)
    open(out_path, 'wb').write(out)

    changed = (out != data)
    print("注入完成： %s" % out_path)
    print("  原大小 %d -> 新大小 %d  (%+d 字节)" % (len(data), len(out), len(out) - len(data)))
    print("  重定位偏移字段 %d 个 | 与原文件是否一致: %s" % (relocs, not changed))
    return out


def main():
    args = [a for a in sys.argv[1:]]
    limit = MAX_LINE_BYTES
    rest = []
    for a in args:
        if a.startswith('--linebytes='):
            limit = int(a.split('=', 1)[1])
        elif a.startswith('--linebytes'):
            continue
        else:
            rest.append(a)
    if len(rest) < 2:
        print(__doc__); sys.exit(1)
    sd = rest[0]
    js = rest[1]
    out = rest[2] if len(rest) > 2 else os.path.splitext(sd)[0] + ".new.SD"
    print("每行字节上限: %d" % limit)
    inject(sd, js, out, limit)


if __name__ == '__main__':
    main()
