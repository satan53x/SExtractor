#!/usr/bin/env python3
"""
csb_inject.py - Frontwing ADV CSB 文本注入
============================================
Engine:  FRONTWING_ADV (SeparateBlue etc.)
Format:  CSB (Compiled Script Binary)

跳转全部基于字符串标签名 → 变长注入安全, node_count 不可变

Usage:
  python csb_inject.py <orig.csb> <trans.json> [output.csb] [--encoding gbk]
  python csb_inject.py <orig_dir> <json_dir> [output_dir] [--encoding gbk]

  --encoding: 注入编码 (默认cp932, 中文汉化用gbk)
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
        nodes.append([ntype, argc, raws])
        pos = p
    return data[:hdr_size], nodes


def build_csb(header, nodes):
    buf = bytearray(header)
    for ntype, argc, raws in nodes:
        buf += struct.pack('<HH', ntype, argc)
        buf += b'\x00' * 4
        for raw in raws:
            buf += struct.pack('<H', len(raw))
            buf += raw
    return bytes(buf)


def dec(raw):
    if raw and raw[-1] == 0:
        return raw[:-1].decode('cp932', errors='replace')
    return raw.decode('cp932', errors='replace')


def enc(text, encoding):
    return text.encode(encoding, errors='replace') + b'\x00'


def inject(csb_path, json_path, out_path, encoding='cp932'):
    with open(csb_path, 'rb') as f:
        data = f.read()
    with open(json_path, 'r', encoding='utf-8') as f:
        trans = json.load(f)

    header, nodes = parse_csb(data)

    by_node = {}
    for t in trans:
        by_node.setdefault(t['node_index'], []).append(t)

    modified = 0
    for i, (ntype, argc, raws) in enumerate(nodes):
        if i not in by_node:
            continue
        for t in by_node[i]:
            new_msg = t.get('message')
            if new_msg is None:
                continue

            if 'select_arg' in t:
                ai = t['select_arg']
                if ai < len(raws):
                    new_raw = enc(new_msg, encoding)
                    if raws[ai] != new_raw:
                        raws[ai] = new_raw
                        modified += 1
            else:
                if ntype == 0x16 and argc == 2 and dec(raws[0]) == '$Msg':
                    new_raw = enc(new_msg, encoding)
                    if raws[1] != new_raw:
                        raws[1] = new_raw
                        modified += 1

                new_name = t.get('name')
                if new_name is not None and not new_name.startswith('$'):
                    for j in range(i - 1, max(i - 8, -1), -1):
                        jt, ja, jr = nodes[j]
                        if jt == 0x16 and ja == 2 and dec(jr[0]) == '$Name':
                            if not dec(jr[1]).startswith('$'):
                                new_raw = enc(new_name, encoding)
                                if jr[1] != new_raw:
                                    jr[1] = new_raw
                                    modified += 1
                            break

    new_data = build_csb(header, nodes)

    orig_nc = struct.unpack_from('<I', data, 8)[0]
    new_nc  = struct.unpack_from('<I', new_data, 8)[0]
    assert orig_nc == new_nc, f"FATAL: node_count changed {orig_nc}→{new_nc}"

    with open(out_path, 'wb') as f:
        f.write(new_data)

    print(f'  {os.path.basename(csb_path)}: {modified} modified ({encoding}), '
          f'{len(data)}→{len(new_data)} ({len(new_data)-len(data):+d}B) → {os.path.basename(out_path)}')
    return modified


def main():
    if len(sys.argv) < 3:
        print("Usage:")
        print("  csb_inject.py <orig.csb> <trans.json> [output.csb] [--encoding gbk]")
        print("  csb_inject.py <orig_dir> <json_dir> [output_dir] [--encoding gbk]")
        sys.exit(1)

    args = sys.argv[1:]
    encoding = 'cp932'
    if '--encoding' in args:
        idx = args.index('--encoding')
        encoding = args[idx + 1]
        args = args[:idx] + args[idx + 2:]

    src = args[0]
    jsn = args[1]

    if os.path.isfile(src):
        out = args[2] if len(args) > 2 else os.path.splitext(src)[0] + '_cn.csb'
        inject(src, jsn, out, encoding)
    elif os.path.isdir(src):
        out_dir = args[2] if len(args) > 2 else src + '_cn'
        os.makedirs(out_dir, exist_ok=True)
        csb_files = sorted(glob.glob(os.path.join(src, '*.csb')))
        total = 0
        skipped = 0
        for cf in csb_files:
            base = os.path.splitext(os.path.basename(cf))[0]
            jf = os.path.join(jsn, base + '.json')
            of = os.path.join(out_dir, os.path.basename(cf))
            if not os.path.exists(jf):
                # 无对应JSON → 原样复制 (dummy等)
                import shutil
                shutil.copy2(cf, of)
                skipped += 1
                continue
            try:
                total += inject(cf, jf, of, encoding)
            except ValueError as e:
                import shutil
                shutil.copy2(cf, of)
                print(f'  {os.path.basename(cf)}: skipped ({e}), copied as-is')
                skipped += 1
        print(f'Done: {total} strings modified, {skipped} files copied as-is')
    else:
        print(f"Not found: {src}")
        sys.exit(1)


if __name__ == '__main__':
    main()
