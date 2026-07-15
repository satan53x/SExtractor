#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
malie_exec_crypt.py  —  Malie 引擎 EXEC 脚本「解密/解压 · 压缩/加密」工具
=========================================================================
处理游戏脚本 EXEC 的两层封装（逆向自 malie.exe / タペストリー）：

    EXEC  =  Camellia-128-ECB( zlib( 脚本字节码 ) )

  · 加密：Camellia-128，ECB 模式，逐 16 字节块独立加解密，无 IV / 无链接 /
    无块号混入；EXEC 总长必为 16 的整数倍，从第 0 字节起即密文，无文件头。
  · 密钥：ASCII 字符串（本作 タペストリー = "u3jY9KhVONGmXSI5"，16 字节 = 128bit，
    取自 malie.exe 中 sub_42DA40 的调用实参）。可用 --key 覆盖。
  · 压缩：标准 zlib（deflate），原作用默认参数（level 6），本工具据此可 bit-exact 还原。
  · 编码：解压得到的字节码里字符串为 **UTF-16LE**（非 Shift-JIS）。

子命令
------
  decrypt <EXEC> [out.bin]      EXEC → Camellia解密 → zlib解压 → 明文字节码
  encrypt <明文.bin> [out]      明文字节码 → zlib压缩 → 补齐 → Camellia加密 → EXEC
  verify  <EXEC>                decrypt→encrypt 回环，逐字节比对（level6 应 bit-perfect）
  info    <EXEC>                显示两层结构信息（密文/压缩流/明文大小、编码判断）
  selftest                      用 RFC 3713 官方向量自检 Camellia 实现

参数
----
  --key <字符串>                覆盖默认密钥（ASCII，长度须 16/24/32）
  --level <0-9>                 zlib 压缩级别（默认 6，与原作一致以便 bit-exact）
  --raw                         decrypt 只解密不解压 / encrypt 只加密不压缩（调试用）

拖放
----
  把文件拖到本脚本图标上会自动判断方向：能按 EXEC 解出 zlib → 执行 decrypt；
  否则当作明文字节码 → 执行 encrypt。

