from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from opcode import (
    ALU_SUBOPS,
    BASE_OPCODE_SPECS,
    CMP_SUBOPS,
    ENCODING,
    JUMP_SUBOPS,
    MAGIC,
    STATEMENT_OPCODE_SPECS,
    ValueRefSpec,
    get_any_opcode_spec,
    get_value_ref_spec,
    is_invalid_opcode,
    opcode_mnemonic,
)


class DecodeError(Exception):
    pass


class BinaryReader:
    def __init__(self, data: bytes, offset: int = 0) -> None:
        self.data = data
        self.pos = offset

    def eof(self) -> bool:
        return self.pos >= len(self.data)

    def tell(self) -> int:
        return self.pos

    def seek(self, pos: int) -> None:
        if not 0 <= pos <= len(self.data):
            raise DecodeError(f"Seek out of range: 0x{pos:X}")
        self.pos = pos

    def peek_u8(self) -> int:
        if self.pos >= len(self.data):
            raise DecodeError("Unexpected EOF while peeking u8")
        return self.data[self.pos]

    def read_u8(self) -> int:
        value = self.peek_u8()
        self.pos += 1
        return value

    def read_u16(self) -> int:
        if self.pos + 2 > len(self.data):
            raise DecodeError("Unexpected EOF while reading u16")
        value = self.data[self.pos] | (self.data[self.pos + 1] << 8)
        self.pos += 2
        return value

    def read_u32(self) -> int:
        if self.pos + 4 > len(self.data):
            raise DecodeError("Unexpected EOF while reading u32")
        value = (
            self.data[self.pos]
            | (self.data[self.pos + 1] << 8)
            | (self.data[self.pos + 2] << 16)
            | (self.data[self.pos + 3] << 24)
        )
        self.pos += 4
        return value

    def read_c_string_bytes(self) -> bytes:
        end = self.data.find(b"\x00", self.pos)
        if end < 0:
            raise DecodeError("Unterminated string")
        value = self.data[self.pos:end]
        self.pos = end + 1
        return value


@dataclass
class HeaderLabel:
    name: str
    target_code_offset: int
    file_offset: int


@dataclass
class ValueRef:
    subopcode: int
    spec: ValueRefSpec
    value: object


@dataclass
class Instruction:
    code_offset: int
    file_offset: int
    opcode: int
    mnemonic: str
    operands: List[object]
    confidence: str
    size: int
    jump_target: Optional[int] = None


@dataclass
class ScdDocument:
    source_path: Path
    data: bytes
    code_offset: int
    header_labels: List[HeaderLabel]
    instructions: List[Instruction]


def decode_cp932(data: bytes) -> str:
    return data.decode(ENCODING)


def quote_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


