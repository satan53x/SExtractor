# -*- coding: utf-8 -*-
"""Popotan exec.dat VM opcode / format definitions. See vm_analysis.md."""
from __future__ import annotations

from typing import Dict

KEYWORDS: Dict[int, str] = {
    1: "bgm", 2: "call", 3: "charclear", 4: "charshow", 5: "clear",
    6: "cmp", 7: "end", 8: "fadd", 9: "fcall", 10: "fjump",
    11: "fload", 12: "fmax", 13: "fpop", 14: "fpush", 15: "fselect",
    16: "fselect_time", 17: "fstore", 18: "gcall", 19: "handler",
    20: "handler_clear", 21: "handler_jump", 22: "handler_set",
    23: "handler_wait", 24: "image", 25: "image_cache", 26: "jump",
    27: "mask", 28: "ol", 29: "page", 30: "pause", 31: "play",
    32: "screen_set", 33: "screen_take", 34: "sound", 35: "system_menu",
    36: "timer_clear", 37: "timer_wait", 38: "tjump", 39: "voice",
}
KEYWORD_BY_NAME: Dict[str, int] = {v: k for k, v in KEYWORDS.items()}

OP_ARG_END = 41
OP_TEXT_A = 42
OP_TEXT_B = 43
OP_NUM_A = 44
OP_NUM_B = 45
OP_NUM_C = 46
OP_TEXT = 47
OP_EVAL = 48
OP_STR = 49
OP_ARG = 50
OP_FSTORE_IMM = 52
OP_JMP = 53
OP_JZ = 54
OP_JNZ = 55


class OpInfo:
    __slots__ = ("mnemonic", "operand")

    def __init__(self, mnemonic: str, operand: str):
        self.mnemonic = mnemonic
        self.operand = operand


def _build_ops() -> Dict[int, OpInfo]:
    ops: Dict[int, OpInfo] = {}
    for code, name in KEYWORDS.items():
        ops[code] = OpInfo(name, "none")
    ops[OP_ARG_END] = OpInfo("arg_end", "none")
    ops[OP_TEXT_A] = OpInfo("text_a", "cstr")
    ops[OP_TEXT_B] = OpInfo("text_b", "cstr")
    ops[OP_NUM_A] = OpInfo("num_a", "u32")
    ops[OP_NUM_B] = OpInfo("num_b", "u32")
    ops[OP_NUM_C] = OpInfo("num_c", "u32")
    ops[OP_TEXT] = OpInfo("text", "cstr")
    ops[OP_EVAL] = OpInfo("eval", "u32_expr")
    ops[OP_STR] = OpInfo("str", "cstr")
    ops[OP_ARG] = OpInfo("arg", "u32_label")
    ops[OP_FSTORE_IMM] = OpInfo("fstore_imm", "u32")
    ops[OP_JMP] = OpInfo("jmp", "u32_label")
    ops[OP_JZ] = OpInfo("jz", "u32_label")
    ops[OP_JNZ] = OpInfo("jnz", "u32_label")
    return ops


OPS: Dict[int, OpInfo] = _build_ops()
OP_BY_NAME: Dict[str, int] = {info.mnemonic: code for code, info in OPS.items()}

EXPR_T = 84
EXPR_U = 85
EXPR_V = 86
EXPR_W = 87

EXPR_KIND_NAMES: Dict[int, str] = {
    84: "T", 85: "ID", 86: "INT", 87: "STR", 88: "CALL", 89: "ARG",
    91: "UPLUS", 92: "ADDROF", 93: "NOT", 94: "NEG", 95: "BNOT", 96: "DEREF",
    97: "POSTINC", 98: "POSTDEC", 99: "PREINC", 100: "PREDEC",
    101: "ADD", 102: "COMMA", 103: "SUB", 104: "DOT", 105: "DIV",
    106: "OP106", 107: "OP107", 108: "LT", 109: "LE", 110: "GT", 111: "GE",
    112: "EQ", 113: "NE", 114: "OP114", 115: "OP115", 116: "OP116", 120: "ASSIGN",
}
EXPR_KIND_BY_NAME: Dict[str, int] = {v: k for k, v in EXPR_KIND_NAMES.items()}

TYPE_KIND_NAMES: Dict[int, str] = {
    1: "void", 2: "char", 3: "uchar", 4: "short", 5: "ushort",
    6: "int", 7: "uint", 8: "long", 9: "ulong", 10: "float", 11: "double",
    12: "named", 14: "array", 15: "array_end", 16: "ptr", 17: "ident",
    18: "unsigned", 19: "signed",
}
TYPE_KIND_BY_NAME: Dict[str, int] = {v: k for k, v in TYPE_KIND_NAMES.items()}


def expr_kind_name(kind: int) -> str:
    return EXPR_KIND_NAMES.get(kind, "N%d" % kind)


def expr_kind_from_name(name: str) -> int:
    if name in EXPR_KIND_BY_NAME:
        return EXPR_KIND_BY_NAME[name]
    if name.startswith("N") and name[1:].isdigit():
        return int(name[1:])
    if name.isdigit():
        return int(name)
    raise ValueError("unknown expr kind: %s" % name)


def type_kind_name(kind: int) -> str:
    return TYPE_KIND_NAMES.get(kind, "t%d" % kind)


def type_kind_from_name(name: str) -> int:
    if name in TYPE_KIND_BY_NAME:
        return TYPE_KIND_BY_NAME[name]
    if name.startswith("t") and name[1:].isdigit():
        return int(name[1:])
    if name.isdigit():
        return int(name)
    raise ValueError("unknown type kind: %s" % name)


def op_info(code: int) -> OpInfo:
    if code in OPS:
        return OPS[code]
    return OpInfo("op_%d" % code, "none")


def op_code(mnemonic: str) -> int:
    if mnemonic in OP_BY_NAME:
        return OP_BY_NAME[mnemonic]
    if mnemonic.startswith("op_") and mnemonic[3:].isdigit():
        return int(mnemonic[3:])
    raise ValueError("unknown opcode mnemonic: %s" % mnemonic)