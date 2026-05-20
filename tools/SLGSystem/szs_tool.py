"""
szs_tool.py — SZS100__ 封包工具（含 SLG_Crypto 加解密）
  unpack: SZS解包 + XOR(0x90) + SLG_Crypto解密，输出明文文件
  pack:   SLG_Crypto加密 + XOR(0x90) + SZS封包，输出可用的.szs

用法:
  python szs_tool.py unpack  <input.szs> <output_dir> [key_hex]
  python szs_tool.py pack    <input_dir>  <output.szs> [key_hex]
  python szs_tool.py verify  <input.szs> [key_hex]
  python szs_tool.py list    <input.szs>

默认密钥: 0x1291f641（天極姫 ～新世大乱・双界の覇者達～）
"""
import struct, os, sys, hashlib, tempfile

# ── 常量 ─────────────────────────────────────────────────────
XOR_KEY     = 0x90
SIGNATURE   = b'SZS100__'
ENTRY_SIZE  = 272        # 256(name) + 8(offset) + 8(size)
HEADER_BASE = 16         # sig(8) + ver(4) + num(4)
DEFAULT_KEY = 0x1291f641
SKIP_CRYPTO = {'_order.txt'}  # 这些文件不做 SLG_Crypto 处理


# ── SZS 层：XOR 0x90 ─────────────────────────────────────────
def _xor(data):
    return bytes(b ^ XOR_KEY for b in data)


# ── SLG_Crypto 层 ────────────────────────────────────────────
def _next_key(key):
    return ((key * 0x343FD + 0x269EC3) & 0xFFFFFFFF) >> 16 & 0x7FFF


def _crypt(data, init_key):
    """加密与解密完全相同（XOR 对称）。"""
    key = init_key
    out = bytearray(len(data))
    for i, b in enumerate(data):
        key = _next_key(key)
        out[i] = b ^ (key & 0xFF)
    return bytes(out)


# ── SZS 目录解析 ─────────────────────────────────────────────
def _read_index(data):
    if data[:8] != SIGNATURE:
        raise ValueError(f"签名错误: {data[:8]!r}")
    ver = struct.unpack_from('<I', data, 8)[0]
    num = struct.unpack_from('<I', data, 12)[0]
    entries = []
    for i in range(num):
        pos  = HEADER_BASE + i * ENTRY_SIZE
        raw  = data[pos:pos + 256]
        end  = raw.index(0) if 0 in raw else 256
        name = raw[:end].decode('cp932').replace(';', os.sep)
        offset = struct.unpack_from('<Q', data, pos + 256)[0]
        size   = struct.unpack_from('<Q', data, pos + 264)[0]
        entries.append((name, offset, size))
    return ver, entries


# ── 子命令 ───────────────────────────────────────────────────
def cmd_list(path):
    ver, entries = _read_index(open(path, 'rb').read())
    print(f"[list] {path}  ver={ver}  count={len(entries)}")
    for name, offset, size in entries:
        print(f"  {name:<40} {hex(offset):>12}  {size:>10,} B")


def cmd_unpack(szs_path, out_dir, key=DEFAULT_KEY):
    data = open(szs_path, 'rb').read()
    ver, entries = _read_index(data)
    os.makedirs(out_dir, exist_ok=True)

    with open(os.path.join(out_dir, '_order.txt'), 'w', encoding='utf-8') as f:
        f.write(f'version\t{ver}\n')
        for name, _, _ in entries:
            f.write(name + '\n')

    print(f"[unpack] {szs_path} → {out_dir}  ({len(entries)} 文件)  key={hex(key)}")
    for name, offset, size in entries:
        raw     = data[offset:offset + size]
        decoded = _xor(raw)                       # 第一层：XOR 0x90
        if os.path.basename(name) not in SKIP_CRYPTO:
            decoded = _crypt(decoded, key)        # 第二层：SLG_Crypto 解密
        out_path = os.path.join(out_dir, name)
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        open(out_path, 'wb').write(decoded)
        print(f"  {name}  ({size:,} B)")
    print("[unpack] 完成。")


