# -*- coding: utf-8 -*-
"""Malie sc.dll exec.dat VM opcode / format definitions. See vm_analysis.md."""
from __future__ import annotations

from typing import Dict

# ScenarioProcessor_Step opcodes (sc.dll 0x10011260).
# opcode byte is fetched by sub_10011240 from code stream.
OP_EVAL = 2          # u16 len + inline expression VM blob (sub_10011440 / sub_100072B0)
OP_JMP = 3           # u32 label index
OP_JZ = 4            # u32 label index (jump if eval result == 0)
OP_JNZ = 5           # u32 label index (jump if eval result != 0)
OP_TEXT = 6          # u32 offset into msg string pool
OP_CALL = 7          # u32 label index (push return, jump)
OP_MESSAGEOUT = 8    # host handler: present line / mark read (sub_10010AD0)
OP_RET = 9           # return from call
OP_PAGE = 10         # host handler: page break
OP_CLEAR = 11        # host handler: clear window / state
OP_ENDTEXT = 12      # host handler: finalize text unit (compiler also closes msg string)
OP_SYNC = 13         # host handler: rare sync/wait variant


class OpInfo:
    __slots__ = ("mnemonic", "operand")

    def __init__(self, mnemonic: str, operand: str):
        self.mnemonic = mnemonic
        self.operand = operand


def _build_ops() -> Dict[int, OpInfo]:
    return {
        OP_EVAL: OpInfo("eval", "eval_blob"),
        OP_JMP: OpInfo("jmp", "u32_label"),
        OP_JZ: OpInfo("jz", "u32_label"),
        OP_JNZ: OpInfo("jnz", "u32_label"),
        OP_TEXT: OpInfo("text", "pool_off"),
        OP_CALL: OpInfo("call", "u32_label"),
        OP_MESSAGEOUT: OpInfo("messageout", "none"),
        OP_RET: OpInfo("ret", "none"),
        OP_PAGE: OpInfo("page", "none"),
        OP_CLEAR: OpInfo("clear", "none"),
        OP_ENDTEXT: OpInfo("endtext", "none"),
        OP_SYNC: OpInfo("sync", "none"),
    }


OPS: Dict[int, OpInfo] = _build_ops()
OP_BY_NAME: Dict[str, int] = {info.mnemonic: code for code, info in OPS.items()}

# ExpressionTree_* kinds are single bytes (not u32) in this sc.dll build.
EXPR_U = 0x55  # 'U' null / empty node written as bare U
EXPR_V = 0x56  # 'V' string
EXPR_W = 0x57  # 'W' int
EXPR_X = 0x58  # 'X' string (alternate)

# Keep legacy names used by tools.
EXPR_T = EXPR_U

