#!/usr/bin/env python3
"""
BunBun Engine TAK Script Tool (保健室～マジカルピュアレッスン♪～)

反汇编: TAK.BIN → 每个脚本一个txt
汇编:   txt → TAK.BIN (自动修正跳转偏移)

字节码:
  通用opcode: 4字节 [op, b1, b2, b3], 全部4字节对齐
  AA(MSG)/A8(NAME): 4字节头 + SJIS文本(偶数字节) [+ 00 00 对齐]
    对齐规则: (4+text_len)%4==0 → 不加null; (4+text_len)%4==2 → 加2字节null
  AC(JUMP): AC offset_lo offset_hi 00, 绝对偏移跳转

Usage:
  python tak_text.py extract <exe> <TAK.BIN> <output_dir>
  python tak_text.py build   <exe> <TAK.BIN> <txt_dir> <out.BIN> <out.exe>
"""

import struct, sys, os, argparse, shutil, glob, re

TAK_INDEX_OFFSET = 0x44748
ALIGNMENT = 0x800

def lzs_decompress(data):
    if len(data) < 8 or data[:3] != b'LZS':
        return data, False
    dsz = struct.unpack_from('<I', data, 4)[0]
    src, end = 8, len(data)
    ring = bytearray(b'\x20' * 4096); rp = 0xFEE
    out = bytearray(); flags = 0
    while len(out) < dsz and src < end:
        flags >>= 1
        if not (flags & 0x100):
            if src >= end: break
            flags = 0xFF00 | data[src]; src += 1
        if flags & 1:
            if src >= end: break
            b = data[src]; src += 1
            out.append(b); ring[rp] = b; rp = (rp+1)&0xFFF
        else:
            if src+1 >= end: break
            b1, b2 = data[src], data[src+1]; src += 2
            ro = ((b2&0xF0)<<4)|b1; ln = (b2&0x0F)+3
            for _ in range(ln):
                if len(out) >= dsz: break
                b = ring[ro]; out.append(b)
                ring[rp] = b; rp = (rp+1)&0xFFF; ro = (ro+1)&0xFFF
    return bytes(out), True

def read_index(exe):
    entries = []
    with open(exe, 'rb') as f:
        f.seek(TAK_INDEX_OFFSET)
        while True:
            d = f.read(12)
            if len(d) < 12: break
            o, s, fl, eid = struct.unpack('<IIHH', d)
            if eid == 0: break
            entries.append({'id': eid, 'offset': o, 'size': s, 'flags': fl})
    return entries

OP_NAMES = {
    0xA1:'CMD', 0xA2:'WAIT', 0xA3:'A3', 0xA4:'VOICE', 0xA5:'BGM',
    0xA6:'SE', 0xA7:'VIS', 0xA9:'NAME_END', 0xAB:'MSG_END', 0xAC:'JUMP',
    0xAD:'VAR', 0xAE:'VAR_AE', 0xAF:'VAR_AF', 0xB0:'VAR_B0', 0xB1:'VAR_B1',
    0xB6:'VAR_B6', 0xB7:'VAR_B7', 0xB8:'VAR_B8', 0xBC:'VAR_BC',
}
NAME_TO_OP = {v: k for k, v in OP_NAMES.items()}

# ==================== Disassemble ====================

def disassemble(data):
    insts = []
    pos = 0
    while pos < len(data):
        b = data[pos]
        if b in (0xAA, 0xA8) and pos+3 < len(data) and data[pos+1] == 0x00:
            itype = 'msg' if b == 0xAA else 'name'
            eid = struct.unpack_from('<H', data, pos+2)[0]
            term = 0xAB if b == 0xAA else 0xA9
            p = pos + 4
            while p < len(data):
                if data[p] == 0x00 or data[p] == term:
                    break
                p += 2
            text_bytes = data[pos+4:p]
            try:
                text = text_bytes.decode('cp932', errors='replace')
            except:
                text = text_bytes.hex()
            insts.append((pos, itype, eid, text))
            # advance past text + optional null padding
            if p < len(data) and data[p] == 0x00:
                while p < len(data) and data[p] == 0x00:
                    p += 1
            pos = p
        elif b >= 0xA0 and not (0xE0 <= b <= 0xFC) and pos+3 < len(data):
            raw = data[pos:pos+4]
            if b == 0xAC:
                target = struct.unpack_from('<H', raw, 1)[0]
                insts.append((pos, 'jump', target))
            else:
                insts.append((pos, 'op4', raw))
            pos += 4
        else:
            pos += 1
    return insts

