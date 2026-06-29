#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
grp_tool.py  —  ICE Soft (Ice 引擎) .GRP 封包 解包/封包工具
====================================================================
适用：EVENT.GRP / SYSTEM.GRP / STAND.GRP / GALLERY.GRP / BG.GRP 等
（エグゼキュート.exe 同系列引擎，GarBro 标记为 ICE / Ankh GrpOpener）

格式（从 エグゼキュート.exe 逆向，函数 sub_420130 / sub_420260 /
sub_420390 / sub_4206F0 完整还原）：

  [偏移表]  N+1 个 u32(LE)：entry_0_off, entry_1_off, ..., entry_{N-1}_off, 0
            · 表首值 = 表自身字节数 = (N+1)*4 = 第一个条目的起始偏移
            · 末尾一个 0 作为终止符
            · 条目 i 大小 = off[i+1]-off[i]（最后一条 = 文件尾-off[N-1]）
  [数据区]  各条目数据依次排列，每条 4 字节对齐

  每个条目的压缩/加密方式由其头部自动判定（解包自动解密）：
    · HDJ ：[u32 原始大小]['HDJ\\0'][LZ位流]            → 自定义 LZ77
    · TPW ：[u32 原始大小]['W'][方式][..]['RIFF']..      → 音频(本系列文本/表不用)
    · RAW ：以上都不匹配 → 原样数据（EVENT.GRP 全部为此类）

封包自动加密：
    · RAW 条目 → 原样写回
    · HDJ 条目 → 重新编码为合法 HDJ 位流（全 literal 模式，游戏可正常解压）
    · 提供 --orig 原始 .grp 时，未改动的条目直接复用原压缩字节 → 逐字节一致、补丁最小

用法
  解包:  python grp_tool.py unpack  <archive.grp> [-o 输出目录]
  封包:  python grp_tool.py pack    <输入目录>    [-o out.grp] [--orig 原archive.grp]
  校验:  python grp_tool.py verify  <archive.grp>
  列表:  python grp_tool.py list    <archive.grp>

拖放（直接把文件/文件夹拖到本脚本图标上）
  · 拖入 .grp 文件      → 解包到 同名_unpacked\\ 目录
  · 拖入 解包出的目录   → 封包为 目录名.grp（自动按 manifest 复用原压缩，需原档同名在侧）