EXPR_KIND_NAMES: Dict[int, str] = {
    0x55: "U",
    0x56: "V",
    0x57: "W",
    0x58: "X",
    # binary ops appear as other single-byte kinds from the compiler
    0x54: "T",
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


# Inline expression VM opcodes (sub_100072B0). Length is known via parent u16.
EXPR_VM_OPS: Dict[int, str] = {
    0: "jmp",
    1: "jz",
    2: "jnz",
    3: "call_local",
    4: "call",
    5: "ret_true",
    6: "ret_false",
    7: "load",
    8: "store",
    9: "push_u32_a",
    10: "push_estr_u8",
    11: "push_estr_u16",
    13: "push_estr_u32",
    14: "push_u32_b",
    15: "dup_slot",
    16: "push0",
    18: "push_u8",
    19: "neg",
    20: "add",
    21: "sub",
    22: "mul",
    23: "div",
    24: "mod",
    25: "and",
    26: "or",
    27: "xor",
    28: "bnot",
    29: "bool",
    30: "land",
    31: "lor",
    32: "lnot",
    33: "lt",
    34: "le",
    35: "gt",
    36: "ge",
    37: "eq",
    38: "ne",
    39: "shl",
    40: "shr",
    41: "postinc",
    42: "postdec",
    43: "preinc",
    44: "predec",
    45: "add_base",
    46: "debug_dump",
}


# ---- Semantic text mapping (source .mls/.txt <-> msg pool bytes) ----
# Voice tag pool/msg entry:
#   07 08 + "v_xxx" + 00
# Line terminators:
#   narration / plain : 07 06
#   voiced dialogue   : 07 09 07 06
# Ruby (rare in this title):
#   07 01 base 0A reading 00

MARKER_NAME_INSERT = bytes([0x07, 0x0C])  # + u8 slot (rare here)
MARKER_NAME1 = bytes([0x07, 0x0C, 0x01])
MARKER_NAME2 = bytes([0x07, 0x0C, 0x02])


def name_insert_bytes(slot: int) -> bytes:
    if not 0 <= int(slot) <= 255:
        raise ValueError("name-insert slot out of range: %s" % slot)
    return bytes([0x07, 0x0C, int(slot) & 0xFF])


MARKER_VOICE = bytes([0x07, 0x08])
MARKER_RUBY = bytes([0x07, 0x01])
MARKER_STYLE = bytes([0x07, 0x02])
MARKER_NEWLINE = bytes([0x07, 0x04])  # $e
MARKER_KWAIT = bytes([0x07, 0x06])    # $k mid-text / plain tail
MARKER_COLOR = 0x01
MARKER_COLOR_END = 0x02
MARKER_FONT = 0x03
MARKER_FONT_END = 0x04
MARKER_SPECIAL = 0x06
RUBY_SEP = 0x0A
TAIL_PLAIN = bytes([0x07, 0x06])
TAIL_VOICED = bytes([0x07, 0x09, 0x07, 0x06])
TAIL_WAIT = bytes([0x06])
TOKEN_WAIT = "%haato"
TOKEN_NEWLINE = "$e"
TOKEN_KWAIT = "$k"
TOKEN_COLOR_END = "$c"
TOKEN_FONT_END = "$f"

# Voice id prefix -> speaker name (from this title's msg/estr cast table)
VOICE_SPEAKER_PREFIX = {
    "v_bw": "松島枇杷子",
    "v_ak": "星山亜紀",
    "v_as": "朝日麻紀",
    "v_mr": "森永栗子",
    "v_ks": "勝屋萌菜香",
    "v_hj": "天野霞",
    "v_mt": "松原美穂",
    "v_wo": "矢追敏美",
    "v_kt": "黒服の女",
    "v_uc": "声",
    "v_bk": "黒服",
    "v_bb": "黒服の女",
    "v_ja": "女生徒１",
    "v_jb": "女生徒２",
    "v_jc": "女生徒３",
    "v_an": "アナウンサー",
}

# Special-effect / system labels commonly called from bytecode (call <label>).
# These are not opcodes; they are scenario labels implementing effect macros.
EFFECT_LABELS = {
    # CG / screen
    "CG", "CG_H", "CG_BG", "CGWAIT", "CGFILTER", "CHARFILTER",
    # character / face
    "CHARA_SHOW", "CHARA_SHOW_DRESS", "CHARA_HIDE", "CHARA_SHOW_DRESS_POS",
    "CHARA_MOVE", "FACE_SHOW", "FACE_SHOW_DRESS",
    "CHARA_AUTO", "CHARA_L", "CHARA_R", "CHARA_C",
    "CHARA_LO", "CHARA_RO", "CHARA_LB", "CHARA_RB",
    "CHARA_LBO", "CHARA_RBO", "CHARA_CB",
    # fade / battle / wipe helpers
    "FADEOUT", "FADEIN", "CLEAR_BATTLE",
}


def speaker_from_voice(voice_id: str) -> str:
    if not voice_id:
        return ""
    v = voice_id.strip()
    if v in VOICE_SPEAKER_PREFIX:
        return VOICE_SPEAKER_PREFIX[v]
    pref = v[:4] if len(v) >= 4 else v
    return VOICE_SPEAKER_PREFIX.get(pref, "")
