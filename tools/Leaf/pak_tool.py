#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
KCAP .pak unpack/pack tool for TtT-style archives.

Format verified from samples fnt.pak / sdt.pak and the exported exe logic:
  header:  'KCAP' + u32 file_count
  entry:   u32 flag + char name[24] + u32 offset + u32 size     (36 bytes)
  data:    if flag != 0 and size > 0: LZSS block, first 8 bytes are
             u32 packed_size, u32 unpacked_size, followed by LZSS stream
           else: raw bytes

Packing defaults to raw entries (flag=0) for modified files, because the engine
has an explicit raw branch. This is larger than the original but avoids needing
bit-identical recompression. Optional --mode literal-lzss writes a simple valid
literal-only LZSS stream.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import struct
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Iterable

MAGIC = b"KCAP"
HEADER_SIZE = 8
ENTRY_SIZE = 36
NAME_SIZE = 24
DEFAULT_ENCODING = "cp932"
MANIFEST_NAME = "_pak_manifest.json"
DELETED_FLAG = 0xCCCCCCCC


@dataclass
class PakEntry:
    index: int
    flag: int
    name: str
    name_hex: str
    offset: int
    packed_size: int
    unpacked_size: int | None = None
    packed_sha256: str | None = None
    unpacked_sha256: str | None = None


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def decode_name(raw: bytes, encoding: str = DEFAULT_ENCODING) -> str:
    raw = raw.split(b"\x00", 1)[0]
    return raw.decode(encoding, errors="replace")


def encode_name_from_entry(entry: dict, encoding: str = DEFAULT_ENCODING) -> bytes:
    # Prefer original bytes to preserve CP932-only spellings exactly.
    if entry.get("name_hex"):
        raw = bytes.fromhex(entry["name_hex"])
    else:
        raw = str(entry["name"]).encode(encoding)
    if len(raw) >= NAME_SIZE:
        raise ValueError(f"archive name too long: {entry.get('name')!r} ({len(raw)} bytes, max {NAME_SIZE - 1})")
    return raw + b"\x00" * (NAME_SIZE - len(raw))


def safe_member_path(root: Path, name: str) -> Path:
    # PAK names in the provided samples are flat names. Keep nested names safe if seen later.
    name = name.replace("\\", "/")
    parts = [p for p in name.split("/") if p not in ("", ".", "..")]
    if not parts:
        parts = ["_empty_name"]
    return root.joinpath(*parts)


def parse_pak(path: Path, encoding: str = DEFAULT_ENCODING) -> tuple[bytes, list[PakEntry]]:
    data = path.read_bytes()
    if len(data) < HEADER_SIZE or data[:4] != MAGIC:
        raise ValueError(f"not a KCAP pak: {path}")
    count = struct.unpack_from("<I", data, 4)[0]
    table_end = HEADER_SIZE + count * ENTRY_SIZE
    if table_end > len(data):
        raise ValueError(f"truncated entry table: count={count}, table_end={table_end}, file_size={len(data)}")

    entries: list[PakEntry] = []
    for i in range(count):
        p = HEADER_SIZE + i * ENTRY_SIZE
        flag = struct.unpack_from("<I", data, p)[0]
        raw_name = data[p + 4:p + 4 + NAME_SIZE].split(b"\x00", 1)[0]
        name = raw_name.decode(encoding, errors="replace")
        offset, size = struct.unpack_from("<II", data, p + 4 + NAME_SIZE)
        if offset > len(data) or offset + size > len(data):
            raise ValueError(f"entry {i} out of range: {name!r}, offset={offset}, size={size}, file_size={len(data)}")
        entries.append(PakEntry(i, flag, name, raw_name.hex(), offset, size))
    return data, entries


