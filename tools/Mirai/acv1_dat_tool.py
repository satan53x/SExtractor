# -*- coding: utf-8 -*-
"""
ACV1 script.dat unpack/pack tool

反汇编依据：
  - sub_4CF6E0: 解析 ACV1 头、count、每项 key/flag/offset/packed_size/out_capacity。
  - sub_4CBC50: 用游戏标题字符串计算 CRC64-ECMA，payload XOR 使用 CRC64 低 32 位。
  - sub_4CFEF0: fseek(offset) -> fread(packed_size) -> DWORD XOR -> zlib inflate。

注意：avc_codec.py 的 SETSUEI/ARCHIVE 布局仅作设计参照，本工具按当前 EXE 反汇编实现。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import struct
import tempfile
import zlib
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

MAGIC_ACV1 = 0x31564341  # b"ACV1"
MAGIC_ACV1_BYTES = b"ACV1"
COUNT_XOR_ACV1 = 0x8B6A4E5F
COUNT_XOR_LEGACY = 0x26ACA46E
CRC64_ECMA_POLY = 0x42F0E1EBA9EA3693
DEFAULT_GAME_TITLE = "みなとカーニバルFD"
ENTRY_SIZE = 21
DEFAULT_ZLIB_LEVEL = 9


@dataclass
class DatEntry:
    index: int
    key_lo: int
    key_hi: int
    flag: int
    offset: int
    packed_size: int
    out_capacity: int
    unpacked_size: int | None = None
    name: str | None = None


def u32le(data: bytes, off: int) -> int:
    return struct.unpack_from("<I", data, off)[0]


def p32(value: int) -> bytes:
    return struct.pack("<I", value & 0xFFFFFFFF)


def crc64_ecma_msb(data: bytes) -> int:
    """复现 sub_4CBC50：init=-1，MSB-first，final=~crc。"""
    crc = 0xFFFFFFFFFFFFFFFF
    for b in data:
        idx = ((crc >> 56) ^ b) & 0xFF
        c = idx << 56
        for _ in range(8):
            if c & 0x8000000000000000:
                c = ((c << 1) ^ CRC64_ECMA_POLY) & 0xFFFFFFFFFFFFFFFF
            else:
                c = (c << 1) & 0xFFFFFFFFFFFFFFFF
        crc = ((crc << 8) & 0xFFFFFFFFFFFFFFFF) ^ c
    return (~crc) & 0xFFFFFFFFFFFFFFFF


def title_crc_low(game_title: str) -> tuple[int, int]:
    crc = crc64_ecma_msb(game_title.encode("cp932"))
    return crc, crc & 0xFFFFFFFF


def parse_index(data: bytes) -> tuple[list[DatEntry], int, bool]:
    """返回 entries, index_end, is_acv1。"""
    magic = u32le(data, 0)
    if magic == MAGIC_ACV1:
        count = u32le(data, 4) ^ COUNT_XOR_ACV1
        pos = 8
        offset_extra_xor = COUNT_XOR_ACV1
        is_acv1 = True
    else:
        # sub_4CF6E0 保留的旧分支。当前 script.dat 走 ACV1 分支。
        count = magic ^ COUNT_XOR_LEGACY
        pos = 4
        offset_extra_xor = 0
        is_acv1 = False

    if count > 100000:
        raise ValueError(f"entry count 异常：{count}")

    entries: list[DatEntry] = []
    for i in range(count):
        if pos + ENTRY_SIZE > len(data):
            raise ValueError(f"index 越界：entry={i}, pos=0x{pos:x}")
        key_lo = u32le(data, pos)
        key_hi = u32le(data, pos + 4)
        pos += 8
        flag = data[pos] ^ (key_lo & 0xFF)
        pos += 1
        offset = u32le(data, pos) ^ offset_extra_xor ^ key_lo
        pos += 4
        packed_size = u32le(data, pos) ^ key_lo
        pos += 4
        out_capacity = u32le(data, pos) ^ key_lo
        pos += 4
        if offset + packed_size > len(data):
            raise ValueError(
                f"payload 越界：entry={i}, off=0x{offset:x}, size=0x{packed_size:x}, file=0x{len(data):x}"
            )
        entries.append(DatEntry(i, key_lo, key_hi, flag, offset, packed_size, out_capacity))
    return entries, pos, is_acv1


def build_index(entries: list[DatEntry], is_acv1: bool = True) -> bytes:
    if not is_acv1:
        raise NotImplementedError("pack 当前只实现 ACV1 分支；旧分支样本不足，避免臆造。")
    buf = bytearray()
    buf += MAGIC_ACV1_BYTES
    buf += p32(len(entries) ^ COUNT_XOR_ACV1)
    for e in entries:
        key_lo = e.key_lo & 0xFFFFFFFF
        key_hi = e.key_hi & 0xFFFFFFFF
        buf += p32(key_lo)
        buf += p32(key_hi)
        buf.append((e.flag ^ (key_lo & 0xFF)) & 0xFF)
        buf += p32(e.offset ^ COUNT_XOR_ACV1 ^ key_lo)
        buf += p32(e.packed_size ^ key_lo)
        buf += p32(e.out_capacity ^ key_lo)
    return bytes(buf)


def xor_payload_dwords(payload: bytes, dword_key: int) -> bytes:
    """sub_4CFEF0 只 XOR packed_size>>2 个 DWORD；尾部 1~3 字节保持原样。"""
    buf = bytearray(payload)
    for i in range(len(buf) // 4):
        off = i * 4
        v = struct.unpack_from("<I", buf, off)[0] ^ dword_key
        struct.pack_into("<I", buf, off, v & 0xFFFFFFFF)
    return bytes(buf)


def unpack_entry(data: bytes, entry: DatEntry, crc_low: int) -> bytes:
    enc = data[entry.offset : entry.offset + entry.packed_size]
    xored = xor_payload_dwords(enc, crc_low ^ entry.key_lo)
    try:
        return zlib.decompress(xored)
    except zlib.error as e:
        raise ValueError(
            f"zlib inflate 失败：entry={entry.index}, off=0x{entry.offset:x}, packed={entry.packed_size}, "
            f"key=0x{(crc_low ^ entry.key_lo) & 0xFFFFFFFF:08x}: {e}"
        ) from e


def pack_entry(plain: bytes, entry: DatEntry, crc_low: int, level: int = DEFAULT_ZLIB_LEVEL) -> bytes:
    comp = zlib.compress(plain, level)
    return xor_payload_dwords(comp, crc_low ^ entry.key_lo)


def safe_filename(s: str, limit: int = 80) -> str:
    s = s.strip().replace("\\", "_").replace("/", "_")
    s = re.sub(r"[\x00-\x1f<>:\"|?*]+", "_", s)
    s = re.sub(r"\s+", "_", s)
    return (s[:limit] or "unnamed").rstrip(" ._") or "unnamed"


def guess_name(index: int, raw: bytes) -> str:
    text = raw.decode("cp932", errors="replace")
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("*") and len(line) > 1:
            label = line[1:].split()[0]
            return f"{index:03d}_{safe_filename(label)}.txt"
    return f"{index:03d}_entry.txt"


def dedupe_name(name: str, used: set[str]) -> str:
    base = name
    n = 1
    while name.lower() in used:
        stem = Path(base).stem
        suffix = Path(base).suffix or ".txt"
        name = f"{stem}_{n}{suffix}"
        n += 1
    used.add(name.lower())
    return name


def unpack_dat(input_path: Path, output_dir: Path, game_title: str = DEFAULT_GAME_TITLE) -> list[DatEntry]:
    data = input_path.read_bytes()
    entries, index_end, is_acv1 = parse_index(data)
    crc, crc_low = title_crc_low(game_title)
    data_base = min((e.offset for e in entries), default=index_end)
    header_gap = data[index_end:data_base] if data_base >= index_end else b""

    output_dir.mkdir(parents=True, exist_ok=True)
    used: set[str] = set()
    for entry in entries:
        plain = unpack_entry(data, entry, crc_low)
        entry.unpacked_size = len(plain)
        entry.name = dedupe_name(guess_name(entry.index, plain), used)
        (output_dir / entry.name).write_bytes(plain)

    manifest: dict[str, Any] = {
        "source": str(input_path),
        "format": "ACV1 script.dat" if is_acv1 else "legacy dat branch",
        "game_title_for_crc64": game_title,
        "crc64_ecma": f"0x{crc:016x}",
        "crc_low_used_by_payload_xor": f"0x{crc_low:08x}",
        "entry_count": len(entries),
        "index_end": index_end,
        "data_base": data_base,
        "header_gap_hex": header_gap.hex(),
        "zlib_level_recommended_for_rebuild": DEFAULT_ZLIB_LEVEL,
        "entries": [asdict(e) for e in entries],
    }
    (output_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return entries


def load_manifest(input_dir: Path) -> dict[str, Any]:
    path = input_dir / "manifest.json"
    if not path.is_file():
        raise FileNotFoundError(f"缺少 manifest.json：{path}\n请先用 unpack 解包，封包依赖 manifest 保留 key/flag/order。")
    return json.loads(path.read_text(encoding="utf-8"))


def entries_from_manifest(manifest: dict[str, Any]) -> list[DatEntry]:
    raw_entries = manifest.get("entries")
    if not isinstance(raw_entries, list):
        raise ValueError("manifest.json 缺少 entries 数组")
    entries: list[DatEntry] = []
    for i, obj in enumerate(raw_entries):
        try:
            entries.append(
                DatEntry(
                    index=int(obj.get("index", i)),
                    key_lo=int(obj["key_lo"]),
                    key_hi=int(obj.get("key_hi", 0)),
                    flag=int(obj.get("flag", 0)),
                    offset=int(obj.get("offset", 0)),
                    packed_size=int(obj.get("packed_size", 0)),
                    out_capacity=int(obj.get("out_capacity", 0)),
                    unpacked_size=obj.get("unpacked_size"),
                    name=obj.get("name"),
                )
            )
        except KeyError as e:
            raise ValueError(f"manifest entry[{i}] 缺少字段：{e}") from e
    entries.sort(key=lambda e: e.index)
    return entries


def get_header_gap(manifest: dict[str, Any], template: Path | None, index_end: int, data_base_hint: int | None) -> bytes:
    if template is not None:
        data = template.read_bytes()
        t_entries, t_index_end, _ = parse_index(data)
        t_data_base = min((e.offset for e in t_entries), default=t_index_end)
        if t_index_end == index_end and t_data_base >= t_index_end:
            return data[t_index_end:t_data_base]
    gap_hex = manifest.get("header_gap_hex")
    if isinstance(gap_hex, str):
        try:
            return bytes.fromhex(gap_hex)
        except ValueError:
            pass
    if isinstance(data_base_hint, int) and data_base_hint >= index_end:
        return b"\x00" * (data_base_hint - index_end)
    return b""


def pack_dat(
    input_dir: Path,
    output_path: Path,
    game_title: str | None = None,
    level: int = DEFAULT_ZLIB_LEVEL,
    template: Path | None = None,
    preserve_capacity: bool = True,
) -> list[DatEntry]:
    manifest = load_manifest(input_dir)
    entries = entries_from_manifest(manifest)
    if not entries:
        raise ValueError("manifest entries 为空")
    if game_title is None:
        game_title = manifest.get("game_title_for_crc64") or DEFAULT_GAME_TITLE
    crc, crc_low = title_crc_low(game_title)

    index_end = 8 + len(entries) * ENTRY_SIZE
    data_base_hint = manifest.get("data_base")
    if not isinstance(data_base_hint, int):
        data_base_hint = None
    header_gap = get_header_gap(manifest, template, index_end, data_base_hint)
    data_pos = index_end + len(header_gap)

    payload_chunks: list[bytes] = []
    rebuilt_entries: list[DatEntry] = []
    for e in entries:
        if not e.name:
            raise ValueError(f"entry {e.index} 缺少 name，无法定位明文文件")
        plain_path = input_dir / e.name
        if not plain_path.is_file():
            raise FileNotFoundError(f"缺少明文文件：{plain_path}")
        plain = plain_path.read_bytes()
        enc = pack_entry(plain, e, crc_low, level=level)
        new_capacity = max(e.out_capacity, len(plain)) if preserve_capacity else len(plain)
        ne = DatEntry(
            index=e.index,
            key_lo=e.key_lo,
            key_hi=e.key_hi,
            flag=e.flag,
            offset=data_pos,
            packed_size=len(enc),
            out_capacity=new_capacity,
            unpacked_size=len(plain),
            name=e.name,
        )
        rebuilt_entries.append(ne)
        payload_chunks.append(enc)
        data_pos += len(enc)

    out = bytearray()
    out += build_index(rebuilt_entries, is_acv1=True)
    out += header_gap
    for chunk in payload_chunks:
        out += chunk

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(out)

    # 同步输出 rebuild manifest，方便继续二次封包。
    rebuilt_manifest = dict(manifest)
    rebuilt_manifest.update(
        {
            "source": str(output_path),
            "game_title_for_crc64": game_title,
            "crc64_ecma": f"0x{crc:016x}",
            "crc_low_used_by_payload_xor": f"0x{crc_low:08x}",
            "entry_count": len(rebuilt_entries),
            "index_end": index_end,
            "data_base": index_end + len(header_gap),
            "header_gap_hex": header_gap.hex(),
            "zlib_level_used_for_rebuild": level,
            "entries": [asdict(e) for e in rebuilt_entries],
        }
    )
    (output_path.with_suffix(output_path.suffix + ".manifest.json")).write_text(
        json.dumps(rebuilt_manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return rebuilt_entries


def compare_dirs(a: Path, b: Path) -> tuple[int, list[str]]:
    files_a = sorted(p for p in a.rglob("*") if p.is_file() and p.name != "manifest.json")
    mismatches: list[str] = []
    checked = 0
    for pa in files_a:
        rel = pa.relative_to(a)
        pb = b / rel
        checked += 1
        if not pb.is_file():
            mismatches.append(f"missing: {rel.as_posix()}")
        elif pa.read_bytes() != pb.read_bytes():
            mismatches.append(f"diff: {rel.as_posix()}")
    return checked, mismatches


def verify_dat(dat_path: Path, game_title: str = DEFAULT_GAME_TITLE) -> tuple[int, int]:
    data = dat_path.read_bytes()
    entries, _, _ = parse_index(data)
    crc, crc_low = title_crc_low(game_title)
    total = 0
    for e in entries:
        plain = unpack_entry(data, e, crc_low)
        e.unpacked_size = len(plain)
        total += len(plain)
    return len(entries), total


def roundtrip(input_dat: Path, work_dir: Path, game_title: str = DEFAULT_GAME_TITLE) -> None:
    if work_dir.exists():
        shutil.rmtree(work_dir)
    unpack_dir = work_dir / "unpacked"
    repack_path = work_dir / "repacked.dat"
    reup_dir = work_dir / "reunpacked"
    unpack_dat(input_dat, unpack_dir, game_title=game_title)
    pack_dat(unpack_dir, repack_path, game_title=game_title, template=input_dat)
    unpack_dat(repack_path, reup_dir, game_title=game_title)
    checked, mismatches = compare_dirs(unpack_dir, reup_dir)
    same_bytes = input_dat.read_bytes() == repack_path.read_bytes()
    print(f"[roundtrip] checked_files={checked} content_mismatches={len(mismatches)} byte_exact={same_bytes}")
    for m in mismatches[:20]:
        print(f"[roundtrip][diff] {m}")
    if mismatches:
        raise SystemExit(2)


def main() -> None:
    ap = argparse.ArgumentParser(description="ACV1 script.dat unpack/pack tool based on the target EXE disassembly.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_unpack = sub.add_parser("unpack", help="解包 script.dat 到目录，并生成 manifest.json")
    p_unpack.add_argument("input", type=Path)
    p_unpack.add_argument("output", type=Path)
    p_unpack.add_argument("--game-title", default=DEFAULT_GAME_TITLE, help="用于 CRC64 派生 payload XOR key 的 cp932 标题字符串")

    p_pack = sub.add_parser("pack", help="从解包目录 + manifest.json 重封包")
    p_pack.add_argument("input_dir", type=Path)
    p_pack.add_argument("output", type=Path)
    p_pack.add_argument("--game-title", default=None, help="默认读取 manifest；必要时手动指定")
    p_pack.add_argument("--level", type=int, default=DEFAULT_ZLIB_LEVEL, choices=range(10), metavar="0-9")
    p_pack.add_argument("--template", type=Path, default=None, help="可选：原始 dat，用于保留索引后未读 gap 字节")
    p_pack.add_argument("--no-preserve-capacity", action="store_true", help="默认 out_capacity=max(原容量, 明文长度)；此选项改为实际明文长度")

    p_verify = sub.add_parser("verify", help="验证 dat 能按当前算法完整解码")
    p_verify.add_argument("input", type=Path)
    p_verify.add_argument("--game-title", default=DEFAULT_GAME_TITLE)

    p_rt = sub.add_parser("roundtrip", help="解包->封包->再解包，比较明文是否一致")
    p_rt.add_argument("input", type=Path)
    p_rt.add_argument("work_dir", type=Path)
    p_rt.add_argument("--game-title", default=DEFAULT_GAME_TITLE)

    args = ap.parse_args()
    if args.cmd == "unpack":
        entries = unpack_dat(args.input, args.output, args.game_title)
        print(
            f"[unpack] entries={len(entries)} packed={sum(e.packed_size for e in entries)} "
            f"unpacked={sum(e.unpacked_size or 0 for e in entries)} output={args.output}"
        )
    elif args.cmd == "pack":
        entries = pack_dat(
            args.input_dir,
            args.output,
            game_title=args.game_title,
            level=args.level,
            template=args.template,
            preserve_capacity=not args.no_preserve_capacity,
        )
        print(
            f"[pack] entries={len(entries)} packed={sum(e.packed_size for e in entries)} "
            f"unpacked={sum(e.unpacked_size or 0 for e in entries)} output={args.output}"
        )
    elif args.cmd == "verify":
        count, total = verify_dat(args.input, args.game_title)
        print(f"[verify] ok entries={count} unpacked={total}")
    elif args.cmd == "roundtrip":
        roundtrip(args.input, args.work_dir, args.game_title)


if __name__ == "__main__":
    main()
