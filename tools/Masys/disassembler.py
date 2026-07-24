# -*- coding: utf-8 -*-
"""MEG bytecode disassembler.

Recommended workflow (no fixed key in this tool):
  1) python 1.py dump Megu.exe meg meg_dec
  2) python disassembler.py meg_dec txt
  3) edit txt/*.asm.txt
  4) python assembler.py txt meg_plain
  5) python 1.py import Megu.exe meg_plain meg_out

String atom layout (expression, NOT top-level opcode):
  0x62 | u16 length | payload
  payload is plaintext after dump; ciphertext if you pass --key/--exe.
"""
from __future__ import annotations

import argparse
import re
import struct
import sys
from pathlib import Path
from typing import List, Optional, Tuple

from opcodelist import (
    EXPR_ATOM,
    EXPR_OPS,
    HEADER_MAGIC,
    HEADER_SIZE,
    OPERAND_MODES,
    OPCODE_INDEX,
    RAW_U32_BEFORE,
    mnemonic,
    set_xor_key,
    xor_crypt,
)


class ParseError(Exception):
    pass


class Reader:
    def __init__(self, data: bytes, base: int = 0):
        self.data = data
        self.pos = 0
        self.base = base

    def tell(self) -> int:
        return self.base + self.pos

    def eof(self) -> bool:
        return self.pos >= len(self.data)

    def read(self, n: int) -> bytes:
        if self.pos + n > len(self.data):
            raise ParseError(f"EOF at {self.tell():08X}, need {n} bytes")
        b = self.data[self.pos : self.pos + n]
        self.pos += n
        return b

    def u8(self) -> int:
        return self.read(1)[0]

    def u16(self) -> int:
        return struct.unpack("<H", self.read(2))[0]

    def i32(self) -> int:
        return struct.unpack("<i", self.read(4))[0]

    def u32(self) -> int:
        return struct.unpack("<I", self.read(4))[0]


def decode_text(data: bytes, encoding: str) -> str:
    out = []
    i = 0
    enc = encoding.lower()
    while i < len(data):
        b = data[i]
        if b < 0x20 or b == 0x7F:
            out.append(f"{{{{{b:02X}}}}}")
            i += 1
            continue
        if enc in ("cp932", "shift_jis", "shift-jis", "sjis"):
            if 0x81 <= b <= 0x9F or 0xE0 <= b <= 0xFC:
                if i + 1 < len(data):
                    try:
                        ch = data[i : i + 2].decode(encoding, errors="strict")
                        if ch and ch != "\ufffd":
                            o = ord(ch)
                            if 0xE000 <= o <= 0xF8FF:
                                out.append(f"{{{{{data[i]:02X}:{data[i+1]:02X}}}}}")
                            else:
                                out.append(ch)
                            i += 2
                            continue
                    except UnicodeDecodeError:
                        pass
                out.append(f"{{{{{b:02X}}}}}")
                i += 1
                continue
        try:
            out.append(bytes([b]).decode(encoding, errors="strict"))
            i += 1
        except UnicodeDecodeError:
            out.append(f"{{{{{b:02X}}}}}")
            i += 1
    return "".join(out)


def parse_expression(r: Reader, encoding: str) -> Tuple[str, bytes]:
    """Postfix expression: atom (atom|op)* 0x00.
    String atom: 0x62 + u16 len + payload (plain after dump).
    """
    start = r.pos
    parts: List[str] = []

    def parse_atom_from(kind: int) -> str:
        if kind not in EXPR_ATOM:
            raise ParseError(f"Unknown expr atom 0x{kind:02X} at {r.tell()-1:08X}")
        name, fmt = EXPR_ATOM[kind]
        if fmt == "u16":
            return f"{name}({r.u16()})"
        if fmt == "i32":
            v = r.i32()
            if v < 0:
                return f"IMM({v})"
            return f"IMM(0x{v:X})" if v > 9 else f"IMM({v})"
        if fmt == "b10":
            return f"IMM10({r.read(10).hex().upper()})"
        if fmt in ("str", "enc_str"):
            ln = r.u16()
            raw = r.read(ln)
            plain = xor_crypt(raw)  # no-op if key is None (decrypted input)
            text = decode_text(plain, encoding)
            return f'STR("{text}")'
        return name

    if r.eof():
        raise ParseError(f"Empty expression at {r.tell():08X}")
    parts.append(parse_atom_from(r.u8()))
    while True:
        if r.eof():
            raise ParseError(f"Unterminated expression at {start:08X}")
        b = r.u8()
        if b == 0x00:
            break
        if b in EXPR_ATOM:
            parts.append(parse_atom_from(b))
        elif b in EXPR_OPS:
            parts.append(EXPR_OPS[b])
        else:
            raise ParseError(f"Unknown expr token 0x{b:02X} at {r.tell()-1:08X}")
    return " ".join(parts), r.data[start:r.pos]



