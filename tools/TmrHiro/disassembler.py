#!/usr/bin/env python3
"""Disassemble Fortune Cookie Select script binaries to semantic asm.txt.

Usage:
  python disassembler.py <input> [output]
  python disassembler.py bin_dir txt_dir
  python disassembler.py script.bin -o out.asm --encoding cp932

Input may be a single decrypted-container script file (from pac_unpack)
or a directory of such files. Output is asm text (or a directory of .asm).
"""

from __future__ import annotations

import argparse
import os
import sys
from typing import Dict, Iterable, List, Optional, Tuple

from opcodelist import (
    DEFAULT_ENCODING,
    OPCODES,
    bytes_to_display,
    extract_label_name,
    find_label_refs,
    get_opcode,
)
from script_codec import decode_script, load_script_file


ASM_HEADER = """\
# FCS Script Disassembly
# encoding: {encoding}
# source: {source}
# lines: {count}
# format: each instruction is one source line; first token is mnemonic or OP_XX
# operands use display text; raw non-printable bytes as {{{{XX}}}}
# labels: lines with LABEL define symbols; JUMP targets keep symbolic names when possible
"""


def collect_labels(lines: List[bytes]) -> Dict[str, int]:
    labels: Dict[str, int] = {}
    for idx, line in enumerate(lines):
        name = extract_label_name(line)
        if name:
            # first definition wins
            labels.setdefault(name, idx)
    return labels


def format_instruction(line: bytes, encoding: str) -> Tuple[str, Optional[str]]:
    """Return (asm_line, defined_label_name_or_None)."""
    if not line:
        return "EMPTY", None

    op = line[0]
    payload = line[1:]
    info = get_opcode(op)
    text = bytes_to_display(payload, encoding)

    defined = extract_label_name(line)

    # Prefer a slightly nicer formatting for common ops without losing bytes.
    # The assembler always: mnemonic + single space + display payload (if any).
    if payload:
        asm = f"{info.mnemonic} {text}"
    else:
        asm = info.mnemonic
    return asm, defined


def disassemble_lines(
    lines: List[bytes],
    encoding: str = DEFAULT_ENCODING,
    source: str = "",
    emit_line_numbers: bool = True,
) -> str:
    labels = collect_labels(lines)
    # reverse map line -> label names (may be multiple rare)
    line_to_labels: Dict[int, List[str]] = {}
    for name, idx in labels.items():
        line_to_labels.setdefault(idx, []).append(name)

    out: List[str] = [
        ASM_HEADER.format(encoding=encoding, source=source, count=len(lines)).rstrip()
    ]
    out.append("")

    for idx, line in enumerate(lines):
        # Emit symbolic label markers BEFORE the defining instruction when opcode is LABEL.
        # The LABEL instruction itself is still emitted so round-trip keeps the opcode byte.
        names = line_to_labels.get(idx, [])
        if names and idx > 0:
            out.append("")  # blank line before label (spec)

        asm, defined = format_instruction(line, encoding)

        # Also annotate refs as comments when useful
        refs = find_label_refs(line)
        comment_bits: List[str] = []
        if defined:
            comment_bits.append(f"def {defined}")
        for r in refs:
            if r in labels and r != defined:
                comment_bits.append(f"ref {r} -> L{labels[r]:04d}")

        if emit_line_numbers:
            prefix = f"L{idx:04d}: "
        else:
            prefix = ""

        if comment_bits:
            out.append(f"{prefix}{asm}  ; {', '.join(comment_bits)}")
        else:
            out.append(f"{prefix}{asm}")

    out.append("")
    return "\n".join(out)


def disassemble_file(
    path: str,
    encoding: str = DEFAULT_ENCODING,
    emit_line_numbers: bool = True,
) -> str:
    data = open(path, "rb").read()
    lines = decode_script(data)
    return disassemble_lines(
        lines,
        encoding=encoding,
        source=os.path.basename(path),
        emit_line_numbers=emit_line_numbers,
    )


def _is_dir(path: str) -> bool:
    return os.path.isdir(path)


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(description="Disassemble FCS script binaries")
    p.add_argument("input", help="script file or input directory (bin)")
    p.add_argument(
        "output",
        nargs="?",
        default=None,
        help="output .asm file or output directory (txt)",
    )
    p.add_argument(
        "-o",
        "--output-file",
        dest="output_opt",
        default=None,
        help="output path (alternative to positional)",
    )
    p.add_argument(
        "--encoding",
        default=DEFAULT_ENCODING,
        help=f"text encoding (default {DEFAULT_ENCODING})",
    )
    p.add_argument(
        "--no-line-numbers",
        action="store_true",
        help="do not emit L#### prefixes",
    )
    args = p.parse_args(argv)
    out_path = args.output_opt or args.output
    enc = args.encoding
    emit_ln = not args.no_line_numbers

    if _is_dir(args.input):
        in_dir = args.input
        out_dir = out_path or (in_dir.rstrip("\\/") + "_asm")
        os.makedirs(out_dir, exist_ok=True)
        names = sorted(
            n
            for n in os.listdir(in_dir)
            if os.path.isfile(os.path.join(in_dir, n)) and not n.startswith("_")
        )
        for name in names:
            src = os.path.join(in_dir, name)
            dst = os.path.join(out_dir, name + ".asm")
            text = disassemble_file(src, encoding=enc, emit_line_numbers=emit_ln)
            with open(dst, "w", encoding="utf-8", newline="\n") as f:
                f.write(text)
            print(f"wrote {dst}")
        print(f"disassembled {len(names)} files -> {out_dir}")
        return 0

    # single file
    text = disassemble_file(args.input, encoding=enc, emit_line_numbers=emit_ln)
    if not out_path:
        out_path = args.input + ".asm"
    # if user passed a directory as output, place file inside
    if out_path.endswith(("/", "\\")) or (
        os.path.isdir(out_path) if os.path.exists(out_path) else False
    ):
        os.makedirs(out_path, exist_ok=True)
        out_path = os.path.join(out_path, os.path.basename(args.input) + ".asm")
    parent = os.path.dirname(os.path.abspath(out_path))
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(out_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    print(f"wrote {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
