#!/usr/bin/env python3
"""
csb_extract.py - Frontwing ADV CSB 文本提取
=============================================
Engine:  FRONTWING_ADV (SeparateBlue etc.)
Format:  CSB (Compiled Script Binary), Shift-JIS

Usage:
  python csb_extract.py <input.csb> [output.json]
  python csb_extract.py <input_dir> [output_dir]   # 批量
"""

import struct, json, sys, os, glob


def parse_csb(data):
    magic = struct.unpack_from('<I', data, 0)[0]
    if magic != 0x63736200:
        raise ValueError(f"Not CSB (magic=0x{magic:08X})")
    hdr_size   = struct.unpack_from('<I', data, 4)[0]
    node_count = struct.unpack_from('<I', data, 8)[0]
    pos = hdr_size
    nodes = []
    for _ in range(node_count):
        ntype = struct.unpack_from('<H', data, pos)[0]
        argc  = struct.unpack_from('<H', data, pos + 2)[0]
        p = pos + 8
        raws = []
        for _ in range(argc):
            slen = struct.unpack_from('<H', data, p)[0]
            raws.append(data[p + 2 : p + 2 + slen])
            p += 2 + slen
        nodes.append((ntype, argc, raws))
        pos = p
    return nodes


def dec(raw):
    if raw and raw[-1] == 0:
        return raw[:-1].decode('cp932', errors='replace')
    return raw.decode('cp932', errors='replace')


def extract(csb_path, json_path):
    with open(csb_path, 'rb') as f:
        data = f.read()

    nodes = parse_csb(data)
    entries = []
    msg_id = 0

    for i, (ntype, argc, raws) in enumerate(nodes):
        # SET $Msg
        if ntype == 0x16 and argc == 2 and dec(raws[0]) == '$Msg':
            name = ''
            for j in range(i - 1, max(i - 8, -1), -1):
                jt, ja, jr = nodes[j]
                if jt == 0x16 and ja == 2 and dec(jr[0]) == '$Name':
                    name = dec(jr[1])
                    break
            entries.append({
                'id': msg_id, 'name': name,
                'message': dec(raws[1]), 'node_index': i,
            })
            msg_id += 1

        # CALL system\\DoSelect
        elif ntype == 0x20 and argc >= 2 and dec(raws[0]) == 'system\\\\DoSelect':
            for ci in range(1, argc):
                entries.append({
                    'id': msg_id, 'name': '【选择肢】',
                    'message': dec(raws[ci]),
                    'node_index': i, 'select_arg': ci,
                })
                msg_id += 1

    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(entries, f, ensure_ascii=False, indent=2)

    n_msg = sum(1 for e in entries if 'select_arg' not in e)
    n_sel = sum(1 for e in entries if 'select_arg' in e)
    print(f'  {os.path.basename(csb_path)}: {n_msg} dialogues + {n_sel} choices → {os.path.basename(json_path)}')
    return len(entries)


def main():
    if len(sys.argv) < 2:
        print("Usage:")
        print("  csb_extract.py <input.csb> [output.json]")
        print("  csb_extract.py <input_dir> [output_dir]")
        sys.exit(1)

    src = sys.argv[1]

    if os.path.isfile(src):
        out = sys.argv[2] if len(sys.argv) > 2 else os.path.splitext(src)[0] + '.json'
        extract(src, out)
    elif os.path.isdir(src):
        out_dir = sys.argv[2] if len(sys.argv) > 2 else src + '_json'
        os.makedirs(out_dir, exist_ok=True)
        files = sorted(glob.glob(os.path.join(src, '*.csb')))
        total = 0
        skipped = 0
        for f in files:
            base = os.path.splitext(os.path.basename(f))[0] + '.json'
            try:
                total += extract(f, os.path.join(out_dir, base))
            except ValueError as e:
                print(f'  {os.path.basename(f)}: skipped ({e})')
                skipped += 1
        print(f'Done: {len(files) - skipped} files extracted, {skipped} skipped, {total} entries total')
    else:
        print(f"Not found: {src}")
        sys.exit(1)


if __name__ == '__main__':
    main()
