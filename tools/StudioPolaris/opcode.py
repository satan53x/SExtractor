from __future__ import annotations

import importlib.util
import sysconfig
from pathlib import Path
from typing import Dict, Iterable, Optional

# Re-export the stdlib opcode module API so local opcode.py does not break
# imports performed by the Python standard library (e.g. inspect -> dis -> opcode).
_STDLIB_OPCODE_PATH = Path(sysconfig.get_paths()["stdlib"]) / "opcode.py"
_STDLIB_OPCODE_SPEC = importlib.util.spec_from_file_location("_stdlib_opcode", _STDLIB_OPCODE_PATH)
if _STDLIB_OPCODE_SPEC is None or _STDLIB_OPCODE_SPEC.loader is None:
    raise RuntimeError(f"Unable to load stdlib opcode module from {_STDLIB_OPCODE_PATH}")
_STDLIB_OPCODE = importlib.util.module_from_spec(_STDLIB_OPCODE_SPEC)
_STDLIB_OPCODE_SPEC.loader.exec_module(_STDLIB_OPCODE)
for _name in dir(_STDLIB_OPCODE):
    if _name in {"__builtins__", "__cached__", "__doc__", "__file__", "__loader__", "__name__", "__package__", "__spec__"}:
        continue
    globals()[_name] = getattr(_STDLIB_OPCODE, _name)

ENCODING = "cp932"
MAGIC = b"SCD_"


class ValueRefSpec:
    __slots__ = ("subopcode", "name", "operand_kind", "length_kind", "result_type", "mnemonic")

    def __init__(self, subopcode: int, name: str, operand_kind: str, length_kind: str, result_type: str, mnemonic: str) -> None:
        self.subopcode = subopcode
        self.name = name
        self.operand_kind = operand_kind
        self.length_kind = length_kind
        self.result_type = result_type
        self.mnemonic = mnemonic


class OpcodeSpec:
    __slots__ = ("opcode", "mnemonic", "category", "confidence", "has_inline_operands", "fixed_size", "description")

    def __init__(
        self,
        opcode: int,
        mnemonic: str,
        category: str,
        confidence: str,
        has_inline_operands: bool = False,
        fixed_size: Optional[int] = None,
        description: str = "",
    ) -> None:
        self.opcode = opcode
        self.mnemonic = mnemonic
        self.category = category
        self.confidence = confidence
        self.has_inline_operands = has_inline_operands
        self.fixed_size = fixed_size
        self.description = description


VALUE_REF_SPECS: Dict[int, ValueRefSpec] = {
    0x01: ValueRefSpec(0x01, "imm8", "u8", "fixed", "int", "IMM8"),
    0x02: ValueRefSpec(0x02, "imm16", "u16", "fixed", "int", "IMM16"),
    0x03: ValueRefSpec(0x03, "var", "u16", "fixed", "raw", "VAR"),
    0x04: ValueRefSpec(0x04, "indirect_var", "u16", "fixed", "raw", "INDIRECT_VAR"),
    0x05: ValueRefSpec(0x05, "imm16_b", "u16", "fixed", "int", "IMM16_B"),
    0x06: ValueRefSpec(0x06, "int_var", "u16", "fixed", "int", "INT_VAR"),
    0x07: ValueRefSpec(0x07, "imm16_c", "u16", "fixed", "int", "IMM16_C"),
    0x08: ValueRefSpec(0x08, "string", "strz", "variable", "string", "STRING"),
}

VALUE_REF_MNEMONIC_TO_SUBOP = {spec.mnemonic: subop for subop, spec in VALUE_REF_SPECS.items()}

JUMP_SUBOPS = {
    0x00: "JMP",
    0x01: "JNZ",
    0x02: "JNZ_PUSH1",
    0x03: "JZ",
    0x04: "JZ_PUSH1",
}
JUMP_MNEMONIC_TO_SUBOP = {name: subop for subop, name in JUMP_SUBOPS.items()}

CMP_SUBOPS = {
    0x00: "CMP_EQ",
    0x01: "CMP_NE",
    0x02: "CMP_LT",
    0x03: "CMP_LE",
    0x04: "CMP_GT",
    0x05: "CMP_GE",
}
CMP_MNEMONIC_TO_SUBOP = {name: subop for subop, name in CMP_SUBOPS.items()}

ALU_SUBOPS = {
    0x00: "ADD",
    0x01: "SUB",
    0x02: "MUL",
    0x03: "DIV",
    0x04: "MOD",
    0x05: "AND",
    0x06: "OR",
    0x07: "NEG",
}
ALU_MNEMONIC_TO_SUBOP = {name: subop for subop, name in ALU_SUBOPS.items()}

