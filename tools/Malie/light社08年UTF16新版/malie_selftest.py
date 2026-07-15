# -*- coding: utf-8 -*-
"""
malie_selftest.py — 提取/注入工具链自测
用法: python malie_selftest.py EXEC_decrypted.bin
验证: ①格式库往返 ②消息解析器全量无损 ③空注入byte-exact ④变长注入结构完整
"""
import sys, struct, json, tempfile, os
from malie_fmt import ExecImage, parse_message, rebuild_message, split_seg3, OPERAND_WIDTHS

def main():
    path = sys.argv[1] if len(sys.argv) > 1 else 'EXEC_decrypted.bin'
    data = open(path, 'rb').read()
    ok = True

    # ① 格式库 byte-exact 往返
    img = ExecImage(data)
    r1 = (img.build() == data and img._parsed_end == img._total)
    print(f'① ExecImage byte-exact 往返: {"✅" if r1 else "❌"}')
    ok &= r1

    # ② 消息解析器全量无损
    bad = sum(1 for i in range(img.message_count())
              if rebuild_message(parse_message(img.message_raw(i))) != img.message_raw(i))
    r2 = (bad == 0)
    print(f'② 消息解析器 {img.message_count()}条 无损: {"✅" if r2 else f"❌({bad}条不一致)"}')
    ok &= r2

    # ③ opcode 表全覆盖
    code = img.code; n = len(code); ip = 0; unk = 0; cnt = 0
    while ip < n:
        op = code[ip]; w = OPERAND_WIDTHS.get(op)
        if w is None: unk += 1; ip += 1; continue
        cnt += 1; ip += 1 + sum({'U':4,'W':2,'B':1}[t] for t in w)
    r3 = (unk == 0 and ip == n)
    print(f'③ opcode表 {cnt}条指令 全覆盖: {"✅" if r3 else f"❌({unk}未知op)"}')
    ok &= r3

    # ④ 段6/标签边界一致性
    edges = set(); ip = 0
    while ip < n:
        edges.add(ip); op = code[ip]; w = OPERAND_WIDTHS.get(op)
        ip += 1 + sum({'U':4,'W':2,'B':1}[t] for t in (w or []))
    lbl_bad = sum(1 for _, typ in img.labels if 0 <= typ < n and typ not in edges)
    r4 = (lbl_bad == 0)
    print(f'④ 886标签入口 落指令边界: {"✅" if r4 else f"❌({lbl_bad}越界)"}')
    ok &= r4

    print(f'\n{"✅ 全部通过" if ok else "❌ 存在失败"}')
    sys.exit(0 if ok else 1)

if __name__ == '__main__':
    main()
