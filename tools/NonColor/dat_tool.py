# -*- coding: utf-8 -*-
"""
らぶおぶ恋愛皇帝ofLOVE! script.dat unpack/pack tool

Format:
  - legacy ACV container branch, no literal "ACV1" magic in the file header.
  - first dword = entry_count ^ 0x26ACA46E
  - entry size = 21 bytes:
      key_lo:u32, key_hi:u32, flag:u8^low8(key_lo), offset:u32^key_lo,
      packed_size:u32^key_lo, out_capacity:u32^key_lo
  - payload = zlib stream encrypted by DWORD XOR:
      dword_key = CRC64_ECMA(game_title_cp932).low32 ^ key_lo
      only size//4 DWORDs are XORed; trailing 1-3 bytes are unchanged.

Important:
  This tool preserves the bytes between the entry table end and the first payload
  (header_gap_hex in manifest).  The provided sample has an 8-byte gap; losing it
  shifts every rebuilt payload offset and is a likely cause of repack failure.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import struct
import zlib
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

MAGIC_ACV1 = 0x31564341  # b"ACV1"
COUNT_XOR_ACV1 = 0x8B6A4E5F
COUNT_XOR_LEGACY = 0x26ACA46E
ENTRY_SIZE = 21
CRC64_ECMA_POLY = 0x42F0E1EBA9EA3693
DEFAULT_GAME_TITLE = "らぶおぶ恋愛皇帝ofLOVE!"
DEFAULT_ENCODING = "cp932"
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
    labels: list[str] | None = None


def u32le(data: bytes, off: int) -> int:
    return struct.unpack_from("<I", data, off)[0]


def p32(value: int) -> bytes:
    return struct.pack("<I", value & 0xFFFFFFFF)


def crc64_ecma_msb(data: bytes) -> int:
    """CRC64-ECMA, init=-1, MSB-first, final=~crc.  Matches the ACV engine routine."""
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


def title_key(game_title: str) -> tuple[int, int]:
    crc = crc64_ecma_msb(game_title.encode("cp932"))
    return crc, crc & 0xFFFFFFFF


def parse_header(data: bytes) -> tuple[bool, int, int, list[DatEntry]]:
    if len(data) < 4:
        raise ValueError("file too small")
    first = u32le(data, 0)
    if first == MAGIC_ACV1:
        if len(data) < 8:
            raise ValueError("truncated ACV1 header")
        has_magic = True
        count = u32le(data, 4) ^ COUNT_XOR_ACV1
        pos = 8
        offset_extra_xor = COUNT_XOR_ACV1
    else:
        has_magic = False
        count = first ^ COUNT_XOR_LEGACY
        pos = 4
        offset_extra_xor = 0

    if count < 0 or count > 100000:
        raise ValueError(f"invalid entry count: {count}")

    table_end = pos + count * ENTRY_SIZE
    if table_end > len(data):
        raise ValueError(f"entry table truncated: need={table_end}, file_size={len(data)}")

    entries: list[DatEntry] = []
    off = pos
    for i in range(count):
        key_lo = u32le(data, off)
        key_hi = u32le(data, off + 4)
        off += 8
        flag = data[off] ^ (key_lo & 0xFF)
        off += 1
        payload_off = u32le(data, off) ^ key_lo ^ offset_extra_xor
        off += 4
        packed_size = u32le(data, off) ^ key_lo
        off += 4
        out_capacity = u32le(data, off) ^ key_lo
        off += 4
        if payload_off + packed_size > len(data):
            raise ValueError(
                f"entry {i} outside file: off=0x{payload_off:X}, size=0x{packed_size:X}, file=0x{len(data):X}"
            )
        entries.append(DatEntry(i, key_lo, key_hi, flag, payload_off, packed_size, out_capacity))
    return has_magic, table_end, count, entries


def build_header(entries: list[DatEntry], has_magic: bool) -> bytes:
    out = bytearray()
    if has_magic:
        out += p32(MAGIC_ACV1)
        out += p32(len(entries) ^ COUNT_XOR_ACV1)
        offset_extra_xor = COUNT_XOR_ACV1
    else:
        out += p32(len(entries) ^ COUNT_XOR_LEGACY)
        offset_extra_xor = 0

    for e in entries:
        key_lo = e.key_lo & 0xFFFFFFFF
        out += p32(key_lo)
        out += p32(e.key_hi)
        out.append((e.flag ^ (key_lo & 0xFF)) & 0xFF)
        out += p32(e.offset ^ key_lo ^ offset_extra_xor)
        out += p32(e.packed_size ^ key_lo)
        out += p32(e.out_capacity ^ key_lo)
    return bytes(out)


def xor_payload_dwords(payload: bytes, dword_key: int) -> bytes:
    buf = bytearray(payload)
    key = dword_key & 0xFFFFFFFF
    for off in range(0, len(buf) // 4 * 4, 4):
        v = struct.unpack_from("<I", buf, off)[0] ^ key
        struct.pack_into("<I", buf, off, v & 0xFFFFFFFF)
    return bytes(buf)


def unpack_entry(data: bytes, entry: DatEntry, key_low32: int) -> bytes:
    enc = data[entry.offset:entry.offset + entry.packed_size]
    comp = xor_payload_dwords(enc, key_low32 ^ entry.key_lo)
    try:
        raw = zlib.decompress(comp)
    except zlib.error as ex:
        raise ValueError(
            f"zlib failed: entry={entry.index}, off=0x{entry.offset:X}, size=0x{entry.packed_size:X}, "
            f"xor=0x{(key_low32 ^ entry.key_lo) & 0xFFFFFFFF:08X}: {ex}"
        ) from ex
    return raw


def pack_entry(raw: bytes, entry: DatEntry, key_low32: int, level: int) -> bytes:
    comp = zlib.compress(raw, level)
    return xor_payload_dwords(comp, key_low32 ^ entry.key_lo)


def safe_name(text: str, limit: int = 80) -> str:
    text = text.strip().lstrip("*")
    text = re.sub(r"[\\/:*?\"<>|\x00-\x1F\s]+", "_", text)
    text = text.strip("._")
    return (text[:limit] or "entry")


def collect_labels(raw: bytes, encoding: str = DEFAULT_ENCODING) -> list[str]:
    s = raw.decode(encoding, errors="ignore")
    labels: list[str] = []
    seen: set[str] = set()
    for m in re.finditer(r"(?m)^\*([^\r\n: /\t]+)", s):
        label = m.group(1).strip()
        if label and label not in seen:
            seen.add(label)
            labels.append(label)
    return labels


def guess_name(entry: DatEntry, raw: bytes, used: set[str], encoding: str) -> str:
    labels = collect_labels(raw, encoding)
    entry.labels = labels
    base = safe_name(labels[0]) if labels else f"{entry.key_hi:08X}_{entry.key_lo:08X}"
    name = f"{entry.index:04d}_{base}.txt"
    stem = Path(name).stem
    suffix = Path(name).suffix or ".txt"
    n = 1
    while name.lower() in used:
        name = f"{stem}_{n}{suffix}"
        n += 1
    used.add(name.lower())
    return name


def manifest_key_low32(manifest: dict[str, Any], fallback_title: str = DEFAULT_GAME_TITLE) -> int:
    if "key_low32" in manifest:
        v = str(manifest["key_low32"])
        return int(v, 16) if v.lower().startswith("0x") else int(v)
    title = str(manifest.get("game_title", fallback_title))
    return title_key(title)[1]


def unpack_dat(input_dat: Path, output_dir: Path, game_title: str, encoding: str) -> None:
    data = input_dat.read_bytes()
    has_magic, table_end, count, entries = parse_header(data)
    crc, key_low32 = title_key(game_title)
    data_base = min((e.offset for e in entries), default=table_end)
    header_gap = data[table_end:data_base] if data_base >= table_end else b""

    files_dir = output_dir / "files"
    files_dir.mkdir(parents=True, exist_ok=True)
    used: set[str] = set()
    total = 0

    for e in entries:
        raw = unpack_entry(data, e, key_low32)
        e.unpacked_size = len(raw)
        e.name = guess_name(e, raw, used, encoding)
        (files_dir / e.name).write_bytes(raw)
        total += len(raw)

    manifest = {
        "format": "ACV1-script-dat-legacy" if not has_magic else "ACV1-script-dat",
        "source": input_dat.name,
        "has_magic": has_magic,
        "game_title": game_title,
        "crc64_ecma": f"0x{crc:016X}",
        "key_low32": f"0x{key_low32:08X}",
        "encoding": encoding,
        "count": count,
        "table_end": table_end,
        "data_base": data_base,
        "header_gap_hex": header_gap.hex(),
        "entries": [asdict(e) for e in entries],
    }
    (output_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[unpack] entries={count}")
    print(f"[unpack] key_low32=0x{key_low32:08X}")
    print(f"[unpack] table_end=0x{table_end:X} data_base=0x{data_base:X} header_gap={len(header_gap)}")
    print(f"[unpack] raw_total={total}")
    print(f"[unpack] output={output_dir}")


def load_manifest(work_dir: Path) -> dict[str, Any]:
    path = work_dir / "manifest.json"
    if not path.is_file():
        raise FileNotFoundError(f"manifest.json not found: {path}")
    m = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(m, dict) or not isinstance(m.get("entries"), list):
        raise ValueError("bad manifest.json")
    return m


def entries_from_manifest(manifest: dict[str, Any]) -> list[DatEntry]:
    entries: list[DatEntry] = []
    for i, obj in enumerate(manifest["entries"]):
        entries.append(DatEntry(
            index=int(obj.get("index", i)),
            key_lo=int(obj["key_lo"]),
            key_hi=int(obj.get("key_hi", 0)),
            flag=int(obj.get("flag", 0)),
            offset=int(obj.get("offset", 0)),
            packed_size=int(obj.get("packed_size", 0)),
            out_capacity=int(obj.get("out_capacity", 0)),
            unpacked_size=obj.get("unpacked_size"),
            name=obj.get("name"),
            labels=obj.get("labels") if isinstance(obj.get("labels"), list) else None,
        ))
    entries.sort(key=lambda e: e.index)
    return entries


def get_header_gap(manifest: dict[str, Any]) -> bytes:
    gap_hex = manifest.get("header_gap_hex", "")
    if isinstance(gap_hex, str) and gap_hex:
        return bytes.fromhex(gap_hex)
    return b""


def pack_dat(work_dir: Path, output_dat: Path, level: int | None, preserve_capacity: bool) -> None:
    manifest = load_manifest(work_dir)
    old_entries = entries_from_manifest(manifest)
    has_magic = bool(manifest.get("has_magic", False))
    key_low32 = manifest_key_low32(manifest)
    header_gap = get_header_gap(manifest)

    table_size = (8 if has_magic else 4) + len(old_entries) * ENTRY_SIZE
    cur = table_size + len(header_gap)
    new_entries: list[DatEntry] = []
    payloads: list[bytes] = []
    raw_total = 0

    for old in old_entries:
        if not old.name:
            raise ValueError(f"entry {old.index} missing name in manifest")
        raw_path = work_dir / "files" / old.name
        if not raw_path.is_file():
            # 兼容老 manifest 可能把路径写在 name 中
            raw_path = work_dir / str(old.name)
        if not raw_path.is_file():
            raise FileNotFoundError(f"missing unpacked file for entry {old.index}: {old.name}")
        raw = raw_path.read_bytes()
        zlevel = old.flag if level is None else level
        if zlevel < 0 or zlevel > 9:
            zlevel = DEFAULT_ZLIB_LEVEL
        enc = pack_entry(raw, old, key_low32, zlevel)
        ne = DatEntry(
            index=old.index,
            key_lo=old.key_lo,
            key_hi=old.key_hi,
            flag=zlevel,
            offset=cur,
            packed_size=len(enc),
            out_capacity=max(old.out_capacity, len(raw)) if preserve_capacity else len(raw),
            unpacked_size=len(raw),
            name=old.name,
            labels=old.labels,
        )
        new_entries.append(ne)
        payloads.append(enc)
        cur += len(enc)
        raw_total += len(raw)

    out = bytearray()
    out += build_header(new_entries, has_magic)
    out += header_gap
    for blob in payloads:
        out += blob

    output_dat.parent.mkdir(parents=True, exist_ok=True)
    output_dat.write_bytes(out)

    rebuilt_manifest = dict(manifest)
    rebuilt_manifest.update({
        "source": output_dat.name,
        "table_end": table_size,
        "data_base": table_size + len(header_gap),
        "count": len(new_entries),
        "key_low32": f"0x{key_low32:08X}",
        "entries": [asdict(e) for e in new_entries],
    })
    (output_dat.with_suffix(output_dat.suffix + ".manifest.json")).write_text(
        json.dumps(rebuilt_manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"[pack] entries={len(new_entries)}")
    print(f"[pack] key_low32=0x{key_low32:08X}")
    print(f"[pack] table_end=0x{table_size:X} header_gap={len(header_gap)} data_base=0x{table_size + len(header_gap):X}")
    print(f"[pack] raw_total={raw_total}")
    print(f"[pack] output_size={len(out)}")
    print(f"[pack] output={output_dat}")


def verify_dat(input_dat: Path, game_title: str) -> None:
    data = input_dat.read_bytes()
    has_magic, table_end, count, entries = parse_header(data)
    crc, key_low32 = title_key(game_title)
    ok = 0
    total = 0
    for e in entries:
        raw = unpack_entry(data, e, key_low32)
        total += len(raw)
        ok += 1
    data_base = min((e.offset for e in entries), default=table_end)
    print(f"[verify] entries={count} ok={ok} raw_total={total}")
    print(f"[verify] has_magic={has_magic} table_end=0x{table_end:X} data_base=0x{data_base:X} header_gap={max(0, data_base-table_end)}")
    print(f"[verify] key_low32=0x{key_low32:08X}")


def compare_dirs(a: Path, b: Path) -> tuple[int, list[str]]:
    files = sorted((a / "files").glob("*"))
    bad: list[str] = []
    checked = 0
    for pa in files:
        if not pa.is_file():
            continue
        checked += 1
        pb = b / "files" / pa.name
        if not pb.is_file():
            bad.append(f"missing: {pa.name}")
        elif pa.read_bytes() != pb.read_bytes():
            bad.append(f"diff: {pa.name}")
    return checked, bad


def roundtrip(input_dat: Path, work_dir: Path, game_title: str, encoding: str) -> None:
    if work_dir.exists():
        shutil.rmtree(work_dir)
    unpack_dir = work_dir / "unpack"
    repack_dat = work_dir / "repack.dat"
    reunpack_dir = work_dir / "reunpack"
    unpack_dat(input_dat, unpack_dir, game_title, encoding)
    pack_dat(unpack_dir, repack_dat, level=None, preserve_capacity=True)
    unpack_dat(repack_dat, reunpack_dir, game_title, encoding)
    checked, bad = compare_dirs(unpack_dir, reunpack_dir)
    print(f"[roundtrip] checked={checked} bad={len(bad)} byte_exact={input_dat.read_bytes() == repack_dat.read_bytes()}")
    for item in bad[:20]:
        print(f"[roundtrip][bad] {item}")
    if bad:
        raise SystemExit(2)


def main() -> None:
    ap = argparse.ArgumentParser(description="らぶおぶ恋愛皇帝ofLOVE! script.dat unpack/pack tool")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("unpack", help="解包 script.dat")
    p.add_argument("input", type=Path)
    p.add_argument("output", type=Path)
    p.add_argument("--game-title", default=DEFAULT_GAME_TITLE)
    p.add_argument("--encoding", default=DEFAULT_ENCODING)

    p = sub.add_parser("pack", help="按 manifest.json 回封")
    p.add_argument("input_dir", type=Path)
    p.add_argument("output", type=Path)
    p.add_argument("--level", type=int, default=None, choices=range(10), metavar="0-9")
    p.add_argument("--no-preserve-capacity", action="store_true")

    p = sub.add_parser("verify", help="只验证 dat 可解码")
    p.add_argument("input", type=Path)
    p.add_argument("--game-title", default=DEFAULT_GAME_TITLE)

    p = sub.add_parser("roundtrip", help="解包->封包->再解包，比较明文")
    p.add_argument("input", type=Path)
    p.add_argument("work_dir", type=Path)
    p.add_argument("--game-title", default=DEFAULT_GAME_TITLE)
    p.add_argument("--encoding", default=DEFAULT_ENCODING)

    args = ap.parse_args()
    if args.cmd == "unpack":
        unpack_dat(args.input, args.output, args.game_title, args.encoding)
    elif args.cmd == "pack":
        pack_dat(args.input_dir, args.output, args.level, preserve_capacity=not args.no_preserve_capacity)
    elif args.cmd == "verify":
        verify_dat(args.input, args.game_title)
    elif args.cmd == "roundtrip":
        roundtrip(args.input, args.work_dir, args.game_title, args.encoding)


if __name__ == "__main__":
    main()
