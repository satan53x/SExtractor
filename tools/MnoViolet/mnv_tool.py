#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
M no Violet DAT unpack/pack helper.

Archive format, as used by SACRIFICE script.dat:
    u32 count
    count * ([fixed-size nul-padded name][u32 size][u32 offset])
    file data, stored consecutively without encryption

Each entry in script.dat is an LZSS-compressed script stream:
    16 zero bytes
    u32 compressed_size
    u32 unpacked_size
    compressed bytes
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import struct
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable


NAME_SIZES = (100, 68, 44)
DEFAULT_NAME_ENCODING = "cp932"
MANIFEST_NAME = "_mnv_manifest.json"
LZSS_FRAME_SIZE = 0x1000
LZSS_FRAME_INIT_POS = 4078
SCRIPT_HEADER_SIZE = 24


@dataclass
class Entry:
    index: int
    raw_name: bytes
    name: str
    size: int
    offset: int

    @property
    def stored_name(self) -> bytes:
        return self.raw_name.split(b"\0", 1)[0]


class MnvError(Exception):
    pass


def log(message: str) -> None:
    print(f"[MNV] {message}")


def read_u32(data: bytes, offset: int) -> int:
    if offset + 4 > len(data):
        raise MnvError(f"读取 u32 越界: 0x{offset:X}")
    return struct.unpack_from("<I", data, offset)[0]


def decode_name(raw_name: bytes, encoding: str) -> str:
    name_bytes = raw_name.split(b"\0", 1)[0]
    try:
        return name_bytes.decode(encoding)
    except UnicodeDecodeError:
        return name_bytes.decode(encoding, errors="replace")


def encode_name(name: str, encoding: str) -> bytes:
    try:
        return name.encode(encoding)
    except UnicodeEncodeError as exc:
        raise MnvError(f"文件名无法用 {encoding} 编码: {name!r}") from exc


def find_name_size(data: bytes) -> int:
    count = read_u32(data, 0)
    if count <= 0 or count > 100000:
        raise MnvError(f"文件数量异常: {count}")

    for name_size in NAME_SIZES:
        index_size = (name_size + 8) * count
        first_offset_pos = 4 + name_size + 4
        if first_offset_pos + 4 > len(data):
            continue
        first_offset = read_u32(data, first_offset_pos)
        if first_offset == 4 + index_size and first_offset < len(data):
            return name_size

    raise MnvError("无法识别 DAT 索引宽度（已尝试 100/68/44 字节文件名）")


def read_entries(data: bytes, name_encoding: str) -> tuple[int, list[Entry]]:
    name_size = find_name_size(data)
    count = read_u32(data, 0)
    index_end = 4 + (name_size + 8) * count
    entries: list[Entry] = []
    pos = 4

    for index in range(count):
        raw_name = data[pos : pos + name_size]
        if not raw_name.split(b"\0", 1)[0]:
            raise MnvError(f"第 {index} 项文件名为空")
        size = read_u32(data, pos + name_size)
        offset = read_u32(data, pos + name_size + 4)
        if offset < index_end or offset + size > len(data):
            raise MnvError(
                f"第 {index} 项放置越界: offset=0x{offset:X}, size=0x{size:X}"
            )
        entries.append(
            Entry(
                index=index,
                raw_name=raw_name,
                name=decode_name(raw_name, name_encoding),
                size=size,
                offset=offset,
            )
        )
        pos += name_size + 8

    return name_size, entries


def safe_output_path(base_dir: Path, archive_name: str) -> Path:
    parts: list[str] = []
    for part in archive_name.replace("/", "\\").split("\\"):
        if not part or part in (".", "..") or ":" in part:
            raise MnvError(f"不安全的封包路径: {archive_name!r}")
        parts.append(part)
    if not parts:
        raise MnvError(f"不安全的封包路径: {archive_name!r}")
    return base_dir.joinpath(*parts)


def rel_archive_path(path: Path, base_dir: Path) -> str:
    return "\\".join(path.relative_to(base_dir).parts)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def is_script_payload(blob: bytes) -> bool:
    if len(blob) < SCRIPT_HEADER_SIZE:
        return False
    compressed_size, unpacked_size = struct.unpack_from("<II", blob, 16)
    return (
        compressed_size == len(blob) - SCRIPT_HEADER_SIZE
        and unpacked_size > 0
        and unpacked_size < 0x10000000
    )


