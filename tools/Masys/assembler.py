# -*- coding: utf-8 -*-
"""MEG bytecode assembler."""
from __future__ import annotations

import argparse
import re
import struct
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from opcodelist import (
    set_xor_key,
    COPYRIGHT,
    EXPR_ATOM,
    EXPR_OPS,
    HEADER_MAGIC,
    HEADER_SIZE,
    MNEMONICS,
    OPERAND_MODES,
    OPCODE_TABLE,
    RAW_U32_BEFORE,
    SPECIAL_OPS,
    xor_crypt,
)

ATOM_NAME_TO_BYTE = {v[0]: k for k, v in EXPR_ATOM.items()}
OP_NAME_TO_BYTE = {v: k for k, v in EXPR_OPS.items()}
PRI_SET = set(OPCODE_TABLE[:126])
EXT_SET = set(OPCODE_TABLE[126:])

NAME_TO_OP: Dict[str, Tuple[int, str]] = {}
for op, name in MNEMONICS.items():
    NAME_TO_OP.setdefault(name, (op, "auto"))
for op, name in SPECIAL_OPS.items():
    NAME_TO_OP[name] = (op, "special")
NAME_TO_OP["SEEK"] = (0x29, "table")
for op in set(list(OPERAND_MODES.keys()) + OPCODE_TABLE):
    NAME_TO_OP.setdefault(f"OP_{op:02X}", (op, "table"))
    NAME_TO_OP.setdefault(f"EXT_{op:02X}", (op, "ext"))


class AsmError(Exception):
    pass


PLACEHOLDER_RE = re.compile(r"\{\{([0-9A-Fa-f]{2})(?::([0-9A-Fa-f]{2}))?\}\}")


def encode_text(text: str, encoding: str) -> bytes:
    out = bytearray()
    i = 0
    while i < len(text):
        m = PLACEHOLDER_RE.match(text, i)
        if m:
            out.append(int(m.group(1), 16))
            if m.group(2):
                out.append(int(m.group(2), 16))
            i = m.end()
            continue
        ch = text[i]
        i += 1
        try:
            out.extend(ch.encode(encoding))
        except UnicodeEncodeError as e:
            raise AsmError(f"Cannot encode {ch!r} with {encoding}: {e}")
    return bytes(out)


def parse_imm(s: str) -> int:
    s = s.strip()
    if s.lower().startswith("0x"):
        return int(s, 16)
    return int(s, 10)


def split_expression_tokens(s: str) -> List[str]:
    tokens = []
    i = 0
    s = s.strip()
    while i < len(s):
        if s[i].isspace():
            i += 1
            continue
        if s.startswith("STR(", i):
            j = i + 4
            if j >= len(s) or s[j] != '"':
                raise AsmError(f"Bad STR near {s[i:i+20]!r}")
            j += 1
            while j < len(s):
                if s[j] == '"':
                    j += 1
                    if j < len(s) and s[j] == ")":
                        j += 1
                        tokens.append(s[i:j])
                        i = j
                        break
                    raise AsmError("STR missing )")
                j += 1
            else:
                raise AsmError("Unterminated STR")
            continue
        m = re.match(r"[A-Za-z_][A-Za-z0-9_]*\([^)]*\)", s[i:])
        if m:
            tokens.append(m.group(0))
            i += m.end()
            continue
        m = re.match(r"[A-Za-z_][A-Za-z0-9_]*", s[i:])
        if m:
            tok = m.group(0)
            tokens.append(tok.upper() if tok.upper() in OP_NAME_TO_BYTE else tok)
            i += m.end()
            continue
        raise AsmError(f"Cannot tokenize near {s[i:i+30]!r}")
    return tokens


