# -*- coding: utf-8 -*-
"""
Malie .mls batch extract / repack

.mls layout:
  [0:13]  b"MalieScenario"
  [13:]   zlib.compress(script_bytes, level=6)

Decompressed payload is plain CP932 (Shift_JIS) scenario source text (CRLF).

Usage:
  # batch extract: bin/*.mls  ->  txt/*.txt
  python mls_pack.py extract bin txt

  # batch repack:  txt/*.txt  ->  bin/*.mls  (or .rebuild.mls)
  python mls_pack.py pack txt bin

  # single file
  python mls_pack.py extract s01.mls -o s01.txt
  python mls_pack.py pack s01.txt -o s01.mls

  # verify round-trip
  python mls_pack.py check scenario
"""

from __future__ import annotations

import argparse
import sys
import zlib
from pathlib import Path
from typing import Iterable, List, Optional, Sequence

MAGIC = b"MalieScenario"
MAGIC_LEN = 13
ZLIB_LEVEL = 6
DEFAULT_TXT_EXT = ".txt"
DEFAULT_MLS_EXT = ".mls"


def extract_bytes(data: bytes) -> bytes:
    if len(data) < MAGIC_LEN:
        raise ValueError("file too small")
    if data[:MAGIC_LEN] != MAGIC:
        raise ValueError(f"bad magic: {data[:MAGIC_LEN]!r}, expected {MAGIC!r}")
    return zlib.decompress(data[MAGIC_LEN:])


def pack_bytes(script: bytes, level: int = ZLIB_LEVEL) -> bytes:
    return MAGIC + zlib.compress(script, level)


def _iter_files(path: Path, suffixes: Sequence[str]) -> List[Path]:
    if path.is_file():
        return [path]
    suf = {s.lower() for s in suffixes}
    return [
        p
        for p in sorted(path.iterdir())
        if p.is_file() and p.suffix.lower() in suf
    ]


def cmd_extract(
    inp: Path,
    out: Optional[Path],
    encoding_note: bool = False,
) -> int:
    files = _iter_files(inp, [".mls", ".bin", ".sc"])
    if not files and inp.is_file():
        files = [inp]
    if not files:
        print(f"no .mls files under {inp}", file=sys.stderr)
        return 1

    multi = inp.is_dir() or len(files) > 1
    if multi:
        dest_dir = out if out else Path("txt")
        dest_dir.mkdir(parents=True, exist_ok=True)
    else:
        dest_dir = None

    ok = 0
    for f in files:
        raw = extract_bytes(f.read_bytes())
        if multi:
            dest = dest_dir / (f.stem + DEFAULT_TXT_EXT)
        elif out is None:
            dest = f.with_suffix(DEFAULT_TXT_EXT)
        elif out.exists() and out.is_dir():
            dest = out / (f.stem + DEFAULT_TXT_EXT)
        elif not out.suffix:
            out.mkdir(parents=True, exist_ok=True)
            dest = out / (f.stem + DEFAULT_TXT_EXT)
        else:
            dest = out
            dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(raw)
        ok += 1
        print(f"[extract] {f.name} -> {dest} ({len(raw)} bytes)")
    print(f"done: {ok} file(s)")
    if encoding_note:
        print("note: payload is CP932/Shift_JIS text with CRLF line endings")
    return 0


def cmd_pack(
    inp: Path,
    out: Optional[Path],
    level: int = ZLIB_LEVEL,
    suffix: str = DEFAULT_MLS_EXT,
) -> int:
    files = _iter_files(inp, [".txt", ".src", ".sc"])
    if not files and inp.is_file():
        files = [inp]
    if not files:
        print(f"no text files under {inp}", file=sys.stderr)
        return 1

    multi = inp.is_dir() or len(files) > 1
    if multi:
        dest_dir = out if out else Path("bin")
        dest_dir.mkdir(parents=True, exist_ok=True)
    else:
        dest_dir = None

    ok = 0
    for f in files:
        script = f.read_bytes()
        # strip UTF-8 BOM if user saved from editor
        if script.startswith(b"\xef\xbb\xbf"):
            script = script[3:]
        data = pack_bytes(script, level=level)
        if multi:
            dest = dest_dir / (f.stem + suffix)
        elif out is None:
            dest = f.with_suffix(suffix)
        elif out.exists() and out.is_dir():
            dest = out / (f.stem + suffix)
        elif not out.suffix:
            out.mkdir(parents=True, exist_ok=True)
            dest = out / (f.stem + suffix)
        else:
            dest = out
            dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        ok += 1
        print(f"[pack] {f.name} -> {dest} ({len(data)} bytes)")
    print(f"done: {ok} file(s)")
    return 0


def cmd_check(inp: Path) -> int:
    files = _iter_files(inp, [".mls", ".bin", ".sc"])
    if not files and inp.is_file():
        files = [inp]
    if not files:
        print(f"no .mls files under {inp}", file=sys.stderr)
        return 1
    ok = fail = 0
    for f in files:
        data = f.read_bytes()
        try:
            raw = extract_bytes(data)
            rec = pack_bytes(raw, ZLIB_LEVEL)
            if rec == data:
                ok += 1
                print(f"[ok] {f.name}")
            else:
                fail += 1
                print(f"[fail] {f.name}: size {len(data)} vs {len(rec)}")
        except Exception as e:
            fail += 1
            print(f"[fail] {f.name}: {e}")
    print(f"result: ok={ok} fail={fail}")
    return 0 if fail == 0 else 2


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="Batch extract / repack MalieScenario .mls files"
    )
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_ex = sub.add_parser("extract", help="decompress .mls -> plain .txt")
    p_ex.add_argument("input", help="input .mls file or directory")
    p_ex.add_argument("output", nargs="?", default=None, help="output .txt or directory")
    p_ex.add_argument("-o", "--output-file", dest="output_opt", default=None)
    p_ex.add_argument("--note", action="store_true", help="print encoding note")

    p_pk = sub.add_parser("pack", help="repack plain .txt -> .mls")
    p_pk.add_argument("input", help="input .txt file or directory")
    p_pk.add_argument("output", nargs="?", default=None, help="output .mls or directory")
    p_pk.add_argument("-o", "--output-file", dest="output_opt", default=None)
    p_pk.add_argument(
        "--level",
        type=int,
        default=ZLIB_LEVEL,
        help=f"zlib level (default {ZLIB_LEVEL}, required for original match)",
    )
    p_pk.add_argument(
        "--suffix",
        default=DEFAULT_MLS_EXT,
        help="output extension for batch pack (default .mls)",
    )

    p_ck = sub.add_parser("check", help="verify extract+pack round-trip")
    p_ck.add_argument("input", help="input .mls file or directory")

    args = ap.parse_args(argv)
    if args.cmd == "extract":
        out = Path(args.output_opt or args.output) if (args.output_opt or args.output) else None
        return cmd_extract(Path(args.input), out, encoding_note=args.note)
    if args.cmd == "pack":
        out = Path(args.output_opt or args.output) if (args.output_opt or args.output) else None
        return cmd_pack(Path(args.input), out, level=args.level, suffix=args.suffix)
    if args.cmd == "check":
        return cmd_check(Path(args.input))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
