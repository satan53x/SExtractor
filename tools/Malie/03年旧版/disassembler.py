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
expr_kind_name = _opcode.expr_kind_name
op_info = _opcode.op_info
type_kind_name = _opcode.type_kind_name

DEFAULT_ENCODING = "cp932"


class Reader:
    def __init__(self, data: bytes):
        self.data = data
        self.pos = 0

    def remaining(self) -> int:
        return len(self.data) - self.pos

    def u32(self) -> int:
        v = struct.unpack_from("<I", self.data, self.pos)[0]
        self.pos += 4
        return v

    def bytes_(self, n: int) -> bytes:
        b = self.data[self.pos : self.pos + n]
        self.pos += n
        return b

    def cstring_bytes(self) -> bytes:
        n = self.u32()
        return self.bytes_(n)


def _normalize_encoding(encoding: str) -> str:
    enc = (encoding or "").lower().replace("-", "_")
    if enc in ("shift_jis", "shiftjis", "sjis", "ms932", "windows_31j"):
        return "cp932"
    return encoding


def decode_payload(data: bytes, encoding: str) -> str:
    """Decode payload bytes to semantic text.

    Uses cp932 for Japanese game scripts. Undecodable / control bytes become {{XX}}.
    Double-quote is escaped as "" for asm string literals.
    """
    encoding = _normalize_encoding(encoding)
    out: List[str] = []
    i = 0
    is_sjis = _normalize_encoding(encoding) == "cp932" or encoding.lower().replace("-", "").replace("_", "") in (
        "shiftjis",
        "sjis",
        "cp932",
        "ms932",
    )
    # After normalize, encoding is often cp932
    is_sjis = True if _normalize_encoding(encoding) == "cp932" else is_sjis
    encoding = _normalize_encoding(encoding)
    while i < len(data):
        b = data[i]
        # CP932 / Shift_JIS lead byte
        if is_sjis and ((0x81 <= b <= 0x9F) or (0xE0 <= b <= 0xFC)):
            if i + 1 < len(data):
                pair = data[i : i + 2]
                try:
                    ch = pair.decode(encoding, errors="strict")
                    # Escape braces so placeholders stay unambiguous
                    if ch == "{":
                        out.append("{{7B}}")
                    elif ch == "}":
                        out.append("{{7D}}")
                    else:
                        out.append(ch)
                    i += 2
                    continue
                except UnicodeDecodeError:
                    pass
            out.append("{{%02X}}" % b)
            i += 1
            continue
        if b in (0x09, 0x0A, 0x0D):
            out.append("{{%02X}}" % b)
            i += 1
            continue
        if 0x20 <= b <= 0x7E:
            ch = chr(b)
            if ch == '"':
                out.append('""')
            elif ch == "{":
                out.append("{{7B}}")
            elif ch == "}":
                out.append("{{7D}}")
            else:
                out.append(ch)
            i += 1
            continue
        if b < 0x20 or b == 0x7F:
            out.append("{{%02X}}" % b)
            i += 1
            continue
        # halfwidth katakana etc. single-byte in cp932 (0xA1-0xDF)
        try:
            ch = bytes([b]).decode(encoding, errors="strict")
            out.append(ch)
        except UnicodeDecodeError:
            out.append("{{%02X}}" % b)
        i += 1
    return "".join(out)


def decode_bytes(raw: bytes, encoding: str) -> str:
    data = raw[:-1] if raw.endswith(b"\x00") else raw
    return decode_payload(data, encoding)


@dataclass
class TypeNode:
    kind: int
    value: int = 0
    next: Optional["TypeNode"] = None


@dataclass
class GlobalVar:
    name: str
    typ: Optional[TypeNode]
    flags: int
    reserved: int
    offset: int


@dataclass
class Label:
    name: str
    offset: int
    index: int


@dataclass
class ExprNode:
    kind: int
    text: Optional[str] = None
    value: Optional[int] = None
    left: Optional["ExprNode"] = None
    right: Optional["ExprNode"] = None


@dataclass
class Instr:
    pc: int
    opcode: int
    mnemonic: str
    operand_kind: str
    imm: Optional[int] = None
    text: Optional[str] = None
    label_name: Optional[str] = None
    expr_index: Optional[int] = None


