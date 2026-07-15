#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
malie_exe_tool.py  —  Malie 引擎 exe「解封包 / 封包」工具
===========================================================
把 Malie 游戏 exe（如 malie.exe）当成一个封包来处理：

  · 游戏脚本 EXEC 与图片 BMP/PNG 等都是 exe 内的【自定义 PE 资源】。
  · 游戏运行时通过 Windows 资源 API + SizeofResource 动态读取，
    所以 EXEC 变大 / 变小都能被正确读取 —— 前提是资源目录被正确重建。
  · 本工具负责「解封包」(unpack) 把资源全部导出，以及「封包」(pack)
    把（可能被替换 / 改了大小的）资源写回 exe，重建资源目录、修好
    PE 头（节大小 / SizeOfImage / 资源目录大小 / PE 校验和）。

子命令
------
  unpack  <malie.exe> [输出目录]        解出所有资源 + 生成清单
  pack    <原始.exe> <资源目录> [输出.exe]   把资源写回，生成新 exe（支持变长）
  verify  <malie.exe>                    解包→原样封包→逐字节比对（应 bit-perfect）
  list    <malie.exe>                    列出 exe 内所有资源

拖放
----
  把 malie.exe 直接拖到本脚本图标上 = unpack（输出到 <exe名>_extracted）。

