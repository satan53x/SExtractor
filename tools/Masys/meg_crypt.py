# -*- coding: utf-8 -*-
"""MEG string decrypt/encrypt tool.

MEG files are not whole-file encrypted. Only expression strings (atom 0x62)
are XOR-protected with key b"Powerd by Masys". This tool walks the bytecode
using the known VM operand layout and decrypts/encrypts those string payloads
in place (length unchanged, structure preserved).

Usage:
  python meg_crypt.py decrypt <in.MEG|dir> [-o <out.MEG|dir>]
  python meg_crypt.py encrypt <in.MEG|dir> [-o <out.MEG|dir>]
  python meg_crypt.py roundtrip <in.MEG>   # verify encrypt(decrypt(x))==x
"""
from __future__ import annotations

import argparse
import struct
import sys
from pathlib import Path
from typing import Callable, List, Optional, Tuple

# allow import opcodelist next to this file or from cwd
_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))
_ROOT = _HERE.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# --- minimal VM tables (same as opcodelist; kept self-contained) ---
XOR_KEY = b"Powerd by Masys"
HEADER_SIZE = 32
MAGIC = b"MEG"

EXPR_ATOM = {
    0x50: ("u16",), 0x51: ("u16",), 0x52: ("u16",),
    0x53: (), 0x54: (), 0x55: (),
    0x57: (), 0x58: (), 0x59: (), 0x5A: (), 0x5B: (), 0x5C: (),
    0x60: ("i32",), 0x61: ("b10",), 0x62: ("str",),
}
EXPR_OPS = {
    0x03, 0x04, 0x05, 0x06, 0x07, 0x08, 0x09, 0x0A, 0x0B,
    0x0D, 0x0E, 0x0F, 0x10, 0x11, 0x12, 0x13, 0x14, 0x15, 0x16,
}

# opcode -> list of expression modes (count matters; mode values unused here)
try:
    from opcodelist import OPERAND_MODES, RAW_U32_BEFORE, OPCODE_INDEX  # type: ignore
except Exception:
    OPERAND_MODES = {}
    RAW_U32_BEFORE = {0xC3: 1, 0xC7: 1}
    OPCODE_INDEX = {}
    # fallback: will still walk specials + treat unknown as free expr

SPECIAL = {0x17, 0x18, 0x19, 0x20, 0x21, 0xFE, 0xFF}


def xor_buf(data: bytearray, start: int, length: int) -> None:
    key = XOR_KEY
    for i in range(length):
        data[start + i] ^= key[i % len(key)]


class WalkerError(Exception):
    pass


def walk_and_crypt(body: bytearray, transform: Callable[[bytearray, int, int], None]) -> int:
    """Walk bytecode; apply transform(body, str_off, str_len) for each STR payload.
    Returns number of strings touched.
    """
    pos = 0
    n = len(body)
    count = 0

    def need(k: int):
        if pos + k > n:
            raise WalkerError(f"EOF at {pos:04X}, need {k}")

    def u8() -> int:
        nonlocal pos
        need(1)
        b = body[pos]
        pos += 1
        return b

    def skip(k: int):
        nonlocal pos
        need(k)
        pos += k

    def walk_expr() -> None:
        nonlocal pos, count
        start = pos
        first = True
        while True:
            if pos >= n:
                raise WalkerError(f"unterminated expr at {start:04X}")
            b = u8()
            if b == 0x00:
                if first:
                    raise WalkerError(f"empty expr at {start:04X}")
                break
            first = False
            if b in EXPR_ATOM:
                kind = EXPR_ATOM[b]
                if kind == ("u16",):
                    skip(2)
                elif kind == ("i32",):
                    skip(4)
                elif kind == ("b10",):
                    skip(10)
                elif kind == ("str",):
                    need(2)
                    ln = struct.unpack_from("<H", body, pos)[0]
                    pos += 2
                    need(ln)
                    transform(body, pos, ln)
                    count += 1
                    pos += ln
                # bare atoms: nothing
            elif b in EXPR_OPS:
                continue
            else:
                raise WalkerError(f"bad expr token 0x{b:02X} at {pos-1:04X}")

    while pos < n:
        op = u8()
        if op == 0xFF:
            continue
        if op == 0xFE:
            sub = u8()
            for _ in range(RAW_U32_BEFORE.get(sub, 0)):
                skip(4)
            for _ in OPERAND_MODES.get(sub, []):
                walk_expr()
            continue
        if op == 0x18 or op == 0x19:
            skip(4)
            continue
        if op in (0x17, 0x20, 0x21):
            walk_expr()
            continue
        # table opcode or free-standing expression
        if OPERAND_MODES and (op in OPERAND_MODES or op in OPCODE_INDEX):
            for _ in range(RAW_U32_BEFORE.get(op, 0)):
                skip(4)
            modes = OPERAND_MODES.get(op, [])
            for _ in modes:
                walk_expr()
            continue
        # free-standing expression (assignment etc.): rewind and parse as expr
        pos -= 1
        walk_expr()

    return count


