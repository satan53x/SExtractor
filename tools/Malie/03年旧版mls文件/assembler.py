# -*- coding: utf-8 -*-
"""
Malie Scenario (.mls) assembler.

Usage:
  python assembler.py <input.asm.txt|input_dir> [output.bin|output_dir]
  python assembler.py txt bin
  python assembler.py sample.asm.txt -o sample.mls --encoding cp932
"""

from __future__ import annotations

import argparse
import re
import sys
import zlib
from pathlib import Path
from typing import List, Optional, Sequence, Tuple, Union

from opcodelist import (
    DEFAULT_ENCODING,
    MAGIC,
    ZLIB_LEVEL,
    container_pack,
    display_to_bytes,
    unquote_asm_string,
)

ASM_EXT = ".asm.txt"
RE_HEADER = re.compile(r"^\.(?P<key>[A-Za-z0-9_]+)\s+(?P<val>.+?)\s*$")
RE_LABEL = re.compile(r"^(?P<name>[A-Za-z_][A-Za-z0-9_@\$]*)\s*:\s*$")
RE_EMPTY = re.compile(r"^EMPTY\s*$")
RE_CMD = re.compile(
    r"^CMD\s+(?P<name>[A-Za-z0-9_]+)\s+"
    r"MIDDLE=(?P<middle>\"(?:\\.|[^\"\\])*\")\s+"
    r"TERM=(?P<term>\"(?:\\.|[^\"\\])*\")"
)
RE_DIALOG = re.compile(
    r"^DIALOG\s+.*\bRAW=(?P<raw>\"(?:\\.|[^\"\\])*\")\s*$"
)
RE_TEXT = re.compile(r"^TEXT\s+(?P<body>\"(?:\\.|[^\"\\])*\")\s*$")


def _iter_asm_files(path: Path) -> List[Path]:
    if path.is_file():
        return [path]
    files: List[Path] = []
    for p in sorted(path.iterdir()):
        if p.is_file() and (
            p.name.endswith(ASM_EXT) or p.suffix.lower() in {".txt", ".asm"}
        ):
            files.append(p)
    return files


def _strip_comment(line: str) -> str:
    out: List[str] = []
    in_str = False
    i = 0
    while i < len(line):
        ch = line[i]
        if in_str:
            out.append(ch)
            if ch == "\\" and i + 1 < len(line):
                out.append(line[i + 1])
                i += 2
                continue
            if ch == '"':
                in_str = False
            i += 1
            continue
        if ch == '"':
            in_str = True
            out.append(ch)
            i += 1
            continue
        if ch == ";":
            break
        out.append(ch)
        i += 1
    return "".join(out).rstrip()


LineItem = Union[bytes, str]


def assemble_text(asm_text: str, encoding_override: Optional[str] = None) -> bytes:
    encoding = encoding_override or DEFAULT_ENCODING
    ends_with_newline = True
    zlib_level = ZLIB_LEVEL
    magic = MAGIC
    parts: List[bytes] = []

    for raw_line in asm_text.splitlines():
        line = raw_line.strip("\ufeff")
        stripped = _strip_comment(line).strip()
        if not stripped:
            continue
        if stripped.startswith(";"):
            continue

        hm = RE_HEADER.match(stripped)
        if hm:
            key = hm.group("key").lower()
            val = hm.group("val").strip()
            if key == "encoding":
                if encoding_override is None:
                    encoding = val
            elif key == "zlib_level":
                zlib_level = int(val)
            elif key == "ends_with_newline":
                ends_with_newline = bool(int(val))
            elif key == "magic":
                magic = unquote_asm_string(val).encode("ascii")
            continue

        lm = RE_LABEL.match(stripped)
        if lm:
            parts.append(f"{lm.group('name')}:".encode(encoding))
            continue

        body = stripped.lstrip()
        if RE_EMPTY.match(body):
            parts.append(b"")
            continue

        m = RE_CMD.match(body)
        if m:
            name = m.group("name")
            middle = unquote_asm_string(m.group("middle"))
            term = unquote_asm_string(m.group("term"))
            line_bytes = (
                b"&"
                + name.encode("ascii")
                + display_to_bytes(middle, encoding)
                + display_to_bytes(term, encoding)
            )
            parts.append(line_bytes)
            continue

        m = RE_DIALOG.match(body)
        if m:
            raw = unquote_asm_string(m.group("raw"))
            parts.append(display_to_bytes(raw, encoding))
            continue

        m = RE_TEXT.match(body)
        if m:
            raw = unquote_asm_string(m.group("body"))
            parts.append(display_to_bytes(raw, encoding))
            continue

        raise ValueError(f"Unrecognized asm line: {raw_line!r}")

    script = b"\r\n".join(parts)
    if ends_with_newline:
        script += b"\r\n"

    if magic == MAGIC and zlib_level == ZLIB_LEVEL:
        return container_pack(script)
    return magic + zlib.compress(script, zlib_level)


def assemble_file(
    in_path: Path,
    out_path: Path,
    encoding: Optional[str] = None,
) -> None:
    text = in_path.read_text(encoding="utf-8")
    data = assemble_text(text, encoding_override=encoding)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(data)
    print(f"[OK] {in_path} -> {out_path} ({len(data)} bytes)")


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Malie .mls assembler")
    ap.add_argument("input", help="Input asm.txt file or directory (e.g. txt)")
    ap.add_argument("output", nargs="?", default=None, help="Output file or directory (e.g. bin)")
    ap.add_argument("-o", "--output-file", dest="output_opt", default=None)
    ap.add_argument("--encoding", default=None)
    args = ap.parse_args(argv)

    in_path = Path(args.input)
    out_path = Path(args.output_opt or args.output) if (args.output_opt or args.output) else None
    if not in_path.exists():
        print(f"Input not found: {in_path}", file=sys.stderr)
        return 1

    files = _iter_asm_files(in_path)
    if not files:
        print(f"No asm files under {in_path}", file=sys.stderr)
        return 1

    multi = in_path.is_dir()
    if multi:
        dest_dir = out_path if out_path else Path("bin")
        dest_dir.mkdir(parents=True, exist_ok=True)
        for f in files:
            name = f.name
            base = name[: -len(ASM_EXT)] if name.endswith(ASM_EXT) else f.stem
            assemble_file(f, dest_dir / f"{base}.mls", encoding=args.encoding)
        return 0

    f = files[0]
    base = f.name[: -len(ASM_EXT)] if f.name.endswith(ASM_EXT) else f.stem
    if out_path is None:
        dest = f.with_name(base + ".mls")
    elif out_path.exists() and out_path.is_dir():
        dest = out_path / f"{base}.mls"
    elif not out_path.suffix:
        out_path.mkdir(parents=True, exist_ok=True)
        dest = out_path / f"{base}.mls"
    else:
        dest = out_path
        dest.parent.mkdir(parents=True, exist_ok=True)
    assemble_file(f, dest, encoding=args.encoding)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