def format_op(raw):
    op, b1 = raw[0], raw[1]
    param = struct.unpack_from('<H', raw, 2)[0]
    name = OP_NAMES.get(op, f'OP_{op:02X}')
    if op == 0xAC:
        target = struct.unpack_from('<H', raw, 1)[0]
        return f'JUMP @{target:04X}'
    elif op == 0xA1:
        return f'CMD {b1:02X} {param:04X}'
    else:
        return f'{name} {b1:02X} {param:04X}'

def insts_to_text(insts):
    lines = []
    for inst in insts:
        off, itype = inst[0], inst[1]
        if itype == 'msg':
            lines.append(f'@{off:04X} MSG {inst[2]:04X} {inst[3]}')
            lines.append(f'@{off:04X} TL  {inst[2]:04X} ')
        elif itype == 'name':
            lines.append(f'@{off:04X} NAME {inst[2]:04X} {inst[3]}')
        elif itype == 'jump':
            lines.append(f'@{off:04X} JUMP @{inst[2]:04X}')
        elif itype == 'op4':
            lines.append(f'@{off:04X} {format_op(inst[2])}')
    return '\n'.join(lines) + '\n'

# ==================== Assemble ====================

def encode_text(text):
    try:
        return text.encode('cp932')
    except UnicodeEncodeError:
        return text.encode('cp932', errors='replace')

def parse_txt(text):
    insts = []
    lines = text.split('\n')
    i = 0
    while i < len(lines):
        line = lines[i].rstrip('\n\r')
        if not line:
            i += 1; continue
        m = re.match(r'^@([0-9A-Fa-f]+)[ \t]+(\S+)[ \t](.*)', line)
        if not m:
            i += 1; continue
        orig_off = int(m.group(1), 16)
        itype = m.group(2)
        rest = m.group(3)

        if itype == 'MSG':
            eid = int(rest[:4], 16)
            text = rest[5:]
            tl_text = None
            if i+1 < len(lines):
                tl = re.match(r'^@[0-9A-Fa-f]+[ \t]+TL[ \t]+[0-9A-Fa-f]+[ \t](.*)', lines[i+1].rstrip())
                if tl:
                    tl_text = tl.group(1)
                    # 只去掉末尾ASCII空白,保留全角空格等
                    if tl_text and tl_text[-1] in ' \t':
                        tl_text = tl_text.rstrip(' \t')
                    i += 1
            insts.append((orig_off, 'msg', eid, tl_text if tl_text else text))
        elif itype == 'NAME':
            eid = int(rest[:4], 16)
            insts.append((orig_off, 'name', eid, rest[5:]))
        elif itype == 'JUMP':
            tm = re.match(r'@([0-9A-Fa-f]+)', rest)
            if tm:
                insts.append((orig_off, 'jump', int(tm.group(1), 16)))
        elif itype == 'RAW':
            insts.append((orig_off, 'raw', bytes.fromhex(rest)))
        else:
            # generic opcode
            if itype.startswith('OP_'):
                op = int(itype[3:], 16)
            elif itype in NAME_TO_OP:
                op = NAME_TO_OP[itype]
            else:
                i += 1; continue
            parts = rest.strip().split()
            b1 = int(parts[0], 16) if len(parts) >= 1 else 0
            param = int(parts[1], 16) if len(parts) >= 2 else 0
            insts.append((orig_off, 'op4', struct.pack('<BBH', op, b1, param)))
        i += 1
    return insts