def process_file(data: bytes, mode: str) -> Tuple[bytes, int]:
    if len(data) < HEADER_SIZE or data[:3] != MAGIC:
        raise WalkerError("not a MEG file (bad magic/header)")
    out = bytearray(data)
    body = memoryview(out)[HEADER_SIZE:]  # type: ignore
    # walk on body slice as bytearray copy then write back — simpler: walk full with offset
    body_arr = bytearray(data[HEADER_SIZE:])

    def transform(buf: bytearray, start: int, length: int):
        # mode decrypt/encrypt both XOR (symmetric)
        xor_buf(buf, start, length)

    cnt = walk_and_crypt(body_arr, transform)
    out[HEADER_SIZE:] = body_arr
    return bytes(out), cnt


def iter_megs(path: Path) -> List[Path]:
    if path.is_file():
        return [path]
    files = sorted(path.glob("*.MEG")) + sorted(path.glob("*.meg"))
    # unique by lower name
    seen = set()
    out = []
    for f in files:
        k = f.name.lower()
        if k not in seen:
            seen.add(k)
            out.append(f)
    return out


def default_out(inp: Path, out: Optional[Path], mode: str) -> Path:
    if out is not None:
        return out
    tag = "_dec" if mode == "decrypt" else "_enc"
    if inp.is_dir():
        return inp.parent / (inp.name + tag)
    return inp.with_name(inp.stem + tag + inp.suffix)


def process_path(inp: Path, out: Optional[Path], mode: str) -> int:
    files = iter_megs(inp)
    if not files:
        print(f"no MEG files in {inp}", file=sys.stderr)
        return 1
    multi = inp.is_dir() or len(files) > 1
    if multi:
        odir = out if out else default_out(inp, None, mode)
        odir.mkdir(parents=True, exist_ok=True)
    else:
        odir = None
        ofile = out if out else default_out(files[0], None, mode)

    rc = 0
    for f in files:
        try:
            data = f.read_bytes()
            new, cnt = process_file(data, mode)
            if multi:
                target = odir / f.name
            else:
                target = ofile
                target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(new)
            print(f"OK {mode} {f.name} -> {target}  (strings={cnt})")
        except Exception as e:
            print(f"FAIL {f.name}: {e}", file=sys.stderr)
            rc = 1
    return rc


def main(argv=None):
    ap = argparse.ArgumentParser(description="MEG string XOR decrypt/encrypt")
    ap.add_argument("mode", choices=["decrypt", "encrypt", "roundtrip"])
    ap.add_argument("input", help="MEG file or directory")
    ap.add_argument("-o", "--output", help="output file or directory")
    args = ap.parse_args(argv)
    inp = Path(args.input)
    if args.mode == "roundtrip":
        data = inp.read_bytes()
        d, c1 = process_file(data, "decrypt")
        e, c2 = process_file(d, "encrypt")
        ok = e == data
        print(f"strings={c1} roundtrip={'OK' if ok else 'FAIL'} len={len(data)}")
        return 0 if ok else 1
    # encrypt and decrypt are the same XOR transform; mode name is for output naming
    return process_path(inp, Path(args.output) if args.output else None, args.mode)


if __name__ == "__main__":
    sys.exit(main())