def lzss_decompress(src: bytes, unpacked_size: int) -> bytes:
    frame = bytearray(LZSS_FRAME_SIZE)
    frame_pos = LZSS_FRAME_INIT_POS
    flags = 0
    src_pos = 0
    out = bytearray()

    while src_pos < len(src) and len(out) < unpacked_size:
        flags >>= 1
        if flags & 0x100 == 0:
            flags = src[src_pos] | 0xFF00
            src_pos += 1

        if flags & 1:
            if src_pos >= len(src):
                break
            value = src[src_pos]
            src_pos += 1
            out.append(value)
            frame[frame_pos] = value
            frame_pos = (frame_pos + 1) & 0xFFF
        else:
            if src_pos + 1 >= len(src):
                break
            lo = src[src_pos]
            hi = src[src_pos + 1]
            src_pos += 2
            back_pos = ((hi & 0xF0) << 4) | lo
            count = (hi & 0x0F) + 3
            for i in range(count):
                value = frame[(back_pos + i) & 0xFFF]
                out.append(value)
                frame[frame_pos] = value
                frame_pos = (frame_pos + 1) & 0xFFF
                if len(out) >= unpacked_size:
                    break

    if len(out) != unpacked_size:
        raise MnvError(
            f"LZSS 解压长度不匹配: 期望 {unpacked_size}, 实际 {len(out)}"
        )
    return bytes(out)


def lzss_compress_literals(data: bytes) -> bytes:
    out = bytearray()
    for pos in range(0, len(data), 8):
        chunk = data[pos : pos + 8]
        out.append((1 << len(chunk)) - 1)
        out.extend(chunk)
    return bytes(out)


def unpack_script_payload(blob: bytes) -> tuple[bytes, dict]:
    if not is_script_payload(blob):
        return blob, {"compressed": False}

    header_prefix = blob[:16]
    compressed_size, unpacked_size = struct.unpack_from("<II", blob, 16)
    compressed = blob[SCRIPT_HEADER_SIZE:]
    unpacked = lzss_decompress(compressed, unpacked_size)
    return unpacked, {
        "compressed": True,
        "header_prefix_hex": header_prefix.hex(),
        "compressed_size": compressed_size,
        "unpacked_size": unpacked_size,
        "raw_sha256": hashlib.sha256(blob).hexdigest(),
        "unpacked_sha256": hashlib.sha256(unpacked).hexdigest(),
    }


def pack_script_payload(data: bytes, item: dict) -> bytes:
    compression = item.get("compression")
    if not isinstance(compression, dict) or not compression.get("compressed"):
        return data

    prefix_hex = compression.get("header_prefix_hex")
    if isinstance(prefix_hex, str) and prefix_hex:
        prefix = bytes.fromhex(prefix_hex)
    else:
        prefix = b"\0" * 16
    if len(prefix) != 16:
        raise MnvError("压缩脚本头前缀长度异常")

    compressed = lzss_compress_literals(data)
    return prefix + struct.pack("<II", len(compressed), len(data)) + compressed


def manifest_from_entries(
    dat_path: Path,
    data: bytes,
    name_size: int,
    entries: Iterable[Entry],
) -> dict:
    return {
        "format": "MnoViolet.DAT",
        "payload_mode": "unpacked_lzss",
        "source": dat_path.name,
        "name_size": name_size,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "entries": [
            {
                "index": e.index,
                "name": e.name,
                "path": e.name.replace("/", "\\"),
                "raw_name_hex": e.raw_name.hex(),
                "packed_size": e.size,
                "offset": e.offset,
                "sha256": sha256_bytes(data[e.offset : e.offset + e.size]),
                "compression": unpack_script_payload(
                    data[e.offset : e.offset + e.size]
                )[1],
            }
            for e in entries
        ],
    }


