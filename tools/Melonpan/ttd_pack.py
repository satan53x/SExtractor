# -*- coding: utf-8 -*-
import os
import sys
import struct

# TTD format based on GARbro Melonpan.TtdOpener
# Header:
#   0x00: signature (4 bytes, usually b'WCW\\x00')
#   0x04: count (int32)
#   0x08: unknown (4 bytes)
# Index starts at 0x0C.
# Each record:
#   +0x00 size   (u32)
#   +0x04 offset (u32)
#   +0x08 unk    (u32)
#   +0x0C name[name_len] (fixed length for all entries)


def u32(data, off):
    return struct.unpack_from('<I', data, off)[0]


def p32(x):
    return struct.pack('<I', x & 0xFFFFFFFF)


def lzss_compress(data):
    """
    LZSS compatible with GARbro LzssStream defaults:
    - frame size: 0x1000
    - init pos:   0xFF0
    - max match:  18
    - threshold:  2 (encoded len >= 3)
    Token format:
      literal: flag bit = 1, then 1 byte
      match:   flag bit = 0, then 2 bytes:
               b1 = pos & 0xFF
               b2 = ((pos >> 4) & 0xF0) | (length - 3)
    """
    if not data:
        return b''

    N = 0x1000
    F = 18
    THRESHOLD = 2  # encode match only if len >= 3

    src = bytearray(data)
    out = bytearray()

    frame_pos = 0xFF0
    i = 0
    n = len(src)

    # emit in blocks of 8 tokens
    while i < n:
        flag_pos = len(out)
        out.append(0)  # placeholder
        flags = 0

        for bit in range(8):
            if i >= n:
                break

            # find best match in previous up to 0x1000 bytes
            best_len = 0
            best_dist = 0
            max_dist = min(N, i)
            max_len = min(F, n - i)

            # brute force search
            for dist in range(1, max_dist + 1):
                j = 0
                # compare src[i+j] with src[i-dist+j]
                while j < max_len and src[i + j] == src[i - dist + j]:
                    j += 1
                if j > best_len:
                    best_len = j
                    best_dist = dist
                    if best_len == max_len:
                        break

            if best_len >= (THRESHOLD + 1):
                # match token
                pos = (frame_pos - best_dist) & 0xFFF
                length = best_len
                b1 = pos & 0xFF
                b2 = ((pos >> 4) & 0xF0) | ((length - 3) & 0x0F)
                out.append(b1)
                out.append(b2)

                # advance frame by length bytes (decoded bytes)
                frame_pos = (frame_pos + length) & 0xFFF
                i += length
            else:
                # literal token
                flags |= (1 << bit)  # literal bit = 1
                out.append(src[i])
                frame_pos = (frame_pos + 1) & 0xFFF
                i += 1

        out[flag_pos] = flags

    return bytes(out)


def parse_ttd(ttd_bytes):
    if len(ttd_bytes) < 12:
        raise ValueError("文件太小，不是有效 TTD。")

    sig = ttd_bytes[:4]
    # GARbro signature is 0x574357 ('WCW'), keep 4th byte as-is
    if sig[:3] != b'WCW':
        raise ValueError("签名不是 WCW，可能不是 Melonpan TTD。")

    count = struct.unpack_from('<i', ttd_bytes, 4)[0]
    if count <= 0 or count > 1000000:
        raise ValueError("条目数异常: %d" % count)

    header_unk = ttd_bytes[8:12]
    index_offset = 12

    first_offset = u32(ttd_bytes, index_offset + 4)
    rec_size = (first_offset - index_offset) // count
    name_len = rec_size - 0x0C
    if name_len < 1:
        raise ValueError("名字长度计算异常: %d" % name_len)

    entries = []
    off = index_offset
    for i in range(count):
        if off + 0x0C + name_len > len(ttd_bytes):
            raise ValueError("索引越界 at entry %d" % i)

        size = u32(ttd_bytes, off + 0)
        data_off = u32(ttd_bytes, off + 4)
        unk = u32(ttd_bytes, off + 8)
        name_raw = ttd_bytes[off + 0x0C: off + 0x0C + name_len]
        name = name_raw.split(b'\x00', 1)[0].decode('cp932', 'ignore')

        if data_off + size > len(ttd_bytes):
            raise ValueError("条目数据越界: %s" % name)

        entries.append({
            'name': name,
            'name_raw': name_raw,
            'size': size,
            'offset': data_off,
            'unk': unk,
        })

        off += (0x0C + name_len)

    return {
        'sig': sig,
        'count': count,
        'header_unk': header_unk,
        'name_len': name_len,
        'entries': entries,
    }


