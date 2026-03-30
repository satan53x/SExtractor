#!/usr/bin/env python3
"""
pak_tool.py - Frontwing ADV Engine PAK Archive Tool
=====================================================
Engine:  FRONTWING_ADV (SeparateBlue / セパレイトブルー)
Format:  PAK ("vav\\0" magic, version 200/201)

PAK Structure
─────────────
  Header (0x20 = 32 bytes):
    +0x00  4B   magic        "vav\\0"
    +0x04  4B   version      200 or 201 (0xC9)
    +0x08  4B   entry_count
    +0x0C  4B   entries_off  (usually 0x20)
    +0x10  16B  reserved     (zeros)

  Entry (0x38 = 56 bytes × entry_count):
    +0x00  32B  filename     (ASCII, \\0 padded)
    +0x20  4B   comp_size    (= orig_size if uncompressed)
    +0x24  4B   orig_size
    +0x28  4B   data_offset  (absolute)
    +0x2C  4B   flags        (encryption/compression mode)
    +0x30  8B   reserved     (zeros)

  Data: concatenated file data starting after index

  Flags decoding (for reading):
    bit7 (0x80): Huffman decompress
    bit4 (0x10): RLE decompress
    low4 (0x0F): XOR post-process
      0 = XOR 0x55 every byte
      1,2,3,5,... = XOR differential (stride = flags & 0xF)
      4 = XOR chain (uint32 level)

  Pack mode uses flags=0x00 (no compression, XOR 0x55 encryption).

Usage:
  python pak_tool.py unpack <input.pak> [output_dir]
  python pak_tool.py pack   <input_dir> <output.pak> [--order original.pak]
"""

import struct, sys, os, glob


# ─────────────────────────── Decryption ──────────────────────────────────────

def decrypt_xor55(data):
    """flags low4 == 0: every byte XOR 0x55"""
    return bytes([b ^ 0x55 for b in data])


def decrypt_xor_stride(data, stride):
    """flags low4 == 1,2,3,5,...: XOR differential with given stride"""
    out = bytearray(data)
    for i in range(stride, len(out)):
        out[i] ^= out[i - stride]
    return bytes(out)