"""
import sys, os, struct, json, hashlib, argparse

MANIFEST = "_grp_manifest.json"

# ============================================================ #
#  位流读取器（忠实还原 exe 中的 32-bit MSB-first dword 位流）   #
# ============================================================ #
def _u32(x):   return x & 0xFFFFFFFF
def _neg(x):   return (x & 0x80000000) != 0   # 最高位 = 符号位

class _BitSrc:
    __slots__ = ("data", "pos", "buf", "bits")
    def __init__(self, data, pos):
        self.data = data
        self.pos = pos            # 字节位置，每次读进 4 字节
        self.buf = 0              # a1[9]  32 位位缓冲
        self.bits = 0             # a1[10] 剩余位数
    def word(self):
        w = struct.unpack_from("<I", self.data, self.pos)[0]
        self.pos += 4
        return w

# ============================================================ #
#  HDJ 解压（sub_420390 的逐行移植）                             #
# ============================================================ #
def hdj_decompress(entry):
    size = struct.unpack_from("<I", entry, 0)[0]
    if entry[4:8] != b"HDJ\x00":
        raise ValueError("不是 HDJ 数据")
    s = _BitSrc(entry, 8)
    out = bytearray(size)
    dst = 0
    half_cnt = 0; half_val = 0       # v42 / v47 —— 16 位缓存
    byte_cnt = 0; byte_val = 0       # v48 / v43 —— 8 位缓存（literal 与 8 位 offset 共用）

    while dst < size:
        if s.bits == 0:
            s.buf = s.word(); s.bits = 32
        s.bits -= 1
        v9 = s.bits
        v10 = s.buf
        if _neg(v10):
            s.buf = _u32(2 * v10)
            if v9 == 0:
                s.buf = s.word(); s.bits = 32
            v14 = s.buf
            ext = 0
            if _neg(v14):
                # —— 13 位有符号 offset 分支 ——
                s.buf = _u32(2 * v14); s.bits -= 1
                if half_cnt:
                    v28 = half_val
                else:
                    v28 = s.word(); half_cnt = 2
                length = (((v28 & 0xFFFF) >> 13) & 7) + 3
                half_val = v28 >> 16
                half_cnt -= 1
                if (((v28 & 0xFFFF) >> 13) & 7) == 7:
                    ext = 1
                cur = _u32(v28 | 0xFFFFE000)
            else:
                # —— 3 位长度 + 8 位 offset 分支 ——
                if s.bits == 0:
                    s.buf = s.word(); s.bits = 32
                v16 = s.bits
                if v16 < 3:
                    w = s.word()
                    v21 = _u32(s.buf | (w >> v16))
                    s.buf = _u32(w << (3 - v16))
                    v17 = v21 >> 29
                    s.bits = 32 - (3 - v16)
                else:
                    v17 = (s.buf >> 29) & 0xFFFFFFFF
                    s.buf = _u32(s.buf << 3)
                    s.bits = v16 - 3
                length = v17 + 2
                if v17 == 3:
                    ext = 1
                if byte_cnt:
                    v24 = byte_val
                else:
                    v24 = s.word(); byte_cnt = 4
                cur = _u32(v24 | 0xFFFFFF00)
                byte_val = v24 >> 8
                byte_cnt -= 1
            if ext:
                # —— 长度扩展（前导 1 计数 + 等长读取）——
                a2 = -1
                while True:
                    if s.bits == 0:
                        s.buf = s.word(); s.bits = 32
                    v30 = s.buf
                    s.buf = _u32(2 * v30); s.bits -= 1; a2 += 1
                    if not _neg(v30):
                        break
                if a2:
                    if s.bits == 0:
                        s.buf = s.word(); s.bits = 32
                    v33 = s.bits
                    if v33 < a2:
                        w = s.word()
                        v34 = _u32(s.buf | (w >> v33)) >> (32 - a2)
                        s.buf = _u32(w << (a2 - v33))
                        s.bits = 32 - (a2 - v33)
                    else:
                        v34 = s.buf >> (32 - a2)
                        s.buf = _u32(s.buf << a2)
                        s.bits = v33 - a2
                    length += v34 + 1
            if cur == 0xFFFFFFFF:
                # offset == -1 → 重复上一个输出字节（RLE）
                b = out[dst - 1]
                out[dst:dst + length] = bytes([b]) * length
                dst += length
            else:
                soff = cur - 0x100000000          # 还原为负偏移
                sp = dst + soff
                for _ in range(length):
                    out[dst] = out[sp]; dst += 1; sp += 1
        else:
            # —— literal（直接字节）——
            s.buf = _u32(2 * v10)
            if byte_cnt:
                v12 = byte_val
            else:
                v12 = s.word(); byte_cnt = 4
            out[dst] = v12 & 0xFF; dst += 1
            byte_val = v12 >> 8
            byte_cnt -= 1
    return bytes(out)

# ============================================================ #
#  HDJ 编码（全 literal 合法位流，游戏解压器可正确还原）         #
# ============================================================ #
def hdj_compress(raw):
    size = len(raw)
    out = bytearray()
    out += struct.pack("<I", size)
    out += b"HDJ\x00"
    pos = 0
    while pos < size:
        out += struct.pack("<I", 0)               # 32 个 0 控制位 = 32 个 literal
        chunk = raw[pos:pos + 32]
        if len(chunk) % 4:
            chunk = chunk + b"\x00" * (4 - len(chunk) % 4)
        out += chunk
        pos += 32
    if len(out) % 4:                              # 整体 4 字节对齐
        out += b"\x00" * (4 - len(out) % 4)
    return bytes(out)

# ============================================================ #
#  条目类型识别                                                 #
# ============================================================ #
def detect_method(entry):
    if len(entry) >= 8:
        sz = struct.unpack_from("<I", entry, 0)[0]
        if sz > 0 and entry[4:8] == b"HDJ\x00":
            return "hdj"
        if sz > 0 and entry[4:5] == b"W" and len(entry) >= 12 and entry[8:12] == b"RIFF":
            return "tpw"
    return "raw"

def friendly_ext(decoded):
    if decoded[:2] == b"BM":     return ".bmp"
    if decoded[:4] == b"RIFF":   return ".wav"
    return ".bin"

# ============================================================ #
#  封包解析                                                     #
# ============================================================ #
def parse_archive(data):
    if len(data) < 8:
        raise ValueError("文件过小，不是有效的 .grp")
    first = struct.unpack_from("<I", data, 0)[0]
    if first < 8 or first % 4 != 0 or first > len(data):
        raise ValueError("偏移表头无效，可能不是本引擎的 .grp")
    nslots = first // 4
    offs = list(struct.unpack_from("<%dI" % nslots, data, 0))
    # 统计终止符 0 之前的有效条目数
    n = 0
    for o in offs:
        if o == 0:
            break
        n += 1
    entries = []
    for i in range(n):
        cur = offs[i]
        nxt = offs[i + 1] if (i + 1 < len(offs) and offs[i + 1] != 0) else len(data)
        if nxt < cur:
            raise ValueError("偏移表非递增，文件可能损坏")
        entries.append((cur, nxt - cur))
    return offs, n, entries

# ============================================================ #
#  解包                                                         #
# ============================================================ #
def cmd_unpack(archive, outdir=None):
    data = open(archive, "rb").read()
    offs, n, entries = parse_archive(data)
    if outdir is None:
        base = os.path.splitext(os.path.basename(archive))[0]
        outdir = os.path.join(os.path.dirname(os.path.abspath(archive)), base + "_unpacked")
    os.makedirs(outdir, exist_ok=True)

    manifest = {
        "archive": os.path.basename(archive),
        "entry_count": n,
        "table_slots": len(offs),
        "entries": [],
    }
    nh = nr = nt = 0
    for i, (off, size) in enumerate(entries):
        raw = data[off:off + size]
        method = detect_method(raw)
        if method == "hdj":
            decoded = hdj_decompress(raw); nh += 1
        elif method == "tpw":
            decoded = raw; nt += 1           # 音频：原样保留（本系列文本/表不出现）
        else:
            decoded = raw; nr += 1
        ext = friendly_ext(decoded) if method != "tpw" else ".tpw"
        fname = "%04d%s" % (i, ext)
        with open(os.path.join(outdir, fname), "wb") as f:
            f.write(decoded)
        manifest["entries"].append({
            "index": i,
            "file": fname,
            "method": method,
            "unpacked_size": len(decoded),
            "packed_offset": off,
            "packed_size": size,
            "sha1": hashlib.sha1(decoded).hexdigest(),
        })
    with open(os.path.join(outdir, MANIFEST), "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    print("[完成] 解包 %s" % archive)
    print("       条目共 %d 个：HDJ解压 %d，RAW %d，TPW %d" % (n, nh, nr, nt))
    print("       输出目录：%s" % outdir)
    return outdir

# ============================================================ #
#  封包                                                         #
# ============================================================ #
def cmd_pack(indir, out=None, orig=None):
    mpath = os.path.join(indir, MANIFEST)
    if not os.path.isfile(mpath):
        raise SystemExit("[错误] 目录中缺少 %s，无法封包（请用 unpack 生成）" % MANIFEST)
    manifest = json.load(open(mpath, encoding="utf-8"))
    ents = manifest["entries"]
    n = manifest["entry_count"]

    if out is None:
        out = os.path.join(os.path.dirname(os.path.abspath(indir.rstrip("/\\"))),
                           manifest.get("archive") or (os.path.basename(indir.rstrip("/\\")) + ".grp"))

    # 自动寻找原档（用于复用未改动条目的原始压缩字节 → 逐字节一致）
    orig_data = None
    if orig is None:
        cand = os.path.join(os.path.dirname(os.path.abspath(indir.rstrip("/\\"))),
                            manifest.get("archive", ""))
        if manifest.get("archive") and os.path.isfile(cand):
            orig = cand
    if orig and os.path.isfile(orig):
        orig_data = open(orig, "rb").read()

    blobs = []
    n_keep = n_raw = n_hdj = n_re = 0
    for e in ents:
        fp = os.path.join(indir, e["file"])
        decoded = open(fp, "rb").read()
        cur_sha = hashlib.sha1(decoded).hexdigest()
        unchanged = (cur_sha == e["sha1"])

        if unchanged and orig_data is not None:
            # 直接复用原始压缩/原始字节 → 逐字节一致
            blob = orig_data[e["packed_offset"]:e["packed_offset"] + e["packed_size"]]
            n_keep += 1
        elif e["method"] == "hdj":
            blob = hdj_compress(decoded); n_hdj += 1; n_re += (0 if unchanged else 1)
        elif e["method"] == "tpw":
            if not unchanged:
                raise SystemExit("[错误] 条目 %04d 为 TPW(音频)且已改动，本工具暂不支持重新编码" % e["index"])
            blob = decoded                       # 原样（解包时即原样保留）
            n_keep += 1
        else:  # raw
            blob = decoded; n_raw += 1; n_re += (0 if unchanged else 1)
        if len(blob) % 4:
            blob = blob + b"\x00" * (4 - len(blob) % 4)
        blobs.append(blob)

    # 重建偏移表：N 个偏移 + 1 个 0 终止符
    nslots = n + 1
    table_size = nslots * 4
    offs = []
    cur = table_size
    for b in blobs:
        offs.append(cur)
        cur += len(b)
    table = b"".join(struct.pack("<I", o) for o in offs) + struct.pack("<I", 0)
    assert len(table) == table_size

    with open(out, "wb") as f:
        f.write(table)
        for b in blobs:
            f.write(b)

    print("[完成] 封包 → %s" % out)
    print("       条目 %d 个：复用原字节 %d，RAW %d，HDJ重编码 %d（其中改动 %d）"
          % (n, n_keep, n_raw, n_hdj, n_re))
    if orig_data is None:
        print("       提示：未提供 --orig，HDJ 条目按全 literal 重新编码（合法但偏大）。")
        print("            如需逐字节最小补丁，封包时加 --orig <原始.grp>。")
    return out

# ============================================================ #
#  校验（语义 round-trip + 提供原档时的逐字节 round-trip）        #
# ============================================================ #
def cmd_verify(archive):
    import tempfile, shutil
    print("[校验] %s" % archive)
    data0 = open(archive, "rb").read()
    tmp = tempfile.mkdtemp(prefix="grpverify_")
    try:
        d = cmd_unpack(archive, os.path.join(tmp, "u1"))
        # A) 语义 round-trip：纯重编码封包 → 再解包 → 解码内容应一致
        out1 = cmd_pack(d, out=os.path.join(tmp, "re1.grp"), orig=None)
        d2 = cmd_unpack(out1, os.path.join(tmp, "u2"))
        m1 = json.load(open(os.path.join(d, MANIFEST), encoding="utf-8"))
        m2 = json.load(open(os.path.join(d2, MANIFEST), encoding="utf-8"))
        sem_ok = ([e["sha1"] for e in m1["entries"]] == [e["sha1"] for e in m2["entries"]]
                  and m1["entry_count"] == m2["entry_count"])
        # B) 逐字节 round-trip：以原档复用未改动条目 → 应与原文件完全一致
        out2 = cmd_pack(d, out=os.path.join(tmp, "re2.grp"), orig=archive)
        data2 = open(out2, "rb").read()
        byte_ok = (data2 == data0)
        h0 = hashlib.sha256(data0).hexdigest()
        h2 = hashlib.sha256(data2).hexdigest()
    finally:
        pass
    print("-" * 60)
    print("  语义 round-trip（解码内容逐条一致）：%s" % ("通过 ✓" if sem_ok else "失败 ✗"))
    print("  逐字节 round-trip（--orig 复用未改动条目）：%s" % ("通过 ✓ bit-perfect" if byte_ok else "失败 ✗"))
    print("    原始 sha256：%s" % h0)
    print("    重建 sha256：%s" % h2)
    shutil.rmtree(tmp, ignore_errors=True)
    return sem_ok and byte_ok

# ============================================================ #
#  列表                                                         #
# ============================================================ #
def cmd_list(archive):
    data = open(archive, "rb").read()
    offs, n, entries = parse_archive(data)
    print("[列表] %s —— 条目 %d 个，偏移表槽位 %d" % (archive, n, len(offs)))
    print("  序号   偏移      大小      方式    解压后大小  预览")
    for i, (off, size) in enumerate(entries):
        raw = data[off:off + size]
        m = detect_method(raw)
        if m == "hdj":
            usz = struct.unpack_from("<I", raw, 0)[0]
            head = hdj_decompress(raw)[:4]
        else:
            usz = size; head = raw[:4]
        print("  %04d  0x%07x  %8d  %-5s  %9d  %s" % (i, off, size, m, usz, head.hex()))

# ============================================================ #
#  入口（含拖放自动判定）                                        #
# ============================================================ #
def main():
    p = argparse.ArgumentParser(description="ICE 引擎 .grp 解包/封包工具")
    sub = p.add_subparsers(dest="cmd")
    sp = sub.add_parser("unpack"); sp.add_argument("archive"); sp.add_argument("-o", "--out")
    sp = sub.add_parser("pack");   sp.add_argument("indir");   sp.add_argument("-o", "--out"); sp.add_argument("--orig")
    sp = sub.add_parser("verify"); sp.add_argument("archive")
    sp = sub.add_parser("list");   sp.add_argument("archive")

    argv = sys.argv[1:]
    if argv and argv[0] not in ("unpack", "pack", "verify", "list", "-h", "--help"):
        # 拖放模式：判断是文件还是目录
        tgt = argv[0]
        if os.path.isdir(tgt):
            cmd_pack(tgt)
        elif os.path.isfile(tgt):
            cmd_unpack(tgt)
        else:
            print("[错误] 找不到：%s" % tgt)
        return

    a = p.parse_args(argv)
    if a.cmd == "unpack":
        cmd_unpack(a.archive, a.out)
    elif a.cmd == "pack":
        cmd_pack(a.indir, a.out, a.orig)
    elif a.cmd == "verify":
        ok = cmd_verify(a.archive)
        sys.exit(0 if ok else 1)
    elif a.cmd == "list":
        cmd_list(a.archive)
    else:
        p.print_help()

if __name__ == "__main__":
    main()