纯 Python 标准库，自包含（内嵌 Camellia S 盒，无需 malie.exe 在场）。
"""

import sys, os, struct, zlib

DEFAULT_KEY = b"u3jY9KhVONGmXSI5"

# ============================================================
#  Camellia-128/192/256（RFC 3713）——S 盒取自标准 Camellia
# ============================================================
SBOX1 = bytes([112,130,44,236,179,39,192,229,228,133,87,53,234,12,174,65,35,239,107,147,69,25,165,33,237,14,79,78,29,101,146,189,134,184,175,143,124,235,31,206,62,48,220,95,94,197,11,26,166,225,57,202,213,71,93,61,217,1,90,214,81,86,108,77,139,13,154,102,251,204,176,45,116,18,43,32,240,177,132,153,223,76,203,194,52,126,118,5,109,183,169,49,209,23,4,215,20,88,58,97,222,27,17,28,50,15,156,22,83,24,242,34,254,68,207,178,195,181,122,145,36,8,232,168,96,252,105,80,170,208,160,125,161,137,98,151,84,91,30,149,224,255,100,210,16,196,0,72,163,247,117,219,138,3,230,218,9,63,221,148,135,92,131,2,205,74,144,51,115,103,246,243,157,127,191,226,82,155,216,38,200,55,198,59,129,150,111,75,19,190,99,46,233,121,167,140,159,110,188,142,41,245,249,182,47,253,180,89,120,152,6,106,231,70,113,186,212,37,171,66,136,162,141,250,114,7,185,85,248,238,172,10,54,73,42,104,60,56,241,164,64,40,211,123,187,201,67,193,21,227,173,244,119,199,128,158])
SBOX2 = bytes(((v << 1) | (v >> 7)) & 0xFF for v in SBOX1)
SBOX3 = bytes(((v >> 1) | (v << 7)) & 0xFF for v in SBOX1)
SBOX4 = bytes(SBOX1[((x << 1) | (x >> 7)) & 0xFF] for x in range(256))

MASK64 = (1 << 64) - 1
MASK128 = (1 << 128) - 1
_S1, _S2, _S3, _S4, _S5, _S6 = (0xA09E667F3BCC908B, 0xB67AE8584CAA73B2,
    0xC6EF372FE94F82BE, 0x54FF53A5F1D36F1C, 0x10E527FADE682D1D, 0xB05688C2B3E6C1FD)


def _rol(x, n, bits):
    x &= (1 << bits) - 1
    return ((x << n) | (x >> (bits - n))) & ((1 << bits) - 1)


def _F(x, k):
    x ^= k
    t0 = SBOX1[(x >> 56) & 0xFF]; t1 = SBOX2[(x >> 48) & 0xFF]
    t2 = SBOX3[(x >> 40) & 0xFF]; t3 = SBOX4[(x >> 32) & 0xFF]
    t4 = SBOX2[(x >> 24) & 0xFF]; t5 = SBOX3[(x >> 16) & 0xFF]
    t6 = SBOX4[(x >> 8) & 0xFF];  t7 = SBOX1[x & 0xFF]
    y1 = t0 ^ t2 ^ t3 ^ t5 ^ t6 ^ t7
    y2 = t0 ^ t1 ^ t3 ^ t4 ^ t6 ^ t7
    y3 = t0 ^ t1 ^ t2 ^ t4 ^ t5 ^ t7
    y4 = t1 ^ t2 ^ t3 ^ t4 ^ t5 ^ t6
    y5 = t0 ^ t1 ^ t5 ^ t6 ^ t7
    y6 = t1 ^ t2 ^ t4 ^ t6 ^ t7
    y7 = t2 ^ t3 ^ t4 ^ t5 ^ t7
    y8 = t0 ^ t3 ^ t4 ^ t5 ^ t6
    return (y1 << 56) | (y2 << 48) | (y3 << 40) | (y4 << 32) | (y5 << 24) | (y6 << 16) | (y7 << 8) | y8


def _FL(x, k):
    x1 = x >> 32; x2 = x & 0xFFFFFFFF
    k1 = k >> 32; k2 = k & 0xFFFFFFFF
    x2 ^= _rol(x1 & k1, 1, 32)
    x1 ^= (x2 | k2)
    return ((x1 << 32) | x2) & MASK64


def _FLINV(y, k):
    y1 = y >> 32; y2 = y & 0xFFFFFFFF
    k1 = k >> 32; k2 = k & 0xFFFFFFFF
    y1 ^= (y2 | k2)
    y2 ^= _rol(y1 & k1, 1, 32)
    return ((y1 << 32) | y2) & MASK64


def key_schedule(key_bytes):
    """支持 16/24/32 字节密钥；返回子密钥字典。"""
    n = len(key_bytes)
    if n not in (16, 24, 32):
        raise ValueError("密钥长度须为 16/24/32 字节，当前 %d" % n)
    if n == 16:
        KL = int.from_bytes(key_bytes, "big"); KR = 0
    elif n == 24:
        KL = int.from_bytes(key_bytes[:16], "big")
        kr = int.from_bytes(key_bytes[16:24], "big")
        KR = (kr << 64) | (kr ^ MASK64)
    else:
        KL = int.from_bytes(key_bytes[:16], "big")
        KR = int.from_bytes(key_bytes[16:32], "big")
    D1 = (KL ^ KR) >> 64; D2 = (KL ^ KR) & MASK64
    D2 ^= _F(D1, _S1); D1 ^= _F(D2, _S2)
    D1 ^= (KL >> 64);   D2 ^= (KL & MASK64)
    D2 ^= _F(D1, _S3);  D1 ^= _F(D2, _S4)
    KA = ((D1 << 64) | D2) & MASK128
    hi = lambda v: (v >> 64) & MASK64
    lo = lambda v: v & MASK64
    s = {}
    if n == 16:
        s['kw1'] = hi(_rol(KL, 0, 128));   s['kw2'] = lo(_rol(KL, 0, 128))
        s['k1']  = hi(_rol(KA, 0, 128));   s['k2']  = lo(_rol(KA, 0, 128))
        s['k3']  = hi(_rol(KL, 15, 128));  s['k4']  = lo(_rol(KL, 15, 128))
        s['k5']  = hi(_rol(KA, 15, 128));  s['k6']  = lo(_rol(KA, 15, 128))
        s['ke1'] = hi(_rol(KA, 30, 128));  s['ke2'] = lo(_rol(KA, 30, 128))
        s['k7']  = hi(_rol(KL, 45, 128));  s['k8']  = lo(_rol(KL, 45, 128))
        s['k9']  = hi(_rol(KA, 45, 128));  s['k10'] = lo(_rol(KL, 60, 128))
        s['k11'] = hi(_rol(KA, 60, 128));  s['k12'] = lo(_rol(KA, 60, 128))
        s['ke3'] = hi(_rol(KL, 77, 128));  s['ke4'] = lo(_rol(KL, 77, 128))
        s['k13'] = hi(_rol(KL, 94, 128));  s['k14'] = lo(_rol(KL, 94, 128))
        s['k15'] = hi(_rol(KA, 94, 128));  s['k16'] = lo(_rol(KA, 94, 128))
        s['k17'] = hi(_rol(KL, 111, 128)); s['k18'] = lo(_rol(KL, 111, 128))
        s['kw3'] = hi(_rol(KA, 111, 128)); s['kw4'] = lo(_rol(KA, 111, 128))
        s['_n18'] = True
    else:
        # 192/256（24 轮）——此处从简，本项目用不到；如需可补全
        raise ValueError("本工具仅需 128 位密钥；192/256 未启用")
    return s


def _crypt128(M, s, decrypt):
    if not decrypt:
        kw1, kw2, kw3, kw4 = s['kw1'], s['kw2'], s['kw3'], s['kw4']
        ks = [s['k1'], s['k2'], s['k3'], s['k4'], s['k5'], s['k6'], s['ke1'], s['ke2'],
              s['k7'], s['k8'], s['k9'], s['k10'], s['k11'], s['k12'], s['ke3'], s['ke4'],
              s['k13'], s['k14'], s['k15'], s['k16'], s['k17'], s['k18']]
    else:
        kw1, kw2, kw3, kw4 = s['kw3'], s['kw4'], s['kw1'], s['kw2']
        ks = [s['k18'], s['k17'], s['k16'], s['k15'], s['k14'], s['k13'], s['ke4'], s['ke3'],
              s['k12'], s['k11'], s['k10'], s['k9'], s['k8'], s['k7'], s['ke2'], s['ke1'],
              s['k6'], s['k5'], s['k4'], s['k3'], s['k2'], s['k1']]
    D1 = M >> 64; D2 = M & MASK64
    D1 ^= kw1; D2 ^= kw2
    D2 ^= _F(D1, ks[0]);  D1 ^= _F(D2, ks[1]);  D2 ^= _F(D1, ks[2])
    D1 ^= _F(D2, ks[3]);  D2 ^= _F(D1, ks[4]);  D1 ^= _F(D2, ks[5])
    D1 = _FL(D1, ks[6]);  D2 = _FLINV(D2, ks[7])
    D2 ^= _F(D1, ks[8]);  D1 ^= _F(D2, ks[9]);  D2 ^= _F(D1, ks[10])
    D1 ^= _F(D2, ks[11]); D2 ^= _F(D1, ks[12]); D1 ^= _F(D2, ks[13])
    D1 = _FL(D1, ks[14]); D2 = _FLINV(D2, ks[15])
    D2 ^= _F(D1, ks[16]); D1 ^= _F(D2, ks[17]); D2 ^= _F(D1, ks[18])
    D1 ^= _F(D2, ks[19]); D2 ^= _F(D1, ks[20]); D1 ^= _F(D2, ks[21])
    D2 ^= kw3; D1 ^= kw4
    return ((D2 << 64) | D1) & MASK128


def camellia_ecb(data, key_bytes, decrypt):
    if len(data) % 16 != 0:
        raise ValueError("ECB 数据长度须为 16 的整数倍（当前 %d）" % len(data))
    s = key_schedule(key_bytes)
    out = bytearray(len(data))
    for i in range(0, len(data), 16):
        M = int.from_bytes(data[i:i + 16], "big")
        C = _crypt128(M, s, decrypt)
        out[i:i + 16] = C.to_bytes(16, "big")
    return bytes(out)


# ============================================================
#  EXEC 两层封装
# ============================================================
def exec_decrypt(cipher, key=DEFAULT_KEY, raw=False):
    plain = camellia_ecb(cipher, key, decrypt=True)   # 去除加密层
    if raw:
        return plain
    d = zlib.decompressobj()
    out = d.decompress(plain)
    out += d.flush()
    return out


def exec_encrypt(bytecode, key=DEFAULT_KEY, level=6, raw=False):
    if raw:
        z = bytecode
    else:
        z = zlib.compress(bytecode, level)            # 压缩层
    if len(z) % 16:                                    # 补齐到 16 的整数倍（零填充）
        z = z + b"\x00" * (16 - len(z) % 16)
    return camellia_ecb(z, key, decrypt=False)         # 加密层


# ============================================================
#  子命令
# ============================================================
def cmd_decrypt(inp, out, key, raw):
    data = open(inp, "rb").read()
    plain = exec_decrypt(data, key, raw)
    if out is None:
        out = os.path.splitext(inp)[0] + (".dec.raw" if raw else ".dec.bin")
    open(out, "wb").write(plain)
    tag = "仅解密(仍为zlib流)" if raw else "解密+解压"
    print("[%s 完成] %s (%d 字节) -> %s (%d 字节)" % (tag, os.path.basename(inp), len(data), out, len(plain)))
    if not raw:
        _sniff_encoding(plain)
    return out


def cmd_encrypt(inp, out, key, level, raw):
    data = open(inp, "rb").read()
    cipher = exec_encrypt(data, key, level, raw)
    if out is None:
        out = os.path.splitext(inp)[0] + ".EXEC"
    open(out, "wb").write(cipher)
    tag = "仅加密(输入已是zlib流)" if raw else ("压缩(level%d)+加密" % level)
    print("[%s 完成] %s (%d 字节) -> %s (%d 字节)" % (tag, os.path.basename(inp), len(data), out, len(cipher)))
    return out


def cmd_verify(inp, key, level):
    cipher = open(inp, "rb").read()
    print("[verify] 输入 EXEC: %d 字节 (%d 块)" % (len(cipher), len(cipher) // 16))
    # 1) 解密+解压
    bytecode = exec_decrypt(cipher, key)
    print("  解密+解压 -> 明文字节码 %d 字节" % len(bytecode))
    # 2) 重新压缩+加密
    rebuilt = exec_encrypt(bytecode, key, level)
    # 3) 逐字节比对
    same = rebuilt == cipher
    print("  重压(level%d)+加密 -> %d 字节" % (level, len(rebuilt)))
    if same:
        print("  encrypt(decrypt(EXEC)) == 原 EXEC ? 是，bit-perfect ✅")
    else:
        print("  逐字节不同（长度 %d vs %d）——原压缩参数可能不同；" % (len(rebuilt), len(cipher)))
        # 功能等价性：解出的明文应一致
        back = exec_decrypt(rebuilt, key)
        print("  功能等价（重压结果再解出的明文 == 原明文）? %s" % ("是 ✅（游戏可正常读取）" if back == bytecode else "否 ❌"))
        if not same and len(rebuilt) == len(cipher):
            for i in range(len(cipher)):
                if cipher[i] != rebuilt[i]:
                    print("    首个差异 @ 0x%X" % i); break
    return same


def cmd_info(inp, key):
    cipher = open(inp, "rb").read()
    print("EXEC 密文: %d 字节  (%d 个 16 字节块, 整除=%s)" % (len(cipher), len(cipher) // 16, len(cipher) % 16 == 0))
    plain = camellia_ecb(cipher, key, decrypt=True)
    print("解密后:    %d 字节  头部 %s  %s" % (len(plain), plain[:4].hex(),
          "→ zlib 流 (78 9c)" if plain[:2] == b"\x78\x9c" else "→ 非 zlib(密钥或格式不符?)"))
    if plain[:2] == b"\x78\x9c":
        d = zlib.decompressobj()
        raw = d.decompress(plain) + d.flush()
        print("zlib 解压:  %d 字节  (压缩流 %d, 尾部填充 %d)" % (len(raw), len(plain) - len(d.unused_data), len(d.unused_data)))
        print("明文字节码头部 32 字节: %s" % raw[:32].hex())
        _sniff_encoding(raw)


def _sniff_encoding(raw):
    # 粗判编码：UTF-16LE 的 ASCII 文本会呈现 大量 "X 00" 交错
    zeros_at_odd = sum(1 for i in range(1, min(4096, len(raw)), 2) if raw[i] == 0)
    n = len(range(1, min(4096, len(raw)), 2))
    ratio = zeros_at_odd / n if n else 0
    if ratio > 0.35:
        print("  编码判断: 字符串疑为 UTF-16LE（奇数位零字节占比 %.0f%%）" % (ratio * 100))
    else:
        print("  编码判断: 非典型 UTF-16LE（奇数位零字节占比 %.0f%%），可能为多字节/Shift-JIS，需进一步分析" % (ratio * 100))


def cmd_selftest():
    key = bytes.fromhex("0123456789abcdeffedcba9876543210")
    pt = bytes.fromhex("0123456789abcdeffedcba9876543210")
    exp = bytes.fromhex("67673138549669730857065648eabe43")
    ct = camellia_ecb(pt, key, decrypt=False)
    dec = camellia_ecb(ct, key, decrypt=True)
    ok = (ct == exp) and (dec == pt)
    print("[selftest] Camellia-128 RFC3713 向量")
    print("  加密:", ct.hex(), "期望:", exp.hex(), "->", "OK" if ct == exp else "FAIL")
    print("  解密回环:", "OK" if dec == pt else "FAIL")
    print("  结论:", "通过 ✅" if ok else "失败 ❌")
    return ok


# ============================================================
#  main
# ============================================================
def _parse_opts(rest):
    key = DEFAULT_KEY; level = 6; raw = False; pos = []
    i = 0
    while i < len(rest):
        a = rest[i]
        if a == "--key":
            key = rest[i + 1].encode("latin1"); i += 2
        elif a == "--level":
            level = int(rest[i + 1]); i += 2
        elif a == "--raw":
            raw = True; i += 1
        else:
            pos.append(a); i += 1
    return key, level, raw, pos


def main(argv):
    if not argv:
        print(__doc__); return 1
    cmds = {"decrypt", "encrypt", "verify", "info", "selftest"}
    dragdrop = False
    if argv[0] not in cmds:
        if len(argv) == 1 and os.path.isfile(argv[0]):
            # 自动判断方向
            data = open(argv[0], "rb").read()
            direction = "encrypt"
            try:
                if len(data) % 16 == 0:
                    p = camellia_ecb(data[:16], DEFAULT_KEY, decrypt=True)
                    if p[:2] == b"\x78\x9c":
                        direction = "decrypt"
            except Exception:
                pass
            argv = [direction, argv[0]]
            dragdrop = True
            print("[拖放] 自动判定为 %s" % direction)
        else:
            print(__doc__); return 1

    cmd = argv[0]
    key, level, raw, pos = _parse_opts(argv[1:])
    try:
        if cmd == "decrypt":
            if not pos: print("用法: decrypt <EXEC> [out.bin]"); return 1
            cmd_decrypt(pos[0], pos[1] if len(pos) > 1 else None, key, raw)
        elif cmd == "encrypt":
            if not pos: print("用法: encrypt <明文.bin> [out_EXEC]"); return 1
            cmd_encrypt(pos[0], pos[1] if len(pos) > 1 else None, key, level, raw)
        elif cmd == "verify":
            if not pos: print("用法: verify <EXEC>"); return 1
            ok = cmd_verify(pos[0], key, level)
            if dragdrop: input("\n按回车键退出...")
            return 0 if ok else 2
        elif cmd == "info":
            if not pos: print("用法: info <EXEC>"); return 1
            cmd_info(pos[0], key)
        elif cmd == "selftest":
            ok = cmd_selftest()
            return 0 if ok else 1
    except Exception as e:
        print("[错误] %s" % e)
        if dragdrop: input("\n按回车键退出...")
        return 1

    if dragdrop: input("\n完成。按回车键退出...")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
