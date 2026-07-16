# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import sys

# MUST run before importing dataclasses/inspect/dis: local opcode.py shadows stdlib.
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
while _SCRIPT_DIR in sys.path:
    sys.path.remove(_SCRIPT_DIR)
# also drop cwd entry if it points here
_sys_path_clean = []
for _p in sys.path:
    if _p in ("", ".") and os.path.abspath(os.getcwd()) == _SCRIPT_DIR:
        continue
    _sys_path_clean.append(_p)
sys.path[:] = _sys_path_clean
import struct
import argparse
import re
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


def _load_opcode():
    import importlib.util
    path = os.path.join(_SCRIPT_DIR, "opcode.py")
    name = "popotan_vm_opcode"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    # restore script dir at end for relative resources if needed
    if _SCRIPT_DIR not in sys.path:
        sys.path.append(_SCRIPT_DIR)
    return mod


_opcode = _load_opcode()
EXPR_T = _opcode.EXPR_T
EXPR_U = _opcode.EXPR_U
EXPR_V = _opcode.EXPR_V
EXPR_W = _opcode.EXPR_W
expr_kind_from_name = _opcode.expr_kind_from_name
op_code = _opcode.op_code
op_info = _opcode.op_info
type_kind_from_name = _opcode.type_kind_from_name

DEFAULT_ENCODING = "cp932"
PLACEHOLDER_RE = re.compile(r"\{\{([0-9A-Fa-f]{2})(?::([0-9A-Fa-f]{2}))?\}\}")


def _normalize_encoding(encoding: str) -> str:
    enc = (encoding or "").lower().replace("-", "_")
    if enc in ("shift_jis", "shiftjis", "sjis", "ms932", "windows_31j"):
        return "cp932"
    return encoding


def encode_text(text: str, encoding: str) -> bytes:
    encoding = _normalize_encoding(encoding)
    out = bytearray()
    i = 0
    n = len(text)
    while i < n:
        if text.startswith("{{", i):
            m = PLACEHOLDER_RE.match(text, i)
            if not m:
                raise ValueError("bad placeholder near %r" % text[i : i + 16])
            out.append(int(m.group(1), 16))
            if m.group(2):
                out.append(int(m.group(2), 16))
            i = m.end()
            continue
        j = i
        while j < n and not text.startswith("{{", j):
            j += 1
        if j > i:
            out.extend(text[i:j].encode(encoding))
        i = j
    return bytes(out)


def write_u32(buf: bytearray, v: int) -> None:
    buf.extend(struct.pack("<I", v & 0xFFFFFFFF))


def write_len_string(buf: bytearray, text: str, encoding: str) -> None:
    payload = encode_text(text, encoding) + b"\x00"
    write_u32(buf, len(payload))
    buf.extend(payload)


@dataclass
class TypeNode:
    kind: int
    value: int
    next: Optional["TypeNode"] = None


@dataclass
class GlobalVar:
    name: str
    typ: Optional[TypeNode]
    flags: int
    reserved: int
    offset: int


@dataclass
class LabelDef:
    index: int
    name: str
    offset: int


@dataclass
class ExprNode:
    kind: int
    text: Optional[str] = None
    value: Optional[int] = None
    left: Optional["ExprNode"] = None
    right: Optional["ExprNode"] = None


@dataclass
class Instr:
    mnemonic: str
    kind: str = "none"
    text: Optional[str] = None
    imm: Optional[int] = None
    label: Optional[str] = None
    expr_index: Optional[int] = None
    labels_here: List[str] = field(default_factory=list)


@dataclass
class AsmUnit:
    encoding: str = DEFAULT_ENCODING
    data_size: int = 0
    globals: List[GlobalVar] = field(default_factory=list)
    label_defs: List[LabelDef] = field(default_factory=list)
    label_name_to_index: Dict[str, int] = field(default_factory=dict)
    exprs: Dict[int, ExprNode] = field(default_factory=dict)
    instrs: List[Instr] = field(default_factory=list)


def strip_comment(line: str) -> str:
    out = []
    in_str = False
    i = 0
    while i < len(line):
        c = line[i]
        if in_str:
            out.append(c)
            if c == '"':
                if i + 1 < len(line) and line[i + 1] == '"':
                    out.append('"')
                    i += 2
                    continue
                in_str = False
            i += 1
            continue
        if c == '"':
            in_str = True
            out.append(c)
            i += 1
            continue
        if c == ";":
            break
        out.append(c)
        i += 1
    return "".join(out).rstrip()