@dataclass
class Script:
    globals: List[GlobalVar] = field(default_factory=list)
    data_size: int = 0
    labels: List[Label] = field(default_factory=list)
    exprs: List[ExprNode] = field(default_factory=list)
    code: bytes = b""
    instrs: List[Instr] = field(default_factory=list)
    encoding: str = DEFAULT_ENCODING


def parse_type(r: Reader) -> Optional[TypeNode]:
    kind = r.u32()
    if kind == 0:
        return None
    value = r.u32()
    return TypeNode(kind, value, parse_type(r))


def parse_expr(r: Reader, encoding: str) -> ExprNode:
    kind = r.u32()
    if kind == EXPR_T:
        return ExprNode(kind)
    if kind in (EXPR_U, EXPR_W):
        raw = r.cstring_bytes()
        return ExprNode(kind, text=decode_bytes(raw, encoding))
    if kind == EXPR_V:
        return ExprNode(kind, value=r.u32())
    left = parse_expr(r, encoding)
    right = parse_expr(r, encoding)
    return ExprNode(kind, left=left, right=right)


def parse_exec(data: bytes, encoding: str) -> Script:
    r = Reader(data)
    sc = Script(encoding=encoding)
    gcount = r.u32()
    for _ in range(gcount):
        raw = r.cstring_bytes()
        name = decode_bytes(raw, encoding)
        typ = parse_type(r)
        flags = r.u32()
        reserved = r.u32()
        offset = r.u32()
        sc.globals.append(GlobalVar(name, typ, flags, reserved, offset))
    sc.data_size = r.u32()
    lcount = r.u32()
    for i in range(lcount):
        raw = r.cstring_bytes()
        name = decode_bytes(raw, encoding)
        off = r.u32()
        sc.labels.append(Label(name, off, i))
    ecount = r.u32()
    # iterative stack parse would be safer for huge depth; recursion is fine for this game AST
    sys.setrecursionlimit(max(10000, sys.getrecursionlimit()))
    for _ in range(ecount):
        sc.exprs.append(parse_expr(r, encoding))
    csize = r.u32()
    sc.code = r.bytes_(csize)
    return sc


def disassemble_code(sc: Script) -> None:
    code = sc.code
    n = len(code)
    pc = 0
    instrs: List[Instr] = []
    while pc < n:
        op = code[pc]
        start = pc
        pc += 1
        info = op_info(op)
        imm = None
        text = None
        label_name = None
        expr_index = None
        if info.operand == "cstr":
            s = pc
            while pc < n and code[pc] != 0:
                pc += 1
            text = decode_payload(bytes(code[s:pc]), sc.encoding)
            if pc < n and code[pc] == 0:
                pc += 1
        elif info.operand in ("u32", "u32_label", "u32_expr"):
            if pc + 4 > n:
                break
            imm = struct.unpack_from("<I", code, pc)[0]
            pc += 4
            if info.operand == "u32_label" and imm < len(sc.labels):
                label_name = sc.labels[imm].name
            if info.operand == "u32_expr":
                expr_index = imm
        instrs.append(
            Instr(start, op, info.mnemonic, info.operand, imm, text, label_name, expr_index)
        )
    sc.instrs = instrs


def format_type(t: Optional[TypeNode]) -> str:
    parts: List[str] = []
    cur = t
    while cur is not None:
        parts.append("%s:%d" % (type_kind_name(cur.kind), cur.value))
        cur = cur.next
    return ",".join(parts) if parts else "void:0"


def format_expr(node: ExprNode) -> str:
    kname = expr_kind_name(node.kind)
    if node.kind == EXPR_T:
        return "T"
    if node.kind in (EXPR_U, EXPR_W):
        return '(%s "%s")' % (kname, node.text or "")
    if node.kind == EXPR_V:
        return "(%s %d)" % (kname, node.value or 0)
    left = format_expr(node.left) if node.left else "T"
    right = format_expr(node.right) if node.right else "T"
    return "(%s %s %s)" % (kname, left, right)


