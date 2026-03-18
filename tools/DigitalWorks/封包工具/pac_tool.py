#!/usr/bin/env python3
"""
BunBun Engine PAC Archive Tool (保健室～マジカルピュアレッスン♪～)

封包格式：
- 索引存exe内部，每条目12字节: offset(u32) + size(u32) + flags(u16) + id(u16)
- 数据按0x800对齐，可能LZS压缩('LZS\x00'+decomp_size(u32)+LZSS)
- 引擎检查'LZS'头，不是则直接使用raw数据 → 封包时无需压缩

Usage:
  python pac_tool.py list   <exe> <pack_name> [--bin <file>]
  python pac_tool.py unpack <exe> <bin_file> <output_dir> [-d]
  python pac_tool.py pack   <exe> <input_dir> <bin_file>
"""

import struct, sys, os, argparse

PACK_CONFIG = {
    'TAK': (0x44748, 'TAK{:05d}.BIN'),
    'VIS': (0x44F28, 'VIS{:05d}.TMX'),
    'STR': (0x47310, 'STR{:05d}.OGG'),
    '_SE': (0x474F0, '_SE{:05d}.OGG'),
    'VCE': (0x47898, 'VCE{:05d}.OGG'),
}
ALIGNMENT = 0x800


def detect_pack(path):
    name = os.path.basename(path).upper()
    for k in PACK_CONFIG:
        if name == f'{k}.BIN':
            return k
    return None


def read_index(exe, pack):
    off = PACK_CONFIG[pack][0]
    entries = []
    with open(exe, 'rb') as f:
        f.seek(off)
        while True:
            d = f.read(12)
            if len(d) < 12: break
            o, s, fl, eid = struct.unpack('<IIHH', d)
            if eid == 0: break
            entries.append({'id': eid, 'offset': o, 'size': s, 'flags': fl})
    return entries


def write_index(exe, pack, entries, bin_size):
    off = PACK_CONFIG[pack][0]
    with open(exe, 'r+b') as f:
        f.seek(off)
        for e in entries:
            f.write(struct.pack('<IIHH', e['offset'], e['size'], e['flags'], e['id']))
        # 哨兵条目: offset=BIN大小, size=BIN大小, flags=0, id=0
        f.write(struct.pack('<IIHH', bin_size, bin_size, 0, 0))


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
            out.append(b); ring[rp] = b; rp = (rp + 1) & 0xFFF
        else:
            if src + 1 >= end: break
            b1, b2 = data[src], data[src+1]; src += 2
            ro = ((b2 & 0xF0) << 4) | b1; ln = (b2 & 0x0F) + 3
            for _ in range(ln):
                if len(out) >= dsz: break
                b = ring[ro]; out.append(b)
                ring[rp] = b; rp = (rp+1)&0xFFF; ro = (ro+1)&0xFFF
    return bytes(out), True


def cmd_list(args):
    pack = args.pack_name.upper().replace('.BIN', '')
    entries = read_index(args.exe, pack)
    tpl = PACK_CONFIG[pack][1]
    print(f"Pack: {pack}.BIN ({len(entries)} files)")
    print(f"{'ID':>6}  {'Offset':>10}  {'Size':>10}  {'Flags':>5}  Filename")
    print("-" * 60)
    for e in entries:
        print(f"{e['id']:6d}  0x{e['offset']:08X}  0x{e['size']:08X}  {e['flags']:5d}  {tpl.format(e['id'])}")


def cmd_unpack(args):
    pack = detect_pack(args.bin_file)
    if not pack:
        sys.exit(f"Error: Cannot detect pack from: {args.bin_file}")
    entries = read_index(args.exe, pack)
    tpl = PACK_CONFIG[pack][1]
    os.makedirs(args.output_dir, exist_ok=True)
    with open(args.bin_file, 'rb') as f:
        bdata = f.read()
    dc = 0
    for e in entries:
        fd = bdata[e['offset']:e['offset']+e['size']]
        fn = tpl.format(e['id'])
        if args.decompress and fd[:3] == b'LZS':
            fd, ok = lzs_decompress(fd)
            if ok: dc += 1
        with open(os.path.join(args.output_dir, fn), 'wb') as f:
            f.write(fd)
    print(f"Unpacked {len(entries)} files to {args.output_dir}/")
    if args.decompress:
        print(f"  ({dc} LZS decompressed)")


def cmd_pack(args):
    pack = detect_pack(args.bin_file)
    if not pack:
        sys.exit(f"Error: Cannot detect pack from: {args.bin_file}")
    entries = read_index(args.exe, pack)
    tpl = PACK_CONFIG[pack][1]
    out = bytearray(); new_entries = []
    for e in entries:
        fn = tpl.format(e['id'])
        fp = os.path.join(args.input_dir, fn)
        if not os.path.exists(fp):
            print(f"  Warning: Missing {fn}"); continue
        with open(fp, 'rb') as f:
            fd = f.read()
        is_packed = 1 if fd[:3] == b'LZS' else 0
        new_entries.append({'id': e['id'], 'offset': len(out), 'size': len(fd), 'flags': is_packed})
        out.extend(fd)
        pad = (ALIGNMENT - len(out) % ALIGNMENT) % ALIGNMENT
        out.extend(b'\x00' * pad)
    with open(args.bin_file, 'wb') as f:
        f.write(out)
    write_index(args.exe, pack, new_entries, len(out))
    print(f"Packed {len(new_entries)} files -> {args.bin_file} ({len(out)} bytes)")
    print(f"Updated index in {args.exe}")


def main():
    p = argparse.ArgumentParser(description='BunBun Engine PAC Tool')
    sub = p.add_subparsers(dest='cmd')
    s1 = sub.add_parser('list')
    s1.add_argument('exe'); s1.add_argument('pack_name')
    s2 = sub.add_parser('unpack')
    s2.add_argument('exe'); s2.add_argument('bin_file'); s2.add_argument('output_dir')
    s2.add_argument('-d', '--decompress', action='store_true')
    s3 = sub.add_parser('pack')
    s3.add_argument('exe'); s3.add_argument('input_dir'); s3.add_argument('bin_file')
    args = p.parse_args()
    {'list': cmd_list, 'unpack': cmd_unpack, 'pack': cmd_pack}.get(args.cmd, lambda a: p.print_help())(args)

if __name__ == '__main__':
    main()