def cmd_pack(in_dir, out_szs, key=DEFAULT_KEY):
    order_path = os.path.join(in_dir, '_order.txt')
    if not os.path.exists(order_path):
        raise FileNotFoundError("找不到 _order.txt，请先用 unpack 生成目录")

    ver, names = 0, []
    for line in open(order_path, encoding='utf-8'):
        line = line.rstrip('\n')
        if line.startswith('#') or not line:
            continue
        if line.startswith('version\t'):
            ver = int(line.split('\t', 1)[1])
        else:
            names.append(line)

    blobs = []
    for rel in names:
        path = os.path.join(in_dir, rel)
        if not os.path.exists(path):
            raise FileNotFoundError(f"缺失: {path}")
        plain = open(path, 'rb').read()
        if os.path.basename(rel) not in SKIP_CRYPTO:
            plain = _crypt(plain, key)            # 第一层：SLG_Crypto 加密
        blobs.append((rel, _xor(plain)))          # 第二层：XOR 0x90

    num = len(blobs)
    out = bytearray(SIGNATURE + struct.pack('<II', ver, num) + bytes(num * ENTRY_SIZE))
    cur = HEADER_BASE + num * ENTRY_SIZE

    print(f"[pack] {in_dir} → {out_szs}  ({num} 文件)  key={hex(key)}")
    for i, (rel, enc) in enumerate(blobs):
        name_b = rel.replace(os.sep, ';').encode('cp932')
        if len(name_b) > 255:
            raise ValueError(f"名称过长: {rel}")
        base = HEADER_BASE + i * ENTRY_SIZE
        out[base:base + len(name_b)] = name_b
        struct.pack_into('<Q', out, base + 256, cur)
        struct.pack_into('<Q', out, base + 264, len(enc))
        out += enc
        cur += len(enc)
        print(f"  {rel}  ({len(enc):,} B)")

    os.makedirs(os.path.dirname(os.path.abspath(out_szs)) or '.', exist_ok=True)
    open(out_szs, 'wb').write(out)
    print(f"[pack] 完成 → {out_szs}  ({len(out):,} B)")


def cmd_verify(szs_path, key=DEFAULT_KEY):
    orig = open(szs_path, 'rb').read()
    with tempfile.TemporaryDirectory() as tmp:
        up  = os.path.join(tmp, 'up')
        rep = os.path.join(tmp, 'r.szs')
        cmd_unpack(szs_path, up, key)
        cmd_pack(up, rep, key)
        new = open(rep, 'rb').read()
    ok  = hashlib.md5(orig).hexdigest() == hashlib.md5(new).hexdigest()
    tag = '✓ bit-perfect' if ok else '✗ 不一致'
    print(f"[verify] {tag}  MD5={hashlib.md5(orig).hexdigest()}")


# ── 入口 ─────────────────────────────────────────────────────
def main():
    if len(sys.argv) < 3:
        print(__doc__); sys.exit(1)
    cmd = sys.argv[1].lower()
    key = int(sys.argv[-1], 16) if len(sys.argv) > 3 and sys.argv[-1].startswith('0x') else DEFAULT_KEY

    if   cmd == 'list':   cmd_list(sys.argv[2])
    elif cmd == 'verify': cmd_verify(sys.argv[2], key)
    elif cmd == 'unpack':
        if len(sys.argv) < 4: sys.exit("用法: unpack <szs> <dir> [key]")
        cmd_unpack(sys.argv[2], sys.argv[3], key)
    elif cmd == 'pack':
        if len(sys.argv) < 4: sys.exit("用法: pack <dir> <szs> [key]")
        cmd_pack(sys.argv[2], sys.argv[3], key)
    else:
        print(f"未知命令: {cmd}"); sys.exit(1)


if __name__ == '__main__':
    main()