def _split_expr_tokens(expr: str) -> List[str]:
    """Tokenize expression text; keep STR("...") intact."""
    tokens: List[str] = []
    i = 0
    s = expr
    while i < len(s):
        if s[i].isspace():
            i += 1
            continue
        if s.startswith("STR(", i):
            j = i + 4
            if j >= len(s) or s[j] != '"':
                # malformed; take rest
                tokens.append(s[i:])
                break
            j += 1
            while j < len(s):
                if s[j] == '"':
                    j += 1
                    if j < len(s) and s[j] == ")":
                        j += 1
                        tokens.append(s[i:j])
                        i = j
                        break
                    raise ParseError(f"bad STR near {s[i:i+40]!r}")
                j += 1
            else:
                raise ParseError("unterminated STR")
            continue
        m = re.match(r"[A-Za-z_][A-Za-z0-9_]*\([^)]*\)|[A-Za-z_][A-Za-z0-9_]*", s[i:])
        if m:
            tokens.append(m.group(0))
            i += m.end()
            continue
        tokens.append(s[i])
        i += 1
    return tokens


def format_expression_lines(expr: str) -> List[str]:
    """
    Split long postfix expressions so each STR("...") starts a new visual line.
    Example:
      VAR_STR(0)
      STR("a") ADD
      VAR_STR(0) ADD
      STR("b") ADD
    """
    tokens = _split_expr_tokens(expr)
    if not tokens:
        return [expr]
    str_count = sum(1 for t in tokens if t.startswith("STR("))
    if str_count <= 1 and len(expr) < 100:
        return [" ".join(tokens)]

    lines: List[str] = []
    buf: List[str] = []
    for t in tokens:
        if t.startswith("STR(") and buf:
            lines.append(" ".join(buf))
            buf = [t]
        else:
            buf.append(t)
    if buf:
        lines.append(" ".join(buf))
    return lines


def format_operand_block(operands: List[str]) -> List[str]:
    """
    Build operand display lines for one instruction.
    - Multiple operands: first on insn line, others as ',\\n cont'
    - Within an operand expression, STR pieces go to their own continuation lines
    """
    if not operands:
        return []
    out: List[str] = []
    for oi, opnd in enumerate(operands):
        parts = format_expression_lines(opnd)
        is_last_op = oi == len(operands) - 1
        for pi, part in enumerate(parts):
            is_last_part = pi == len(parts) - 1
            # comma only after complete operand (last part of that operand), if more operands follow
            suffix = "," if is_last_part and not is_last_op else ""
            out.append(part + suffix)
    return out


def script_body_limit(body: bytes) -> int:
    """Ver ~300 appends 8 bytes after final RET(0xFF): 00 | u32 | u8 | 0xBF | 0x01."""
    if (
        len(body) >= 9
        and body[-9] == 0xFF
        and body[-8] == 0x00
        and body[-2] == 0xBF
        and body[-1] == 0x01
    ):
        return len(body) - 8
    return len(body)


def parse_header(data: bytes):
    if len(data) < HEADER_SIZE:
        raise ParseError("File too small for MEG header")
    if data[0:3] != HEADER_MAGIC:
        raise ParseError(f"Bad magic {data[0:3]!r}")
    version = struct.unpack_from("<H", data, 3)[0]
    flag = data[5]
    copyright_ = data[6:32]
    body = data[32:]
    lim = script_body_limit(body)
    footer = body[lim:]
    return version, flag, copyright_, body[:lim], footer


