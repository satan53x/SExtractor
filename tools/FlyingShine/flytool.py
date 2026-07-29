#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Flying Shine PD archive tool (GaRBro PD/2 / FlyingShinePDFile).

Usage:
  python flytool.py unpack <archive.pd> <out_dir>
  python flytool.py pack <in_dir> <archive.pd>
"""

from __future__ import annotations

import argparse
import json
import struct
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

SIGNATURE = b"FlyingShinePDFile\x00"
HEADER_SIZE = 0x20
ENTRY_SIZE = 0x30
NAME_FIELD_SIZE = 0x24
MANIFEST_NAME = ".flytool_manifest.json"
CP932 = "cp932"


class PdError(Exception):
    pass


def xor_bytes(data: bytes, key: int) -> bytes:
    k = key & 0xFF
    if k == 0:
        return data
    return bytes(b ^ k for b in data)


def is_script_name(name: str) -> bool:
    lower = name.lower()
    return lower.endswith(".def") or lower.endswith(".dsf")


def is_ogg_name(name: str) -> bool:
    return name.lower().endswith(".ogg")


def decrypt_script_payload(data: bytes) -> Tuple[bytes, Optional[int], bool]:
    """GaRBro OpenEntry for .def/.dsf: key = last_byte ^ 0x0A; require prev ^ key == 0x0D."""
    if len(data) < 2:
        return data, None, False
    key = data[-1] ^ 0x0A
    if (data[-2] ^ key) != 0x0D:
        return data, None, False
    return xor_bytes(data, key), key, True


def encrypt_script_payload(plain: bytes, key: int) -> bytes:
    if len(plain) < 2:
        raise PdError("script payload too small to encrypt")
    if plain[-2] != 0x0D or plain[-1] != 0x0A:
        raise PdError("script payload must end with CRLF (\\r\\n)")
    return xor_bytes(plain, key & 0xFF)


def fix_ogg_header(data: bytes) -> bytes:
    """GaRBro OpenOgg repair for broken first-page header."""
    if len(data) <= 0x22:
        return data
    if data[0:4] != b"OggS":
        return data
    if not (
        data[0x1A] != 1
        and data[0x1B] == 0x1E
        and data[0x1C] == 1
        and data[0x1D:0x24] == b"vorbis"
    ):
        return data
    out = bytearray(data)
    out[0x1A] = 1
    return bytes(out)


def parse_header(data: bytes) -> Dict[str, Any]:
    if len(data) < HEADER_SIZE:
        raise PdError("file too small")
    if data[0:18] != SIGNATURE:
        raise PdError("not a FlyingShinePDFile archive")
    crc = struct.unpack_from("<H", data, 0x12)[0]
    key = data[0x14]
    reserved = data[0x15:0x18]
    stamp = struct.unpack_from("<I", data, 0x18)[0]
    count = struct.unpack_from("<I", data, 0x1C)[0]
    if count <= 0 or count > 0x10000:
        raise PdError(f"invalid entry count: {count}")
    if HEADER_SIZE + count * ENTRY_SIZE > len(data):
        raise PdError("index exceeds file size")
    return {
        "crc": crc,
        "key": key,
        "reserved": reserved.hex(),
        "stamp": stamp,
        "count": count,
    }


def read_entries(data: bytes, key: int, count: int) -> List[Dict[str, Any]]:
    entries: List[Dict[str, Any]] = []
    off = HEADER_SIZE
    for i in range(count):
        raw = data[off : off + ENTRY_SIZE]
        dec = bytearray(xor_bytes(raw, key))
        name_bytes = bytes(dec[0:NAME_FIELD_SIZE])
        z = name_bytes.find(b"\x00")
        if z <= 0 or z >= NAME_FIELD_SIZE:
            raise PdError(f"entry {i}: invalid name")
        try:
            name = name_bytes[:z].decode(CP932)
        except UnicodeDecodeError as exc:
            raise PdError(f"entry {i}: name is not cp932") from exc
        shift = struct.unpack_from("<I", dec, 0x24)[0]
        offset = struct.unpack_from("<I", dec, 0x28)[0] - shift
        size = struct.unpack_from("<I", dec, 0x2C)[0] - shift
        if offset < 0 or size < 0 or offset + size > len(data):
            raise PdError(f"entry {i} ({name}): invalid offset/size")
        entries.append(
            {
                "name": name,
                "shift": shift,
                "offset": int(offset),
                "size": int(size),
                "name_pad": name_bytes[z + 1 :].hex(),
            }
        )
        off += ENTRY_SIZE
    return entries


def unpack_archive(archive: Path, out_dir: Path) -> None:
    data = archive.read_bytes()
    header = parse_header(data)
    entries = read_entries(data, header["key"], header["count"])
    out_dir.mkdir(parents=True, exist_ok=True)

    manifest_entries: List[Dict[str, Any]] = []
    for ent in entries:
        raw = data[ent["offset"] : ent["offset"] + ent["size"]]
        payload = raw
        content_key = None
        encrypted = False
        ogg_fixed = False

        if is_script_name(ent["name"]):
            payload, content_key, encrypted = decrypt_script_payload(raw)
        elif is_ogg_name(ent["name"]):
            fixed = fix_ogg_header(raw)
            ogg_fixed = fixed != raw
            payload = fixed

        safe_name = Path(ent["name"]).name
        if safe_name != ent["name"]:
            raise PdError(f"refusing nested entry name: {ent['name']!r}")
        target = out_dir / safe_name
        if target.exists():
            raise PdError(f"duplicate entry name: {safe_name}")
        target.write_bytes(payload)

        manifest_entries.append(
            {
                "name": ent["name"],
                "shift": ent["shift"],
                "offset": ent["offset"],
                "size": ent["size"],
                "name_pad": ent["name_pad"],
                "content_key": content_key if content_key is not None else ent["shift"],
                "encrypted": encrypted,
                "ogg_fixed": ogg_fixed,
                "extracted_size": len(payload),
            }
        )

    manifest = {
        "format": "FlyingShinePDFile",
        "version": 2,
        "source": archive.name,
        "header": header,
        "entries": manifest_entries,
    }
    (out_dir / MANIFEST_NAME).write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"unpacked {len(entries)} files -> {out_dir}")


def build_name_field(name: str, name_pad_hex: Optional[str] = None) -> bytes:
    try:
        name_bytes = name.encode(CP932)
    except UnicodeEncodeError as exc:
        raise PdError(f"file name not encodable as cp932: {name}") from exc
    if len(name_bytes) >= NAME_FIELD_SIZE:
        raise PdError(f"file name too long: {name}")
    field = bytearray(NAME_FIELD_SIZE)
    field[: len(name_bytes)] = name_bytes
    field[len(name_bytes)] = 0
    if name_pad_hex:
        pad = bytes.fromhex(name_pad_hex)
        start = len(name_bytes) + 1
        field[start : start + len(pad)] = pad[: NAME_FIELD_SIZE - start]
    return bytes(field)


def ensure_crlf_ending(data: bytes) -> bytes:
    if len(data) >= 2 and data[-2] == 0x0D and data[-1] == 0x0A:
        return data
    if data.endswith(b"\n") and not data.endswith(b"\r\n"):
        return data[:-1] + b"\r\n"
    return data + b"\r\n"


def pack_archive(in_dir: Path, archive: Path) -> None:
    if not in_dir.is_dir():
        raise PdError(f"input directory not found: {in_dir}")

    manifest_path = in_dir / MANIFEST_NAME
    manifest: Optional[Dict[str, Any]] = None
    if manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    files: List[Dict[str, Any]] = []
    if manifest and manifest.get("entries"):
        for ent in manifest["entries"]:
            name = ent["name"]
            path = in_dir / Path(name).name
            if not path.is_file():
                raise PdError(f"missing file for manifest entry: {name}")
            files.append(
                {
                    "name": name,
                    "path": path,
                    "shift": ent.get("shift"),
                    "content_key": ent.get("content_key", ent.get("shift")),
                    "name_pad": ent.get("name_pad"),
                    "encrypted": ent.get("encrypted"),
                }
            )
    else:
        names = sorted(
            p.name
            for p in in_dir.iterdir()
            if p.is_file() and p.name != MANIFEST_NAME and not p.name.startswith(".")
        )
        if not names:
            raise PdError("no files to pack")
        for name in names:
            files.append(
                {
                    "name": name,
                    "path": in_dir / name,
                    "shift": None,
                    "content_key": None,
                    "name_pad": None,
                    "encrypted": None,
                }
            )

    if len(files) > 0x10000:
        raise PdError("too many files")

    if manifest and manifest.get("header"):
        hdr = manifest["header"]
        key = int(hdr.get("key", 0x48)) & 0xFF
        crc = int(hdr.get("crc", 0)) & 0xFFFF
        stamp = int(hdr.get("stamp", 20040810)) & 0xFFFFFFFF
        reserved = bytes.fromhex(hdr.get("reserved", "000000"))
        if len(reserved) != 3:
            reserved = b"\x00\x00\x00"
    else:
        key = 0x48
        crc = 0
        stamp = 20040810
        reserved = b"\x00\x00\x00"

    count = len(files)
    data_offset = HEADER_SIZE + count * ENTRY_SIZE
    blobs: List[bytes] = []
    meta: List[Tuple[int, int, int, bytes]] = []
    cursor = data_offset
    used_keys = set()

    for item in files:
        plain = item["path"].read_bytes()
        name = item["name"]
        shift = item.get("shift")
        content_key = item.get("content_key")
        encrypted_flag = item.get("encrypted")

        if is_script_name(name):
            should_encrypt = True if encrypted_flag is None else bool(encrypted_flag)
            if should_encrypt:
                if shift is not None:
                    ck = int(shift) & 0xFF
                elif content_key is not None:
                    ck = int(content_key) & 0xFF
                else:
                    ck = next((k for k in range(1, 256) if k not in used_keys), 1)
                used_keys.add(ck)
                plain = ensure_crlf_ending(plain)
                blob = encrypt_script_payload(plain, ck)
                shift = ck
            else:
                blob = plain
                shift = 0 if shift is None else int(shift)
        else:
            blob = plain
            shift = 0 if shift is None else int(shift)

        name_field = build_name_field(name, item.get("name_pad"))
        size = len(blob)
        blobs.append(blob)
        meta.append((shift, cursor, size, name_field))
        cursor += size

    out = bytearray()
    out += SIGNATURE
    out += struct.pack("<H", crc)
    out += bytes([key & 0xFF])
    out += reserved
    out += struct.pack("<I", stamp)
    out += struct.pack("<I", count)

    for shift, offset, size, name_field in meta:
        entry = bytearray(ENTRY_SIZE)
        entry[0:NAME_FIELD_SIZE] = name_field
        struct.pack_into("<I", entry, 0x24, shift & 0xFFFFFFFF)
        struct.pack_into("<I", entry, 0x28, (offset + shift) & 0xFFFFFFFF)
        struct.pack_into("<I", entry, 0x2C, (size + shift) & 0xFFFFFFFF)
        out += xor_bytes(bytes(entry), key)

    for blob in blobs:
        out += blob

    archive.parent.mkdir(parents=True, exist_ok=True)
    archive.write_bytes(bytes(out))
    print(f"packed {count} files -> {archive} ({len(out)} bytes)")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Flying Shine PD (FlyingShinePDFile) unpack/pack tool",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_unpack = sub.add_parser("unpack", help="unpack archive to directory")
    p_unpack.add_argument("archive", type=Path)
    p_unpack.add_argument("out_dir", type=Path)

    p_pack = sub.add_parser("pack", help="pack directory to archive")
    p_pack.add_argument("in_dir", type=Path)
    p_pack.add_argument("archive", type=Path)
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "unpack":
            unpack_archive(args.archive, args.out_dir)
        elif args.command == "pack":
            pack_archive(args.in_dir, args.archive)
        else:
            parser.error(f"unknown command: {args.command}")
        return 0
    except PdError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
