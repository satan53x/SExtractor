# -*- coding: utf-8 -*-
"""Opcode / control-byte definitions for crimson (2003) exec.dat VM.

Text-control ground truth comes from IDA:
  sub_434A80 (0x434A80)  - text stream walker / measure
  sub_434810 (0x434810)  - strip/normalize stream (07 04 -> LF)
  sub_42CC80 / opcode.py KEYWORDS - script VM opcodes (separate from 0x07 text controls)
"""
from __future__ import annotations

from typing import Dict

# Script VM keywords (code section opcodes 1..39)
KEYWORDS: Dict[int, str] = {
    1: "nop",
    2: "page",
    3: "call",
    4: "return",
    5: "wait",
    6: "jump",
    7: "select",
    8: "select_end",
    9: "image",
    10: "image_end",
    11: "bgm",
    12: "bgm_stop",
    13: "se",
    14: "se_stop",
    15: "movie",
    16: "movie_end",
    17: "fade",
    18: "fade_end",
    19: "pause",
    20: "clear",
    21: "window",
    22: "window_end",
    23: "layer",
    24: "layer_end",
    25: "effect",
    26: "effect_end",
    27: "shake",
    28: "quake",
    29: "flash",
    30: "color",
    31: "volume",
    32: "loop",
    33: "loop_end",
    34: "system",
    35: "debug",
    36: "date",
    37: "time",
    38: "random",
    39: "end",
}

# Non-keyword code opcodes
OP_ARG_END = 41
OP_TEXT_A = 43
OP_TEXT_B = 44
OP_NUM_A = 45
OP_NUM_B = 46
OP_NUM_C = 47
OP_TEXT = 48          # u32 pool_offset
OP_EVAL = 49          # u16 len + inline blob
OP_STR = 50           # inline cstring
OP_ARG = 51           # u32
OP_FSTORE_IMM = 53    # u32
OP_JMP = 54
OP_JZ = 55
OP_JNZ = 56


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


# ---------------------------------------------------------------------------
# Text stream control bytes (pool / dialogue), from IDA sub_434A80 / sub_434810
# Lead-in always 0x07. Subcode is the next byte.
#
#  01 ruby   : 07 01 <base SJIS> 0A <reading SJIS> 00  then OUTER text continues
#  02 effect : 07 02 <u8>   (rare)
#  04 newline: 07 04        (source $e; strip walker emits 0x0A)
#  05 skip   : 07 05 <u16 len> <payload>
#  06 plain end / page tick (often final tail; also mid-entry sentence break)
#  07 nested : 07 07 <block...00> <cstr00>
#  08 voice  : 07 08 <voice_id ASCII> 00  then dialogue continues after NUL
#  09 voiced terminator (often followed by 07 06)
#  0C name   : 07 0C 01 / 07 0C 02  ($1 / $2)
# ---------------------------------------------------------------------------

CTRL_LEAD = 0x07
CTRL_RUBY = 0x01
CTRL_FX = 0x02
CTRL_NL = 0x04
CTRL_SKIP = 0x05
CTRL_PLAIN = 0x06
CTRL_NEST = 0x07
CTRL_VOICE = 0x08
CTRL_VOICED = 0x09
CTRL_NAME = 0x0C

MARKER_RUBY = bytes([CTRL_LEAD, CTRL_RUBY])
MARKER_FX_PREFIX = bytes([CTRL_LEAD, CTRL_FX])
MARKER_NL = bytes([CTRL_LEAD, CTRL_NL])          # $e
MARKER_SKIP_PREFIX = bytes([CTRL_LEAD, CTRL_SKIP])
MARKER_PLAIN = bytes([CTRL_LEAD, CTRL_PLAIN])    # 07 06
MARKER_NEST = bytes([CTRL_LEAD, CTRL_NEST])
MARKER_VOICE = bytes([CTRL_LEAD, CTRL_VOICE])
MARKER_VOICED = bytes([CTRL_LEAD, CTRL_VOICED])  # 07 09
MARKER_NAME1 = bytes([CTRL_LEAD, CTRL_NAME, 0x01])
MARKER_NAME2 = bytes([CTRL_LEAD, CTRL_NAME, 0x02])

TAIL_PLAIN = MARKER_PLAIN                         # 07 06
TAIL_VOICED = bytes([CTRL_LEAD, CTRL_VOICED, CTRL_LEAD, CTRL_PLAIN])  # 07 09 07 06
TAIL_WAIT = bytes([0x06])                         # rare lone 0x06 mid-chunk
TOKEN_WAIT = "%haato"
TOKEN_NL = "$e"                                   # 07 04
TOKEN_LINE = "%p"                                 # mid-entry 07 06 (legacy)
TOKEN_VOICED_MID = "%pv"                           # mid-entry 07 09 07 06 (+0A* as newlines)
MARKER_MUSIC = bytes([0xFF, 0x00])                 # IDA 0xFF as 2-byte glyph; source maps to ♪
TOKEN_MUSIC = "♪"

# Crimson cast (from 文本/1/scene*.txt voice tags)
VOICE_SPEAKER_PREFIX = {
    "v_mu": "睦月",
    "v_ar": "亜梨子",
    "v_hi": "姫野",
    "v_ha": "晴香",
    "v_yu": "由理",
    "v_ry": "涼子",
    "v_sk": "沙綺",
    "v_ka": "桂",
    "v_sa": "沙綺",
    "v_na": "夏美",
    "v_no": "紀子",
    "v_ri": "理絵",
}


def speaker_from_voice(voice_id: str) -> str:
    if not voice_id:
        return ""
    v = voice_id.strip()
    if v in VOICE_SPEAKER_PREFIX:
        return VOICE_SPEAKER_PREFIX[v]
    pref = v[:4] if len(v) >= 4 else v
    return VOICE_SPEAKER_PREFIX.get(pref, "")
