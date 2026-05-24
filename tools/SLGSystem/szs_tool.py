"""
szs_tool.py — SZS100__ 封包工具（支持 XOR 和减法两种加密模式）

用法:
  python szs_tool.py unpack  <input.szs>  <output_dir>  [key_hex] [--mode xor|sub]
  python szs_tool.py pack    <input_dir>  <output.szs>  [key_hex] [--mode xor|sub]
  python szs_tool.py verify  <input.szs>  [key_hex] [--mode xor|sub]
  python szs_tool.py list    <input.szs>

加密模式:
  xor（默认）: plain = (stored ^ 0x90) ^ ks[i]   天極姫系列
  sub        : plain = (stored ^ 0x90) - ks[i]   三極姫/Sangoku Hime 系列

已知密钥(seed):
  0x1291f641  天極姫 ～新世大乱・双界の覇者達～
  0xe41ef641  天極姫2
  0x7f501e37  三極姫 ～乱世、天下三分の計～ Renewal（--mode sub）
"""
import struct, os, sys, hashlib, tempfile

SIGNATURE   = b'SZS100__'
ENTRY_SIZE  = 272
HEADER_BASE = 16
XOR_KEY     = 0x90
LCG_A       = 0x343FD
LCG_C       = 0x269EC3
DEFAULT_KEY  = 0x1291f641
DEFAULT_MODE = 'xor'


# ── 密钥流生成（两种模式共用同一 LCG） ───────────────────────
def _keystream(length, seed):
    x = seed & 0xFFFFFFFF
    out = bytearray(length)
    for i in range(length):
        x = (x * LCG_A + LCG_C) & 0xFFFFFFFF
        out[i] = (x >> 16) & 0xFF
    return out


# ── 加解密（mode='xor': XOR 对称；mode='sub': 减法/加法） ────
def _decrypt(data, seed, mode):
    ks = _keystream(len(data), seed)
    out = bytearray(len(data))
    for i, b in enumerate(data):
        b2 = b ^ XOR_KEY
        out[i] = (b2 ^ ks[i]) if mode == 'xor' else ((b2 - ks[i]) & 0xFF)
    return bytes(out)


def _encrypt(data, seed, mode):
    ks = _keystream(len(data), seed)
    out = bytearray(len(data))
    for i, b in enumerate(data):
        enc = (b ^ ks[i]) if mode == 'xor' else ((b + ks[i]) & 0xFF)
        out[i] = enc ^ XOR_KEY
    return bytes(out)


# ── SZS 索引 ─────────────────────────────────────────────────
def _read_index(data):
    if data[:8] != SIGNATURE:
        raise ValueError(f"签名错误: {data[:8]!r}")
    ver = struct.unpack_from('<I', data, 8)[0]
    num = struct.unpack_from('<I', data, 12)[0]
    entries = []
    for i in range(num):
        pos    = HEADER_BASE + i * ENTRY_SIZE
        raw    = data[pos:pos + 256]
        end    = raw.index(0) if 0 in raw else 256
        name   = raw[:end].decode('cp932').replace(';', os.sep)
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


def cmd_unpack(szs_path, out_dir, seed, mode):
    data = open(szs_path, 'rb').read()
    ver, entries = _read_index(data)
    os.makedirs(out_dir, exist_ok=True)

    with open(os.path.join(out_dir, '_order.txt'), 'w', encoding='utf-8') as f:
        f.write(f'version\t{ver}\n')
        f.write(f'mode\t{mode}\n')
        for name, _, _ in entries:
            f.write(name + '\n')

    print(f"[unpack] {szs_path} → {out_dir}  ({len(entries)} 文件)  seed={hex(seed)}  mode={mode}")
    for name, offset, size in entries:
        raw      = data[offset:offset + size]
        decoded  = _decrypt(raw, seed, mode)
        out_path = os.path.join(out_dir, name)
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        open(out_path, 'wb').write(decoded)
        print(f"  {name}  ({size:,} B)")
    print("[unpack] 完成。")


def cmd_pack(in_dir, out_szs, seed, mode):
    order_path = os.path.join(in_dir, '_order.txt')
    if not os.path.exists(order_path):
        raise FileNotFoundError("找不到 _order.txt，请先用 unpack 生成目录")

    ver, names, saved_mode = 0, [], None
    for line in open(order_path, encoding='utf-8'):
        line = line.rstrip('\n')
        if not line or line.startswith('#'):
            continue
        if line.startswith('version\t'):
            ver = int(line.split('\t', 1)[1])
        elif line.startswith('mode\t'):
            saved_mode = line.split('\t', 1)[1]
        else:
            names.append(line)

    # _order.txt 里记录的 mode 优先，命令行可覆盖
    effective_mode = mode if mode != DEFAULT_MODE else (saved_mode or mode)

    blobs = []
    for rel in names:
        path = os.path.join(in_dir, rel)
        if not os.path.exists(path):
            raise FileNotFoundError(f"缺失: {path}")
        plain = open(path, 'rb').read()
        blobs.append((rel, _encrypt(plain, seed, effective_mode)))

    num = len(blobs)
    out = bytearray(SIGNATURE + struct.pack('<II', ver, num) + bytes(num * ENTRY_SIZE))
    cur = HEADER_BASE + num * ENTRY_SIZE

    print(f"[pack] {in_dir} → {out_szs}  ({num} 文件)  seed={hex(seed)}  mode={effective_mode}")
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


def cmd_verify(szs_path, seed, mode):
    orig = open(szs_path, 'rb').read()
    with tempfile.TemporaryDirectory() as tmp:
        up  = os.path.join(tmp, 'up')
        rep = os.path.join(tmp, 'r.szs')
        cmd_unpack(szs_path, up, seed, mode)
        cmd_pack(up, rep, seed, mode)
        new = open(rep, 'rb').read()
    ok  = hashlib.md5(orig).hexdigest() == hashlib.md5(new).hexdigest()
    tag = '✓ bit-perfect' if ok else '✗ 不一致'
    print(f"[verify] {tag}  MD5={hashlib.md5(orig).hexdigest()}")


# ── 入口 ─────────────────────────────────────────────────────
def main():
    if len(sys.argv) < 3:
        print(__doc__); sys.exit(1)

    cmd  = sys.argv[1].lower()
    args = sys.argv[2:]

    # 解析 --mode
    mode = DEFAULT_MODE
    if '--mode' in args:
        idx  = args.index('--mode')
        mode = args[idx + 1].lower()
        args = args[:idx] + args[idx + 2:]
    if mode not in ('xor', 'sub'):
        sys.exit(f"未知 mode: {mode}，只支持 xor 或 sub")

    # 解析 seed（最后一个 0x... 参数）
    seed = DEFAULT_KEY
    if args and args[-1].startswith('0x'):
        seed = int(args[-1], 16)
        args = args[:-1]

    if   cmd == 'list':   cmd_list(args[0])
    elif cmd == 'verify': cmd_verify(args[0], seed, mode)
    elif cmd == 'unpack':
        if len(args) < 2: sys.exit("用法: unpack <szs> <dir> [seed] [--mode xor|sub]")
        cmd_unpack(args[0], args[1], seed, mode)
    elif cmd == 'pack':
        if len(args) < 2: sys.exit("用法: pack <dir> <szs> [seed] [--mode xor|sub]")
        cmd_pack(args[0], args[1], seed, mode)
    else:
        print(f"未知命令: {cmd}"); sys.exit(1)


if __name__ == '__main__':
    main()
