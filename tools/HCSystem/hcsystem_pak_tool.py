"""
hcsystem PAK 解封包工具
用法:
  python hcsystem_pak_tool.py unpack <pak> [输出目录]
  python hcsystem_pak_tool.py pack   <输入目录> <输出pak>
  python hcsystem_pak_tool.py list   <pak>
  python hcsystem_pak_tool.py verify <pak> [工作目录]
"""
import sys, os, struct, hashlib, shutil, tempfile

SIGNATURE  = b'PACK'
ENTRY_SIZE = 0x4C
NAME_SIZE  = 0x40

def crypt_index(data):
    for i in range(len(data)):
        b = data[i]
        data[i] = ((b << 4) | (b >> 4)) & 0xFF

def lzss_decompress(data, size):
    frame = bytearray(b' ' * 4096)
    fp, out, i = 0xFEE, bytearray(), 0
    while i < len(data) and len(out) < size:
        ctrl = data[i]; i += 1
        for bit in range(8):
            if len(out) >= size or i >= len(data): break
            if ctrl & (1 << bit):
                b = data[i]; i += 1
                out.append(b); frame[fp] = b; fp = (fp+1) & 0xFFF
            else:
                if i+1 >= len(data): break
                lo, hi = data[i], data[i+1]; i += 2
                mp, ml = lo | ((hi & 0xF0) << 4), (hi & 0x0F) + 3
                for _ in range(ml):
                    if len(out) >= size: break
                    c = frame[mp & 0xFFF]
                    out.append(c); frame[fp] = c; fp = (fp+1) & 0xFFF; mp += 1
    return bytes(out)

def read_index(data):
    if data[:4] != SIGNATURE:
        raise ValueError('不是PACK文件')
    count = struct.unpack_from('<I', data, 4)[0]
    is_enc = data[8] == 1
    idx = bytearray(data[0xC : 0xC + ENTRY_SIZE * count])
    if is_enc:
        crypt_index(idx)
    entries, pos = [], 0
    for _ in range(count):
        nb = idx[pos:pos+NAME_SIZE]
        nl = next((j for j in range(0, NAME_SIZE, 2) if nb[j]==0 and nb[j+1]==0), NAME_SIZE)
        name = nb[:nl].decode('utf-16-le', errors='replace')
        pos += NAME_SIZE
        u, p, o = struct.unpack_from('<III', idx, pos); pos += 0xC
        entries.append({'name': name, 'unpacked_size': u, 'packed_size': p,
                        'offset': o, 'is_packed': p != 0, 'actual_size': p or u})
    return entries, is_enc

def build_index(entries, is_enc):
    buf = bytearray()
    for e in entries:
        enc = e['name'].encode('utf-16-le')[:NAME_SIZE]
        buf += enc + b'\x00' * (NAME_SIZE - len(enc))
        buf += struct.pack('<III', e['unpacked_size'], e['packed_size'], e['offset'])
    if is_enc:
        crypt_index(buf)
    return bytes(buf)

def cmd_list(pak):
    data = open(pak,'rb').read()
    entries, is_enc = read_index(data)
    print(f'[信息] 文件数={len(entries)}, 索引加密={is_enc}')
    print(f'{"序号":>4}  {"文件名":<32}  {"原始大小":>10}  {"压缩大小":>10}  {"偏移":>12}  LZSS')
    for i, e in enumerate(entries):
        print(f'{i:4d}  {e["name"]:<32}  {e["unpacked_size"]:>10}  {e["packed_size"]:>10}  {e["offset"]:#012x}  {"是" if e["is_packed"] else "否"}')

def cmd_unpack(pak, out_dir):
    data = open(pak,'rb').read()
    entries, _ = read_index(data)
    os.makedirs(out_dir, exist_ok=True)
    order = ['# hcsystem PAK文件顺序\n']
    for i, e in enumerate(entries):
        raw = data[e['offset']:e['offset']+e['actual_size']]
        try:
            fd = lzss_decompress(raw, e['unpacked_size']) if e['is_packed'] else raw
            if e['is_packed'] and len(fd) != e['unpacked_size']:
                print(f'[警告] {e["name"]}: 解压大小不符')
        except Exception as ex:
            print(f'[错误] {e["name"]}: 解压失败({ex})，保存原始数据')
            fd = raw
        open(os.path.join(out_dir, e['name']), 'wb').write(fd)
        order.append(f'{i}\t{e["name"]}\n')
        print(f'[解包] [{i:3d}] {e["name"]}  ({e["actual_size"]} -> {len(fd)} 字节)')
    open(os.path.join(out_dir, '_order.txt'), 'w', encoding='utf-8').writelines(order)
    print(f'[完成] 解包 {len(entries)} 个文件 → {out_dir}')