def parse_quoted(s: str, start: int = 0) -> Tuple[str, int]:
    if start >= len(s) or s[start] != '"':
        raise ValueError("expected quote: %r" % s[start:])
    i = start + 1
    out = []
    while i < len(s):
        if s[i] == '"':
            if i + 1 < len(s) and s[i + 1] == '"':
                out.append('"')
                i += 2
                continue
            return "".join(out), i + 1
        out.append(s[i])
        i += 1
    raise ValueError("unterminated string")


def parse_type_spec(spec: str) -> Optional[TypeNode]:
    spec = spec.strip()
    if not spec or spec == "void:0":
        return None
    head = None
    tail = None
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        k_s, v_s = part.split(":", 1)
        node = TypeNode(type_kind_from_name(k_s.strip()), int(v_s.strip(), 0))
        if head is None:
            head = tail = node
        else:
            tail.next = node
            tail = node
    return head


class ExprParser:
    def __init__(self, s: str):
        self.s = s
        self.i = 0

    def skip(self) -> None:
        while self.i < len(self.s) and self.s[self.i].isspace():
            self.i += 1

    def parse(self) -> ExprNode:
        self.skip()
        if self.s.startswith("T", self.i) and (
            self.i + 1 >= len(self.s) or not (self.s[self.i + 1].isalnum() or self.s[self.i + 1] == "_")
        ):
            self.i += 1
            return ExprNode(EXPR_T)
        if self.s[self.i] != "(":
            raise ValueError("expected ( : %r" % self.s[self.i :])
        self.i += 1
        self.skip()
        j = self.i
        while j < len(self.s) and (self.s[j].isalnum() or self.s[j] == "_"):
            j += 1
        kname = self.s[self.i : j]
        self.i = j
        kind = expr_kind_from_name(kname)
        self.skip()
        if kind == EXPR_T:
            if self.i < len(self.s) and self.s[self.i] == ")":
                self.i += 1
            return ExprNode(EXPR_T)
        if kind in (EXPR_U, EXPR_W):
            text, ni = parse_quoted(self.s, self.i)
            self.i = ni
            self.skip()
            if self.i >= len(self.s) or self.s[self.i] != ")":
                raise ValueError("expected )")
            self.i += 1
            return ExprNode(kind, text=text)
        if kind == EXPR_V:
            j = self.i
            if self.s[j : j + 2].lower() == "0x":
                j += 2
                while j < len(self.s) and self.s[j] in "0123456789abcdefABCDEF":
                    j += 1
            else:
                if self.s[j] == "-":
                    j += 1
                while j < len(self.s) and self.s[j].isdigit():
                    j += 1
            val = int(self.s[self.i : j], 0) & 0xFFFFFFFF
            self.i = j
            self.skip()
            if self.i >= len(self.s) or self.s[self.i] != ")":
                raise ValueError("expected )")
            self.i += 1
            return ExprNode(kind, value=val)
        left = self.parse()
        self.skip()
        right = self.parse()
        self.skip()
        if self.i >= len(self.s) or self.s[self.i] != ")":
            raise ValueError("expected ) after binary")
        self.i += 1
        return ExprNode(kind, left=left, right=right)