def disassemble_body(body: bytes, encoding: str, version: int):
    r = Reader(body)
    labels = {}
    xrefs = []
    insns = []

    while not r.eof():
        addr = r.pos
        op = r.u8()
        operands = []

        if op == 0xFF:
            insns.append({"addr": addr, "name": "RET", "operands": [], "end": r.pos})
            continue

        if op == 0xFE:
            if r.eof():
                raise ParseError(f"Truncated FE at {addr:08X}")
            sub = r.u8()
            # Always use EXT_xx so assembler can re-emit FE prefix unambiguously.
            name = f"EXT_{sub:02X}"
            if sub in RAW_U32_BEFORE:
                for _ in range(RAW_U32_BEFORE[sub]):
                    operands.append(f"U32(0x{r.u32():X})")
            for _mode in OPERAND_MODES.get(sub, []):
                et, _ = parse_expression(r, encoding)
                operands.append(et)
            insns.append({"addr": addr, "name": name, "operands": operands, "end": r.pos, "op": sub, "ext": True})
            continue

        if op == 0x18:
            target = r.u32()
            xrefs.append(target)
            insns.append({"addr": addr, "name": "JMP", "operands": [f"loc_{target:08X}"], "end": r.pos, "target": target})
            continue
        if op == 0x19:
            target = r.u32()
            xrefs.append(target)
            insns.append({"addr": addr, "name": "CALL", "operands": [f"loc_{target:08X}"], "end": r.pos, "target": target})
            continue
        if op == 0x17:
            et, _ = parse_expression(r, encoding)
            insns.append({"addr": addr, "name": "JTRUE_SKIP5", "operands": [et], "end": r.pos})
            continue
        if op == 0x20:
            et, _ = parse_expression(r, encoding)
            insns.append({"addr": addr, "name": "SETCMP", "operands": [et], "end": r.pos})
            continue
        if op == 0x21:
            et, _ = parse_expression(r, encoding)
            insns.append({"addr": addr, "name": "JNE_SKIP5", "operands": [et], "end": r.pos})
            continue

        # NOTE: 0x62 is NOT a top-level opcode. It is a string atom inside expressions.
        # Unknown table opcodes fall back to free-standing EXPR (assignment etc.)
        if op not in OPCODE_INDEX:
            r.pos = addr
            et, _ = parse_expression(r, encoding)
            insns.append({"addr": addr, "name": "EXPR", "operands": [et], "end": r.pos, "op": None})
            continue

        name = mnemonic(op, extended=False)
        if op in RAW_U32_BEFORE:
            for _ in range(RAW_U32_BEFORE[op]):
                operands.append(f"U32(0x{r.u32():X})")
        for _mode in OPERAND_MODES.get(op, []):
            et, _ = parse_expression(r, encoding)
            operands.append(et)

        if op == 0x29 and len(operands) == 1 and operands[0].startswith("IMM("):
            inner = operands[0][4:-1]
            try:
                target = int(inner, 16) if inner.lower().startswith("0x") else int(inner)
                xrefs.append(target)
                operands[0] = f"loc_{target:08X}"
                name = "SEEK"
                insns.append({"addr": addr, "name": name, "operands": operands, "end": r.pos, "target": target, "op": op})
                continue
            except ValueError:
                pass

        insns.append({"addr": addr, "name": name, "operands": operands, "end": r.pos, "op": op})

    for t in xrefs:
        labels[t] = f"loc_{t:08X}"

    lines = [
        '; .encoding "' + encoding + '"',
        f"; MEG version={version} body_size={len(body)}",
        "; strings assumed PLAINTEXT (run 1.py dump first). Use --exe/--key only for ciphertext MEG.",
        "; string atom = 0x62 + u16 len + payload (expression operand, not top-level opcode)",
        "",
    ]
    for insn in insns:
        if insn["addr"] in labels:
            lines.append("")
            lines.append(f"{labels[insn['addr']]}:")
        if not insn["operands"]:
            lines.append(f"    {insn['name']}")
            continue
        # Pretty multi-line: each STR(...) on its own continuation line.
        # Assembler joins indented continuations back into one instruction.
        blocks = format_operand_block(insn["operands"])
        lines.append(f"    {insn['name']:<16} {blocks[0]}")
        for b in blocks[1:]:
            lines.append(f"                     {b}")
    if len(body) in labels:
        lines.append("")
        lines.append(f"{labels[len(body)]}:")
    return lines, insns, labels


