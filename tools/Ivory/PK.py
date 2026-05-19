import os
import struct
import sys
import argparse
import json

def rol32(v, count):
    count &= 0x1F
    return ((v << count) | (v >> (32 - count))) & 0xFFFFFFFF

def generate_keys(seed):
    ctl = [0] * 32
    keys = [0] * 32
    for i in range(32):
        code = 0
        k = seed
        for _ in range(16):
            code = (((k ^ (k >> 1)) << 15) | ((code & 0xFFFF) >> 1)) & 0xFFFFFFFF
            k >>= 2
        keys[i] = seed
        ctl[i] = code & 0xFFFF
        seed = rol32(seed, 1)
    return ctl, keys

def process_data(data, seed, is_encrypt=False):
    ctl, keys = generate_keys(seed)
    ints_count = len(data) // 4
    
    if ints_count == 0:
        return data

    ints = list(struct.unpack(f'<{ints_count}I', data[:ints_count * 4]))

    for i in range(ints_count):
        val = ints[i]
        
        if is_encrypt:
            val ^= keys[i & 0x1F]

        code = ctl[i & 0x1F]
        d = 0
        v3, v2, v1 = 3, 2, 1
        
        for _ in range(16):
            if (code & 1) != 0:
                d |= ((val & v1) << 1) | ((val >> 1) & (v2 >> 1))
            else:
                d |= val & v3
            code >>= 1
            v3 = (v3 << 2) & 0xFFFFFFFF
            v2 = (v2 << 2) & 0xFFFFFFFF
            v1 = (v1 << 2) & 0xFFFFFFFF

        if not is_encrypt:
            d ^= keys[i & 0x1F]

        ints[i] = d

    res = struct.pack(f'<{ints_count}I', *ints)
    return res + data[ints_count * 4:]

def unpack_pk(filepath, outdir):
    with open(filepath, 'rb') as f:
        sig = f.read(4)
        if sig == b'fPK ':
            fmt_long = '<I'
            long_sz = 4
        elif sig == b'fPK2':
            fmt_long = '<Q'
            long_sz = 8
        else:
            raise ValueError(f"Invalid signature: {sig}. Expected 'fPK ' or 'fPK2'.")

        max_offset = struct.unpack(fmt_long, f.read(long_sz))[0]
        sections = {}

        while f.tell() < max_offset:
            sec_start = f.tell()
            id_bytes = f.read(4)
            if not id_bytes:
                break
            
            sec_size = struct.unpack(fmt_long, f.read(long_sz))[0]
            hdr_size = struct.unpack(fmt_long, f.read(long_sz))[0]

            if sec_size < 4 or hdr_size > sec_size:
                raise ValueError(f"Corrupted section {id_bytes}")

            content_pos = sec_start + hdr_size

            if id_bytes == b'cLST':
                f.read(4)
                count = struct.unpack('<i', f.read(4))[0]
                key = struct.unpack('<I', f.read(4))[0]
                
                f.seek(content_pos)
                enc_data = f.read(sec_size - hdr_size)
                sections['cLST'] = {
                    'count': count, 
                    'data': process_data(enc_data, key, is_encrypt=False)
                }
                
            elif id_bytes == b'cNAM':
                f.read(4)
                key = struct.unpack('<I', f.read(4))[0]
                
                f.seek(content_pos)
                enc_data = f.read(sec_size - hdr_size)
                sections['cNAM'] = {
                    'data': process_data(enc_data, key, is_encrypt=False)
                }
                
            elif id_bytes == b'cDAT':
                sections['cDAT'] = {'base_offset': content_pos}

            f.seek(sec_start + sec_size)

    if not all(k in sections for k in ('cLST', 'cNAM', 'cDAT')):
        raise ValueError("Archive is missing essential sections (cLST, cNAM, or cDAT).")

    names_data = sections['cNAM']['data']
    def get_name(offset):
        end = names_data.find(b'\x00', offset)
        if end == -1: end = len(names_data)
        return names_data[offset:end].decode('cp932')

    entries = []
    lst_data = sections['cLST']['data']
    for i in range(sections['cLST']['count']):
        offset = i * (long_sz * 3)
        name_off, file_off, file_size = struct.unpack(
            f'<{fmt_long[1:]}{fmt_long[1:]}{fmt_long[1:]}', 
            lst_data[offset:offset + (long_sz * 3)]
        )
        entries.append({
            'name': get_name(name_off),
            'offset': file_off + sections['cDAT']['base_offset'],
            'size': file_size
        })

    os.makedirs(outdir, exist_ok=True)
    with open(filepath, 'rb') as f:
        for entry in entries:
            outpath = os.path.join(outdir, entry['name'].replace('\\', '/'))
            os.makedirs(os.path.dirname(outpath), exist_ok=True)
            
            f.seek(entry['offset'])
            data = f.read(entry['size'])
            
            with open(outpath, 'wb') as outf:
                outf.write(data)
            print(f"Extracted: {entry['name']}")

    manifest_path = os.path.join(outdir, '_pk_manifest.json')
    manifest = {
        'signature': sig.decode('ascii', errors='replace'),
        'entries': [e['name'] for e in entries],
    }
    with open(manifest_path, 'w', encoding='utf-8') as mf:
        json.dump(manifest, mf, ensure_ascii=False, indent=2)
    print(f"Wrote manifest: {manifest_path}")