def lzss_decompress(stream: bytes, out_size: int | None = None) -> bytes:
    """Decompress the 4 KiB sliding-window LZSS used by sub_401870."""
    ring = bytearray([0x20] * 4096)
    r = 4078
    out = bytearray()
    pos = 0
    flags = 0

    while pos < len(stream):
        flags >>= 1
        if (flags & 0x100) == 0:
            flags = stream[pos] | 0xFF00
            pos += 1
            if pos > len(stream):
                break
        if pos >= len(stream):
            break

        b0 = stream[pos]
        pos += 1
        if flags & 1:
            out.append(b0)
            ring[r & 0xFFF] = b0
            r += 1
        else:
            if pos >= len(stream):
                break
            b1 = stream[pos]
            pos += 1
            ref = ((b1 & 0xF0) << 4) | b0
            length = (b1 & 0x0F) + 3
            for _ in range(length):
                c = ring[ref & 0xFFF]
                ref += 1
                out.append(c)
                ring[r & 0xFFF] = c
                r += 1
                if out_size is not None and len(out) >= out_size:
                    break
        if out_size is not None and len(out) >= out_size:
            break

    if out_size is not None and len(out) != out_size:
        raise ValueError(f"LZSS size mismatch: got {len(out)}, expected {out_size}")
    return bytes(out)


def lzss_literal_compress(data: bytes) -> bytes:
    """A simple valid LZSS encoder: emits all bytes as literals.

    It is not size-efficient, but the game decompressor accepts it. For patching,
    raw mode is usually preferable; this mode is provided for cases where you want
    to keep entries on the compressed branch.
    """
    out = bytearray()
    for i in range(0, len(data), 8):
        chunk = data[i:i + 8]
        out.append((1 << len(chunk)) - 1)  # 1 bit means literal.
        out.extend(chunk)
    return bytes(out)


def extract_payload(pak_data: bytes, entry: PakEntry) -> bytes:
    raw = pak_data[entry.offset:entry.offset + entry.packed_size]
    if entry.packed_size == 0:
        entry.unpacked_size = 0
        return b""
    if entry.flag != 0:
        if len(raw) < 8:
            raise ValueError(f"compressed entry too small: {entry.name}")
        packed_size_hdr, out_size = struct.unpack_from("<II", raw, 0)
        # The exe ignores packed_size_hdr and trusts the table size, but record it for diagnostics.
        entry.unpacked_size = out_size
        return lzss_decompress(raw[8:], out_size)
    entry.unpacked_size = entry.packed_size
    return raw


def cmd_list(args: argparse.Namespace) -> None:
    pak_data, entries = parse_pak(Path(args.pak), args.encoding)
    print(f"pak={args.pak}")
    print(f"entries={len(entries)} size={len(pak_data)}")
    print("index flag       offset     packed    unpacked  name")
    for e in entries:
        unpacked = ""
        if args.with_sizes and e.packed_size:
            payload = extract_payload(pak_data, e)
            unpacked = str(len(payload))
        print(f"{e.index:5d} 0x{e.flag:08X} {e.offset:10d} {e.packed_size:10d} {unpacked:>10}  {e.name}")


def cmd_unpack(args: argparse.Namespace) -> None:
    pak_path = Path(args.pak)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    pak_data, entries = parse_pak(pak_path, args.encoding)

    manifest: dict = {
        "format": "KCAP-36",
        "source_pak": pak_path.name,
        "encoding": args.encoding,
        "magic": MAGIC.decode("ascii"),
        "entry_size": ENTRY_SIZE,
        "name_size": NAME_SIZE,
        "entries": [],
    }

    total_out = 0
    for e in entries:
        raw = pak_data[e.offset:e.offset + e.packed_size]
        payload = extract_payload(pak_data, e)
        e.packed_sha256 = sha256(raw)
        e.unpacked_sha256 = sha256(payload)
        total_out += len(payload)

        out_path = safe_member_path(out_dir, e.name)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(payload)

        obj = asdict(e)
        obj["path"] = out_path.relative_to(out_dir).as_posix()
        manifest["entries"].append(obj)

    manifest_path = out_dir / MANIFEST_NAME
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")
    print(f"[unpack] entries={len(entries)} decoded_bytes={total_out} output={out_dir}")
    print(f"[unpack] manifest={manifest_path}")


def build_payload(data: bytes, mode: str) -> tuple[int, bytes]:
    if len(data) == 0:
        return DELETED_FLAG, b""  # caller may override with original flag for zero-size entries
    if mode == "raw":
        return 0, data
    if mode == "literal-lzss":
        stream = lzss_literal_compress(data)
        block = struct.pack("<II", len(stream) + 8, len(data)) + stream
        return 1, block
    raise ValueError(f"unknown pack mode: {mode}")