def disassemble_file(path: Path, encoding: str = "cp932") -> str:
    data = path.read_bytes()
    version, flag, copyright_, body, footer = parse_header(data)
    lines, _, _ = disassemble_body(body, encoding, version)
    header = [
        f"; source: {path.name}",
        f"; .meg_version {version}",
        f"; .meg_flag {flag}",
        f"; .copyright_hex {copyright_.hex()}",
    ]
    if footer:
        header.append(f"; .meg_footer_hex {footer.hex()}")
    # fix encoding directive without broken escapes
    out_lines = header + lines
    # ensure encoding line uses normal quotes
    fixed = []
    for ln in out_lines:
        if "PLACEHOLDER" in ln:
            fixed.append('; .encoding "' + encoding + '"')
        elif ln.startswith("; .encoding"):
            fixed.append('; .encoding "' + encoding + '"')
        else:
            fixed.append(ln)
    return "\n".join(fixed) + "\n"


def process_path(inp: Path, out: Path, encoding: str):
    if inp.is_dir():
        out.mkdir(parents=True, exist_ok=True)
        files = sorted(list(inp.glob("*.MEG")) + list(inp.glob("*.meg")))
        seen, uniq = set(), []
        for f in files:
            k = f.name.lower()
            if k not in seen:
                seen.add(k)
                uniq.append(f)
        files = uniq
        if not files:
            files = sorted([p for p in inp.iterdir() if p.is_file()])
        for f in files:
            text = disassemble_file(f, encoding)
            op = out / (f.stem + ".asm.txt")
            op.write_text(text, encoding="utf-8")
            print(f"OK {f.name} -> {op.name}")
    else:
        text = disassemble_file(inp, encoding)
        if out.exists() and out.is_dir():
            op = out / (inp.stem + ".asm.txt")
        elif not out.suffix:
            out.mkdir(parents=True, exist_ok=True)
            op = out / (inp.stem + ".asm.txt")
        else:
            op = out
            op.parent.mkdir(parents=True, exist_ok=True)
        op.write_text(text, encoding="utf-8")
        print(f"OK {inp} -> {op}")


def load_key_from_args(args) -> None:
    if getattr(args, "key", None):
        set_xor_key(args.key.encode("latin1", errors="replace"))
        return
    if getattr(args, "exe", None):
        # reuse 1.py feature extractor if present
        try:
            import importlib.util
            p = Path(__file__).resolve().parent / "1.py"
            if not p.exists():
                p = Path("1.py")
            spec = importlib.util.spec_from_file_location("meg_key", p)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            key, why = mod.extract_key_from_exe(Path(args.exe))
            set_xor_key(key)
            print(f"[key from exe] {key!r} ({why})")
        except Exception as e:
            raise SystemExit(f"failed to load key from exe: {e}")
    else:
        set_xor_key(None)  # plaintext mode


def main(argv=None):
    ap = argparse.ArgumentParser(description="MEG script disassembler (prefer decrypted MEG)")
    ap.add_argument("input")
    ap.add_argument("output", nargs="?")
    ap.add_argument("-o", "--output-file", dest="output_opt")
    ap.add_argument("--encoding", default="cp932")
    ap.add_argument("--key", help="XOR key if input MEG still encrypted (not recommended)")
    ap.add_argument("--exe", help="extract XOR key from exe if input still encrypted")
    args = ap.parse_args(argv)
    load_key_from_args(args)
    inp = Path(args.input)
    if args.output_opt:
        out = Path(args.output_opt)
    elif args.output:
        out = Path(args.output)
    else:
        out = inp.with_suffix(".asm.txt") if inp.is_file() else Path("txt")
    try:
        process_path(inp, out, args.encoding)
    except ParseError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