def emit_asm(sc: Script) -> str:
    lines: List[str] = []
    lines.append("; Popotan exec.dat disassembly")
    lines.append("; encoding: %s" % sc.encoding)
    lines.append(
        "; globals: %d  labels: %d  exprs: %d  code: %d"
        % (len(sc.globals), len(sc.labels), len(sc.exprs), len(sc.code))
    )
    lines.append("")
    lines.append("; ============================================================")
    lines.append("; Global variables")
    lines.append("; ============================================================")
    lines.append(".data_size %d" % sc.data_size)
    for g in sc.globals:
        lines.append(
            '.global "%s", type=%s, flags=%d, reserved=%d, offset=%d'
            % (g.name, format_type(g.typ), g.flags, g.reserved, g.offset)
        )
    lines.append("")
    lines.append("; ============================================================")
    lines.append("; Label table (index order)")
    lines.append("; ============================================================")
    for lab in sc.labels:
        lines.append('.label_def %d, "%s", offset=%d' % (lab.index, lab.name, lab.offset))
    lines.append("")
    lines.append("; ============================================================")
    lines.append("; Expression pool")
    lines.append("; ============================================================")
    for i, e in enumerate(sc.exprs):
        lines.append(".expr %d %s" % (i, format_expr(e)))
    lines.append("")
    lines.append("; ============================================================")
    lines.append("; Code")
    lines.append("; ============================================================")
    labels_by_off: Dict[int, List[Label]] = {}
    for lab in sc.labels:
        labels_by_off.setdefault(lab.offset, []).append(lab)
    for ins in sc.instrs:
        if ins.pc in labels_by_off:
            lines.append("")
            for lab in labels_by_off[ins.pc]:
                lines.append("%s:" % lab.name)
        if ins.operand_kind == "none":
            lines.append("    %s" % ins.mnemonic)
        elif ins.operand_kind == "cstr":
            lines.append('    %s "%s"' % (ins.mnemonic, ins.text or ""))
        elif ins.operand_kind == "u32":
            lines.append("    %s %d" % (ins.mnemonic, ins.imm))
        elif ins.operand_kind == "u32_label":
            if ins.label_name is not None:
                lines.append("    %s %s" % (ins.mnemonic, ins.label_name))
            else:
                lines.append("    %s %d" % (ins.mnemonic, ins.imm))
        elif ins.operand_kind == "u32_expr":
            lines.append("    %s expr_%d" % (ins.mnemonic, ins.expr_index))
        else:
            lines.append("    %s" % ins.mnemonic)
    end_pc = len(sc.code)
    if end_pc in labels_by_off:
        lines.append("")
        for lab in labels_by_off[end_pc]:
            lines.append("%s:" % lab.name)
    lines.append("")
    return "\n".join(lines)


def disassemble_file(in_path: str, out_path: str, encoding: str) -> None:
    with open(in_path, "rb") as f:
        data = f.read()
    sc = parse_exec(data, encoding)
    disassemble_code(sc)
    text = emit_asm(sc)
    out_dir = os.path.dirname(os.path.abspath(out_path))
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    with open(out_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    print("[ok] %s -> %s" % (in_path, out_path))
    print(
        "     globals=%d labels=%d exprs=%d code=%d instrs=%d"
        % (len(sc.globals), len(sc.labels), len(sc.exprs), len(sc.code), len(sc.instrs))
    )


def batch_bin_to_txt(bin_dir: str, txt_dir: str, encoding: str) -> None:
    os.makedirs(txt_dir, exist_ok=True)
    files = [n for n in os.listdir(bin_dir) if os.path.isfile(os.path.join(bin_dir, n))]
    for name in files:
        disassemble_file(os.path.join(bin_dir, name), os.path.join(txt_dir, name + ".asm.txt"), encoding)


def main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) >= 2 and not argv[0].startswith("-") and not argv[1].startswith("-"):
        if os.path.isdir(argv[0]):
            encoding = DEFAULT_ENCODING
            if "--encoding" in argv:
                encoding = argv[argv.index("--encoding") + 1]
            batch_bin_to_txt(argv[0], argv[1], encoding)
            return 0
    ap = argparse.ArgumentParser(description="Disassemble Popotan exec.dat")
    ap.add_argument("input")
    ap.add_argument("output", nargs="?")
    ap.add_argument("-o", dest="out_file")
    ap.add_argument("--encoding", default=DEFAULT_ENCODING)
    args = ap.parse_args(argv)
    if os.path.isdir(args.input):
        batch_bin_to_txt(args.input, args.output or args.out_file or "txt", args.encoding)
        return 0
    out = args.out_file or args.output or (os.path.basename(args.input) + ".asm.txt")
    disassemble_file(args.input, out, args.encoding)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())