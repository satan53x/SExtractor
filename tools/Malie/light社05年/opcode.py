# -*- coding: utf-8 -*-
"""sispara2/Malie-like exec.dat VM opcode / format definitions. See vm_analysis.md."""
from __future__ import annotations

from typing import Dict

# Keyword opcodes 1..39 (from host keyword table; same names as older Popotan VM).
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

# sispara2-era operand opcodes (shifted +1 vs older Popotan exec.dat).
# Interpreter dispatch table at 0x42C274 (opcode = index + 2).
OP_ARG_END = 41          # reserved / unused in this build's sample
OP_TEXT_A = 43           # case16: inline cstring
OP_TEXT_B = 44           # case16: inline cstring
OP_NUM_A = 45            # case17: u32
OP_NUM_B = 46            # case17: u32
OP_NUM_C = 47            # case17: u32
OP_TEXT = 48             # case18: u32 offset into trailing string pool
OP_EVAL = 49             # case19: u16 length + inline expression VM blob
OP_STR = 50              # case20: inline cstring (arg string / param)
OP_ARG = 51              # u32 argument (consumed as keyword arg list item)
OP_FSTORE_IMM = 53       # u32 (fstore immediate / stack push style)
OP_JMP = 54              # case22: u32 label index
OP_JZ = 55               # case22: u32 label index
OP_JNZ = 56              # case22: u32 label index


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
    ops[OP_TEXT] = OpInfo("text", "pool_off")
    ops[OP_EVAL] = OpInfo("eval", "eval_blob")
    ops[OP_STR] = OpInfo("str", "cstr")
    ops[OP_ARG] = OpInfo("arg", "u32")
    ops[OP_FSTORE_IMM] = OpInfo("fstore_imm", "u32")
    ops[OP_JMP] = OpInfo("jmp", "u32_label")
    ops[OP_JZ] = OpInfo("jz", "u32_label")
    ops[OP_JNZ] = OpInfo("jnz", "u32_label")
    return ops


OPS: Dict[int, OpInfo] = _build_ops()
OP_BY_NAME: Dict[str, int] = {info.mnemonic: code for code, info in OPS.items()}

# Legacy AST expression node kinds (still used when expr_count > 0).
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


# ---- Semantic text mapping (source .txt <-> exec.dat pool bytes) ----
# Custom player name markers inside dialogue:
#   $1 -> 07 0C 01
#   $2 -> 07 0C 02
# Voice tag pool entry:
#   07 08 + "v_xxx"
# Line terminators (not shown in semantic text / restored on assemble):
#   narration / plain : 07 06
#   voiced dialogue   : 07 09 07 06

MARKER_NAME1 = bytes([0x07, 0x0C, 0x01])
MARKER_NAME2 = bytes([0x07, 0x0C, 0x02])
MARKER_VOICE = bytes([0x07, 0x08])
TAIL_PLAIN = bytes([0x07, 0x06])
TAIL_VOICED = bytes([0x07, 0x09, 0x07, 0x06])
TAIL_WAIT = bytes([0x06])  # MLS %haato mid-line cut / multi-chunk boundary in pool
TOKEN_WAIT = "%haato"  # same token as Malie .mls source scripts

# Voice id prefix -> speaker name (from scenario sources + common cast)
VOICE_SPEAKER_PREFIX = {
    "v_yu": "雪奈",
    "v_hi": "ひな",
    "v_ho": "蛍",
    "v_mi": "瑞葉",
    "v_ik": "郁子",
    "v_yk": "由香里",
    "v_sa": "沙由理",
    "v_ko": "子供",
    "v_ak": "亜姫",
    "v_nt": "菜月",
    "v_na": "菜月",
    "v_li": "璃",
    "v_ri": "里穂",
    "v_ts": "椿",
}


def speaker_from_voice(voice_id: str) -> str:
    if not voice_id:
        return ""
    v = voice_id.strip()
    if v in VOICE_SPEAKER_PREFIX:
        return VOICE_SPEAKER_PREFIX[v]
    pref = v[:4] if len(v) >= 4 else v
    return VOICE_SPEAKER_PREFIX.get(pref, "")
