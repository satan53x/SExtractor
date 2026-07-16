# -*- coding: utf-8 -*-
"""
Malie Scenario (.mls) disassembler.

Usage:
  python disassembler.py <input.bin|input_dir> [output.txt|output_dir]
  python disassembler.py bin txt
  python disassembler.py sample.mls -o sample.asm.txt --encoding cp932
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Set, Tuple

from opcodelist import (
    DEFAULT_ENCODING,
    MAGIC,
    ZLIB_LEVEL,
    bytes_to_display,
    container_unpack,
    is_jump_command,
    parse_command_line,
    parse_dialog_line,
    quote_asm_string,
    _RE_LABEL,
)

ASM_EXT = ".asm.txt"
BIN_EXTS = {".mls", ".bin", ".sc", ".dat"}


def _iter_input_files(path: Path) -> List[Path]:
    if path.is_file():
        return [path]
    return [
        p
        for p in sorted(path.iterdir())
        if p.is_file() and (p.suffix.lower() in BIN_EXTS or p.suffix == "")
    ]


def split_script_byte_lines(script: bytes) -> Tuple[List[bytes], bool]:
    """Split on CRLF. Returns (line_bytes_list, ends_with_newline)."""
    if not script:
        return [], False
    ends = script.endswith(b"\r\n")
    if ends:
        body = script[:-2]
        if not body:
            return [], True
        parts = body.split(b"\r\n")
        return parts, True
    return script.split(b"\r\n"), False


def collect_jump_targets(line_strs: Sequence[str]) -> Set[str]:
    targets: Set[str] = set()
    for line in line_strs:
        m = _RE_LABEL.match(line)
        if m:
            continue
        cmd = parse_command_line(line)
        if not cmd or not is_jump_command(cmd["name"]):
            continue
        args = cmd["args"].strip()
        if args:
            targets.add(args.split()[0])
    return targets


def disassemble_bytes(
    data: bytes,
    encoding: str = DEFAULT_ENCODING,
    source_name: str = "",
) -> str:
    script = container_unpack(data)
    raw_lines, ends_with_newline = split_script_byte_lines(script)

    # Decode each line for classification; payload emission always uses
    # bytes_to_display(raw_line) so placeholders preserve undecodable bytes.
    line_strs: List[str] = []
    for rb in raw_lines:
        try:
            line_strs.append(rb.decode(encoding))
        except UnicodeDecodeError:
            line_strs.append(rb.decode(encoding, errors="replace"))

    # Byte offsets of each line start
    offsets: List[int] = []
    pos = 0
    for i, rb in enumerate(raw_lines):
        offsets.append(pos)
        pos += len(rb)
        if i < len(raw_lines) - 1 or ends_with_newline:
            pos += 2

    name_to_off: Dict[str, int] = {}
    for off, s in zip(offsets, line_strs):
        m = _RE_LABEL.match(s)
        if m:
            name_to_off[m.group(1)] = off

    jump_names = collect_jump_targets(line_strs)
    emit_labels: Dict[int, str] = {}
    for name, off in name_to_off.items():
        emit_labels[off] = name
    for t in jump_names:
        if t in name_to_off:
            emit_labels[name_to_off[t]] = t

    out: List[str] = []
    out.append("; Malie Scenario disassembly")
    if source_name:
        out.append(f"; source: {source_name}")
    out.append(
        f"; size: {len(data)} container bytes, {len(script)} script bytes"
    )
    out.append(f".magic {quote_asm_string(MAGIC.decode('ascii'))}")
    out.append(f".encoding {encoding}")
    out.append(f".zlib_level {ZLIB_LEVEL}")
    out.append(f".ends_with_newline {1 if ends_with_newline else 0}")
    out.append(f".script_size {len(script)}")
    out.append("")

    for off, rb, s in zip(offsets, raw_lines, line_strs):
        if off in emit_labels:
            if out and out[-1] != "":
                out.append("")
            out.append(f"{emit_labels[off]}:")
            m = _RE_LABEL.match(s)
            if m and m.group(1) == emit_labels[off]:
                # Source line is pure label definition.
                continue

        if rb == b"":
            out.append("EMPTY")
            continue

        m = _RE_LABEL.match(s)
        if m:
            if off not in emit_labels:
                if out and out[-1] != "":
                    out.append("")
                out.append(f"{m.group(1)}:")
            continue

        disp = bytes_to_display(rb, encoding)
        cmd = parse_command_line(s)
        if cmd:
            name = cmd["name"]
            # Exact middle/term from original bytes for zero-mutation.
            # line = b'&' + name_ascii + middle + term
            prefix = b"&" + name.encode("ascii")
            if not rb.startswith(prefix):
                # Unusual casing / encoding — dump whole line as TEXT.
                out.append(f"  TEXT {quote_asm_string(disp)}")
                continue
            rest = rb[len(prefix) :]
            term = b""
            middle = rest
            if rest.endswith(b" ; "):
                term = b" ; "
                middle = rest[: -len(term)]
            elif rest.endswith(b" ;"):
                term = b" ;"
                middle = rest[: -len(term)]
            elif rest.endswith(b";"):
                term = b";"
                middle = rest[: -len(term)]
            mid_disp = bytes_to_display(middle, encoding)
            term_disp = bytes_to_display(term, encoding)
            note = ""
            if is_jump_command(name) and cmd["args"].strip():
                target = cmd["args"].strip().split()[0]
                note = f" ; target={target}"
            out.append(
                f"  CMD {name} "
                f"MIDDLE={quote_asm_string(mid_disp)} "
                f"TERM={quote_asm_string(term_disp)}"
                f"{note}"
            )
            continue

        if s.startswith("#"):
            dlg = parse_dialog_line(s)
            if dlg is not None:
                fields = [
                    f"CHANNEL={dlg['channel']}",
                    f"SPEAKER={quote_asm_string(bytes_to_display(dlg['speaker'].encode(encoding, errors='replace'), encoding))}",
                ]
                if dlg["voice"]:
                    fields.append(
                        f"VOICE={quote_asm_string(bytes_to_display(dlg['voice'].encode(encoding, errors='replace'), encoding))}"
                    )
                fields.append(f"RAW={quote_asm_string(disp)}")
                out.append("  DIALOG " + " ".join(fields))
                continue

        out.append(f"  TEXT {quote_asm_string(disp)}")

    out.append("")
    out.append("; end")
    return "\r\n".join(out) + "\r\n"


def disassemble_file(in_path: Path, out_path: Path, encoding: str) -> None:
    data = in_path.read_bytes()
    text = disassemble_bytes(data, encoding=encoding, source_name=in_path.name)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(text, encoding="utf-8", newline="")
    print(f"[OK] {in_path} -> {out_path}")


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Malie .mls disassembler")
    ap.add_argument("input", help="Input .mls file or directory (e.g. bin)")
    ap.add_argument("output", nargs="?", default=None, help="Output file or directory (e.g. txt)")
    ap.add_argument("-o", "--output-file", dest="output_opt", default=None)
    ap.add_argument("--encoding", default=DEFAULT_ENCODING)
    args = ap.parse_args(argv)

    in_path = Path(args.input)
    out_path = Path(args.output_opt or args.output) if (args.output_opt or args.output) else None
    if not in_path.exists():
        print(f"Input not found: {in_path}", file=sys.stderr)
        return 1

    files = _iter_input_files(in_path)
    if not files:
        print(f"No input files under {in_path}", file=sys.stderr)
        return 1

    multi = in_path.is_dir()
    if multi:
        dest_dir = out_path if out_path else Path("txt")
        dest_dir.mkdir(parents=True, exist_ok=True)
        for f in files:
            disassemble_file(f, dest_dir / (f.stem + ASM_EXT), args.encoding)
        return 0

    f = files[0]
    if out_path is None:
        dest = f.with_name(f.stem + ASM_EXT)
    elif out_path.exists() and out_path.is_dir():
        dest = out_path / (f.stem + ASM_EXT)
    elif not out_path.suffix:
        out_path.mkdir(parents=True, exist_ok=True)
        dest = out_path / (f.stem + ASM_EXT)
    else:
        dest = out_path
        dest.parent.mkdir(parents=True, exist_ok=True)
    disassemble_file(f, dest, args.encoding)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
