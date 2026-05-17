# -*- coding: utf-8 -*-
"""AGSI SB2 结构级解包 / 封包工具。

只处理 .sb 的大段结构，不做文本提取、不做文本注入。

用法：
    python agsi_sb_tool.py unpack majo2.sb dump_majo2 --overwrite
    python agsi_sb_tool.py pack dump_majo2 majo2_repack.sb --compare-original majo2.sb
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import struct
from pathlib import Path
from typing import Callable, Dict, List, Tuple

MAGIC = b"SB2 "
HEADER_SIZE = 0x2C
DUMP_FORMAT = "AGSI_SB2_DUMP_SIMPLE_V1"

SEGMENT_PLAN = [
    ("CODE", "CODE.bin"),
    ("TTBL", "TTBL.bin"),
    ("FTBL", "FTBL_0.bin"),
    ("FTBL", "FTBL_1.bin"),
    ("VTBL", "VTBL.bin"),
    ("CSTR", "CSTR.bin"),
    ("CDBL", "CDBL.bin"),
    ("DBG_", "DBG_0.bin"),
    ("DBG_", "DBG_1.bin"),
]


def u32(data: bytes, off: int) -> int:
    return struct.unpack_from("<I", data, off)[0]


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


class Reader:
    def __init__(self, data: bytes):
        self.data = data
        self.pos = 0

    def read(self, n: int) -> bytes:
        if n < 0:
            raise ValueError(f"negative read size: {n}")
        if self.pos + n > len(self.data):
            raise EOFError(f"read out of range: pos=0x{self.pos:x}, size=0x{n:x}, file=0x{len(self.data):x}")
        out = self.data[self.pos:self.pos + n]
        self.pos += n
        return out

    def read_u32(self) -> int:
        return u32(self.read(4), 0)

    def expect_tag(self, tag: bytes) -> int:
        off = self.pos
        got = self.read(4)
        if got != tag:
            raise ValueError(f"tag mismatch at 0x{off:x}: got={got!r}, expected={tag!r}")
        return off


def skip_len_string_plus_ints(r: Reader, int_count_after: int) -> None:
    n = r.read_u32()
    r.read(n)
    r.read(4 * int_count_after)


def skip_ttbl(r: Reader, count: int) -> None:
    for _ in range(count):
        r.read(8)
        member_count = u32(r.data, r.pos - 4)
        for _ in range(member_count):
            r.read(4)
            _dim_count = r.read_u32()
            r.read(16)
            r.read(4)


def skip_ftbl(r: Reader, count: int) -> None:
    for _ in range(count):
        skip_len_string_plus_ints(r, 3)


def skip_vtbl(r: Reader, count: int) -> None:
    r.read(count * 12)


def skip_cstr(r: Reader, count: int) -> Tuple[int, int, int]:
    table_offset = r.pos
    total = 0
    for _ in range(count):
        _off = r.read_u32()
        size = r.read_u32()
        total += size
    pool_offset = r.pos
    r.read(total)
    return table_offset, pool_offset, total


def skip_cdbl(r: Reader, count: int) -> None:
    r.read(count * 8)


def skip_dbg_files(r: Reader) -> None:
    count = r.read_u32()
    for _ in range(count):
        n = r.read_u32()
        r.read(n)


def skip_dbg_lines(r: Reader) -> None:
    count = r.read_u32()
    r.read(count * 12)


def parse_segments(data: bytes) -> Tuple[bytes, Tuple[int, ...], List[Dict[str, object]]]:
    r = Reader(data)
    header = r.read(HEADER_SIZE)
    if header[:4] != MAGIC:
        raise ValueError(f"not SB2 file: magic={header[:4]!r}")
    header_values = struct.unpack("<11I", header)

    code_size = header_values[3]
    ttbl_count = header_values[5]
    ftbl0_count = header_values[6]
    ftbl1_count = header_values[7]
    vtbl_count = header_values[8]
    cstr_count = header_values[9]
    cdbl_count = header_values[10]

    segments: List[Dict[str, object]] = []

    def take(index: int, tag_text: str, file_name: str, skip_func: Callable[[], object]) -> None:
        tag = tag_text.encode("ascii")
        tag_offset = r.expect_tag(tag)
        data_offset = r.pos
        extra = skip_func()
        data_end = r.pos
        seg = {
            "index": index,
            "tag": tag_text,
            "file": file_name,
            "tag_offset": tag_offset,
            "data_offset": data_offset,
            "size": data_end - data_offset,
        }
        if isinstance(extra, tuple) and tag_text == "CSTR":
            table_offset, pool_offset, pool_size = extra
            seg.update({
                "cstr_count": cstr_count,
                "cstr_table_offset_in_file": table_offset,
                "cstr_pool_offset_in_file": pool_offset,
                "cstr_pool_size": pool_size,
                "cstr_table_size": cstr_count * 8,
            })
        segments.append(seg)

    take(0, "CODE", "CODE.bin", lambda: r.read(code_size))
    take(1, "TTBL", "TTBL.bin", lambda: skip_ttbl(r, ttbl_count))
    take(2, "FTBL", "FTBL_0.bin", lambda: skip_ftbl(r, ftbl0_count))
    take(3, "FTBL", "FTBL_1.bin", lambda: skip_ftbl(r, ftbl1_count))
    take(4, "VTBL", "VTBL.bin", lambda: skip_vtbl(r, vtbl_count))
    take(5, "CSTR", "CSTR.bin", lambda: skip_cstr(r, cstr_count))
    take(6, "CDBL", "CDBL.bin", lambda: skip_cdbl(r, cdbl_count))
    take(7, "DBG_", "DBG_0.bin", lambda: skip_dbg_files(r))
    take(8, "DBG_", "DBG_1.bin", lambda: skip_dbg_lines(r))

    if r.pos != len(data):
        # 这里不直接失败，保留尾部信息；目前 majo2.sb 应该正好读到 EOF。
        segments.append({
            "index": 9,
            "tag": "TAIL",
            "file": "TAIL.bin",
            "tag_offset": r.pos,
            "data_offset": r.pos,
            "size": len(data) - r.pos,
            "no_tag": True,
        })
    return header, header_values, segments


def cmd_unpack(args: argparse.Namespace) -> None:
    src = Path(args.input)
    out_dir = Path(args.output_dir)
    data = src.read_bytes()
    header, header_values, segments = parse_segments(data)

    if out_dir.exists():
        if args.overwrite:
            shutil.rmtree(out_dir)
        elif any(out_dir.iterdir()):
            raise FileExistsError(f"output dir is not empty: {out_dir}")
    out_dir.mkdir(parents=True, exist_ok=True)

    (out_dir / "header.bin").write_bytes(header)
    for seg in segments:
        file_name = str(seg["file"])
        data_offset = int(seg["data_offset"])
        size = int(seg["size"])
        (out_dir / file_name).write_bytes(data[data_offset:data_offset + size])

    manifest = {
        "format": DUMP_FORMAT,
        "source_file": src.name,
        "source_size": len(data),
        "source_sha256": hashlib.sha256(data).hexdigest(),
        "header_values": list(header_values),
        "segments": segments,
        "notes": "*.bin 为去掉 4 字节 tag 后的段 payload；pack 时按 manifest 顺序补回 tag。",
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "input": str(src),
        "output_dir": str(out_dir),
        "segments": len(segments),
        "source_size": len(data),
    }, ensure_ascii=False, indent=2))


def cmd_pack(args: argparse.Namespace) -> None:
    dump_dir = Path(args.dump_dir)
    out_path = Path(args.output)
    manifest_path = dump_dir / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"manifest.json not found: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("format") != DUMP_FORMAT:
        raise ValueError(f"unsupported dump format: {manifest.get('format')!r}")

    header = bytearray((dump_dir / "header.bin").read_bytes())
    if len(header) != HEADER_SIZE or bytes(header[:4]) != MAGIC:
        raise ValueError("bad header.bin")

    # CODE 段长度可能会被手动改动，因此默认回填 header[0x0C]。
    segments = manifest["segments"]
    code_file = dump_dir / segments[0]["file"]
    struct.pack_into("<I", header, 0x0C, code_file.stat().st_size)

    out = bytearray(header)
    for seg in segments:
        file_name = str(seg["file"])
        payload = (dump_dir / file_name).read_bytes()
        if not seg.get("no_tag"):
            tag = str(seg["tag"]).encode("ascii")
            if len(tag) != 4:
                raise ValueError(f"bad tag in manifest: {seg!r}")
            out += tag
        out += payload

    out_path.write_bytes(bytes(out))
    report = {
        "dump_dir": str(dump_dir),
        "output": str(out_path),
        "output_size": out_path.stat().st_size,
        "output_sha256": sha256_file(out_path),
    }
    if args.compare_original:
        original = Path(args.compare_original)
        report.update({
            "original": str(original),
            "original_size": original.stat().st_size,
            "original_sha256": sha256_file(original),
            "byte_equal": original.read_bytes() == out_path.read_bytes(),
        })
    print(json.dumps(report, ensure_ascii=False, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description="AGSI SB2 结构级解包/封包工具")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_unpack = sub.add_parser("unpack", help=".sb -> dump_dir")
    p_unpack.add_argument("input", help="输入 .sb")
    p_unpack.add_argument("output_dir", help="输出目录")
    p_unpack.add_argument("--overwrite", action="store_true", help="覆盖已有输出目录")
    p_unpack.set_defaults(func=cmd_unpack)

    p_pack = sub.add_parser("pack", help="dump_dir -> .sb")
    p_pack.add_argument("dump_dir", help="解包目录")
    p_pack.add_argument("output", help="输出 .sb")
    p_pack.add_argument("--compare-original", help="可选：与原始 .sb 做字节级对比")
    p_pack.set_defaults(func=cmd_pack)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