BASE_OPCODE_SPECS: Dict[int, OpcodeSpec] = {
    0x00: OpcodeSpec(0x00, "TEXT", "inline", "high", True, None, "Variable-length text block"),
    0x01: OpcodeSpec(0x01, "STORE", "inline", "high", True, None, "Store stack value into variable ref"),
    0x02: OpcodeSpec(0x02, "PUSH_REF", "inline", "high", True, None, "Push typed value ref"),
    0x03: OpcodeSpec(0x03, "STACK_MARK", "inline", "low", False, 1, "Pop raw cell to temp mark"),
    0x04: OpcodeSpec(0x04, "JMP_FAMILY", "inline", "high", True, None, "Jump family with subopcode"),
    0x05: OpcodeSpec(0x05, "CMP_FAMILY", "inline", "high", True, 2, "Comparison family with subopcode"),
    0x06: OpcodeSpec(0x06, "ALU_FAMILY", "inline", "high", True, 2, "ALU family with subopcode"),
}

STATEMENT_OPCODE_SPECS: Dict[int, OpcodeSpec] = {
    0x14: OpcodeSpec(0x14, "FLAG_OP", "statement", "high", False, 1),
    0x15: OpcodeSpec(0x15, "FLAG_TEST_N", "statement", "high", False, 1),
    0x16: OpcodeSpec(0x16, "SELECT_RAW", "statement", "high", False, 1),
    0x17: OpcodeSpec(0x17, "IS_NONZERO", "statement", "med", False, 1),
    0x18: OpcodeSpec(0x18, "WAIT0", "statement", "med", False, 1),
    0x19: OpcodeSpec(0x19, "WAIT_CH", "statement", "high", False, 1),
    0x1A: OpcodeSpec(0x1A, "SET_LABEL_STR", "statement", "high", False, 1),
    0x1B: OpcodeSpec(0x1B, "SELECT_LABEL_STR", "statement", "high", False, 1),
    0x1C: OpcodeSpec(0x1C, "LOAD_SCRIPT", "statement", "high", False, 1),
    0x1D: OpcodeSpec(0x1D, "CALL_BASE_WITH_LOCALS", "statement", "med", False, 1),
    0x1E: OpcodeSpec(0x1E, "CALL_SCRIPT", "statement", "high", False, 1),
    0x1F: OpcodeSpec(0x1F, "RETURN_TO_BASE_WITH_LOCALS", "statement", "med", False, 1),
    0x20: OpcodeSpec(0x20, "COND_SELECT_STR", "statement", "med", False, 1),
    0x21: OpcodeSpec(0x21, "COND_SELECT_STR2", "statement", "med", False, 1),
    0x22: OpcodeSpec(0x22, "RETURN_FRAME", "statement", "high", False, 1),
    0x23: OpcodeSpec(0x23, "SYS_QUERY_STR", "statement", "med", False, 1),
    0x24: OpcodeSpec(0x24, "WAIT_POLL", "statement", "med", False, 1),
    0x25: OpcodeSpec(0x25, "SET_OPTION", "statement", "med", False, 1),
    0x26: OpcodeSpec(0x26, "GET_OPTION", "statement", "high", False, 1),
    0x28: OpcodeSpec(0x28, "BGM_CTRL", "statement", "med", False, 1),
    0x29: OpcodeSpec(0x29, "TEXT_SLOT_CFG", "statement", "med", False, 1),
    0x2A: OpcodeSpec(0x2A, "PLAY_VIC", "statement", "med", False, 1),
    0x2B: OpcodeSpec(0x2B, "PLAY_VIC_WAV", "statement", "med", False, 1),
    0x2C: OpcodeSpec(0x2C, "PLAY_MOVIE", "statement", "high", False, 1),
    0x2D: OpcodeSpec(0x2D, "STORE_AUDIO_STATE", "statement", "med", False, 1),
    0x31: OpcodeSpec(0x31, "GET_DATETIME", "statement", "high", False, 1),
    0x32: OpcodeSpec(0x32, "SUBSYS_TOGGLE", "statement", "med", False, 1),
    0x33: OpcodeSpec(0x33, "CALL_40C410", "statement", "low", False, 1),
    0x34: OpcodeSpec(0x34, "CALL_40C470", "statement", "low", False, 1),
    0x35: OpcodeSpec(0x35, "GET_2VALS", "statement", "med", False, 1),
    0x36: OpcodeSpec(0x36, "SET_MODE_SIMPLE", "statement", "med", False, 1),
    0x37: OpcodeSpec(0x37, "SET_PACKED24", "statement", "high", False, 1),
    0x38: OpcodeSpec(0x38, "CREATE_OBJ_A", "statement", "med", False, 1),
    0x39: OpcodeSpec(0x39, "CREATE_OBJ_B", "statement", "med", False, 1),
    0x3A: OpcodeSpec(0x3A, "CREATE_OBJ_C", "statement", "med", False, 1),
    0x3B: OpcodeSpec(0x3B, "OBJ_ACTIVATE", "statement", "med", False, 1),
    0x3C: OpcodeSpec(0x3C, "OBJ_DESTROY", "statement", "high", False, 1),
    0x3D: OpcodeSpec(0x3D, "OBJ_DEACTIVATE", "statement", "med", False, 1),
    0x3E: OpcodeSpec(0x3E, "OBJ_SET_FLAG", "statement", "med", False, 1),
    0x3F: OpcodeSpec(0x3F, "OBJ_SET_RESOURCE", "statement", "med", False, 1),
    0x40: OpcodeSpec(0x40, "LOAD_HEX_WORDS", "statement", "med", False, 1),
    0x41: OpcodeSpec(0x41, "REGISTER_STRING", "statement", "high", False, 1),
    0x42: OpcodeSpec(0x42, "DRAW_GRID", "statement", "med", False, 1),
    0x43: OpcodeSpec(0x43, "MENU_DEFINE", "statement", "high", False, 1),
    0x44: OpcodeSpec(0x44, "CALL_40D0A0", "statement", "low", False, 1),
    0x45: OpcodeSpec(0x45, "CHOICE_DEFINE", "statement", "med", False, 1),
    0x46: OpcodeSpec(0x46, "OBJ_TRIPLE_OP", "statement", "low", False, 1),
    0x47: OpcodeSpec(0x47, "CHOICE_EXEC", "statement", "med", False, 1),
    0x48: OpcodeSpec(0x48, "CHOICE_PAGE", "statement", "med", False, 1),
    0x49: OpcodeSpec(0x49, "SAVE_SLOT", "statement", "high", False, 1),
    0x4A: OpcodeSpec(0x4A, "LOAD_SLOT", "statement", "high", False, 1),
    0x4B: OpcodeSpec(0x4B, "SAVE_NAMED_STATE", "statement", "med", False, 1),
    0x4C: OpcodeSpec(0x4C, "SET_CHECKPOINT", "statement", "med", False, 1),
    0x4D: OpcodeSpec(0x4D, "EXIT_OR_DIALOG", "statement", "med", False, 1),
    0x4E: OpcodeSpec(0x4E, "CLEAR_FLAG_BANKS", "statement", "high", False, 1),
    0x4F: OpcodeSpec(0x4F, "CALL_BY_ID", "statement", "low", False, 1),
    0x50: OpcodeSpec(0x50, "TRANSITION", "statement", "high", False, 1),
    0x51: OpcodeSpec(0x51, "SURF_CREATE", "statement", "high", False, 1),
    0x52: OpcodeSpec(0x52, "SURF_LOAD_GR2", "statement", "high", False, 1),
    0x53: OpcodeSpec(0x53, "SURF_LOAD_GR2_FRAME", "statement", "high", False, 1),
    0x54: OpcodeSpec(0x54, "SURF_SAVE_BMP", "statement", "high", False, 1),
    0x55: OpcodeSpec(0x55, "CHAR_LOAD_GR2", "statement", "med", False, 1),
    0x56: OpcodeSpec(0x56, "CHAR_LOAD_GR2_FRAME", "statement", "med", False, 1),
    0x57: OpcodeSpec(0x57, "SURF_FILL_RECT", "statement", "med", False, 1),
    0x58: OpcodeSpec(0x58, "SURF_BLIT", "statement", "high", False, 1),
    0x59: OpcodeSpec(0x59, "SURF_BLIT_EX", "statement", "med", False, 1),
    0x5A: OpcodeSpec(0x5A, "SURF_ALPHA_BLIT", "statement", "high", False, 1),
    0x5B: OpcodeSpec(0x5B, "SURF_MASK_BLEND", "statement", "med", False, 1),
    0x5C: OpcodeSpec(0x5C, "SURF_MASK_BLEND_PCT", "statement", "med", False, 1),
    0x5D: OpcodeSpec(0x5D, "SURF_TO_SCREEN_TRANS", "statement", "med", False, 1),
    0x5E: OpcodeSpec(0x5E, "SURF_DRAW_LINE", "statement", "high", False, 1),
    0x5F: OpcodeSpec(0x5F, "CHAR_RAW_COPY", "statement", "med", False, 1),
    0x60: OpcodeSpec(0x60, "WIDGET_DEFINE", "statement", "med", False, 1),
    0x61: OpcodeSpec(0x61, "WIDGET_POS", "statement", "high", False, 1),
    0x62: OpcodeSpec(0x62, "WIDGET_ACTIVATE", "statement", "high", False, 1),
    0x63: OpcodeSpec(0x63, "WIDGET_RESET_SPECIAL", "statement", "low", False, 1),
    0x64: OpcodeSpec(0x64, "FILE_EXISTS_KIND", "statement", "med", False, 1),
    0x96: OpcodeSpec(0x96, "SYS_DIALOG_A", "statement", "med", False, 1),
    0x97: OpcodeSpec(0x97, "FATAL_CALL", "statement", "low", False, 1),
    0x98: OpcodeSpec(0x98, "SHOW_NAME", "statement", "high", False, 1),
    0x99: OpcodeSpec(0x99, "SET_BG", "statement", "high", False, 1),
    0x9A: OpcodeSpec(0x9A, "SET_CHAR_SCENE", "statement", "high", False, 1),
    0x9B: OpcodeSpec(0x9B, "SET_EVENT_IMAGE", "statement", "high", False, 1),
    0x9C: OpcodeSpec(0x9C, "SET_EVENT_TILE", "statement", "high", False, 1),
    0x9D: OpcodeSpec(0x9D, "SYS_DIALOG_B", "statement", "med", False, 1),
    0x9E: OpcodeSpec(0x9E, "EMIT_ENCODED_TEXT", "statement", "med", False, 1),
    0x9F: OpcodeSpec(0x9F, "SHELL_EXEC", "statement", "high", False, 1),
}