def write_manifest(path: Path, manifest: dict) -> None:
    path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def load_manifest(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise MnvError(f"找不到 manifest: {path}") from exc
    except json.JSONDecodeError as exc:
        raise MnvError(f"manifest 不是合法 JSON: {path}") from exc


def command_list(args: argparse.Namespace) -> int:
    dat_path = Path(args.dat)
    data = dat_path.read_bytes()
    name_size, entries = read_entries(data, args.name_encoding)

    log(f"文件: {dat_path}")
    log(f"数量: {len(entries)}")
    log(f"文件名槽宽: {name_size} 字节")
    for e in entries:
        print(f"{e.index:04d}  off=0x{e.offset:08X}  size={e.size:8d}  {e.name}")

    if args.output:
        manifest = manifest_from_entries(dat_path, data, name_size, entries)
        write_manifest(Path(args.output), manifest)
        log(f"已写出清单: {args.output}")
    return 0


def command_unpack(args: argparse.Namespace) -> int:
    dat_path = Path(args.dat)
    out_dir = Path(args.out_dir)
    data = dat_path.read_bytes()
    name_size, entries = read_entries(data, args.name_encoding)

    if out_dir.exists() and any(out_dir.iterdir()) and not args.force:
        raise MnvError(f"输出目录非空: {out_dir}（需要覆盖时加 --force）")
    out_dir.mkdir(parents=True, exist_ok=True)

    for e in entries:
        out_path = safe_output_path(out_dir, e.name)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        payload, _compression = unpack_script_payload(data[e.offset : e.offset + e.size])
        out_path.write_bytes(payload)

    manifest = manifest_from_entries(dat_path, data, name_size, entries)
    write_manifest(out_dir / args.manifest, manifest)

    log(f"已解包 {len(entries)} 个文件到: {out_dir}")
    log(f"已写出 manifest: {out_dir / args.manifest}")
    return 0


def build_archive_from_manifest(
    in_dir: Path,
    out_path: Path,
    manifest: dict,
    name_encoding: str,
) -> None:
    entries = manifest.get("entries")
    if not isinstance(entries, list) or not entries:
        raise MnvError("manifest 中没有 entries")

    name_size = int(manifest.get("name_size") or 0)
    if name_size <= 0:
        raise MnvError("manifest 缺少 name_size")

    count = len(entries)
    data_start = 4 + (name_size + 8) * count
    offset = data_start
    index_records: list[tuple[bytes, bytes, int, int]] = []
    payloads: list[bytes] = []

    for expected_index, item in enumerate(entries):
        index = int(item.get("index", expected_index))
        if index != expected_index:
            raise MnvError(f"manifest index 不连续: 期望 {expected_index}, 实际 {index}")

        archive_path = item.get("path") or item.get("name")
        if not isinstance(archive_path, str) or not archive_path:
            raise MnvError(f"第 {index} 项缺少 path/name")

        raw_name_hex = item.get("raw_name_hex")
        if isinstance(raw_name_hex, str) and raw_name_hex:
            raw_name = bytes.fromhex(raw_name_hex)
            if len(raw_name) != name_size:
                raise MnvError(f"第 {index} 项 raw_name_hex 长度不等于 name_size")
        else:
            raw_stored = encode_name(archive_path, name_encoding)
            if len(raw_stored) >= name_size:
                raise MnvError(f"第 {index} 项文件名过长: {archive_path!r}")
            raw_name = raw_stored + b"\0" * (name_size - len(raw_stored))

        file_path = safe_output_path(in_dir, archive_path)
        payload = pack_script_payload(file_path.read_bytes(), item)
        index_records.append((raw_name, payload, len(payload), offset))
        payloads.append(payload)
        offset += len(payload)

    with out_path.open("wb") as f:
        f.write(struct.pack("<I", count))
        for raw_name, _payload, size, entry_offset in index_records:
            f.write(raw_name)
            f.write(struct.pack("<II", size, entry_offset))
        for payload in payloads:
            f.write(payload)


def command_pack(args: argparse.Namespace) -> int:
    in_dir = Path(args.in_dir)
    manifest_path = Path(args.manifest) if args.manifest else in_dir / MANIFEST_NAME
    out_path = Path(args.output)
    manifest = load_manifest(manifest_path)
    build_archive_from_manifest(in_dir, out_path, manifest, args.name_encoding)
    log(f"已封包: {out_path}")
    log(f"SHA256: {sha256_file(out_path)}")
    return 0


def command_verify(args: argparse.Namespace) -> int:
    dat_path = Path(args.dat)
    logs_dir = Path(args.logs_dir)
    logs_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    verify_dir = Path(
        tempfile.mkdtemp(prefix=f"mnv_verify_{stamp}_", dir=str(logs_dir))
    )
    unpack_dir = verify_dir / "unpack"
    rebuild_path = verify_dir / "rebuild.dat"
    report_path = logs_dir / f"mnv_verify_{stamp}.txt"

    try:
        unpack_args = argparse.Namespace(
            dat=str(dat_path),
            out_dir=str(unpack_dir),
            manifest=MANIFEST_NAME,
            name_encoding=args.name_encoding,
            force=False,
        )
        command_unpack(unpack_args)
        manifest = load_manifest(unpack_dir / MANIFEST_NAME)
        build_archive_from_manifest(
            unpack_dir, rebuild_path, manifest, args.name_encoding
        )

        repack_unpack_dir = verify_dir / "repack_unpack"
        repack_unpack_args = argparse.Namespace(
            dat=str(rebuild_path),
            out_dir=str(repack_unpack_dir),
            manifest=MANIFEST_NAME,
            name_encoding=args.name_encoding,
            force=False,
        )
        command_unpack(repack_unpack_args)

        mismatches = []
        for item in manifest["entries"]:
            archive_path = item.get("path") or item.get("name")
            left = safe_output_path(unpack_dir, archive_path)
            right = safe_output_path(repack_unpack_dir, archive_path)
            left_data = left.read_bytes()
            right_data = right.read_bytes()
            if left_data != right_data:
                mismatches.append(
                    {
                        "index": item.get("index"),
                        "path": archive_path,
                        "left_sha256": sha256_bytes(left_data),
                        "right_sha256": sha256_bytes(right_data),
                    }
                )

        original_hash = sha256_file(dat_path)
        rebuild_hash = sha256_file(rebuild_path)
        archive_bit_perfect = dat_path.read_bytes() == rebuild_path.read_bytes()
        payload_roundtrip = not mismatches

        report = [
            "M no Violet DAT verify",
            f"source={dat_path}",
            f"original_sha256={original_hash}",
            f"rebuild_sha256={rebuild_hash}",
            f"archive_bit_perfect={archive_bit_perfect}",
            f"payload_roundtrip={payload_roundtrip}",
            f"mismatch_count={len(mismatches)}",
            f"work_dir={verify_dir}",
        ]
        if mismatches:
            report.append("mismatches=" + json.dumps(mismatches[:20], ensure_ascii=False))
        report_path.write_text("\n".join(report) + "\n", encoding="utf-8")
        log(f"验证报告: {report_path}")

        if payload_roundtrip:
            if archive_bit_perfect:
                log("round-trip 结果: 封包逐字节一致")
            else:
                log("round-trip 结果: 解压明文逐文件一致（重压后封包字节允许变化）")
            if not args.keep_temp:
                shutil.rmtree(verify_dir)
                log("已清理临时验证目录")
            return 0

        log("round-trip 结果: 解压明文不一致")
        log(f"保留临时目录用于排查: {verify_dir}")
        return 1
    except Exception:
        log(f"验证失败，保留临时目录用于排查: {verify_dir}")
        raise


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="M no Violet DAT 解包/封包工具",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--name-encoding",
        default=DEFAULT_NAME_ENCODING,
        help="封包内文件名编码",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_list = sub.add_parser("list", help="列出封包文件")
    p_list.add_argument("dat")
    p_list.add_argument("-o", "--output", help="可选：写出 manifest JSON")
    p_list.set_defaults(func=command_list)

    p_unpack = sub.add_parser("unpack", help="解包 DAT")
    p_unpack.add_argument("dat")
    p_unpack.add_argument("out_dir")
    p_unpack.add_argument(
        "--manifest",
        default=MANIFEST_NAME,
        help="输出目录中的 manifest 文件名",
    )
    p_unpack.add_argument("--force", action="store_true", help="允许输出到非空目录")
    p_unpack.set_defaults(func=command_unpack)

    p_pack = sub.add_parser("pack", help="按 manifest 重新封包")
    p_pack.add_argument("in_dir")
    p_pack.add_argument("output")
    p_pack.add_argument(
        "--manifest",
        help="manifest 路径；默认读取输入目录下的 _mnv_manifest.json",
    )
    p_pack.set_defaults(func=command_pack)

    p_verify = sub.add_parser("verify", help="解包后重封并进行 bit-perfect 验证")
    p_verify.add_argument("dat")
    p_verify.add_argument("--logs-dir", default="logs", help="日志目录")
    p_verify.add_argument(
        "--keep-temp",
        action="store_true",
        help="保留验证用临时解包目录",
    )
    p_verify.set_defaults(func=command_verify)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except MnvError as exc:
        print(f"[MNV][错误] {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