def encode_expression(tokens: List[str], encoding: str) -> bytes:
    """Encode postfix tokens: atom (atom|op)* then 0x00."""
    out = bytearray()

    def enc_atom(tok: str) -> bytes:
        if tok.startswith("STR(") and tok.endswith(")"):
            inner = tok[4:-1]
            if not (inner.startswith('"') and inner.endswith('"')):
                raise AsmError(f"Bad STR token {tok}")
            plain = encode_text(inner[1:-1], encoding)
            enc = xor_crypt(plain)
            return bytes([0x62]) + struct.pack("<H", len(enc)) + enc
        if tok.startswith("IMM10(") and tok.endswith(")"):
            raw = bytes.fromhex(tok[6:-1].replace(" ", ""))
            if len(raw) != 10:
                raise AsmError("IMM10 must be 10 bytes")
            return bytes([0x61]) + raw
        if tok.startswith("IMM(") and tok.endswith(")"):
            v = parse_imm(tok[4:-1])
            return bytes([0x60]) + struct.pack("<i", v)
        m = re.match(r"([A-Z_]+)\((\d+)\)$", tok)
        if m:
            name, idx = m.group(1), int(m.group(2))
            if name not in ATOM_NAME_TO_BYTE:
                raise AsmError(f"Unknown atom {name}")
            b = ATOM_NAME_TO_BYTE[name]
            if EXPR_ATOM[b][1] != "u16":
                raise AsmError(f"Atom {name} does not take index")
            return bytes([b]) + struct.pack("<H", idx)
        if tok in ATOM_NAME_TO_BYTE:
            return bytes([ATOM_NAME_TO_BYTE[tok]])
        raise AsmError(f"Bad atom token {tok}")

    if not tokens:
        raise AsmError("Empty expression")
    for tok in tokens:
        if tok in OP_NAME_TO_BYTE:
            out.append(OP_NAME_TO_BYTE[tok])
        else:
            out.extend(enc_atom(tok))
    out.append(0x00)
    return bytes(out)


def parse_asm(text: str):
    encoding = "cp932"
    version = 0x96
    flag = 0
    copyright_ = COPYRIGHT
    footer = b""
    insns = []
    # Join pretty-print continuations:
    # any line with indent > base_insn_indent continues previous instruction,
    # until a non-indented label / new insn / blank / comment-only.
    joined = []
    buf = ""
    for raw_line in text.splitlines():
        if not raw_line.strip():
            if buf:
                joined.append(buf)
                buf = ""
            continue
        indent = len(raw_line) - len(raw_line.lstrip(" 	"))
        s = raw_line.strip()
        if s.startswith(";") or s.startswith("."):
            if buf:
                joined.append(buf)
                buf = ""
            joined.append(s)
            continue
        if s.endswith(":") and indent == 0:
            if buf:
                joined.append(buf)
                buf = ""
            joined.append(s)
            continue
        # continuation: deeper indent than a normal "    NAME" (4 spaces)
        if buf and indent > 4 and not s.endswith(":"):
            # expression pieces often have no leading comma
            if buf.rstrip().endswith(","):
                buf = buf.rstrip() + " " + s
            else:
                buf = buf.rstrip() + " " + s
            continue
        if buf:
            joined.append(buf)
        buf = s
    if buf:
        joined.append(buf)

    for raw_line in joined:
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith(";") or line.startswith("."):
            m = re.search(r'\.encoding\s+"([^"]+)"', line)
            if m:
                encoding = m.group(1)
            m = re.search(r"\.meg_version\s+(\d+)", line)
            if m:
                version = int(m.group(1))
            m = re.search(r"\.meg_flag\s+(\d+)", line)
            if m:
                flag = int(m.group(1))
            m = re.search(r"\.copyright_hex\s+([0-9A-Fa-f]+)", line)
            if m:
                raw = bytes.fromhex(m.group(1))
                copyright_ = (raw + b"\x00" * 26)[:26]
            m = re.search(r"\.meg_footer_hex\s+([0-9A-Fa-f]+)", line)
            if m:
                footer = bytes.fromhex(m.group(1))
            continue
        if re.match(r"^[A-Za-z_][A-Za-z0-9_]*:$", line):
            insns.append({"type": "label", "name": line[:-1]})
            continue
        m = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)\s*(.*)$", line)
        if not m:
            raise AsmError(f"Bad line: {raw_line}")
        name = m.group(1)
        rest = m.group(2).strip()
        # strip comment outside quotes
        if ";" in rest:
            in_q = False
            buf = []
            for ch in rest:
                if ch == '"':
                    in_q = not in_q
                if ch == ";" and not in_q:
                    break
                buf.append(ch)
            rest = "".join(buf).rstrip()
        operands = []
        if rest:
            cur = []
            depth = 0
            in_q = False
            for ch in rest + ",":
                if ch == '"':
                    in_q = not in_q
                    cur.append(ch)
                    continue
                if not in_q:
                    if ch == "(":
                        depth += 1
                    elif ch == ")":
                        depth -= 1
                    elif ch == "," and depth == 0:
                        operands.append("".join(cur).strip())
                        cur = []
                        continue
                cur.append(ch)
            operands = [o for o in operands if o]
        insns.append({"type": "op", "name": name, "operands": operands})
    return encoding, version, flag, copyright_, footer, insns