def decrypt_xor_chain4(data):
    """flags low4 == 4: XOR chain at uint32 level then byte level"""
    out = bytearray(data)
    # uint32 level chain
    for i in range(8, len(out) - 3, 4):
        v = struct.unpack_from('<I', out, i)[0]
        p = struct.unpack_from('<I', out, i - 4)[0]
        struct.pack_into('<I', out, i, v ^ p)
    # byte level chain for remaining
    for i in range(max(8, (len(out) // 4) * 4), len(out)):
        out[i] ^= out[i - 1]
    return bytes(out)


def decrypt_entry(data, flags):
    """Apply post-processing decryption based on flags low 4 bits."""
    low4 = flags & 0x0F
    if low4 == 0:
        return decrypt_xor55(data)
    elif low4 == 4:
        return decrypt_xor_chain4(data)
    else:
        return decrypt_xor_stride(data, low4)


def encrypt_xor55(data):
    """Encrypt for flags=0x00: every byte XOR 0x55 (same as decrypt)"""
    return bytes([b ^ 0x55 for b in data])


# ─────────────────────────── Unpack ──────────────────────────────────────────

def cmd_unpack(pak_path, out_dir):
    with open(pak_path, 'rb') as f:
        pak = f.read()

    # Parse header
    magic = pak[0:4]
    if magic != b'vav\x00':
        raise ValueError(f"Not a PAK file (magic={magic})")

    version = struct.unpack_from('<I', pak, 4)[0]
    entry_count = struct.unpack_from('<I', pak, 8)[0]
    entries_off = struct.unpack_from('<I', pak, 0xC)[0]

    print(f'PAK: version={version} entries={entry_count}')

    os.makedirs(out_dir, exist_ok=True)

    skipped = 0
    for i in range(entry_count):
        eoff = entries_off + i * 0x38
        name = pak[eoff:eoff + 0x20].split(b'\x00')[0].decode('ascii', errors='replace')
        comp_size = struct.unpack_from('<I', pak, eoff + 0x20)[0]
        orig_size = struct.unpack_from('<I', pak, eoff + 0x24)[0]
        data_off = struct.unpack_from('<I', pak, eoff + 0x28)[0]
        flags = struct.unpack_from('<I', pak, eoff + 0x2C)[0]

        raw = pak[data_off:data_off + comp_size]

        if flags & 0x80:
            # Huffman compressed — cannot decompress in Python (non-standard tree)
            # Skip and warn
            print(f'  [{i:3d}] {name:24s} SKIP (flags=0x{flags:02X}, Huffman compressed)')
            skipped += 1
            continue

        # No Huffman — check RLE
        if flags & 0x10:
            raw = rle_decompress(raw, orig_size)

        # If (flags & 0xF0) == 0, it's a plain copy (already done)
        # Apply XOR post-processing
        result = decrypt_entry(raw, flags)

        out_path = os.path.join(out_dir, name)
        with open(out_path, 'wb') as f:
            f.write(result)

        print(f'  [{i:3d}] {name:24s} {len(result):8d}B flags=0x{flags:02X}')

    if skipped > 0:
        print(f'\nWarning: {skipped} compressed files skipped (use GARbro to unpack those)')
    print(f'Done: {entry_count - skipped}/{entry_count} files extracted to {out_dir}/')


def rle_decompress(src, orig_size):
    """FUN_00402070: RLE decompress"""
    out = bytearray()
    si = 0
    while si < len(src) and len(out) < orig_size:
        b = src[si]
        if (b & 0x80) == 0:
            count = b
            si += 1
            for _ in range(count):
                if si >= len(src) or len(out) >= orig_size:
                    break
                out.append(src[si])
                si += 1
        else:
            count = b & 0x7F
            si += 1
            if si >= len(src):
                break
            val = src[si]
            si += 1
            for _ in range(count):
                if len(out) >= orig_size:
                    break
                out.append(val)
    return bytes(out)


# ─────────────────────────── Pack ────────────────────────────────────────────

def cmd_pack(input_dir, pak_path, order_pak=None):
    """Pack directory into PAK with flags=0x00 (XOR 0x55, no compression)."""

    version = 200  # default: version 200 (more compatible, does lowercase conversion)

    # Determine file order
    if order_pak and os.path.isfile(order_pak):
        file_list, version = get_order_from_pak(order_pak)
        print(f'Using file order from {os.path.basename(order_pak)} ({len(file_list)} entries, version={version})')
    else:
        file_list = sorted([
            f for f in os.listdir(input_dir)
            if os.path.isfile(os.path.join(input_dir, f))
        ])
        print(f'Using alphabetical order ({len(file_list)} files, version={version})')

    # Build case-insensitive lookup for input_dir files
    dir_files = {}
    for f in os.listdir(input_dir):
        if os.path.isfile(os.path.join(input_dir, f)):
            dir_files[f.lower()] = f  # lowercase key → actual filename

    # Match order list to actual files (case-insensitive)
    existing = []
    missing = []
    for name in file_list:
        actual = dir_files.get(name.lower())
        if actual:
            existing.append((name, actual))  # (pak_name, disk_name)
        else:
            missing.append(name)

    if missing:
        print(f'Warning: {len(missing)} files from order not found in input dir, they will be skipped')

    entry_count = len(existing)
    entries_off = 0x20
    data_start = entries_off + entry_count * 0x38

    # Build entries and data
    entries = []
    data_parts = []
    current_offset = data_start

    for pak_name, disk_name in existing:
        path = os.path.join(input_dir, disk_name)
        with open(path, 'rb') as f:
            orig_data = f.read()

        # Encrypt: XOR 0x55
        enc_data = encrypt_xor55(orig_data)
        orig_size = len(orig_data)
        comp_size = len(enc_data)  # same, no compression

        entries.append({
            'name': pak_name,  # preserve original case from pak
            'comp_size': comp_size,
            'orig_size': orig_size,
            'data_offset': current_offset,
            'flags': 0x00,  # XOR 0x55, no compression
        })

        data_parts.append(enc_data)
        current_offset += comp_size

    # Write PAK
    buf = bytearray()

    # Header (0x20)
    buf += b'vav\x00'
    buf += struct.pack('<I', version)  # preserve original version
    buf += struct.pack('<I', entry_count)
    buf += struct.pack('<I', entries_off)
    buf += b'\x00' * 16  # reserved

    # Entry table
    for e in entries:
        name_bytes = e['name'].encode('ascii')
        name_padded = name_bytes + b'\x00' * (32 - len(name_bytes))
        buf += name_padded[:32]
        buf += struct.pack('<I', e['comp_size'])
        buf += struct.pack('<I', e['orig_size'])
        buf += struct.pack('<I', e['data_offset'])
        buf += struct.pack('<I', e['flags'])
        buf += b'\x00' * 8  # reserved

    # Data
    for part in data_parts:
        buf += part

    with open(pak_path, 'wb') as f:
        f.write(buf)

    print(f'Packed {entry_count} files → {pak_path} ({len(buf)} bytes)')


def get_order_from_pak(pak_path):
    """Extract file order and version from an existing PAK."""
    with open(pak_path, 'rb') as f:
        data = f.read()

    if data[0:4] != b'vav\x00':
        raise ValueError("Not a valid PAK file for ordering")

    version = struct.unpack_from('<I', data, 4)[0]
    entry_count = struct.unpack_from('<I', data, 8)[0]
    entries_off = struct.unpack_from('<I', data, 0xC)[0]

    names = []
    for i in range(entry_count):
        eoff = entries_off + i * 0x38
        name = data[eoff:eoff + 0x20].split(b'\x00')[0].decode('ascii', errors='replace')
        names.append(name)
    return names, version


# ─────────────────────────── Main ────────────────────────────────────────────

def main():
    if len(sys.argv) < 3:
        print("Usage:")
        print("  pak_tool.py unpack <input.pak> [output_dir]")
        print("  pak_tool.py pack   <input_dir> <output.pak> [--order original.pak]")
        sys.exit(1)

    cmd = sys.argv[1].lower()

    if cmd == 'unpack':
        pak = sys.argv[2]
        out = sys.argv[3] if len(sys.argv) > 3 else os.path.splitext(pak)[0] + '_unpacked'
        cmd_unpack(pak, out)

    elif cmd == 'pack':
        if len(sys.argv) < 4:
            print("Usage: pak_tool.py pack <input_dir> <output.pak> [--order original.pak]")
            sys.exit(1)
        input_dir = sys.argv[2]
        pak_path = sys.argv[3]

        order_pak = None
        if '--order' in sys.argv:
            idx = sys.argv.index('--order')
            if idx + 1 < len(sys.argv):
                order_pak = sys.argv[idx + 1]

        cmd_pack(input_dir, pak_path, order_pak)

    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)


if __name__ == '__main__':
    main()
