# -*- coding: utf-8 -*-
"""AGSI SB2 CSTR 原始二进制解码 / 编码工具。

这个脚本不做文本提取、不生成 JSON、不做注入。
只在 CSTR.bin 与 CSTR_decode.bin 之间做可逆转换：

    CSTR.bin        : offset/size 表 + 混淆字符串池
    CSTR_decode.bin : offset/size 表 + 明文 CP932 字符串池

用法：
    python agsi_cstr_codec.py decode dump_majo2
    python agsi_cstr_codec.py encode dump_majo2

也支持直接指定文件：
    python agsi_cstr_codec.py decode-file CSTR.bin CSTR_decode.bin --count 75527
    python agsi_cstr_codec.py encode-file CSTR_decode.bin CSTR.bin --count 75527
"""
from __future__ import annotations

import argparse
import json
import struct
from pathlib import Path

DUMP_FORMAT = "AGSI_SB2_DUMP_SIMPLE_V1"


def swap_nibble_bytes(buf: bytes) -> bytes:
    # agsi.dll 中对字符串池每个字节做 b = (b >> 4) | (b << 4)。
    # 该操作自反：decode 和 encode 都调用同一个函数。
    return bytes((((b >> 4) | ((b & 0x0F) << 4)) & 0xFF) for b in buf)


def load_cstr_count_from_manifest(dump_dir: Path) -> int:
    manifest_path = dump_dir / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"manifest.json not found: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("format") != DUMP_FORMAT:
        raise ValueError(f"unsupported dump format: {manifest.get('format')!r}")
    for seg in manifest.get("segments", []):
        if seg.get("tag") == "CSTR" and seg.get("file") == "CSTR.bin":
            if "cstr_count" in seg:
                return int(seg["cstr_count"])
    hv = manifest.get("header_values")
    if isinstance(hv, list) and len(hv) > 9:
        return int(hv[9])
    raise ValueError("cannot find CSTR count in manifest.json")


def split_cstr_payload(data: bytes, count: int) -> tuple[bytes, bytes, int]:
    table_size = count * 8
    if len(data) < table_size:
        raise ValueError(f"CSTR payload too small: size={len(data)}, table_size={table_size}")

    table = data[:table_size]
    pool = data[table_size:]
    expected_pool_size = 0
    for i in range(count):
        off, size = struct.unpack_from("<II", table, i * 8)
        expected_pool_size += size
        if off + size > len(pool):
            raise ValueError(
                f"CSTR entry out of range: id={i}, off={off}, size={size}, pool={len(pool)}"
            )
    if expected_pool_size != len(pool):
        raise ValueError(f"CSTR pool size mismatch: expected={expected_pool_size}, actual={len(pool)}")
    return table, pool, expected_pool_size


def decode_cstr_file(input_path: Path, output_path: Path, count: int) -> dict:
    data = input_path.read_bytes()
    table, pool_obfuscated, pool_size = split_cstr_payload(data, count)
    pool_plain = swap_nibble_bytes(pool_obfuscated)
    output_path.write_bytes(table + pool_plain)
    return {
        "mode": "decode",
        "input": str(input_path),
        "output": str(output_path),
        "count": count,
        "table_size": len(table),
        "pool_size": pool_size,
        "output_size": output_path.stat().st_size,
    }


def encode_cstr_file(input_path: Path, output_path: Path, count: int) -> dict:
    data = input_path.read_bytes()
    table, pool_plain, pool_size = split_cstr_payload(data, count)
    pool_obfuscated = swap_nibble_bytes(pool_plain)
    output_path.write_bytes(table + pool_obfuscated)
    return {
        "mode": "encode",
        "input": str(input_path),
        "output": str(output_path),
        "count": count,
        "table_size": len(table),
        "pool_size": pool_size,
        "output_size": output_path.stat().st_size,
    }


def cmd_decode(args: argparse.Namespace) -> None:
    dump_dir = Path(args.dump_dir)
    count = args.count if args.count is not None else load_cstr_count_from_manifest(dump_dir)
    input_path = dump_dir / args.input_name
    output_path = dump_dir / args.output_name
    report = decode_cstr_file(input_path, output_path, count)
    print(json.dumps(report, ensure_ascii=False, indent=2))


def cmd_encode(args: argparse.Namespace) -> None:
    dump_dir = Path(args.dump_dir)
    count = args.count if args.count is not None else load_cstr_count_from_manifest(dump_dir)
    input_path = dump_dir / args.input_name
    output_path = dump_dir / args.output_name
    if output_path.exists() and not args.overwrite:
        raise FileExistsError(f"output exists, use --overwrite: {output_path}")
    report = encode_cstr_file(input_path, output_path, count)
    print(json.dumps(report, ensure_ascii=False, indent=2))


def cmd_decode_file(args: argparse.Namespace) -> None:
    if args.count is None:
        raise ValueError("decode-file requires --count")
    report = decode_cstr_file(Path(args.input), Path(args.output), int(args.count))
    print(json.dumps(report, ensure_ascii=False, indent=2))


def cmd_encode_file(args: argparse.Namespace) -> None:
    if args.count is None:
        raise ValueError("encode-file requires --count")
    report = encode_cstr_file(Path(args.input), Path(args.output), int(args.count))
    print(json.dumps(report, ensure_ascii=False, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description="AGSI CSTR 原始二进制解码/编码工具")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_decode = sub.add_parser("decode", help="dump_dir/CSTR.bin -> dump_dir/CSTR_decode.bin")
    p_decode.add_argument("dump_dir")
    p_decode.add_argument("--input-name", default="CSTR.bin")
    p_decode.add_argument("--output-name", default="CSTR_decode.bin")
    p_decode.add_argument("--count", type=int, help="CSTR 条目数；默认从 manifest.json 读取")
    p_decode.set_defaults(func=cmd_decode)

    p_encode = sub.add_parser("encode", help="dump_dir/CSTR_decode.bin -> dump_dir/CSTR.bin")
    p_encode.add_argument("dump_dir")
    p_encode.add_argument("--input-name", default="CSTR_decode.bin")
    p_encode.add_argument("--output-name", default="CSTR.bin")
    p_encode.add_argument("--count", type=int, help="CSTR 条目数；默认从 manifest.json 读取")
    p_encode.add_argument("--overwrite", action="store_true", help="允许覆盖输出 CSTR.bin")
    p_encode.set_defaults(func=cmd_encode)

    p_decode_file = sub.add_parser("decode-file", help="直接解码单个 CSTR 文件")
    p_decode_file.add_argument("input")
    p_decode_file.add_argument("output")
    p_decode_file.add_argument("--count", type=int, required=True)
    p_decode_file.set_defaults(func=cmd_decode_file)

    p_encode_file = sub.add_parser("encode-file", help="直接编码单个 CSTR_decode 文件")
    p_encode_file.add_argument("input")
    p_encode_file.add_argument("output")
    p_encode_file.add_argument("--count", type=int, required=True)
    p_encode_file.set_defaults(func=cmd_encode_file)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