def cmd_pack(args: argparse.Namespace) -> None:
    in_dir = Path(args.in_dir)
    manifest_path = Path(args.manifest) if args.manifest else in_dir / MANIFEST_NAME
    if not manifest_path.exists():
        raise FileNotFoundError(f"manifest not found: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    entries = manifest.get("entries")
    if not isinstance(entries, list):
        raise ValueError("manifest missing entries list")
    encoding = args.encoding or manifest.get("encoding") or DEFAULT_ENCODING

    table_size = HEADER_SIZE + len(entries) * ENTRY_SIZE
    table = bytearray(MAGIC + struct.pack("<I", len(entries)) + b"\x00" * (len(entries) * ENTRY_SIZE))
    body = bytearray()

    for i, ent in enumerate(entries):
        name = ent.get("name", "")
        rel_path = ent.get("path") or name
        src_path = safe_member_path(in_dir, rel_path)
        if src_path.exists():
            data = src_path.read_bytes()
        else:
            # Missing zero-length entries are allowed; missing real files are errors.
            if int(ent.get("unpacked_size") or 0) == 0:
                data = b""
            else:
                raise FileNotFoundError(f"missing unpacked file for entry {i}: {src_path}")

        if len(data) == 0:
            # Preserve original special marker such as 0xCCCCCCCC for empty/deleted entries.
            flag = int(ent.get("flag", 0)) & 0xFFFFFFFF
            payload = b""
        else:
            flag, payload = build_payload(data, args.mode)

        offset = table_size + len(body)
        size = len(payload)
        name_raw = encode_name_from_entry(ent, encoding)
        ep = HEADER_SIZE + i * ENTRY_SIZE
        table[ep:ep + ENTRY_SIZE] = struct.pack("<I", flag) + name_raw + struct.pack("<II", offset, size)
        body.extend(payload)

    out_path = Path(args.out_pak)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(bytes(table) + bytes(body))
    print(f"[pack] entries={len(entries)} mode={args.mode} output={out_path} size={out_path.stat().st_size}")


def cmd_verify(args: argparse.Namespace) -> None:
    pak_data, entries = parse_pak(Path(args.pak), args.encoding)
    root = Path(args.dir)
    bad = 0
    ok = 0
    for e in entries:
        payload = extract_payload(pak_data, e)
        path = safe_member_path(root, e.name)
        if not path.exists():
            print(f"[verify][missing] {e.name}")
            bad += 1
            continue
        disk = path.read_bytes()
        if disk != payload:
            print(f"[verify][diff] {e.name}: pak={len(payload)} disk={len(disk)}")
            bad += 1
        else:
            ok += 1
    print(f"[verify] ok={ok} bad={bad}")
    if bad:
        raise SystemExit(1)


def make_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="KCAP .pak unpack/pack tool")
    p.add_argument("--encoding", default=DEFAULT_ENCODING, help="file-name encoding, default cp932")
    sub = p.add_subparsers(dest="command", required=True)

    sp = sub.add_parser("list", help="list archive entries")
    sp.add_argument("pak")
    sp.add_argument("--with-sizes", action="store_true", help="also decompress entries to show unpacked size")
    sp.set_defaults(func=cmd_list)

    sp = sub.add_parser("unpack", help="unpack archive and write decoded files + manifest")
    sp.add_argument("pak")
    sp.add_argument("out_dir")
    sp.set_defaults(func=cmd_unpack)

    sp = sub.add_parser("pack", help="pack files according to _pak_manifest.json")
    sp.add_argument("in_dir")
    sp.add_argument("out_pak")
    sp.add_argument("--manifest", help="manifest path; default <in_dir>/_pak_manifest.json")
    sp.add_argument("--mode", choices=["raw", "literal-lzss"], default="raw", help="raw is recommended for modified files")
    sp.set_defaults(func=cmd_pack)

    sp = sub.add_parser("verify", help="compare decoded pak contents with an unpacked directory")
    sp.add_argument("pak")
    sp.add_argument("dir")
    sp.set_defaults(func=cmd_verify)
    return p


def main(argv: Iterable[str] | None = None) -> int:
    args = make_argparser().parse_args(argv)
    args.func(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
