from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from opcode import (
    ALU_MNEMONIC_TO_SUBOP,
    CMP_MNEMONIC_TO_SUBOP,
    ENCODING,
    INLINE_MNEMONICS,
    JUMP_MNEMONIC_TO_SUBOP,
    MAGIC,
    STATEMENT_MNEMONIC_TO_OPCODE,
    ValueRefSpec,
    get_value_ref_subopcode_by_mnemonic,
)


class AssembleError(Exception):
    pass


@dataclass
class HeaderLabelDecl:
    name: str
    label_name: str


@dataclass
class CodeInstruction:
    source_line: int
    mnemonic: str
    operands: object


@dataclass
class Program:
    magic: bytes
    header_labels: List[HeaderLabelDecl]
    instructions: List[CodeInstruction]
    code_labels: Dict[str, int]


JUMP_MNEMONICS = set(JUMP_MNEMONIC_TO_SUBOP.keys())
CMP_MNEMONICS = set(CMP_MNEMONIC_TO_SUBOP.keys())
ALU_MNEMONICS = set(ALU_MNEMONIC_TO_SUBOP.keys())


class AsmParser:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.lines = path.read_text(encoding="utf-8").splitlines()

    def parse(self) -> Program:
        magic: Optional[bytes] = None
        header_labels: List[HeaderLabelDecl] = []
        instructions: List[CodeInstruction] = []
        code_labels: Dict[str, int] = {}
        current_index = 0
        in_code = False

        for line_no, raw_line in enumerate(self.lines, 1):
            line = self._strip_comment(raw_line).strip()
            if not line:
                continue
            if line.startswith(".file"):
                continue
            if line.startswith(".magic"):
                payload = line[len(".magic") :].strip()
                magic_text = json.loads(payload)
                magic = magic_text.encode("ascii")
                continue
            if line.startswith(".header_label"):
                payload = line[len(".header_label") :].strip()
                name_text, label_name = self._split_header_label(payload, line_no)
                header_labels.append(HeaderLabelDecl(name=name_text, label_name=label_name))
                continue
            if line == ".code":
                in_code = True
                continue
            if not in_code:
                raise AssembleError(f"Unsupported directive before .code at line {line_no}: {line}")
            if line.endswith(":"):
                label_name = line[:-1].strip()
                if not label_name:
                    raise AssembleError(f"Empty label at line {line_no}")
                if label_name in code_labels:
                    raise AssembleError(f"Duplicate label {label_name} at line {line_no}")
                code_labels[label_name] = current_index
                continue
            mnemonic, operands = self._parse_instruction(line, line_no)
            instructions.append(CodeInstruction(line_no, mnemonic, operands))
            current_index += 1

        if magic is None:
            raise AssembleError("Missing .magic directive")
        if magic != MAGIC:
            raise AssembleError(f"Unsupported magic {magic!r}")
        return Program(magic, header_labels, instructions, code_labels)

    def _strip_comment(self, line: str) -> str:
        in_string = False
        escaped = False
        for idx, ch in enumerate(line):
            if in_string:
                if escaped:
                    escaped = False
                elif ch == "\\":
                    escaped = True
                elif ch == '"':
                    in_string = False
                continue
            if ch == '"':
                in_string = True
            elif ch == ';':
                return line[:idx]
        return line

    def _split_header_label(self, payload: str, line_no: int) -> Tuple[str, str]:
        parts = self._split_args(payload)
        if len(parts) != 2:
            raise AssembleError(f"Invalid .header_label at line {line_no}: {payload}")
        try:
            name_text = json.loads(parts[0])
        except json.JSONDecodeError as exc:
            raise AssembleError(f"Invalid header label string at line {line_no}: {exc}") from exc
        label_name = parts[1].strip()
        if not label_name:
            raise AssembleError(f"Missing label reference at line {line_no}")
        return name_text, label_name

    def _split_args(self, text: str) -> List[str]:
        parts: List[str] = []
        current: List[str] = []
        in_string = False
        escaped = False
        for ch in text:
            if in_string:
                current.append(ch)
                if escaped:
                    escaped = False
                elif ch == "\\":
                    escaped = True
                elif ch == '"':
                    in_string = False
                continue
            if ch == '"':
                in_string = True
                current.append(ch)
            elif ch == ',':
                parts.append("".join(current).strip())
                current = []
            else:
                current.append(ch)
        tail = "".join(current).strip()
        if tail:
            parts.append(tail)
        return parts

    def _parse_instruction(self, line: str, line_no: int) -> Tuple[str, object]:
        pieces = line.split(None, 1)
        mnemonic = pieces[0].upper()
        operand_text = pieces[1].strip() if len(pieces) > 1 else ""

        if mnemonic == "TEXT":
            args = self._split_args(operand_text)
            if not args:
                raise AssembleError(f"TEXT requires at least one string at line {line_no}")
            try:
                values = [json.loads(arg) for arg in args]
            except json.JSONDecodeError as exc:
                raise AssembleError(f"Invalid TEXT string at line {line_no}: {exc}") from exc
            if len(values) == 1:
                return mnemonic, values[0].split("\n")
            return mnemonic, values

        if mnemonic in {"STORE", "PUSH_REF"}:
            parts = operand_text.split(None, 1)
            if len(parts) != 2:
                raise AssembleError(f"{mnemonic} requires value-ref operands at line {line_no}")
            ref_mnemonic = parts[0].upper()
            rest = parts[1].strip()
            if ref_mnemonic == "STRING":
                try:
                    value = json.loads(rest)
                except json.JSONDecodeError as exc:
                    raise AssembleError(f"Invalid string operand at line {line_no}: {exc}") from exc
            else:
                value = self._parse_int(rest, line_no)
            return mnemonic, (ref_mnemonic, value)

        if mnemonic in JUMP_MNEMONICS:
            if not operand_text:
                raise AssembleError(f"{mnemonic} requires a target label at line {line_no}")
            return mnemonic, operand_text

        if mnemonic in CMP_MNEMONICS or mnemonic in ALU_MNEMONICS or mnemonic in INLINE_MNEMONICS:
            if operand_text:
                raise AssembleError(f"Unexpected operands for {mnemonic} at line {line_no}")
            return mnemonic, None

        if mnemonic in STATEMENT_MNEMONIC_TO_OPCODE:
            if operand_text:
                raise AssembleError(f"Unexpected operands for {mnemonic} at line {line_no}")
            return mnemonic, None

        raise AssembleError(f"Unknown mnemonic at line {line_no}: {mnemonic}")

    def _parse_int(self, text: str, line_no: int) -> int:
        try:
            return int(text, 0)
        except ValueError as exc:
            raise AssembleError(f"Invalid integer at line {line_no}: {text}") from exc