def cmd_pack(in_dir, out_pak):
    order_path = os.path.join(in_dir, '_order.txt')
    if not os.path.exists(order_path):
        print(f'[错误] 找不到 {order_path}'); sys.exit(1)
    names = [l.split('\t',1)[1].strip() for l in open(order_path,encoding='utf-8')
             if l.strip() and not l.startswith('#') and '\t' in l]
    data_start = 0xC + ENTRY_SIZE * len(names)
    entries, blobs, cur = [], [], data_start
    for name in names:
        fp = os.path.join(in_dir, name)
        if not os.path.exists(fp):
            print(f'[错误] 文件不存在: {fp}'); sys.exit(1)
        raw = open(fp,'rb').read()
        entries.append({'name': name, 'unpacked_size': len(raw), 'packed_size': 0,
                        'offset': cur, 'is_packed': False, 'actual_size': len(raw)})
        blobs.append(raw); cur += len(raw)
        print(f'[封包] {name}  ({len(raw)} 字节)')
    with open(out_pak,'wb') as f:
        f.write(SIGNATURE + struct.pack('<I', len(names)) + bytes([1,0,0,0]))
        f.write(build_index(entries, True))
        for b in blobs: f.write(b)
    print(f'[完成] 封包 {len(names)} 个文件 → {out_pak}')

def cmd_verify(pak, work_dir=None):
    cleanup = work_dir is None
    if cleanup:
        work_dir = tempfile.mkdtemp(prefix='hcpak_verify_')
    unpack_dir  = os.path.join(work_dir, 'unpack')
    repack_path = os.path.join(work_dir, 'repack.pak')
    print(f'[验证] 解包 → {unpack_dir}')
    cmd_unpack(pak, unpack_dir)
    print(f'\n[验证] 封包 → {repack_path}')
    cmd_pack(unpack_dir, repack_path)
    print('\n[验证] 逐文件内容对比...')
    orig_data = open(pak,'rb').read()
    new_data  = open(repack_path,'rb').read()
    oe_list, _ = read_index(orig_data)
    ne_list, _ = read_index(new_data)
    all_ok = True
    for oe, ne in zip(oe_list, ne_list):
        raw  = orig_data[oe['offset']:oe['offset']+oe['actual_size']]
        orig = lzss_decompress(raw, oe['unpacked_size']) if oe['is_packed'] else raw
        new  = new_data[ne['offset']:ne['offset']+ne['actual_size']]
        ok   = hashlib.md5(orig).digest() == hashlib.md5(new).digest()
        if not ok: all_ok = False
        print(f'  [{"OK" if ok else "FAIL"}] {oe["name"]}')
    if cleanup:
        shutil.rmtree(work_dir, ignore_errors=True)
    print('\n[验证通过] 所有文件内容一致 ✓' if all_ok else '\n[验证失败] 存在不一致文件')

def main():
    if len(sys.argv) < 3:
        print(__doc__); sys.exit(1)
    cmd = sys.argv[1].lower()
    if   cmd == 'list':   cmd_list(sys.argv[2])
    elif cmd == 'unpack': cmd_unpack(sys.argv[2], sys.argv[3] if len(sys.argv)>3 else os.path.splitext(sys.argv[2])[0])
    elif cmd == 'pack':
        if len(sys.argv) < 4: print('[错误] pack 需要 <输入目录> <输出pak>'); sys.exit(1)
        cmd_pack(sys.argv[2], sys.argv[3])
    elif cmd == 'verify': cmd_verify(sys.argv[2], sys.argv[3] if len(sys.argv)>3 else None)
    else: print(f'[错误] 未知命令: {cmd}'); print(__doc__); sys.exit(1)

if __name__ == '__main__':
    main()