def resolve_op(name: str):
    uname = name.upper()
    if uname in ("RET", "OP_FF"):
        return 0xFF, "special"
    if uname.startswith("EXT_"):
        return int(uname[4:], 16), "ext"
    if uname.startswith("OP_"):
        return int(uname[3:], 16), "table"
    if uname not in NAME_TO_OP:
        raise AsmError(f"Unknown mnemonic {name}")
    return NAME_TO_OP[uname]


def encode_insn(name: str, operands: List[str], labels: Dict[str, int], resolve: bool, encoding: str) -> bytes:
    uname = name.upper()

    if uname in ("RET", "OP_FF"):
        return b"\xFF"
    if uname == "EXPR":
        if len(operands) != 1:
            raise AsmError("EXPR needs 1 expression")
        return encode_expression(split_expression_tokens(operands[0]), encoding)
    if uname == "JMP":
        t = operands[0]
        if t.startswith("loc_"):
            if resolve and t not in labels:
                raise AsmError(f"Unknown label {t}")
            target = labels.get(t, 0)
        else:
            target = parse_imm(t)
        return b"\x18" + struct.pack("<I", target & 0xFFFFFFFF)
    if uname == "CALL":
        t = operands[0]
        if t.startswith("loc_"):
            if resolve and t not in labels:
                raise AsmError(f"Unknown label {t}")
            target = labels.get(t, 0)
        else:
            target = parse_imm(t)
        return b"\x19" + struct.pack("<I", target & 0xFFFFFFFF)
    if uname in ("JTRUE_SKIP5", "SETCMP", "JNE_SKIP5"):
        opb = {"JTRUE_SKIP5": 0x17, "SETCMP": 0x20, "JNE_SKIP5": 0x21}[uname]
        return bytes([opb]) + encode_expression(split_expression_tokens(operands[0]), encoding)

    op, kind = resolve_op(uname)

    # Primary control ops are bare; extended table (index>=126) uses FE prefix.
    bare_control = {0x17, 0x18, 0x19, 0x20, 0x21, 0xFF, 0xFE}
    if kind == "ext":
        use_fe = True
    elif op in bare_control:
        use_fe = False
    elif op in EXT_SET and op not in PRI_SET:
        use_fe = True
    else:
        use_fe = False
    if uname == "SEEK":
        # Scripts use bare 0x29, not FE 29.
        use_fe = False
        op = 0x29
    if uname == "GETPOS":
        # Prefer bare 0x28 (primary scripts); FE 28 exists but rare.
        use_fe = False
        op = 0x28

    out = bytearray()
    if use_fe:
        out.append(0xFE)
    out.append(op & 0xFF)

    ops_left = list(operands)
    nraw = RAW_U32_BEFORE.get(op, 0)
    for _ in range(nraw):
        if not ops_left:
            raise AsmError(f"{uname} missing U32 operand")
        o = ops_left.pop(0)
        if o.startswith("U32("):
            v = parse_imm(o[4:-1])
        elif o.startswith("loc_"):
            if resolve and o not in labels:
                raise AsmError(f"Unknown label {o}")
            v = labels.get(o, 0)
        else:
            v = parse_imm(o)
        out += struct.pack("<I", v & 0xFFFFFFFF)

    modes = list(OPERAND_MODES.get(op, []))
    if modes and len(ops_left) != len(modes):
        raise AsmError(f"{uname}: expected {nraw} u32 + {len(modes)} exprs, got {len(operands)}")
    for o in ops_left:
        if o.startswith("loc_"):
            if resolve and o not in labels:
                raise AsmError(f"Unknown label {o}")
            v = labels.get(o, 0)
            out += encode_expression([f"IMM(0x{v:X})"], encoding)
        else:
            out += encode_expression(split_expression_tokens(o), encoding)
    return bytes(out)