INVALID_OPCODE_RANGES = (
    range(0x07, 0x14),
    range(0x27, 0x28),
    range(0x2E, 0x31),
    range(0x65, 0x96),
)

INLINE_MNEMONICS = {
    "TEXT",
    "STORE",
    "PUSH_REF",
    "STACK_MARK",
    *JUMP_MNEMONIC_TO_SUBOP.keys(),
    *CMP_MNEMONIC_TO_SUBOP.keys(),
    *ALU_MNEMONIC_TO_SUBOP.keys(),
}

STATEMENT_MNEMONIC_TO_OPCODE = {spec.mnemonic: opcode for opcode, spec in STATEMENT_OPCODE_SPECS.items()}


def iter_invalid_opcodes() -> Iterable[int]:
    for opcode_range in INVALID_OPCODE_RANGES:
        yield from opcode_range


INVALID_OPCODE_SET = set(iter_invalid_opcodes())


def is_invalid_opcode(opcode: int) -> bool:
    return opcode in INVALID_OPCODE_SET


def get_base_opcode_spec(opcode: int) -> Optional[OpcodeSpec]:
    return BASE_OPCODE_SPECS.get(opcode)


def get_statement_opcode_spec(opcode: int) -> Optional[OpcodeSpec]:
    return STATEMENT_OPCODE_SPECS.get(opcode)


