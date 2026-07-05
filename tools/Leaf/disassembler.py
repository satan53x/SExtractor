"""SDT bytecode disassembler.

Drag one or more .SDT files onto this script, or run from a shell:

    python disassembler.py input.SDT [-o output.asm.txt] [--encoding cp932]
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import sys
from typing import Any, Dict, List, Sequence, Set

import opcodelist as opdefs


class DecodeError(Exception):
    pass


@dataclass
class Instruction:
    offset: int
    opcode: int
    mnemonic: str
    operands: List[Any]
    size: int
    external: bool = False


def need(data: bytes, off: int, size: int, path: Path) -> None:
    if off < 0 or off + size > len(data):
        raise DecodeError(f"{path}: body+0x{off:08X}: need {size} byte(s), body size is 0x{len(data):X}")


def u8(data: bytes, off: int, path: Path) -> int:
    need(data, off, 1, path)
    return data[off]


def u16(data: bytes, off: int, path: Path) -> int:
    need(data, off, 2, path)
    return int.from_bytes(data[off:off + 2], "little", signed=False)


def i16(data: bytes, off: int, path: Path) -> int:
    need(data, off, 2, path)
    return int.from_bytes(data[off:off + 2], "little", signed=True)


def u32(data: bytes, off: int, path: Path) -> int:
    need(data, off, 4, path)
    return int.from_bytes(data[off:off + 4], "little", signed=False)


def i32(data: bytes, off: int, path: Path) -> int:
    need(data, off, 4, path)
    return int.from_bytes(data[off:off + 4], "little", signed=True)


def label_for(offset: int) -> str:
    return f"loc_{offset:08X}"


def quote_directive(text: str) -> str:
    return '"' + text.replace('"', '""') + '"'


def placeholder(bs: bytes) -> str:
    return "{{" + ":".join(f"{b:02X}" for b in bs) + "}}"


def is_private_use(ch: str) -> bool:
    code = ord(ch)
    return (
        0xE000 <= code <= 0xF8FF
        or 0xF0000 <= code <= 0xFFFFD
        or 0x100000 <= code <= 0x10FFFD
    )


def safe_text(ch: str) -> bool:
    if ch in {'{', '}'}:
        return False
    code = ord(ch)
    if code < 0x20 or code == 0x7F:
        return False
    return not is_private_use(ch)


def render_bytes(raw: bytes, encoding: str) -> str:
    parts: List[str] = []
    i = 0
    while i < len(raw):
        b = raw[i]
        if b < 0x20 or b == 0x7F:
            parts.append(placeholder(bytes([b])))
            i += 1
            continue
        best_len = 0
        best_text = ""
        for n in range(1, min(4, len(raw) - i) + 1):
            chunk = raw[i:i + n]
            try:
                text = chunk.decode(encoding)
                if text.encode(encoding) != chunk:
                    continue
            except (UnicodeDecodeError, UnicodeEncodeError, LookupError):
                continue
            if len(text) != 1:
                continue
            if is_private_use(text):
                parts.append(placeholder(chunk))
                best_len = n
                best_text = ""
                break
            if not safe_text(text):
                continue
            best_len = n
            best_text = text
            break
        if best_len:
            if best_text:
                parts.append(best_text.replace('"', '""'))
            i += best_len
        else:
            parts.append(placeholder(bytes([b])))
            i += 1
    return '"' + "".join(parts) + '"'


def render_string_call(kind: str, raw: bytes, encoding: str) -> str:
    return f"{kind}({render_bytes(raw, encoding)})"


def decode_typed_i32(data: bytes, off: int, path: Path) -> tuple[Dict[str, Any], int]:
    mode = u8(data, off, path)
    off += 1
    if mode == 2:
        ln = u8(data, off, path)
        off += 1
        need(data, off, ln, path)
        raw = data[off:off + ln]
        off += ln
        return {"kind": "typed_i32", "mode": mode, "raw": raw}, off
    value = i32(data, off, path)
    off += 4
    return {"kind": "typed_i32", "mode": mode, "value": value}, off


def render_typed_i32(value: Dict[str, Any], encoding: str) -> str:
    mode = value["mode"]
    if mode == 0:
        return f"local({value['value']})"
    if mode == 1:
        return f"imm({value['value']})"
    if mode == 2:
        return f"numstr({render_bytes(value['raw'], encoding)})"
    return f"typed({mode}, {value['value']})"


def decode_external(body: bytes, off: int, opcode: int, path: Path) -> Instruction:
    cmd = opdefs.EXTERNALS_BY_OPCODE.get(opcode)
    if cmd is None:
        raise DecodeError(f"{path}: body+0x{off:08X} file+0x{opdefs.HEADER_SIZE + off:08X}: unknown external opcode 0x{opcode:04X}")
    pos = off + 2
    operands: List[Any] = []
    for desc in cmd.descriptors:
        if desc in (1, 7):
            operands.append({"desc": desc, "value": u8(body, pos, path)})
            pos += 1
        elif desc == 2:
            value, pos = decode_typed_i32(body, pos, path)
            operands.append(value)
        elif desc == 3:
            ln = u8(body, pos, path)
            pos += 1
            need(body, pos, ln, path)
            operands.append({"desc": desc, "raw": body[pos:pos + ln]})
            pos += ln
        elif desc == 4:
            ln = u16(body, pos, path)
            pos += 2
            need(body, pos, ln, path)
            operands.append({"desc": desc, "raw": body[pos:pos + ln]})
            pos += ln
        elif desc == 5:
            operands.append({"desc": desc, "local": u8(body, pos, path)})
            pos += 1
        elif desc == 6:
            local = u8(body, pos, path)
            cmp_op = u8(body, pos + 1, path)
            typed, pos2 = decode_typed_i32(body, pos + 2, path)
            operands.append({"desc": desc, "local": local, "cmp": cmp_op, "typed": typed})
            pos = pos2
        elif desc in (8, 9):
            operands.append({"desc": desc, "value": u16(body, pos, path)})
            pos += 2
        else:
            raise DecodeError(f"{path}: body+0x{off:08X}: unsupported descriptor {desc} for opcode 0x{opcode:04X}")
    return Instruction(off, opcode, cmd.name, operands, pos - off, external=True)


def decode_builtin(body: bytes, off: int, opcode: int, path: Path) -> Instruction:
    spec = opdefs.BUILTINS_BY_OPCODE.get(opcode)
    if spec is None:
        if 0x002A <= opcode < 0x0040:
            raise DecodeError(f"{path}: body+0x{off:08X} file+0x{opdefs.HEADER_SIZE + off:08X}: reserved opcode 0x{opcode:04X}; possible prior length desync")
        raise DecodeError(f"{path}: body+0x{off:08X} file+0x{opdefs.HEADER_SIZE + off:08X}: unknown builtin opcode 0x{opcode:04X}")

    ops: List[Any] = []
    m = spec.mnemonic
    if m in {"END", "PUSH_LOCALS", "POP_LOCALS", "RET", "YIELD_NOP"}:
        size = 2
    elif m == "MOV_LOCAL_LOCAL":
        ops = [u8(body, off + 2, path), u8(body, off + 3, path)]
        size = 4
    elif m == "MOV_LOCAL_IMM32":
        ops = [u8(body, off + 2, path), i32(body, off + 3, path)]
        size = 7
    elif m == "SWAP_LOCAL":
        ops = [u8(body, off + 2, path), u8(body, off + 3, path)]
        size = 4
    elif m == "RAND_LOCAL":
        ops = [u8(body, off + 2, path)]
        size = 3
    elif m == "JCC_LOCAL_LOCAL_SKIP":
        ops = [u8(body, off + 2, path), u8(body, off + 3, path), u8(body, off + 4, path), u32(body, off + 5, path)]
        size = 9
    elif m == "JCC_LOCAL_IMM32_SKIP":
        ops = [u8(body, off + 2, path), u8(body, off + 3, path), i32(body, off + 4, path), u32(body, off + 8, path)]
        size = 12
    elif m == "JCC_LOCAL_LOCAL_ELSE":
        ops = [u8(body, off + 2, path), u8(body, off + 3, path), u8(body, off + 4, path), u32(body, off + 5, path), u32(body, off + 9, path)]
        size = 13
    elif m == "JCC_LOCAL_IMM32_ELSE":
        ops = [u8(body, off + 2, path), u8(body, off + 3, path), i32(body, off + 4, path), u32(body, off + 8, path), u32(body, off + 12, path)]
        size = 16
    elif m == "LOOP_DEC_JNZ":
        ops = [u8(body, off + 2, path), u32(body, off + 3, path)]
        size = 7
    elif m == "JMP":
        ops = [u32(body, off + 2, path)]
        size = 6
    elif m in {"INC_LOCAL", "DEC_LOCAL", "BITNOT_LOCAL", "NEG_LOCAL"}:
        ops = [u8(body, off + 2, path)]
        size = 3
    elif m.endswith("_LOCAL") and 0x0010 <= opcode <= 0x001F and opcode % 2 == 0:
        ops = [u8(body, off + 2, path), u8(body, off + 3, path)]
        size = 4
    elif m.endswith("_IMM32") and 0x0010 <= opcode <= 0x001F and opcode % 2 == 1:
        ops = [u8(body, off + 2, path), i32(body, off + 3, path)]
        size = 7
    elif m == "EVAL_EXPR":
        dst = u8(body, off + 2, path)
        expr_len = i16(body, off + 3, path)
        if expr_len < 0:
            raise DecodeError(f"{path}: body+0x{off:08X}: negative EVAL_EXPR length {expr_len}")
        need(body, off + 5, expr_len, path)
        ops = [dst, body[off + 5:off + 5 + expr_len]]
        size = 5 + expr_len
    elif m == "CALL_ENTRY":
        ops = [u8(body, off + 2, path)]
        size = 3
    elif m in {"WAIT_FRAMES", "WAIT_TIME_MS"}:
        ops = [i16(body, off + 2, path)]
        size = 4
    elif m == "LOAD_SDT":
        ln = u8(body, off + 2, path)
        need(body, off + 3, ln, path)
        ops = [body[off + 3:off + 3 + ln]]
        size = 3 + ln
    else:
        raise DecodeError(f"{path}: body+0x{off:08X}: no decoder for builtin {m}")
    need(body, off, size, path)
    return Instruction(off, opcode, m, ops, size)


def decode_body(body: bytes, path: Path) -> List[Instruction]:
    instructions: List[Instruction] = []
    off = 0
    while off < len(body):
        opcode = u16(body, off, path)
        if opcode < 0x002A:
            inst = decode_builtin(body, off, opcode, path)
        elif 0x002A <= opcode < 0x0040:
            raise DecodeError(f"{path}: body+0x{off:08X} file+0x{opdefs.HEADER_SIZE + off:08X}: reserved opcode 0x{opcode:04X}; possible prior length desync")
        else:
            inst = decode_external(body, off, opcode, path)
        if inst.size <= 0:
            raise DecodeError(f"{path}: body+0x{off:08X}: decoder produced non-positive size")
        instructions.append(inst)
        off += inst.size
    return instructions


def collect_labels(entries: Sequence[int], instructions: Sequence[Instruction], body_size: int, path: Path) -> Set[int]:
    labels: Set[int] = set()
    boundaries = {inst.offset for inst in instructions}
    boundaries.add(body_size)
    for value in entries:
        if value:
            target = value - 1
            if target < 0 or target > body_size:
                raise DecodeError(f"{path}: entry target 0x{target:08X} outside body size 0x{body_size:X}")
            labels.add(target)
    for inst in instructions:
        m = inst.mnemonic
        targets: List[int] = []
        if m in {"JCC_LOCAL_LOCAL_SKIP", "JCC_LOCAL_IMM32_SKIP"}:
            targets = [inst.operands[3]]
        elif m in {"JCC_LOCAL_LOCAL_ELSE", "JCC_LOCAL_IMM32_ELSE"}:
            targets = [inst.operands[3], inst.operands[4]]
        elif m == "LOOP_DEC_JNZ":
            targets = [inst.operands[1]]
        elif m == "JMP":
            targets = [inst.operands[0]]
        for target in targets:
            if target not in boundaries:
                raise DecodeError(f"{path}: body+0x{inst.offset:08X}: target 0x{target:08X} is not an instruction boundary")
            labels.add(target)
    return labels


def render_builtin(inst: Instruction, encoding: str) -> str:
    m = inst.mnemonic
    o = inst.operands
    if not o:
        return m
    if m in {"MOV_LOCAL_LOCAL", "SWAP_LOCAL"}:
        return f"{m} L{o[0]}, L{o[1]}"
    if m == "MOV_LOCAL_IMM32":
        return f"{m} L{o[0]}, {o[1]}"
    if m in {"RAND_LOCAL", "INC_LOCAL", "DEC_LOCAL", "BITNOT_LOCAL", "NEG_LOCAL"}:
        return f"{m} L{o[0]}"
    if m == "JCC_LOCAL_LOCAL_SKIP":
        return f"{m} L{o[0]}, {opdefs.CMP_OPS.get(o[1], 'cmp' + str(o[1]))}, L{o[2]}, {label_for(o[3])}"
    if m == "JCC_LOCAL_IMM32_SKIP":
        return f"{m} L{o[0]}, {opdefs.CMP_OPS.get(o[1], 'cmp' + str(o[1]))}, {o[2]}, {label_for(o[3])}"
    if m == "JCC_LOCAL_LOCAL_ELSE":
        return f"{m} L{o[0]}, {opdefs.CMP_OPS.get(o[1], 'cmp' + str(o[1]))}, L{o[2]}, {label_for(o[3])}, {label_for(o[4])}"
    if m == "JCC_LOCAL_IMM32_ELSE":
        return f"{m} L{o[0]}, {opdefs.CMP_OPS.get(o[1], 'cmp' + str(o[1]))}, {o[2]}, {label_for(o[3])}, {label_for(o[4])}"
    if m == "LOOP_DEC_JNZ":
        return f"{m} L{o[0]}, {label_for(o[1])}"
    if m == "JMP":
        return f"{m} {label_for(o[0])}"
    if 0x0010 <= inst.opcode <= 0x001F:
        if inst.opcode % 2 == 0:
            return f"{m} L{o[0]}, L{o[1]}"
        return f"{m} L{o[0]}, {o[1]}"
    if m == "EVAL_EXPR":
        return f"{m} L{o[0]}, expr_raw({render_bytes(o[1], encoding)})"
    if m == "CALL_ENTRY":
        return f"{m} {o[0]}"
    if m in {"WAIT_FRAMES", "WAIT_TIME_MS"}:
        return f"{m} {o[0]}"
    if m == "LOAD_SDT":
        return f"{m} {render_string_call('str8', o[0], encoding)}"
    raise DecodeError(f"internal: no renderer for {m}")


def render_external(inst: Instruction, encoding: str) -> str:
    rendered: List[str] = []
    for value in inst.operands:
        desc = value.get("desc")
        if value.get("kind") == "typed_i32":
            rendered.append(render_typed_i32(value, encoding))
        elif desc == 1:
            rendered.append(f"u8({value['value']})")
        elif desc == 7:
            rendered.append(f"u8_alt({value['value']})")
        elif desc == 3:
            rendered.append(render_string_call("str8", value["raw"], encoding))
        elif desc == 4:
            rendered.append(render_string_call("str16", value["raw"], encoding))
        elif desc == 5:
            rendered.append(f"out(L{value['local']})")
        elif desc == 6:
            cmp_text = opdefs.CMP_OPS.get(value["cmp"], "cmp" + str(value["cmp"]))
            rendered.append(f"cmp(L{value['local']}, {cmp_text}, {render_typed_i32(value['typed'], encoding)})")
        elif desc == 8:
            rendered.append(f"u16({value['value']})")
        elif desc == 9:
            rendered.append(f"u16_alt({value['value']})")
        else:
            raise DecodeError(f"internal: no external renderer for operand {value}")
    return inst.mnemonic if not rendered else f"{inst.mnemonic} " + ", ".join(rendered)


def parse_sdt(path: Path) -> tuple[List[int], bytes]:
    data = path.read_bytes()
    if len(data) < opdefs.HEADER_SIZE:
        raise DecodeError(f"{path}: file is too small for SDT header ({len(data)} bytes)")
    magic0 = int.from_bytes(data[0:2], "little")
    magic1 = int.from_bytes(data[2:4], "little")
    if magic0 != opdefs.MAGIC0 or magic1 != opdefs.MAGIC1:
        raise DecodeError(f"{path}: bad magic 0x{magic0:04X} 0x{magic1:04X}, expected 0x{opdefs.MAGIC0:04X} 0x{opdefs.MAGIC1:04X}")
    file_size = int.from_bytes(data[4:8], "little")
    if file_size != len(data):
        raise DecodeError(f"{path}: header file_size {file_size} != actual size {len(data)}")
    entries = [int.from_bytes(data[opdefs.ENTRY_TABLE_OFFSET + i * 4:opdefs.ENTRY_TABLE_OFFSET + i * 4 + 4], "little") for i in range(opdefs.ENTRY_COUNT)]
    return entries, data[opdefs.HEADER_SIZE:]


def disassemble_file(input_path: Path, output_path: Path, encoding: str) -> None:
    entries, body = parse_sdt(input_path)
    instructions = decode_body(body, input_path)
    labels = collect_labels(entries, instructions, len(body), input_path)

    lines: List[str] = []
    lines.append("; SDTASM v1")
    lines.append(f".encoding {quote_directive(encoding)}")
    lines.append(f".source {quote_directive(input_path.name)}")
    lines.append(f".file_size {opdefs.HEADER_SIZE + len(body)}")
    lines.append("; omitted .entry slots are 0")
    for i, entry in enumerate(entries):
        if entry:
            lines.append(f".entry {i}, {label_for(entry - 1)}")

    for inst in instructions:
        if inst.offset in labels:
            lines.append("")
            lines.append(f"{label_for(inst.offset)}:")
        rendered = render_external(inst, encoding) if inst.external else render_builtin(inst, encoding)
        lines.append(f"    {rendered}")
    if len(body) in labels:
        lines.append("")
        lines.append(f"{label_for(len(body))}:")

    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def output_for(input_path: Path, output_arg: str | None, multiple: bool) -> Path:
    if output_arg is None:
        return input_path.with_name(input_path.stem + ".asm.txt")
    out = Path(output_arg)
    if multiple:
        if not out.exists() or not out.is_dir():
            raise DecodeError("-o must be an existing directory when disassembling multiple input files")
        return out / (input_path.stem + ".asm.txt")
    return out


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Disassemble SDT script bytecode to semantic asm text.")
    parser.add_argument("inputs", nargs="+", help="input .SDT file(s)")
    parser.add_argument("-o", "--output", help="output asm file, or existing directory for multiple inputs")
    parser.add_argument("--encoding", default=opdefs.DEFAULT_ENCODING, help="text encoding for structured strings (default: cp932)")
    args = parser.parse_args(argv)

    failed = 0
    multiple = len(args.inputs) > 1
    for item in args.inputs:
        input_path = Path(item)
        try:
            out = output_for(input_path, args.output, multiple)
            disassemble_file(input_path, out, args.encoding)
            print(f"{input_path} -> {out}")
        except Exception as exc:
            failed += 1
            print(f"error: {exc}", file=sys.stderr)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