def build_replace_map(folder):
    mp = {}
    for fn in os.listdir(folder):
        p = os.path.join(folder, fn)
        if os.path.isfile(p):
            mp[fn.lower()] = p
    return mp


def repack_ttd(src_ttd, replace_dir, out_ttd):
    with open(src_ttd, 'rb') as f:
        src = f.read()

    info = parse_ttd(src)
    entries = info['entries']
    count = info['count']
    name_len = info['name_len']
    replace_map = build_replace_map(replace_dir)

    new_blobs = []
    replaced = 0

    for e in entries:
        old_blob = src[e['offset']: e['offset'] + e['size']]
        rep_path = replace_map.get(e['name'].lower())

        if not rep_path:
            # unchanged: keep original bytes exactly
            new_blob = old_blob
        else:
            with open(rep_path, 'rb') as rf:
                new_raw = rf.read()

            old_packed = (len(old_blob) >= 8 and old_blob[:4] == b'DSFF')

            if old_packed:
                # if user already provided DSFF stream, use as-is
                if len(new_raw) >= 8 and new_raw[:4] == b'DSFF':
                    new_blob = new_raw
                else:
                    comp = lzss_compress(new_raw)
                    new_blob = b'DSFF' + p32(len(new_raw)) + comp
            else:
                new_blob = new_raw

            replaced += 1
            print(u"[替换] %s <- %s (old=%d, new=%d)" %
                  (e['name'], os.path.basename(rep_path), e['size'], len(new_blob)))

        new_blobs.append(new_blob)

    # rebuild archive
    index_size = count * (0x0C + name_len)
    data_start = 12 + index_size

    # recalc offsets/sizes
    cur = data_start
    for i, e in enumerate(entries):
        e['new_offset'] = cur
        e['new_size'] = len(new_blobs[i])
        cur += e['new_size']

    out = bytearray()
    # header
    out += info['sig']                 # keep original 4 bytes
    out += struct.pack('<i', count)    # count
    out += info['header_unk']          # keep original unknown

    # index
    for e in entries:
        out += p32(e['new_size'])
        out += p32(e['new_offset'])
        out += p32(e['unk'])           # preserve unknown field
        # fixed-size name field
        nr = e['name_raw']
        if len(nr) != name_len:
            nr = nr[:name_len].ljust(name_len, b'\x00')
        out += nr

    # data
    for b in new_blobs:
        out += b

    with open(out_ttd, 'wb') as f:
        f.write(out)

    print(u"\n完成: %s" % out_ttd)
    print(u"总条目: %d, 替换: %d" % (count, replaced))


def main():
    if len(sys.argv) != 4:
        print(u"用法: python 2.py 原文件.ttd 需要封包回去的文件夹 out.ttd")
        return 1

    src_ttd = sys.argv[1]
    replace_dir = sys.argv[2]
    out_ttd = sys.argv[3]

    if not os.path.isfile(src_ttd):
        print(u"错误: 原文件不存在: %s" % src_ttd)
        return 1
    if not os.path.isdir(replace_dir):
        print(u"错误: 文件夹不存在: %s" % replace_dir)
        return 1

    try:
        repack_ttd(src_ttd, replace_dir, out_ttd)
    except Exception as e:
        print(u"失败: %s" % e)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
