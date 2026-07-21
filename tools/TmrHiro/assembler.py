#!/usr/bin/env python3
"""Assemble FCS asm.txt back to script binary (byte-identical when from our disassembler).

Usage:
  python assembler.py <input.asm|txt_dir> [output|bin_dir]
  python assembler.py txt bin
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from typing import List, Optional, Tuple

from opcodelist import (
    DEFAULT_ENCODING,
    MNEMONIC_TO_OPCODE,
    display_to_bytes,
    get_opcode,
)
from script_codec import encode_script


LINE_RE = re.compile(
    r"^(?:L(?P<idx>\d+):\s*)?"  # optional L0000:
    r"(?P<body>.*)$"
)
COMMENT_SPLIT = re.compile(r"\s+;\s")


def parse_asm_text(text: str, encoding: str = DEFAULT_ENCODING) -> Tuple[List[bytes], str]:
    """Parse asm into decrypted line payloads.

    Returns (lines, encoding_from_header_or_arg).
    """
    enc = encoding
    lines: List[bytes] = []
    for raw in text.splitlines():
        # Keep trailing operand spaces; only strip BOM / CR.
        s = raw.replace("\r", "").lstrip("\ufeff")
        if not s.strip():
            continue
        if s.lstrip().startswith("#"):
            hs = s.strip()
            if hs.lower().startswith("# encoding:"):
                enc = hs.split(":", 1)[1].strip() or enc
            continue

        m = LINE_RE.match(s)
        if not m:
            raise ValueError(f"bad line: {raw!r}")
        body = m.group("body")
        # Do not strip trailing spaces from body — they may be significant payload.
        body_stripped_left = body.lstrip()
        if not body_stripped_left:
            continue
        body = body_stripped_left
        # strip trailing comment emitted by disassembler ("  ; ...")
        if "  ; " in body:
            body = body.split("  ; ", 1)[0]
            # keep intentional trailing spaces before comment marker
        elif body.startswith(";"):
            continue

        # EMPTY mnemonic
        if body.strip() == "EMPTY" and body.strip() == body:
            lines.append(b"")
            continue
        if body == "EMPTY":
            lines.append(b"")
            continue

        # mnemonic [operands...]  (first ASCII space separates mnemonic from payload)
        if " " in body:
            mnem, operand = body.split(" ", 1)
        else:
            mnem, operand = body, ""

        mnem = mnem.strip()
        if mnem.startswith("OP_") and len(mnem) == 5:
            try:
                code = int(mnem[3:], 16)
            except ValueError as e:
                raise ValueError(f"bad opcode token {mnem}") from e
        elif mnem in MNEMONIC_TO_OPCODE:
            code = MNEMONIC_TO_OPCODE[mnem]
        else:
            # allow raw hex opcode like 0x14
            if mnem.lower().startswith("0x"):
                code = int(mnem, 16)
            else:
                raise ValueError(f"unknown mnemonic: {mnem!r} (line {raw!r})")

        payload = display_to_bytes(operand, enc) if operand else b""
        lines.append(bytes([code & 0xFF]) + payload)

    return lines, enc


def assemble_file(path: str, encoding: str = DEFAULT_ENCODING) -> bytes:
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()
    lines, enc = parse_asm_text(text, encoding=encoding)
    return encode_script(lines)


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(description="Assemble FCS asm.txt to script binary")
    p.add_argument("input", help="asm file or directory")
    p.add_argument(
        "output",
        nargs="?",
        default=None,
        help="output binary path/dir (default: *.rebuild next to input)",
    )
    p.add_argument("--encoding", default=DEFAULT_ENCODING)
    args = p.parse_args(argv)

    if os.path.isdir(args.input):
        in_dir = args.input
        out_dir = args.output or (in_dir.rstrip("\\/") + "_bin")
        os.makedirs(out_dir, exist_ok=True)
        names = sorted(
            n
            for n in os.listdir(in_dir)
            if n.lower().endswith(".asm") and os.path.isfile(os.path.join(in_dir, n))
        )
        for name in names:
            src = os.path.join(in_dir, name)
            base = name[:-4] if name.lower().endswith(".asm") else name
            # strip double extension .asm
            if base.endswith(".asm"):
                base = base[:-4]
            dst = os.path.join(out_dir, base)
            data = assemble_file(src, encoding=args.encoding)
            with open(dst, "wb") as f:
                f.write(data)
            print(f"wrote {dst} ({len(data)} bytes)")
        print(f"assembled {len(names)} files -> {out_dir}")
        return 0

    data = assemble_file(args.input, encoding=args.encoding)
    out = args.output
    if not out:
        if args.input.lower().endswith(".asm"):
            out = args.input[:-4] + ".rebuild"
        else:
            out = args.input + ".rebuild"
    parent = os.path.dirname(os.path.abspath(out))
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(out, "wb") as f:
        f.write(data)
    print(f"wrote {out} ({len(data)} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