class Disassembler:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.data = path.read_bytes()
        self.reader = BinaryReader(self.data)

    def parse(self) -> ScdDocument:
        if len(self.data) < 8:
            raise DecodeError("File too small for SCD header")
        if self.data[:4] != MAGIC:
            raise DecodeError(f"Unsupported container or magic: {self.data[:4]!r}")
        self.reader.seek(4)
        code_offset = self.reader.read_u32()
        if code_offset < 8 or code_offset > len(self.data):
            raise DecodeError(f"Invalid code offset: 0x{code_offset:X}")
        header_labels = self._parse_header_labels(code_offset)
        instructions = self._parse_code(code_offset)
        return ScdDocument(self.path, self.data, code_offset, header_labels, instructions)

    def _parse_header_labels(self, code_offset: int) -> List[HeaderLabel]:
        labels: List[HeaderLabel] = []
        self.reader.seek(8)
        while self.reader.tell() < code_offset:
            entry_offset = self.reader.tell()
            target = self.reader.read_u32()
            name = decode_cp932(self.reader.read_c_string_bytes())
            labels.append(HeaderLabel(name=name, target_code_offset=target, file_offset=entry_offset))
        if self.reader.tell() != code_offset:
            raise DecodeError(
                f"Header labels ended at 0x{self.reader.tell():X}, expected code offset 0x{code_offset:X}"
            )
        return labels

    def _parse_code(self, code_offset: int) -> List[Instruction]:
        instructions: List[Instruction] = []
        self.reader.seek(code_offset)
        while not self.reader.eof():
            file_offset = self.reader.tell()
            relative_offset = file_offset - code_offset
            opcode = self.reader.read_u8()
            if opcode in BASE_OPCODE_SPECS:
                instruction = self._decode_base_opcode(relative_offset, file_offset, opcode)
            elif opcode in STATEMENT_OPCODE_SPECS:
                spec = STATEMENT_OPCODE_SPECS[opcode]
                instruction = Instruction(
                    code_offset=relative_offset,
                    file_offset=file_offset,
                    opcode=opcode,
                    mnemonic=spec.mnemonic,
                    operands=[],
                    confidence=spec.confidence,
                    size=1,
                )
            elif is_invalid_opcode(opcode):
                raise DecodeError(f"Invalid opcode 0x{opcode:02X} at code offset 0x{relative_offset:08X}")
            else:
                raise DecodeError(f"Unknown opcode 0x{opcode:02X} at code offset 0x{relative_offset:08X}")
            instructions.append(instruction)
        return instructions

    def _decode_base_opcode(self, code_offset: int, file_offset: int, opcode: int) -> Instruction:
        spec = BASE_OPCODE_SPECS[opcode]
        if opcode == 0x00:
            strings: List[str] = []
            while True:
                strings.append(decode_cp932(self.reader.read_c_string_bytes()))
                if self.reader.eof():
                    break
                if self.reader.peek_u8() != 0:
                    break
                self.reader.read_u8()
            size = self.reader.tell() - file_offset
            return Instruction(code_offset, file_offset, opcode, spec.mnemonic, strings, spec.confidence, size)
        if opcode in (0x01, 0x02):
            value_ref = self._decode_value_ref()
            size = self.reader.tell() - file_offset
            return Instruction(code_offset, file_offset, opcode, spec.mnemonic, [value_ref], spec.confidence, size)
        if opcode == 0x03:
            return Instruction(code_offset, file_offset, opcode, spec.mnemonic, [], spec.confidence, 1)
        if opcode == 0x04:
            subopcode = self.reader.read_u8()
            if subopcode not in JUMP_SUBOPS:
                raise DecodeError(f"Unknown jump subopcode 0x{subopcode:02X} at code offset 0x{code_offset:08X}")
            target = self.reader.read_u32()
            size = self.reader.tell() - file_offset
            return Instruction(
                code_offset=code_offset,
                file_offset=file_offset,
                opcode=opcode,
                mnemonic=JUMP_SUBOPS[subopcode],
                operands=[target],
                confidence=spec.confidence,
                size=size,
                jump_target=target,
            )
        if opcode == 0x05:
            subopcode = self.reader.read_u8()
            if subopcode not in CMP_SUBOPS:
                raise DecodeError(f"Unknown cmp subopcode 0x{subopcode:02X} at code offset 0x{code_offset:08X}")
            return Instruction(code_offset, file_offset, opcode, CMP_SUBOPS[subopcode], [], spec.confidence, 2)
        if opcode == 0x06:
            subopcode = self.reader.read_u8()
            if subopcode not in ALU_SUBOPS:
                raise DecodeError(f"Unknown alu subopcode 0x{subopcode:02X} at code offset 0x{code_offset:08X}")
            return Instruction(code_offset, file_offset, opcode, ALU_SUBOPS[subopcode], [], spec.confidence, 2)
        raise DecodeError(f"Unhandled base opcode 0x{opcode:02X}")

    def _decode_value_ref(self) -> ValueRef:
        subopcode = self.reader.read_u8()
        spec = get_value_ref_spec(subopcode)
        if spec is None:
            here = self.reader.tell() - 1
            raise DecodeError(f"Unknown value-ref subopcode 0x{subopcode:02X} at file offset 0x{here:08X}")
        if spec.operand_kind == "u8":
            value: object = self.reader.read_u8()
        elif spec.operand_kind == "u16":
            value = self.reader.read_u16()
        elif spec.operand_kind == "strz":
            value = decode_cp932(self.reader.read_c_string_bytes())
        else:
            raise DecodeError(f"Unsupported operand kind: {spec.operand_kind}")
        return ValueRef(subopcode=subopcode, spec=spec, value=value)