def parse_asm(text: str) -> AsmUnit:
    unit = AsmUnit()
    for line in text.splitlines():
        m = re.match(r";\s*encoding:\s*(\S+)", line.strip())
        if m:
            unit.encoding = m.group(1)
            break

    pending: List[str] = []
    max_expr = -1
    for lineno, raw in enumerate(text.splitlines(), 1):
        line = strip_comment(raw).strip()
        if not line:
            continue
        if line.endswith(":") and not line.startswith("."):
            pending.append(line[:-1].strip())
            continue
        if line.startswith(".data_size"):
            unit.data_size = int(line.split(None, 1)[1], 0)
            continue
        if line.startswith(".global"):
            body = line[len(".global") :].strip()
            name, pos = parse_quoted(body, 0)
            rest = body[pos:].lstrip().lstrip(",").strip()
            # type may contain commas (type=array:10,int:4); split on known keys
            fields = {"type": "", "flags": "0", "reserved": "0", "offset": "0"}
            key_re = re.compile(r"(?:^|,\s*)(type|flags|reserved|offset)=")
            matches = list(key_re.finditer(rest))
            for i, m in enumerate(matches):
                key = m.group(1)
                start = m.end()
                end = matches[i + 1].start() if i + 1 < len(matches) else len(rest)
                fields[key] = rest[start:end].strip().rstrip(",").strip()
            unit.globals.append(
                GlobalVar(
                    name,
                    parse_type_spec(fields.get("type", "")),
                    int(fields.get("flags", "0"), 0),
                    int(fields.get("reserved", "0"), 0),
                    int(fields.get("offset", "0"), 0),
                )
            )
            continue
        if line.startswith(".label_def"):
            body = line[len(".label_def") :].strip()
            m = re.match(r"(\d+)\s*,\s*", body)
            if not m:
                raise ValueError("line %d: bad label_def" % lineno)
            idx = int(m.group(1))
            body2 = body[m.end() :]
            name, pos = parse_quoted(body2, 0)
            rest = body2[pos:].lstrip().lstrip(",").strip()
            off = 0
            if rest.startswith("offset="):
                off = int(rest.split("=", 1)[1], 0)
            unit.label_defs.append(LabelDef(idx, name, off))
            unit.label_name_to_index[name] = idx
            continue
        if line.startswith(".expr"):
            body = line[len(".expr") :].strip()
            m = re.match(r"(\d+)\s+", body)
            if not m:
                raise ValueError("line %d: bad expr" % lineno)
            idx = int(m.group(1))
            unit.exprs[idx] = ExprParser(body[m.end() :]).parse()
            if idx > max_expr:
                max_expr = idx
            continue
        m = re.match(r"(\S+)(?:\s+(.*))?$", line)
        if not m:
            raise ValueError("line %d: bad instr" % lineno)
        mnem = m.group(1)
        arg = (m.group(2) or "").strip()
        ins = Instr(mnemonic=mnem, labels_here=list(pending))
        pending.clear()
        if not arg:
            ins.kind = "none"
        elif arg.startswith("expr_"):
            ins.kind = "expr"
            ins.expr_index = int(arg[5:], 0)
        elif arg.startswith('"'):
            ins.kind = "str"
            ins.text, _ = parse_quoted(arg, 0)
        elif re.fullmatch(r"-?\d+|0x[0-9A-Fa-f]+", arg):
            ins.kind = "int"
            ins.imm = int(arg, 0) & 0xFFFFFFFF
        else:
            ins.kind = "label"
            ins.label = arg
        unit.instrs.append(ins)

    if pending:
        unit.instrs.append(Instr(mnemonic="__eof__", kind="none", labels_here=list(pending)))

    for i in range(max_expr + 1):
        if i not in unit.exprs:
            unit.exprs[i] = ExprNode(EXPR_T)

    if unit.label_defs:
        unit.label_defs.sort(key=lambda x: x.index)
        unit.label_name_to_index = {ld.name: ld.index for ld in unit.label_defs}
    return unit


def emit_type(buf: bytearray, t: Optional[TypeNode]) -> None:
    cur = t
    while cur is not None:
        write_u32(buf, cur.kind)
        write_u32(buf, cur.value)
        cur = cur.next
    write_u32(buf, 0)


def emit_expr(buf: bytearray, node: ExprNode, encoding: str) -> None:
    write_u32(buf, node.kind)
    if node.kind == EXPR_T:
        return
    if node.kind in (EXPR_U, EXPR_W):
        write_len_string(buf, node.text or "", encoding)
        return
    if node.kind == EXPR_V:
        write_u32(buf, node.value or 0)
        return
    emit_expr(buf, node.left or ExprNode(EXPR_T), encoding)
    emit_expr(buf, node.right or ExprNode(EXPR_T), encoding)



# Inline source tokens embedded in `text "..."` that expand back to ops.
INLINE_TOKEN_RE = re.compile(r"(\$1|\$2|%haato)")
HAATO_EXPR_NEEDLE_DOT = "(DOT (INT 100) (INT 68))"