def _pack_entries_from_manifest(indir, manifest):
    entries = []
    for name_str in manifest['entries']:
        rel_fs = name_str.replace('/', os.sep).replace('\\', os.sep)
        full_path = os.path.join(indir, rel_fs)
        if not os.path.isfile(full_path):
            raise FileNotFoundError(f"Missing file listed in manifest: {name_str} -> {full_path}")
        entries.append({
            'path': full_path,
            'name_str': name_str,
            'name_bytes': name_str.encode('cp932'),
            'size': os.path.getsize(full_path)
        })
    return entries

def pack_pk(indir, outpath):
    manifest_path = os.path.join(indir, '_pk_manifest.json')
    manifest = None
    if os.path.isfile(manifest_path):
        with open(manifest_path, 'r', encoding='utf-8') as mf:
            manifest = json.load(mf)
        if not isinstance(manifest, dict) or 'entries' not in manifest:
            raise ValueError(f"Invalid manifest format: {manifest_path}")
        entries = _pack_entries_from_manifest(indir, manifest)
    else:
        entries = []
        for root, dirnames, files in os.walk(indir):
            dirnames.sort()
            files.sort()
            for file in files:
                full_path = os.path.join(root, file)
                rel_path = os.path.relpath(full_path, indir)
                if rel_path == '_pk_manifest.json':
                    continue
                
                # PK names are compared bytewise by the game and use '/' separators.
                name_str = rel_path.replace('\\', '/')
                name_bytes = name_str.encode('cp932')
                entries.append({
                    'path': full_path,
                    'name_str': name_str,
                    'name_bytes': name_bytes,
                    'size': os.path.getsize(full_path)
                })
        # Runtime lookup is binary-search-based, so keep cLST/cNAM name order sorted.
        entries.sort(key=lambda e: e['name_bytes'])

    names_buf = bytearray()
    for entry in entries:
        entry['name_off'] = len(names_buf)
        names_buf.extend(entry['name_bytes'] + b'\x00')

    while len(names_buf) % 4 != 0:
        names_buf.append(0)

    lst_buf = bytearray()
    current_file_off = 0
    for entry in entries:
        lst_buf.extend(struct.pack('<III', entry['name_off'], current_file_off, entry['size']))
        current_file_off += entry['size']

    clst_key = 0x00000000
    cnam_key = 0x00000000

    clst_enc = process_data(bytes(lst_buf), clst_key, is_encrypt=True)
    cnam_enc = process_data(bytes(names_buf), cnam_key, is_encrypt=True)

    sig = b'fPK '
    if manifest and manifest.get('signature') == 'fPK2':
        sig = b'fPK2'
    max_offset_v1 = 4 + 4 + (24 + len(clst_enc)) + (20 + len(cnam_enc)) + (12 + current_file_off)
    if max_offset_v1 > 0xFFFFFFFF:
        sig = b'fPK2'

    if sig == b'fPK2':
        fmt_long = '<Q'
        long_sz = 8
    else:
        fmt_long = '<I'
        long_sz = 4

    clst_sec_size = (4 + long_sz + long_sz + 4 + 4 + 4) + len(clst_enc)  # id,size,hdr,unk,count,key + data
    cnam_sec_size = (4 + long_sz + long_sz + 4 + 4) + len(cnam_enc)       # id,size,hdr,unk,key + data
    cdat_sec_size = (4 + long_sz + long_sz) + current_file_off             # id,size,hdr + data
    max_offset = 4 + long_sz + clst_sec_size + cnam_sec_size + cdat_sec_size

    with open(outpath, 'wb') as f:
        f.write(sig)
        f.write(struct.pack(fmt_long, max_offset))

        # cLST Section
        f.write(b'cLST')
        f.write(struct.pack(fmt_long, clst_sec_size))
        f.write(struct.pack(fmt_long, 4 + long_sz + long_sz + 4 + 4 + 4))
        f.write(struct.pack('<I', 1))
        f.write(struct.pack('<i', len(entries)))
        f.write(struct.pack('<I', clst_key))
        f.write(clst_enc)

        # cNAM Section
        f.write(b'cNAM')
        f.write(struct.pack(fmt_long, cnam_sec_size))
        f.write(struct.pack(fmt_long, 4 + long_sz + long_sz + 4 + 4))
        f.write(struct.pack('<I', 0))
        f.write(struct.pack('<I', cnam_key))
        f.write(cnam_enc)

        # cDAT Section
        f.write(b'cDAT')
        f.write(struct.pack(fmt_long, cdat_sec_size))
        f.write(struct.pack(fmt_long, 4 + long_sz + long_sz))

        for entry in entries:
            with open(entry['path'], 'rb') as inf:
                while True:
                    chunk = inf.read(1024 * 1024)
                    if not chunk: 
                        break
                    f.write(chunk)
                    
    print(f"Packed {len(entries)} files into {outpath}")

if __name__ == '__main__':
    if len(sys.argv) < 4:
        print("Usage:")
        print("  Unpack: pk.py -u <archive_base> <output_folder>")
        print("  Pack:   pk.py -p <input_folder> <output_archive>")
        sys.exit(1)

    mode = sys.argv[1].lower()
    target = sys.argv[2]
    output = sys.argv[3]

    if mode in ('unpack', '-u'):
        unpack_pk(target, output)
    elif mode in ('pack', '-p'):
        pack_pk(target, output)
    else:
        print("Invalid mode")