def render_value_ref(value_ref: ValueRef) -> str:
    if value_ref.spec.operand_kind == "strz":
        return f"{value_ref.spec.mnemonic} {quote_string(value_ref.value)}"
    return f"{value_ref.spec.mnemonic} 0x{int(value_ref.value):X}"


def label_name_for_offset(code_offset: int) -> str:
    return f"loc_{code_offset:08X}"


def render_instruction(instruction: Instruction, label_map: Dict[int, str]) -> str:
    suffix = ""
    if instruction.confidence == "low":
        suffix = " ; confidence=low"
    elif instruction.confidence == "med":
        suffix = " ; confidence=med"

    if instruction.opcode in (0x01, 0x02):
        return f"    {instruction.mnemonic} {render_value_ref(instruction.operands[0])}{suffix}"
    if instruction.opcode == 0x00:
        text = "\n".join(instruction.operands)
        return f"    {instruction.mnemonic} {quote_string(text)}{suffix}"
    if instruction.opcode == 0x04:
        target = instruction.jump_target
        if target is None:
            raise DecodeError("Jump instruction missing target")
        return f"    {instruction.mnemonic} {label_map[target]}{suffix}"
    return f"    {instruction.mnemonic}{suffix}"


def build_label_map(document: ScdDocument) -> Dict[int, str]:
    offsets = {label.target_code_offset for label in document.header_labels}
    offsets.update(
        instruction.jump_target
        for instruction in document.instructions
        if instruction.jump_target is not None
    )
    offsets = {offset for offset in offsets if offset is not None}
    for offset in offsets:
        if offset < 0 or offset > len(document.data) - document.code_offset:
            raise DecodeError(f"Label target out of code range: 0x{offset:08X}")
    instruction_offsets = {instruction.code_offset for instruction in document.instructions}
    for offset in offsets:
        if offset not in instruction_offsets:
            raise DecodeError(f"Label target not aligned to instruction boundary: 0x{offset:08X}")

    label_map: Dict[int, str] = {}
    used_names: Dict[str, int] = {}
    for header_label in document.header_labels:
        existing_offset = used_names.get(header_label.name)
        if existing_offset is not None and existing_offset != header_label.target_code_offset:
            raise DecodeError(
                f"Duplicate header label name {header_label.name!r} for different offsets: "
                f"0x{existing_offset:08X} vs 0x{header_label.target_code_offset:08X}"
            )
        label_map[header_label.target_code_offset] = header_label.name
        used_names[header_label.name] = header_label.target_code_offset

    for offset in sorted(offsets):
        if offset not in label_map:
            name = label_name_for_offset(offset)
            label_map[offset] = name
            used_names[name] = offset
    return label_map


def emit_asm(document: ScdDocument) -> str:
    label_map = build_label_map(document)
    lines: List[str] = []
    lines.append(".file kind=raw_scd")
    lines.append(f".magic {quote_string(document.data[:4].decode('ascii'))}")
    lines.append("")
    for header_label in document.header_labels:
        lines.append(
            f".header_label {quote_string(header_label.name)}, {label_map[header_label.target_code_offset]}"
        )
    lines.append("")
    lines.append(".code")
    for instruction in document.instructions:
        if instruction.code_offset in label_map:
            lines.append("")
            lines.append(f"{label_map[instruction.code_offset]}:")
        lines.append(render_instruction(instruction, label_map))
    lines.append("")
    return "\n".join(lines)


def default_output_path(input_path: Path) -> Path:
    script_dir = Path(__file__).resolve().parent
    return script_dir / f"{input_path.stem}.asm.txt"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Disassemble SCD bytecode into semantic asm.txt")
    parser.add_argument("input", help="Input .scd file")
    parser.add_argument("-o", "--output", help="Output asm path")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    input_path = Path(args.input)
    output_path = Path(args.output) if args.output else default_output_path(input_path)
    document = Disassembler(input_path).parse()
    output_path.write_text(emit_asm(document), encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