def _format_expr_for_match(node: "ExprNode") -> str:
    def rec(n: "ExprNode") -> str:
        if n is None:
            return "T"
        if n.kind == EXPR_T:
            return "T"
        if n.kind == EXPR_U:
            return '(ID "%s")' % (n.text or "")
        if n.kind == EXPR_W:
            return '(STR "%s")' % (n.text or "")
        if n.kind == EXPR_V:
            return "(INT %d)" % (n.value or 0)
        names = {
            88: "CALL", 89: "ARG", 101: "ADD", 102: "COMMA", 103: "SUB",
            104: "DOT", 105: "DIV", 108: "LT", 109: "LE", 110: "GT", 111: "GE",
            112: "EQ", 113: "NE", 120: "ASSIGN", 95: "BNOT",
        }
        kn = names.get(n.kind, "N%d" % n.kind)
        if n.left is None and n.right is None:
            return "(%s)" % kn
        return "(%s %s %s)" % (kn, rec(n.left), rec(n.right))
    return rec(node)


def _expr_is_haato_asm(node: "ExprNode") -> bool:
    s = _format_expr_for_match(node)
    return (
        "FrameLayer_SendMessage" in s
        and HAATO_EXPR_NEEDLE_DOT in s
        and ("{{01}}" in s or "\uf8f3" in s)
    )


def _collect_haato_expr_indices(unit: "AsmUnit") -> List[int]:
    if not unit.exprs:
        return []
    out: List[int] = []
    for i in sorted(unit.exprs.keys()):
        if _expr_is_haato_asm(unit.exprs[i]):
            out.append(i)
    return out


def emit_text_ops(
    code: bytearray,
    opc: int,
    text: str,
    encoding: str,
    haato_q: List[int],
    haato_pos: List[int],
) -> None:
    """Emit one or more ops for a cstr instruction, expanding $1/$2/%haato."""
    parts = INLINE_TOKEN_RE.split(text or "")
    if len(parts) == 1:
        code.append(opc & 0xFF)
        code.extend(encode_text(text or "", encoding))
        code.append(0)
        return
    for part in parts:
        if part == "$1":
            code.append(op_code("num_c") & 0xFF)
            write_u32(code, 1)
        elif part == "$2":
            code.append(op_code("num_c") & 0xFF)
            write_u32(code, 2)
        elif part == "%haato":
            if haato_pos[0] >= len(haato_q):
                raise ValueError(
                    "not enough %haato expr slots in .expr pool "
                    "(need more FrameLayer_SendMessage 100.68)"
                )
            idx = haato_q[haato_pos[0]]
            haato_pos[0] += 1
            code.append(op_code("eval") & 0xFF)
            write_u32(code, idx)
        elif part:
            code.append(opc & 0xFF)
            code.extend(encode_text(part, encoding))
            code.append(0)