只依赖 Python 标准库。默认 Windows 运行，命令行 / 拖放皆可。
"""

import sys, os, struct, json, hashlib, shutil, tempfile

MANIFEST_NAME = "_malie_exe_manifest.json"

# ---- 标准 PE 资源类型 ID → 友好名（仅用于显示 / 目录名，清单里记录原始 ID） ----
STD_TYPE = {
    1: "CURSOR", 2: "BITMAP", 3: "ICON", 4: "MENU", 5: "DIALOG", 6: "STRING",
    7: "FONTDIR", 8: "FONT", 9: "ACCELERATOR", 10: "RCDATA", 11: "MESSAGETABLE",
    12: "GROUP_CURSOR", 14: "GROUP_ICON", 16: "VERSION", 17: "DLGINCLUDE",
    19: "PLUGPLAY", 20: "VXD", 21: "ANICURSOR", 22: "ANIICON", 23: "HTML",
    24: "MANIFEST",
}
# GARbro 对少数类型用的别名（为了让导出目录尽量贴近 GARbro 的样子）
GARBRO_ALIAS = {"BITMAP": "RT_BITMAP", "VERSION": "RT_VERSION"}


def _align(x, a):
    return (x + a - 1) & ~(a - 1)


# ============================================================
#  PE 解析
# ============================================================
class PE:
    def __init__(self, data: bytes):
        self.d = data
        self._parse()

    def u16(self, o): return struct.unpack_from("<H", self.d, o)[0]
    def u32(self, o): return struct.unpack_from("<I", self.d, o)[0]

    def _parse(self):
        d = self.d
        if d[:2] != b"MZ":
            raise ValueError("不是 PE 文件（缺少 MZ 头）")
        self.e_lfanew = self.u32(0x3C)
        if d[self.e_lfanew:self.e_lfanew + 4] != b"PE\x00\x00":
            raise ValueError("不是 PE 文件（缺少 PE 签名）")
        coff = self.e_lfanew + 4
        self.nsec = self.u16(coff + 2)
        opt_size = self.u16(coff + 16)
        opt = coff + 20
        magic = self.u16(opt)
        if magic != 0x10B:
            raise ValueError("只支持 PE32（本 exe magic=0x%X）" % magic)
        self.image_base = self.u32(opt + 28)
        self.sec_align = self.u32(opt + 32)
        self.file_align = self.u32(opt + 36)
        # 头字段偏移（封包时要改的）
        self.off_sizeofimage = opt + 56
        self.off_checksum = opt + 64
        dd = opt + 96                       # 数据目录数组
        self.off_res_dd = dd + 2 * 8        # RESOURCE = index 2 : (RVA,Size)
        self.res_rva = self.u32(self.off_res_dd)
        self.res_dd_size = self.u32(self.off_res_dd + 4)
        # 节表
        secoff = opt + opt_size
        self.secs = []          # (name, vrva, vsize, rawptr, rawsize, row_off)
        self.rsrc_row = None
        for i in range(self.nsec):
            b = secoff + i * 40
            nm = d[b:b + 8].split(b"\x00")[0].decode("latin1")
            vsz = self.u32(b + 8); vrva = self.u32(b + 12)
            rawsz = self.u32(b + 16); rawptr = self.u32(b + 20)
            self.secs.append((nm, vrva, vsz, rawptr, rawsz, b))
            if nm == ".rsrc":
                self.rsrc_row = b
                self.rsrc = (nm, vrva, vsz, rawptr, rawsz, b)
        if self.rsrc_row is None:
            raise ValueError("该 exe 没有 .rsrc 资源节")

    def rva_to_off(self, rva):
        for nm, vrva, vsz, rawptr, rawsz, _ in self.secs:
            if vrva <= rva < vrva + max(vsz, rawsz):
                return rawptr + (rva - vrva)
        raise ValueError("RVA 0x%X 不在任何节内" % rva)

    # ---- 遍历资源目录树，返回全部叶子（数据项） ----
    def walk_resources(self):
        d = self.d
        res_off = self.rva_to_off(self.res_rva)
        self.res_off = res_off
        entries = []

        def read_dirstr(rel):
            o = res_off + rel
            ln = self.u16(o)
            return d[o + 2:o + 2 + ln * 2].decode("utf-16le", "replace")

        def walk(diroff, level, chain):
            nnamed = self.u16(diroff + 12)
            nid = self.u16(diroff + 14)
            base = diroff + 16
            for i in range(nnamed + nid):
                e = base + i * 8
                nameid = self.u32(e)
                off = self.u32(e + 4)
                if nameid & 0x80000000:
                    key = ("str", read_dirstr(nameid & 0x7FFFFFFF))
                else:
                    key = ("id", nameid)
                full = chain + [key]
                if off & 0x80000000:
                    walk(res_off + (off & 0x7FFFFFFF), level + 1, full)
                else:
                    de = res_off + off              # IMAGE_RESOURCE_DATA_ENTRY
                    drva = self.u32(de)
                    size = self.u32(de + 4)
                    cp = self.u32(de + 8)
                    typ = full[0]
                    name = full[1] if len(full) > 1 else ("id", 0)
                    lang = full[2][1] if len(full) > 2 else 0
                    entries.append({
                        "type": typ, "name": name, "lang": lang,
                        "desc_off": de, "data_rva": drva, "size": size,
                        "codepage": cp, "data_off": self.rva_to_off(drva),
                    })
        walk(res_off, 0, [])
        return entries


# ---- 友好显示名 ----
def type_label(typ):
    if typ[0] == "str":
        return typ[1]
    nm = STD_TYPE.get(typ[1], "TYPE%d" % typ[1])
    return GARBRO_ALIAS.get(nm, nm)


def name_label(name):
    return name[1] if name[0] == "str" else str(name[1])


def _safe_component(s):
    bad = '<>:"/\\|?*'
    return "".join("_" if c in bad else c for c in str(s))


# ============================================================
#  unpack
# ============================================================
def unpack(exe_path, outdir=None):
    data = open(exe_path, "rb").read()
    pe = PE(data)
    entries = pe.walk_resources()

    if outdir is None:
        outdir = os.path.splitext(exe_path)[0] + "_extracted"
    os.makedirs(outdir, exist_ok=True)

    # 计算每条资源的尾部填充（到下一块数据的起点，最后一块到节尾）
    _, _, _, rawptr, rawsz, _ = pe.rsrc
    sec_start = rawptr
    sec_rawend = rawptr + rawsz
    order = sorted(entries, key=lambda r: r["data_off"])
    first_blob = order[0]["data_off"]
    for i, r in enumerate(order):
        end = r["data_off"] + r["size"]
        nxt = order[i + 1]["data_off"] if i + 1 < len(order) else sec_rawend
        r["pad"] = nxt - end
        if r["pad"] < 0:
            raise ValueError("资源数据重叠，无法安全解析：%s" % name_label(r["name"]))

    # 同一 (type,name) 有多个 language 时，文件名追加 __langXXXX 以避免覆盖
    key2langs = {}
    for r in entries:
        k = (type_label(r["type"]), name_label(r["name"]))
        key2langs.setdefault(k, set()).add(r["lang"])

    manifest_entries = []
    written = 0
    for r in entries:
        tl = type_label(r["type"]); nl = name_label(r["name"])
        multi = len(key2langs[(tl, nl)]) > 1
        fname = _safe_component(nl) + ("__lang%d" % r["lang"] if multi else "")
        rel = os.path.join(_safe_component(tl), fname)
        dest = os.path.join(outdir, rel)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with open(dest, "wb") as f:
            f.write(data[r["data_off"]:r["data_off"] + r["size"]])
        written += 1
        manifest_entries.append({
            "path": rel.replace("\\", "/"),
            "type": {"kind": r["type"][0], "val": r["type"][1]},
            "name": {"kind": r["name"][0], "val": r["name"][1]},
            "lang": r["lang"],
            "codepage": r["codepage"],
            "desc_off": r["desc_off"],
            "orig_data_off": r["data_off"],
            "orig_size": r["size"],
            "orig_pad": r["pad"],
        })

    manifest = {
        "tool": "malie_exe_tool",
        "format": "Malie exe (PE32 resource container)",
        "note": "EXEC 等为自定义 PE 资源；游戏用 SizeofResource 动态读取，可变长。"
                "pack 需以原始 exe 为模板，重建 .rsrc 并修 PE 头。",
        "source_exe": os.path.basename(exe_path),
        "source_size": len(data),
        "source_sha256": hashlib.sha256(data).hexdigest(),
        "image_base": pe.image_base,
        "sec_align": pe.sec_align,
        "file_align": pe.file_align,
        "res_rva": pe.res_rva,
        "rsrc_sec_start": sec_start,
        "rsrc_sec_rawend": sec_rawend,
        "rsrc_first_blob": first_blob,
        "rsrc_orig_vsize": pe.rsrc[2],
        "off_sizeofimage": pe.off_sizeofimage,
        "off_checksum": pe.off_checksum,
        "off_res_dd": pe.off_res_dd,
        "off_rsrc_row": pe.rsrc_row,
        "orig_checksum": pe.u32(pe.off_checksum),
        "orig_sizeofimage": pe.u32(pe.off_sizeofimage),
        "entries": manifest_entries,
    }
    with open(os.path.join(outdir, MANIFEST_NAME), "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=1)

    print("[解封包完成] %d 个资源 -> %s" % (written, outdir))
    exec_e = next((e for e in entries if type_label(e["type"]) == "EXEC"), None)
    if exec_e:
        print("  ★ 脚本文件 EXEC : %d 字节  (导出到 %s/EXEC/%s)"
              % (exec_e["size"], os.path.basename(outdir), name_label(exec_e["name"])))
        print("    （EXEC 目前是加密态，解密/解压交给下一步的 EXEC 专用工具。）")
    print("  清单已写入 %s（封包时需要它）" % MANIFEST_NAME)
    return outdir


# ============================================================
#  PE 校验和（等价于 imagehlp!CheckSumMappedFile）
# ============================================================
def pe_checksum(data: bytes, csum_off: int) -> int:
    total = 0
    n = len(data)
    limit = n & ~1
    i = 0
    while i < limit:
        if csum_off <= i < csum_off + 4:
            w = 0
        else:
            w = data[i] | (data[i + 1] << 8)
        total += w
        total = (total & 0xFFFF) + (total >> 16)
        i += 2
    if n & 1:
        total += data[-1]
        total = (total & 0xFFFF) + (total >> 16)
    total = (total & 0xFFFF) + (total >> 16)
    total = (total + (total >> 16)) & 0xFFFF
    return (total + n) & 0xFFFFFFFF


# ============================================================
#  pack
# ============================================================
def pack(orig_exe, resdir, out_path=None):
    base = bytearray(open(orig_exe, "rb").read())
    mpath = os.path.join(resdir, MANIFEST_NAME)
    if not os.path.exists(mpath):
        raise ValueError("资源目录里找不到 %s，无法封包。请先对同一个 exe 做 unpack。" % MANIFEST_NAME)
    m = json.load(open(mpath, encoding="utf-8"))

    # 校验模板 exe 是否就是当初 unpack 的那一个
    if len(base) != m["source_size"] or hashlib.sha256(base).hexdigest() != m["source_sha256"]:
        print("[警告] 提供的原始 exe 与清单记录的不一致（大小/哈希不同）。"
              "封包会基于你给的这个 exe 进行，请确认无误。")

    sec_start = m["rsrc_sec_start"]
    first_blob = m["rsrc_first_blob"]
    res_rva = m["res_rva"]
    file_align = m["file_align"]
    sec_align = m["sec_align"]

    if out_path is None:
        b, e = os.path.splitext(os.path.basename(orig_exe))
        out_path = os.path.join(os.path.dirname(os.path.abspath(orig_exe)) or ".",
                                b + "_patched" + e)

    # 元数据区（资源目录树 + 目录字符串 + 数据描述符）原样取自模板 exe
    meta_region = bytearray(base[sec_start:first_blob])

    # 按原始数据顺序重排所有资源块（保持块间原始填充）
    ents = sorted(m["entries"], key=lambda r: r["orig_data_off"])
    new_rsrc = bytearray(meta_region)
    cursor = first_blob                    # 当前写入位置（绝对文件偏移）
    total_delta = 0
    changed = []
    for r in ents:
        fp = os.path.join(resdir, r["path"])
        if not os.path.exists(fp):
            raise ValueError("缺少资源文件：%s" % r["path"])
        blob = open(fp, "rb").read()
        new_off = cursor
        new_rva = new_off - sec_start + res_rva
        # 追加资源数据
        new_rsrc += blob
        # 追加该资源后的原始填充字节（保持 bit-perfect / 排版不变）
        pad_src = r["orig_data_off"] + r["orig_size"]
        pad = base[pad_src:pad_src + r["orig_pad"]]
        new_rsrc += pad
        cursor += len(blob) + r["orig_pad"]
        # 回填数据描述符：DataRVA 与 Size
        doff = r["desc_off"] - sec_start   # 描述符在 new_rsrc 内的偏移
        struct.pack_into("<I", new_rsrc, doff, new_rva)
        struct.pack_into("<I", new_rsrc, doff + 4, len(blob))
        if len(blob) != r["orig_size"]:
            changed.append((r["path"], r["orig_size"], len(blob)))
        total_delta += len(blob) - r["orig_size"]

    content_len = len(new_rsrc)                       # 到最后一块+填充为止
    new_vsize = m["rsrc_orig_vsize"] + total_delta    # 虚拟大小随净增量平移
    new_rawsize = _align(content_len, file_align)
    new_rsrc += b"\x00" * (new_rawsize - content_len) # 节对齐填充

    # 拼装：模板 exe 的 [0, sec_start) + 新 .rsrc
    out = bytearray(base[:sec_start]) + new_rsrc

    # ---- 修 PE 头 ----
    struct.pack_into("<I", out, m["off_rsrc_row"] + 8, new_vsize)      # .rsrc VirtualSize
    struct.pack_into("<I", out, m["off_rsrc_row"] + 16, new_rawsize)   # .rsrc SizeOfRawData
    struct.pack_into("<I", out, m["off_res_dd"] + 4, new_vsize)        # RESOURCE 目录 Size
    new_sizeofimage = _align(res_rva + new_vsize, sec_align)
    struct.pack_into("<I", out, m["off_sizeofimage"], new_sizeofimage) # SizeOfImage
    # PE 校验和（先清零字段再算）
    csum = pe_checksum(bytes(out), m["off_checksum"])
    struct.pack_into("<I", out, m["off_checksum"], csum)

    with open(out_path, "wb") as f:
        f.write(out)

    print("[封包完成] -> %s  (%d 字节)" % (out_path, len(out)))
    if changed:
        print("  改动的资源：")
        for p, o, n in changed:
            d = n - o
            print("    %-28s %d -> %d 字节 (%+d)" % (p, o, n, d))
        print("  .rsrc 净增量 %+d 字节；已重建资源目录并修好 PE 头（VSize/RawSize/"
              "SizeOfImage/资源目录大小/校验和）。" % total_delta)
    else:
        print("  无资源改动（应与原 exe 逐字节一致，可用 verify 确认）。")
    return out_path


# ============================================================
#  verify / list
# ============================================================
def verify(exe_path):
    orig = open(exe_path, "rb").read()
    tmp = tempfile.mkdtemp(prefix="malie_verify_")
    try:
        d = os.path.join(tmp, "ex")
        unpack(exe_path, d)
        out = os.path.join(tmp, "rebuilt.exe")
        pack(exe_path, d, out)
        rebuilt = open(out, "rb").read()
        same = orig == rebuilt
        print("\n[verify] 原样封包 == 原 exe ? %s" % ("是，bit-perfect ✅" if same
              else "否 ❌（大小 %d vs %d）" % (len(orig), len(rebuilt))))
        if not same:
            # 定位第一个差异
            for i in range(min(len(orig), len(rebuilt))):
                if orig[i] != rebuilt[i]:
                    print("  首个差异 @ 0x%X : %02X vs %02X" % (i, orig[i], rebuilt[i]))
                    break
        return same
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def list_cmd(exe_path):
    data = open(exe_path, "rb").read()
    pe = PE(data)
    entries = pe.walk_resources()
    print("exe: %s   大小 %d 字节   资源 %d 条" % (exe_path, len(data), len(entries)))
    print("%-14s %-16s %-6s %10s  %-10s" % ("TYPE", "NAME", "LANG", "SIZE", "FILE_OFF"))
    print("-" * 64)
    for r in sorted(entries, key=lambda r: r["data_off"]):
        tl = type_label(r["type"]); nl = name_label(r["name"])
        mark = "  ★脚本" if tl == "EXEC" else ""
        print("%-14s %-16s %-6d %10d  0x%08X%s" %
              (tl[:14], nl[:16], r["lang"], r["size"], r["data_off"], mark))


# ============================================================
#  main
# ============================================================
USAGE = __doc__


def main(argv):
    if len(argv) == 0:
        print(USAGE); return 1

    # 拖放：单个存在的文件、且第一个参数不是子命令 → unpack
    cmds = {"unpack", "pack", "verify", "list"}
    dragdrop = False
    if argv[0] not in cmds:
        if len(argv) == 1 and os.path.isfile(argv[0]):
            argv = ["unpack", argv[0]]
            dragdrop = True
        else:
            print(USAGE); return 1

    cmd, rest = argv[0], argv[1:]
    try:
        if cmd == "unpack":
            if not rest:
                print("用法: unpack <malie.exe> [输出目录]"); return 1
            unpack(rest[0], rest[1] if len(rest) > 1 else None)
        elif cmd == "pack":
            if len(rest) < 2:
                print("用法: pack <原始.exe> <资源目录> [输出.exe]"); return 1
            pack(rest[0], rest[1], rest[2] if len(rest) > 2 else None)
        elif cmd == "verify":
            if not rest:
                print("用法: verify <malie.exe>"); return 1
            ok = verify(rest[0])
            return 0 if ok else 2
        elif cmd == "list":
            if not rest:
                print("用法: list <malie.exe>"); return 1
            list_cmd(rest[0])
    except Exception as e:
        print("[错误] %s" % e)
        if dragdrop:
            input("\n按回车键退出...")
        return 1

    if dragdrop:
        input("\n完成。按回车键退出...")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