class Assembler:
    def __init__(self, program: Program) -> None:
        self.program = program

    def assemble(self) -> bytes:
        label_offsets = self._layout_code()
        code_bytes = bytearray()
        for instruction in self.program.instructions:
            code_bytes.extend(self._encode_instruction(instruction, label_offsets))

        code_offset = 8 + sum(4 + len(label.name.encode(ENCODING)) + 1 for label in self.program.header_labels)
        header = bytearray()
        header.extend(self.program.magic)
        header.extend(code_offset.to_bytes(4, "little"))
        for header_label in self.program.header_labels:
            if header_label.label_name not in label_offsets:
                raise AssembleError(f"Header label target not defined: {header_label.label_name}")
            header.extend(label_offsets[header_label.label_name].to_bytes(4, "little"))
            header.extend(header_label.name.encode(ENCODING))
            header.append(0)
        return bytes(header + code_bytes)

    def _layout_code(self) -> Dict[str, int]:
        index_offsets: List[int] = []
        current = 0
        for instruction in self.program.instructions:
            index_offsets.append(current)
            current += self._instruction_size(instruction)

        label_offsets: Dict[str, int] = {}
        for label_name, instruction_index in self.program.code_labels.items():
            if instruction_index == len(self.program.instructions):
                label_offsets[label_name] = current
            else:
                label_offsets[label_name] = index_offsets[instruction_index]
        return label_offsets

    def _instruction_size(self, instruction: CodeInstruction) -> int:
        mnemonic = instruction.mnemonic
        if mnemonic == "TEXT":
            strings: List[str] = instruction.operands
            size = 1
            for idx, text in enumerate(strings):
                size += len(text.encode(ENCODING)) + 1
                if idx + 1 < len(strings):
                    size += 1
            return size
        if mnemonic in {"STORE", "PUSH_REF"}:
            return 1 + self._value_ref_size(instruction.operands)
        if mnemonic == "STACK_MARK":
            return 1
        if mnemonic in JUMP_MNEMONICS:
            return 6
        if mnemonic in CMP_MNEMONICS or mnemonic in ALU_MNEMONICS:
            return 2
        if mnemonic in STATEMENT_MNEMONIC_TO_OPCODE:
            return 1
        raise AssembleError(f"Cannot size instruction: {mnemonic}")

    def _value_ref_size(self, operand: Tuple[str, object]) -> int:
        ref_mnemonic, value = operand
        subopcode = get_value_ref_subopcode_by_mnemonic(ref_mnemonic)
        if subopcode is None:
            raise AssembleError(f"Unknown value-ref mnemonic: {ref_mnemonic}")
        if ref_mnemonic == "IMM8":
            return 2
        if ref_mnemonic in {"IMM16", "VAR", "INDIRECT_VAR", "IMM16_B", "INT_VAR", "IMM16_C"}:
            return 3
        if ref_mnemonic == "STRING":
            return 2 + len(str(value).encode(ENCODING))
        raise AssembleError(f"Unhandled value-ref size for: {ref_mnemonic}")

    def _encode_instruction(self, instruction: CodeInstruction, label_offsets: Dict[str, int]) -> bytes:
        mnemonic = instruction.mnemonic
        out = bytearray()

        if mnemonic == "TEXT":
            out.append(0x00)
            strings: List[str] = instruction.operands
            for idx, text in enumerate(strings):
                out.extend(text.encode(ENCODING))
                out.append(0)
                if idx + 1 < len(strings):
                    out.append(0)
            return bytes(out)

        if mnemonic == "STORE":
            out.append(0x01)
            out.extend(self._encode_value_ref(instruction.operands))
            return bytes(out)

        if mnemonic == "PUSH_REF":
            out.append(0x02)
            out.extend(self._encode_value_ref(instruction.operands))
            return bytes(out)

        if mnemonic == "STACK_MARK":
            return b"\x03"

        if mnemonic in JUMP_MNEMONICS:
            if instruction.operands not in label_offsets:
                raise AssembleError(f"Undefined jump target: {instruction.operands}")
            out.append(0x04)
            out.append(JUMP_MNEMONIC_TO_SUBOP[mnemonic])
            out.extend(label_offsets[instruction.operands].to_bytes(4, "little"))
            return bytes(out)

        if mnemonic in CMP_MNEMONICS:
            return bytes((0x05, CMP_MNEMONIC_TO_SUBOP[mnemonic]))

        if mnemonic in ALU_MNEMONICS:
            return bytes((0x06, ALU_MNEMONIC_TO_SUBOP[mnemonic]))

        opcode = STATEMENT_MNEMONIC_TO_OPCODE.get(mnemonic)
        if opcode is not None:
            return bytes((opcode,))

        raise AssembleError(f"Unhandled instruction mnemonic: {mnemonic}")

    def _encode_value_ref(self, operand: Tuple[str, object]) -> bytes:
        ref_mnemonic, value = operand
        subopcode = get_value_ref_subopcode_by_mnemonic(ref_mnemonic)
        if subopcode is None:
            raise AssembleError(f"Unknown value-ref mnemonic: {ref_mnemonic}")
        out = bytearray((subopcode,))
        if ref_mnemonic == "IMM8":
            int_value = int(value)
            if not 0 <= int_value <= 0xFF:
                raise AssembleError(f"IMM8 out of range: {int_value}")
            out.append(int_value)
            return bytes(out)
        if ref_mnemonic in {"IMM16", "VAR", "INDIRECT_VAR", "IMM16_B", "INT_VAR", "IMM16_C"}:
            int_value = int(value)
            if not 0 <= int_value <= 0xFFFF:
                raise AssembleError(f"U16 operand out of range: {int_value}")
            out.extend(int_value.to_bytes(2, "little"))
            return bytes(out)
        if ref_mnemonic == "STRING":
            out.extend(str(value).encode(ENCODING))
            out.append(0)
            return bytes(out)
        raise AssembleError(f"Unhandled value-ref mnemonic: {ref_mnemonic}")


def default_output_path(input_path: Path) -> Path:
    name = input_path.name
    if name.endswith('.asm.txt'):
        base = name[:-8]
    else:
        base = input_path.stem
    script_dir = Path(__file__).resolve().parent
    return script_dir / f"{base}.rebuild.scd"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Reassemble semantic SCD asm.txt into binary")
    parser.add_argument("input", help="Input asm.txt path")
    parser.add_argument("-o", "--output", help="Output .scd path")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    input_path = Path(args.input)
    output_path = Path(args.output) if args.output else default_output_path(input_path)
    program = AsmParser(input_path).parse()
    output_path.write_bytes(Assembler(program).assemble())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
