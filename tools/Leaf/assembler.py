"""SDT semantic asm assembler.

Drag an .asm.txt file onto this script, or run from a shell:

    python assembler.py input.asm.txt [-o output.SDT] [--encoding cp932]
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import re
import sys
from typing import Dict, List, Sequence

import opcodelist as opdefs


class AsmError(Exception):
    pass


@dataclass
class Directive:
    name: str
    args: str
    line_no: int


@dataclass
class Label:
    name: str
    line_no: int


@dataclass
class Inst:
    mnemonic: str
    operands: List[str]
    line_no: int


Node = Directive | Label | Inst


def strip_comment(line: str) -> str:
    in_string = False
    i = 0
    while i < len(line):
        ch = line[i]
        if ch == '"':
            if in_string and i + 1 < len(line) and line[i + 1] == '"':
                i += 2
                continue
            in_string = not in_string
        elif ch == ';' and not in_string:
            return line[:i]
        i += 1
    return line


def split_top(text: str, sep: str = ',') -> List[str]:
    parts: List[str] = []
    start = 0
    depth = 0
    in_string = False
    i = 0
    while i < len(text):
        ch = text[i]
        if ch == '"':
            if in_string and i + 1 < len(text) and text[i + 1] == '"':
                i += 2
                continue
            in_string = not in_string
        elif not in_string:
            if ch in '([':
                depth += 1
            elif ch in ')]':
                depth -= 1
                if depth < 0:
                    raise AsmError(f"unbalanced delimiter in {text!r}")
            elif ch == sep and depth == 0:
                parts.append(text[start:i].strip())
                start = i + 1
        i += 1
    if in_string:
        raise AsmError(f"unterminated string in {text!r}")
    if depth != 0:
        raise AsmError(f"unbalanced delimiter in {text!r}")
    tail = text[start:].strip()
    if tail:
        parts.append(tail)
    return parts


def parse_call(text: str) -> tuple[str, List[str]]:
    text = text.strip()
    m = re.fullmatch(r'([A-Za-z_][A-Za-z0-9_]*)\((.*)\)', text, flags=re.S)
    if not m:
        raise AsmError(f"expected function-style operand, got {text!r}")
    return m.group(1), split_top(m.group(2))


def unquote(text: str) -> str:
    text = text.strip()
    if len(text) < 2 or text[0] != '"' or text[-1] != '"':
        raise AsmError(f"expected quoted string, got {text!r}")
    out: List[str] = []
    i = 1
    while i < len(text) - 1:
        ch = text[i]
        if ch == '"':
            if i + 1 < len(text) - 1 and text[i + 1] == '"':
                out.append('"')
                i += 2
                continue
            raise AsmError(f"unescaped quote in {text!r}; use doubled quotes")
        out.append(ch)
        i += 1
    return ''.join(out)


def parse_asm_string(text: str, encoding: str) -> bytes:
    content = unquote(text)
    out = bytearray()
    buf: List[str] = []
    i = 0

    def flush() -> None:
        if buf:
            out.extend(''.join(buf).encode(encoding))
            buf.clear()

    while i < len(content):
        if content[i:i + 2] == '{{':
            end = content.find('}}', i + 2)
            if end == -1:
                raise AsmError(f"unterminated placeholder in {text!r}")
            flush()
            body = content[i + 2:end]
            pieces = body.split(':')
            if not pieces or any(not re.fullmatch(r'[0-9A-Fa-f]{2}', p) for p in pieces):
                raise AsmError(f"invalid placeholder {{{{{body}}}}}")
            out.extend(int(p, 16) for p in pieces)
            i = end + 2
        else:
            ch = content[i]
            buf.append(ch)
            i += 1
    flush()
    return bytes(out)


def parse_int(text: str) -> int:
    text = text.strip()
    try:
        return int(text, 0)
    except ValueError as exc:
        raise AsmError(f"expected integer, got {text!r}") from exc


def parse_u8(text: str) -> int:
    value = parse_int(text)
    if not 0 <= value <= 0xFF:
        raise AsmError(f"u8 out of range: {value}")
    return value


def parse_u16(text: str) -> int:
    value = parse_int(text)
    if not 0 <= value <= 0xFFFF:
        raise AsmError(f"u16 out of range: {value}")
    return value


def parse_i16(text: str) -> int:
    value = parse_int(text)
    if not -0x8000 <= value <= 0x7FFF:
        raise AsmError(f"i16 out of range: {value}")
    return value


def parse_i32_value(text: str) -> int:
    value = parse_int(text)
    if not -0x80000000 <= value <= 0x7FFFFFFF:
        raise AsmError(f"i32 out of range: {value}")
    return value


def parse_local(text: str) -> int:
    text = text.strip()
    m = re.fullmatch(r'L(\d+)', text)
    if m:
        return parse_u8(m.group(1))
    name, args = parse_call(text)
    if name != 'local' or len(args) != 1:
        raise AsmError(f"expected local operand L0/local(0), got {text!r}")
    return parse_u8(args[0])


def parse_cmp(text: str) -> int:
    text = text.strip()
    if text in opdefs.CMP_VALUES:
        return opdefs.CMP_VALUES[text]
    m = re.fullmatch(r'cmp(\d+)', text)
    if m:
        return parse_u8(m.group(1))
    raise AsmError(f"unknown comparison operator {text!r}")


def i16_bytes(value: int) -> bytes:
    return value.to_bytes(2, 'little', signed=True)


def u16_bytes(value: int) -> bytes:
    return value.to_bytes(2, 'little')


def i32_bytes(value: int) -> bytes:
    return value.to_bytes(4, 'little', signed=True)


def u32_bytes(value: int) -> bytes:
    return value.to_bytes(4, 'little')


def resolve_label(text: str, labels: Dict[str, int] | None) -> int:
    text = text.strip()
    if labels is None:
        return 0
    if text not in labels:
        raise AsmError(f"unknown label {text!r}")
    return labels[text]


def encode_typed(text: str, encoding: str) -> bytes:
    name, args = parse_call(text)
    if name == 'local' and len(args) == 1:
        return bytes([0]) + i32_bytes(parse_i32_value(args[0]))
    if name == 'imm' and len(args) == 1:
        return bytes([1]) + i32_bytes(parse_i32_value(args[0]))
    if name == 'numstr' and len(args) == 1:
        raw = parse_asm_string(args[0], encoding)
        if len(raw) > 0xFF:
            raise AsmError(f"numstr too long: {len(raw)} bytes")
        return bytes([2, len(raw)]) + raw
    if name == 'typed' and len(args) == 2:
        mode = parse_u8(args[0])
        if mode == 2:
            raise AsmError('typed(2, ...) is ambiguous; use numstr("...")')
        return bytes([mode]) + i32_bytes(parse_i32_value(args[1]))
    raise AsmError(f"expected typed_i32 operand, got {text!r}")


def encode_desc(desc: int, text: str, encoding: str) -> bytes:
    text = text.strip()
    if desc == 1:
        name, args = parse_call(text)
        if name != 'u8' or len(args) != 1:
            raise AsmError(f"expected u8(...), got {text!r}")
        return bytes([parse_u8(args[0])])
    if desc == 7:
        name, args = parse_call(text)
        if name != 'u8_alt' or len(args) != 1:
            raise AsmError(f"expected u8_alt(...), got {text!r}")
        return bytes([parse_u8(args[0])])
    if desc == 2:
        return encode_typed(text, encoding)
    if desc in (3, 4):
        name, args = parse_call(text)
        expected = 'str8' if desc == 3 else 'str16'
        if name != expected or len(args) != 1:
            raise AsmError(f"expected {expected}(...), got {text!r}")
        raw = parse_asm_string(args[0], encoding)
        if desc == 3:
            if len(raw) > 0xFF:
                raise AsmError(f"str8 too long: {len(raw)} bytes")
            return bytes([len(raw)]) + raw
        if len(raw) > 0xFFFF:
            raise AsmError(f"str16 too long: {len(raw)} bytes")
        return u16_bytes(len(raw)) + raw
    if desc == 5:
        name, args = parse_call(text)
        if name != 'out' or len(args) != 1:
            raise AsmError(f"expected out(Ln), got {text!r}")
        return bytes([parse_local(args[0])])
    if desc == 6:
        name, args = parse_call(text)
        if name != 'cmp' or len(args) != 3:
            raise AsmError(f"expected cmp(Ln, op, typed), got {text!r}")
        return bytes([parse_local(args[0]), parse_cmp(args[1])]) + encode_typed(args[2], encoding)
    if desc == 8:
        name, args = parse_call(text)
        if name != 'u16' or len(args) != 1:
            raise AsmError(f"expected u16(...), got {text!r}")
        return u16_bytes(parse_u16(args[0]))
    if desc == 9:
        name, args = parse_call(text)
        if name != 'u16_alt' or len(args) != 1:
            raise AsmError(f"expected u16_alt(...), got {text!r}")
        return u16_bytes(parse_u16(args[0]))
    raise AsmError(f"unsupported descriptor code {desc}")


def encode_external(inst: Inst, encoding: str) -> bytes:
    cmd = opdefs.EXTERNALS_BY_NAME.get(inst.mnemonic)
    if cmd is None:
        raise AsmError(f"line {inst.line_no}: unknown external mnemonic {inst.mnemonic!r}")
    if len(inst.operands) != len(cmd.descriptors):
        raise AsmError(f"line {inst.line_no}: {inst.mnemonic} expects {len(cmd.descriptors)} operands, got {len(inst.operands)}")
    out = bytearray(u16_bytes(cmd.opcode))
    for desc, text in zip(cmd.descriptors, inst.operands):
        out.extend(encode_desc(desc, text, encoding))
    return bytes(out)


def encode_expr_operand(text: str, encoding: str) -> bytes:
    name, args = parse_call(text)
    if name == 'expr_raw' and len(args) == 1:
        return parse_asm_string(args[0], encoding)
    if name == 'expr' and len(args) == 1:
        body = args[0].strip()
        if not (body.startswith('[') and body.endswith(']')):
            raise AsmError('expr(...) must contain a bracketed token list')
        tokens = split_top(body[1:-1])
        out = bytearray()
        for token in tokens:
            tname, targs = parse_call(token)
            if tname == 'imm32' and len(targs) == 1:
                out.append(0)
                out.extend(i32_bytes(parse_i32_value(targs[0])))
            elif tname == 'local' and len(targs) == 1:
                out.extend([1, parse_u8(targs[0])])
            elif tname == 'op' and len(targs) == 1:
                op_text = targs[0].strip()
                if op_text in opdefs.EXPR_VALUES:
                    code = opdefs.EXPR_VALUES[op_text]
                else:
                    code = parse_u8(op_text)
                out.extend([2, code])
            else:
                raise AsmError(f"unsupported EVAL_EXPR token {token!r}")
        return bytes(out)
    raise AsmError(f"expected expr_raw(...) or expr([...]), got {text!r}")


def encode_builtin(inst: Inst, labels: Dict[str, int] | None, encoding: str) -> bytes:
    spec = opdefs.BUILTINS_BY_NAME.get(inst.mnemonic)
    if spec is None:
        raise AsmError(f"line {inst.line_no}: unknown builtin mnemonic {inst.mnemonic!r}")
    ops = inst.operands
    m = inst.mnemonic

    def expect(n: int) -> None:
        if len(ops) != n:
            raise AsmError(f"line {inst.line_no}: {m} expects {n} operands, got {len(ops)}")

    out = bytearray(u16_bytes(spec.opcode))
    if m in {"END", "PUSH_LOCALS", "POP_LOCALS", "RET", "YIELD_NOP"}:
        expect(0)
    elif m in {"MOV_LOCAL_LOCAL", "SWAP_LOCAL"}:
        expect(2)
        out.extend([parse_local(ops[0]), parse_local(ops[1])])
    elif m == "MOV_LOCAL_IMM32":
        expect(2)
        out.append(parse_local(ops[0]))
        out.extend(i32_bytes(parse_i32_value(ops[1])))
    elif m == "RAND_LOCAL":
        expect(1)
        out.append(parse_local(ops[0]))
    elif m == "JCC_LOCAL_LOCAL_SKIP":
        expect(4)
        out.extend([parse_local(ops[0]), parse_cmp(ops[1]), parse_local(ops[2])])
        out.extend(u32_bytes(resolve_label(ops[3], labels)))
    elif m == "JCC_LOCAL_IMM32_SKIP":
        expect(4)
        out.extend([parse_local(ops[0]), parse_cmp(ops[1])])
        out.extend(i32_bytes(parse_i32_value(ops[2])))
        out.extend(u32_bytes(resolve_label(ops[3], labels)))
    elif m == "JCC_LOCAL_LOCAL_ELSE":
        expect(5)
        out.extend([parse_local(ops[0]), parse_cmp(ops[1]), parse_local(ops[2])])
        out.extend(u32_bytes(resolve_label(ops[3], labels)))
        out.extend(u32_bytes(resolve_label(ops[4], labels)))
    elif m == "JCC_LOCAL_IMM32_ELSE":
        expect(5)
        out.extend([parse_local(ops[0]), parse_cmp(ops[1])])
        out.extend(i32_bytes(parse_i32_value(ops[2])))
        out.extend(u32_bytes(resolve_label(ops[3], labels)))
        out.extend(u32_bytes(resolve_label(ops[4], labels)))
    elif m == "LOOP_DEC_JNZ":
        expect(2)
        out.append(parse_local(ops[0]))
        out.extend(u32_bytes(resolve_label(ops[1], labels)))
    elif m == "JMP":
        expect(1)
        out.extend(u32_bytes(resolve_label(ops[0], labels)))
    elif m in {"INC_LOCAL", "DEC_LOCAL", "BITNOT_LOCAL", "NEG_LOCAL"}:
        expect(1)
        out.append(parse_local(ops[0]))
    elif 0x0010 <= spec.opcode <= 0x001F:
        expect(2)
        out.append(parse_local(ops[0]))
        if spec.opcode % 2 == 0:
            out.append(parse_local(ops[1]))
        else:
            out.extend(i32_bytes(parse_i32_value(ops[1])))
    elif m == "EVAL_EXPR":
        expect(2)
        out.append(parse_local(ops[0]))
        raw = encode_expr_operand(ops[1], encoding)
        if len(raw) > 0x7FFF:
            raise AsmError(f"line {inst.line_no}: EVAL_EXPR packet too long: {len(raw)}")
        out.extend(i16_bytes(len(raw)))
        out.extend(raw)
    elif m == "CALL_ENTRY":
        expect(1)
        out.append(parse_u8(ops[0]))
    elif m in {"WAIT_FRAMES", "WAIT_TIME_MS"}:
        expect(1)
        out.extend(i16_bytes(parse_i16(ops[0])))
    elif m == "LOAD_SDT":
        expect(1)
        name, args = parse_call(ops[0])
        if name != 'str8' or len(args) != 1:
            raise AsmError(f"line {inst.line_no}: LOAD_SDT expects str8(...)")
        raw = parse_asm_string(args[0], encoding)
        if len(raw) > 0xFF:
            raise AsmError(f"line {inst.line_no}: LOAD_SDT filename too long: {len(raw)}")
        out.append(len(raw))
        out.extend(raw)
    else:
        raise AsmError(f"line {inst.line_no}: no encoder for builtin {m}")
    return bytes(out)


def encode_inst(inst: Inst, labels: Dict[str, int] | None, encoding: str) -> bytes:
    if inst.mnemonic in opdefs.BUILTINS_BY_NAME:
        return encode_builtin(inst, labels, encoding)
    return encode_external(inst, encoding)


def parse_nodes(text: str) -> tuple[List[Node], str | None, str | None]:
    nodes: List[Node] = []
    asm_encoding: str | None = None
    source: str | None = None
    for line_no, raw_line in enumerate(text.splitlines(), 1):
        line = strip_comment(raw_line).strip()
        if not line:
            continue
        if line.endswith(':'):
            name = line[:-1].strip()
            if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', name):
                raise AsmError(f"line {line_no}: invalid label {name!r}")
            nodes.append(Label(name, line_no))
            continue
        if line.startswith('.'):
            if ' ' in line:
                name, args = line.split(None, 1)
            else:
                name, args = line, ''
            directive = Directive(name, args.strip(), line_no)
            nodes.append(directive)
            if name == '.encoding':
                asm_encoding = unquote(args.strip())
            elif name == '.source':
                source = unquote(args.strip())
            continue
        if ' ' in line:
            mnemonic, rest = line.split(None, 1)
            operands = split_top(rest)
        else:
            mnemonic, operands = line, []
        nodes.append(Inst(mnemonic, operands, line_no))
    return nodes, asm_encoding, source


def assemble_nodes(nodes: List[Node], encoding: str) -> bytes:
    labels: Dict[str, int] = {}
    entries: Dict[int, str | None] = {}
    offset = 0

    for node in nodes:
        if isinstance(node, Label):
            if node.name in labels:
                raise AsmError(f"line {node.line_no}: duplicate label {node.name}")
            labels[node.name] = offset
        elif isinstance(node, Directive):
            if node.name == '.entry':
                parts = split_top(node.args)
                if len(parts) != 2:
                    raise AsmError(f"line {node.line_no}: .entry expects index, target")
                idx = parse_u8(parts[0])
                target = parts[1].strip()
                entries[idx] = None if target == '0' else target
            elif node.name in {'.encoding', '.source', '.file_size'}:
                pass
            else:
                raise AsmError(f"line {node.line_no}: unknown directive {node.name}")
        elif isinstance(node, Inst):
            offset += len(encode_inst(node, None, encoding))

    body = bytearray()
    for node in nodes:
        if isinstance(node, Inst):
            body.extend(encode_inst(node, labels, encoding))

    header = bytearray(opdefs.HEADER_SIZE)
    header[0:2] = u16_bytes(opdefs.MAGIC0)
    header[2:4] = u16_bytes(opdefs.MAGIC1)
    header[4:8] = u32_bytes(opdefs.HEADER_SIZE + len(body))
    for i in range(opdefs.ENTRY_COUNT):
        target = entries.get(i)
        value = 0
        if target is not None:
            if target not in labels:
                raise AsmError(f".entry {i} references unknown label {target!r}")
            value = labels[target] + 1
        start = opdefs.ENTRY_TABLE_OFFSET + i * 4
        header[start:start + 4] = u32_bytes(value)
    return bytes(header + body)


def default_output(input_path: Path, source: str | None) -> Path:
    if source:
        src = Path(source).name
        if src.lower().endswith('.sdt'):
            return input_path.with_name(src + '.rebuild.SDT')
    return input_path.with_suffix(input_path.suffix + '.rebuild')


def assemble_file(input_path: Path, output_path: Path | None, override_encoding: str | None) -> Path:
    text = input_path.read_text(encoding='utf-8')
    nodes, asm_encoding, source = parse_nodes(text)
    encoding = override_encoding or asm_encoding or opdefs.DEFAULT_ENCODING
    data = assemble_nodes(nodes, encoding)
    out = output_path or default_output(input_path, source)
    out.write_bytes(data)
    return out


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Assemble semantic SDT asm text back to binary SDT.')
    parser.add_argument('input', help='input asm.txt file')
    parser.add_argument('-o', '--output', help='output binary path')
    parser.add_argument('--encoding', help='override text encoding for string operands')
    args = parser.parse_args(argv)

    try:
        out = assemble_file(Path(args.input), Path(args.output) if args.output else None, args.encoding)
        print(f"{args.input} -> {out}")
        return 0
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