def assemble(unit: AsmUnit) -> bytes:
    encoding = unit.encoding
    code = bytearray()
    label_offsets: Dict[str, int] = {}
    real = [ins for ins in unit.instrs if ins.mnemonic != "__eof__"]
    eof_labels: List[str] = []
    for ins in unit.instrs:
        if ins.mnemonic == "__eof__":
            eof_labels.extend(ins.labels_here)

    haato_q = _collect_haato_expr_indices(unit)
    haato_pos = [0]

    for ins in real:
        for lb in ins.labels_here:
            label_offsets[lb] = len(code)
        opc = op_code(ins.mnemonic)
        info = op_info(opc)
        if info.operand == "cstr":
            if ins.kind != "str":
                raise ValueError("%s needs string" % ins.mnemonic)
            # Expand inline $1/$2/%haato inside dialogue text back to original ops.
            if INLINE_TOKEN_RE.search(ins.text or ""):
                emit_text_ops(code, opc, ins.text or "", encoding, haato_q, haato_pos)
            else:
                code.append(opc & 0xFF)
                code.extend(encode_text(ins.text or "", encoding))
                code.append(0)
            continue
        code.append(opc & 0xFF)
        if info.operand == "none":
            pass
        elif info.operand == "u32":
            if ins.kind != "int":
                raise ValueError("%s needs int" % ins.mnemonic)
            write_u32(code, ins.imm or 0)
        elif info.operand == "u32_label":
            if ins.kind == "label":
                idx = unit.label_name_to_index.get(ins.label)
                if idx is None:
                    raise ValueError("unknown label %s" % ins.label)
                write_u32(code, idx)
            elif ins.kind == "int":
                write_u32(code, ins.imm or 0)
            else:
                raise ValueError("%s needs label" % ins.mnemonic)
        elif info.operand == "u32_expr":
            if ins.kind == "expr":
                write_u32(code, ins.expr_index or 0)
            elif ins.kind == "int":
                write_u32(code, ins.imm or 0)
            else:
                raise ValueError("%s needs expr_N" % ins.mnemonic)
        else:
            raise ValueError("bad operand %s" % info.operand)

    if haato_pos[0] != 0 and haato_pos[0] != len(haato_q):
        # Only enforce exact consumption when at least one %haato was expanded.
        # Leftover slots are fine if asm still has explicit eval expr_N for some hearts.
        pass

    end_off = len(code)
    for lb in eof_labels:
        label_offsets[lb] = end_off

    out = bytearray()
    write_u32(out, len(unit.globals))
    for g in unit.globals:
        write_len_string(out, g.name, encoding)
        emit_type(out, g.typ)
        write_u32(out, g.flags)
        write_u32(out, g.reserved)
        write_u32(out, g.offset)
    write_u32(out, unit.data_size)

    if unit.label_defs:
        max_i = max(ld.index for ld in unit.label_defs)
        arr: List[Optional[LabelDef]] = [None] * (max_i + 1)
        for ld in unit.label_defs:
            arr[ld.index] = ld
        write_u32(out, len(arr))
        for i, ld in enumerate(arr):
            if ld is None:
                write_len_string(out, "$MISSING_%d" % i, encoding)
                write_u32(out, 0)
            else:
                off = label_offsets.get(ld.name, ld.offset)
                write_len_string(out, ld.name, encoding)
                write_u32(out, off)
    else:
        write_u32(out, 0)

    if unit.exprs:
        max_e = max(unit.exprs.keys())
        write_u32(out, max_e + 1)
        for i in range(max_e + 1):
            emit_expr(out, unit.exprs.get(i, ExprNode(EXPR_T)), encoding)
    else:
        write_u32(out, 0)

    write_u32(out, len(code))
    out.extend(code)
    return bytes(out)


def assemble_file(in_path: str, out_path: str, encoding: Optional[str] = None) -> None:
    with open(in_path, "r", encoding="utf-8") as f:
        text = f.read()
    unit = parse_asm(text)
    if encoding:
        unit.encoding = encoding
    data = assemble(unit)
    out_dir = os.path.dirname(os.path.abspath(out_path))
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    with open(out_path, "wb") as f:
        f.write(data)
    print("[ok] %s -> %s (%d bytes)" % (in_path, out_path, len(data)))


def batch_txt_to_bin(txt_dir: str, bin_dir: str, encoding: Optional[str] = None) -> None:
    os.makedirs(bin_dir, exist_ok=True)
    for name in os.listdir(txt_dir):
        in_path = os.path.join(txt_dir, name)
        if not os.path.isfile(in_path):
            continue
        if not (name.endswith(".asm.txt") or name.endswith(".txt")):
            continue
        base = name
        if base.endswith(".asm.txt"):
            base = base[: -len(".asm.txt")]
        elif base.endswith(".txt"):
            base = base[: -len(".txt")]
        assemble_file(in_path, os.path.join(bin_dir, base + ".rebuild"), encoding)


def main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) >= 2 and not argv[0].startswith("-") and not argv[1].startswith("-"):
        if os.path.isdir(argv[0]):
            encoding = None
            if "--encoding" in argv:
                encoding = argv[argv.index("--encoding") + 1]
            batch_txt_to_bin(argv[0], argv[1], encoding)
            return 0
    ap = argparse.ArgumentParser(description="Assemble Popotan exec.dat asm")
    ap.add_argument("input")
    ap.add_argument("output", nargs="?")
    ap.add_argument("-o", dest="out_file")
    ap.add_argument("--encoding", default=None)
    args = ap.parse_args(argv)
    if os.path.isdir(args.input):
        batch_txt_to_bin(args.input, args.output or args.out_file or "bin", args.encoding)
        return 0
    out = args.out_file or args.output
    if not out:
        base = os.path.basename(args.input)
        if base.endswith(".asm.txt"):
            base = base[: -len(".asm.txt")]
        out = base + ".rebuild"
    assemble_file(args.input, out, args.encoding)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())