def assemble(insts):
    output = bytearray()
    old_to_new = {}
    jumps = []

    for inst in insts:
        orig_off, itype = inst[0], inst[1]
        old_to_new[orig_off] = len(output)

        if itype in ('msg', 'name'):
            _, _, eid, text = inst
            op = 0xAA if itype == 'msg' else 0xA8
            output.extend(struct.pack('<BBH', op, 0x00, eid))
            tb = encode_text(text)
            # 确保文本字节长度为偶数(SJIS双字节, 理论上总是偶数)
            if len(tb) % 2 == 1:
                tb += b'\x00'
            output.extend(tb)
            # 4字节对齐: (4+tlen)%4==2 → 加2字节null; ==0 → 不加
            if (4 + len(tb)) % 4 == 2:
                output.extend(b'\x00\x00')
        elif itype == 'jump':
            _, _, old_target = inst
            jumps.append((len(output), old_target))
            output.extend(struct.pack('<BHB', 0xAC, 0, 0))
        elif itype == 'op4':
            _, _, raw = inst
            output.extend(raw)
        elif itype == 'raw':
            _, _, raw = inst
            output.extend(raw)

    # Fix jumps
    for jpos, old_target in jumps:
        if old_target in old_to_new:
            new_target = old_to_new[old_target]
        else:
            candidates = sorted(old_to_new.keys())
            best = min(candidates, key=lambda k: abs(k - old_target))
            new_target = old_to_new[best] + (old_target - best)
        struct.pack_into('<H', output, jpos + 1, new_target)

    # 文件末尾4字节null padding
    output.extend(b'\x00\x00\x00\x00')

    return bytes(output)

# ==================== Commands ====================

def cmd_extract(args):
    entries = read_index(args.exe)
    with open(args.tak_bin, 'rb') as f:
        bdata = f.read()
    os.makedirs(args.output_dir, exist_ok=True)
    total = 0
    for entry in entries:
        fd = bdata[entry['offset']:entry['offset']+entry['size']]
        fd, _ = lzs_decompress(fd)
        insts = disassemble(fd)
        txt = insts_to_text(insts)
        fname = f"TAK{entry['id']:03d}.txt"
        with open(os.path.join(args.output_dir, fname), 'w', encoding='utf-8') as f:
            f.write(txt)
        total += len(insts)
    print(f"Extracted {len(entries)} scripts ({total} instructions)")

def cmd_build(args):
    entries = read_index(args.exe)
    with open(args.tak_bin, 'rb') as f:
        bdata = f.read()
    txts = {}
    for tf in sorted(glob.glob(os.path.join(args.txt_dir, 'TAK*.txt'))):
        m = re.match(r'TAK(\d+)\.txt', os.path.basename(tf), re.I)
        if m:
            with open(tf, 'r', encoding='utf-8') as f:
                txts[int(m.group(1))] = f.read()
    if not txts:
        sys.exit(f"No TAKxxx.txt in {args.txt_dir}/")
    print(f"Loaded {len(txts)} scripts")

    new_bin = bytearray()
    new_entries = []
    for entry in entries:
        fd = bdata[entry['offset']:entry['offset']+entry['size']]
        decomp, _ = lzs_decompress(fd)
        if entry['id'] in txts:
            insts = parse_txt(txts[entry['id']])
            new_data = assemble(insts)
        else:
            new_data = decomp
        new_entries.append({'id': entry['id'], 'offset': len(new_bin),
                           'size': len(new_data), 'flags': 0})
        new_bin.extend(new_data)
        pad = (ALIGNMENT - len(new_bin) % ALIGNMENT) % ALIGNMENT
        new_bin.extend(b'\x00' * pad)

    with open(args.out_bin, 'wb') as f:
        f.write(new_bin)
    shutil.copy2(args.exe, args.out_exe)
    with open(args.out_exe, 'r+b') as f:
        f.seek(TAK_INDEX_OFFSET)
        for e in new_entries:
            f.write(struct.pack('<IIHH', e['offset'], e['size'], e['flags'], e['id']))
        # 哨兵条目: offset=BIN大小, size=BIN大小, flags=0, id=0
        bin_size = len(new_bin)
        f.write(struct.pack('<IIHH', bin_size, bin_size, 0, 0))
    print(f"Built {len(new_entries)} scripts -> {args.out_bin} ({len(new_bin)} bytes)")
    print(f"Updated {args.out_exe}")

def main():
    p = argparse.ArgumentParser(description='BunBun TAK Script Tool')
    sub = p.add_subparsers(dest='cmd')
    s1 = sub.add_parser('extract')
    s1.add_argument('exe'); s1.add_argument('tak_bin'); s1.add_argument('output_dir')
    s2 = sub.add_parser('build')
    s2.add_argument('exe'); s2.add_argument('tak_bin'); s2.add_argument('txt_dir')
    s2.add_argument('out_bin'); s2.add_argument('out_exe')
    args = p.parse_args()
    {'extract': cmd_extract, 'build': cmd_build}.get(args.cmd, lambda a: p.print_help())(args)

if __name__ == '__main__':
    main()