def assemble(text: str) -> bytes:
    encoding, version, flag, copyright_, footer, items = parse_asm(text)

    # size-stable pass for labels (IMM always 6 bytes)
    label_pos: Dict[str, int] = {}
    pos = 0
    for it in items:
        if it["type"] == "label":
            label_pos[it["name"]] = pos
        else:
            pos += len(encode_insn(it["name"], it["operands"], label_pos, False, encoding))

    body = bytearray()
    for it in items:
        if it["type"] == "label":
            continue
        body += encode_insn(it["name"], it["operands"], label_pos, True, encoding)

    header = HEADER_MAGIC + struct.pack("<H", version & 0xFFFF) + bytes([flag & 0xFF]) + copyright_
    if len(header) != HEADER_SIZE:
        header = (HEADER_MAGIC + struct.pack("<H", version & 0xFFFF) + bytes([flag & 0xFF]) + copyright_.ljust(26, b"\x00"))[:HEADER_SIZE]
    return header + bytes(body) + footer


def process_path(inp: Path, out: Path, encoding_override: Optional[str]):
    if inp.is_dir():
        out.mkdir(parents=True, exist_ok=True)
        files = sorted(set(list(inp.glob("*.asm.txt")) + list(inp.glob("*.txt"))))
        for f in files:
            text = f.read_text(encoding="utf-8")
            if encoding_override and ".encoding" not in text:
                text = '; .encoding "' + encoding_override + '"\n' + text
            data = assemble(text)
            base = f.name[:-8] if f.name.endswith(".asm.txt") else f.stem
            op = out / (base + ".meg")
            op.write_bytes(data)
            print(f"OK {f.name} -> {op.name}")
    else:
        text = inp.read_text(encoding="utf-8")
        data = assemble(text)
        if out.exists() and out.is_dir():
            op = out / (inp.stem.replace(".asm", "") + ".meg")
        else:
            op = out
            op.parent.mkdir(parents=True, exist_ok=True)
        op.write_bytes(data)
        print(f"OK {inp} -> {op}")


def main(argv=None):
    ap = argparse.ArgumentParser(description="MEG script assembler")
    ap.add_argument("input")
    ap.add_argument("output", nargs="?")
    ap.add_argument("-o", "--output-file", dest="output_opt")
    ap.add_argument("--encoding", default=None)
    ap.add_argument("--key", help="XOR key only if re-encoding ciphertext MEG")
    ap.add_argument("--exe", help="load key from exe if needed")
    args = ap.parse_args(argv)
    inp = Path(args.input)
    out = Path(args.output_opt or args.output or (inp.with_suffix(".rebuild") if inp.is_file() else Path("bin")))
    # default plaintext (post-dump). optional key for ciphertext workflow
    if getattr(args, 'key', None):
        set_xor_key(args.key.encode('latin1', errors='replace'))
    elif getattr(args, 'exe', None):
        import importlib.util
        p = Path('1.py')
        spec = importlib.util.spec_from_file_location('meg_key', p)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        key, why = mod.extract_key_from_exe(Path(args.exe))
        set_xor_key(key)
        print(f'[key from exe] {key!r} ({why})')
    else:
        set_xor_key(None)
    try:
        process_path(inp, out, args.encoding)
    except AsmError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