def get_any_opcode_spec(opcode: int) -> Optional[OpcodeSpec]:
    return BASE_OPCODE_SPECS.get(opcode) or STATEMENT_OPCODE_SPECS.get(opcode)


def get_statement_opcode_by_mnemonic(mnemonic: str) -> Optional[int]:
    return STATEMENT_MNEMONIC_TO_OPCODE.get(mnemonic.upper())


def get_value_ref_spec(subopcode: int) -> Optional[ValueRefSpec]:
    return VALUE_REF_SPECS.get(subopcode)


def get_value_ref_subopcode_by_mnemonic(mnemonic: str) -> Optional[int]:
    return VALUE_REF_MNEMONIC_TO_SUBOP.get(mnemonic.upper())


def get_jump_subopcode(mnemonic: str) -> Optional[int]:
    return JUMP_MNEMONIC_TO_SUBOP.get(mnemonic.upper())


def get_cmp_subopcode(mnemonic: str) -> Optional[int]:
    return CMP_MNEMONIC_TO_SUBOP.get(mnemonic.upper())


def get_alu_subopcode(mnemonic: str) -> Optional[int]:
    return ALU_MNEMONIC_TO_SUBOP.get(mnemonic.upper())


def opcode_mnemonic(opcode: int, subopcode: Optional[int] = None) -> str:
    if opcode == 0x04:
        if subopcode not in JUMP_SUBOPS:
            raise KeyError(f"Unknown jump subopcode: {subopcode!r}")
        return JUMP_SUBOPS[subopcode]
    if opcode == 0x05:
        if subopcode not in CMP_SUBOPS:
            raise KeyError(f"Unknown cmp subopcode: {subopcode!r}")
        return CMP_SUBOPS[subopcode]
    if opcode == 0x06:
        if subopcode not in ALU_SUBOPS:
            raise KeyError(f"Unknown alu subopcode: {subopcode!r}")
        return ALU_SUBOPS[subopcode]
    spec = get_any_opcode_spec(opcode)
    if spec is None:
        raise KeyError(f"Unknown opcode: 0x{opcode:02X}")
    return spec.mnemonic
