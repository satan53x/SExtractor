# -*- coding: utf-8 -*-
"""MEG script VM opcode definitions (Dice/Masys MEG bytecode)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

# Strings in MEG may be XOR-encrypted. Prefer decrypting with 1.py first.
# If you must decode ciphertext in-place, pass key via --key/--exe.
XOR_KEY = None  # None => treat string payloads as plaintext (post-dump)

# File header: "MEG" + u16 version + u8 + 26-byte copyright
HEADER_MAGIC = b"MEG"
HEADER_SIZE = 32  # 3 + 2 + 1 + 26
COPYRIGHT = b"Copyright(c) dice co.,ltd."
assert len(COPYRIGHT) == 26

# Expression atomic kinds
EXPR_ATOM = {
    0x50: ("VAR_NUM", "u16"),      # P + u16 index -> numeric var
    0x51: ("VAR_POINT", "u16"),    # Q + u16
    0x52: ("VAR_STR", "u16"),      # R + u16
    0x53: ("FLAG", None),          # S runtime flag n2_0
    0x54: ("REG_T", None),         # T
    0x55: ("REG_U", None),         # U string
    0x57: ("SCR_H", None),         # W
    0x58: ("SCR_W", None),         # X
    0x59: ("WIN_L", None),         # Y
    0x5A: ("WIN_T", None),         # Z
    0x5B: ("WIN_W", None),         # [
    0x5C: ("WIN_H", None),         # \
    0x60: ("IMM", "i32"),          # ` + i32
    0x61: ("IMM10", "b10"),        # a + 10 raw bytes (long double)
    0x62: ("STR", "str"),          # b + u16 len + payload (plain after dump, or XOR if key set)
}

# Operator bytes used after first atom (expression continues until 0x00)
EXPR_OPS = {
    0x03: "STORE",
    0x04: "ADD",
    0x05: "SUB",
    0x06: "MUL",
    0x07: "DIV",
    0x08: "MOD",
    0x09: "AND",
    0x0A: "OR",
    0x0B: "XOR",
    0x0D: "SHL",
    0x0E: "SHR",
    0x0F: "EQ",
    0x10: "NE",
    0x11: "LT",
    0x12: "GT",
    0x13: "LE",
    0x14: "GE",
    0x15: "LAND",
    0x16: "LOR",
}

# Special bare control opcodes (not dispatched via handler table)
SPECIAL_OPS = {
    0x17: "JTRUE_SKIP5",   # expr(mode2); if true seek +5
    0x18: "JMP",           # u32 abs
    0x19: "CALL",          # u32 abs, push ret
    0x20: "SETCMP",        # expr(mode0); X_0 = X
    0x21: "JNE_SKIP5",     # expr(mode0); if X_0 != X seek +5
    0xFE: "EXT",           # prefix for extended table
    0xFF: "RET",           # pop or end
}

# Primary + extended opcode table (index -> opcode byte), from 0x47C995
OPCODE_TABLE = [
    0xDA, 0xDB, 0xD3, 0x80, 0x81, 0x82, 0x83, 0x84, 0xCC, 0xCD, 0x86, 0x85, 0x89, 0x8A, 0x8B, 0x8C,
    0x8D, 0x8E, 0x8F, 0x90, 0x91, 0x92, 0x93, 0x94, 0x95, 0x96, 0x98, 0x99, 0x9A, 0x9B, 0x9C, 0x9D,
    0x9E, 0x9F, 0xA0, 0xA1, 0xA2, 0xA3, 0xA4, 0xA5, 0xA6, 0xA7, 0xA8, 0xD6, 0xA9, 0xD7, 0xAA, 0xD8,
    0xAB, 0xAC, 0xAD, 0xAE, 0xAF, 0xB0, 0xB1, 0xB2, 0xB3, 0xB4, 0xB5, 0xB6, 0xCB, 0xB7, 0xB8, 0xB9,
    0xBA, 0xBB, 0xD0, 0xBC, 0xBD, 0xD2, 0xBE, 0xC0, 0xC1, 0xC2, 0xC4, 0xC5, 0xC6, 0xC8, 0xC9, 0xCF,
    0xCA, 0xDC, 0xDD, 0xDE, 0xDF, 0xE0, 0xE1, 0xCE, 0xE2, 0xE3, 0xE4, 0xE5, 0xE6, 0xE7, 0xE8, 0xE9,
    0xEA, 0xEB, 0xEC, 0xED, 0xEE, 0xEF, 0xF0, 0xF1, 0xF2, 0xF3, 0xF4, 0xF5, 0xF6, 0xF7, 0xF8, 0xF9,
    0xFA, 0xFB, 0xFC, 0xFD, 0xD4, 0x87, 0x88, 0x97, 0xBF, 0xC3, 0xC7, 0xD1, 0xD5, 0xD9,
    # extended (index >= 126), used with FE prefix (also unique bare)
    0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08, 0x09, 0x0A, 0x0B, 0x0C, 0x0D, 0x0E, 0x0F,
    0x10, 0x11, 0x12, 0x13, 0x14, 0x15, 0x16, 0x17, 0x18, 0x19, 0x1A, 0x1B, 0x1C, 0x1D, 0x1E, 0x1F,
    0x20, 0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x27, 0x28, 0x29, 0x2A, 0x2B, 0x2C, 0x2D, 0x2E, 0x2F,
    0x30, 0x31,
]
assert len(OPCODE_TABLE) == 176

# Handler addresses (documentation)
HANDLER_TABLE = [
    0x416F50, 0x416F78, 0x416FAC, 0x417CBC, 0x417CF0, 0x417EA0, 0x417F18, 0x4182DC,
    0x418E68, 0x418EF4, 0x418F80, 0x41906C, 0x4192B8, 0x419CB0, 0x419D70, 0x419FAC,
    0x41A028, 0x41AAB8, 0x41AEC4, 0x41B0A8, 0x41B370, 0x41B4B0, 0x41B90C, 0x41BB0C,
    0x41BCC0, 0x41BF2C, 0x41C040, 0x41C178, 0x41C418, 0x41C590, 0x41C864, 0x41C970,
    0x41CBD8, 0x41CD24, 0x41CFBC, 0x41D0A4, 0x41D1D8, 0x41D1DC, 0x41D1E0, 0x41D1E4,
    0x41D1E8, 0x41D1EC, 0x41D1F0, 0x41D1F4, 0x41D1F8, 0x41D1FC, 0x41D200, 0x41D204,
    0x41D208, 0x41D2A0, 0x41D338, 0x41D3A8, 0x41D750, 0x41E6B0, 0x41EF94, 0x41F87C,
    0x4201D4, 0x420EDC, 0x42142C, 0x421980, 0x421F14, 0x422890, 0x422978, 0x4229C8,
    0x422A4C, 0x422A74, 0x422AA0, 0x422B50, 0x422BF0, 0x422C00, 0x422C6C, 0x422ED4,
    0x422F10, 0x4231DC, 0x42391C, 0x423A08, 0x423D8C, 0x4242D8, 0x424338, 0x4245B8,
    0x4245E8, 0x424634, 0x42464C, 0x424664, 0x42467C, 0x424710, 0x424A60, 0x424B0C,
    0x424B6C, 0x424EA8, 0x4251E4, 0x425228, 0x425314, 0x425378, 0x4253DC, 0x425410,
    0x4254AC, 0x425554, 0x425570, 0x4256B0, 0x4257D8, 0x425834, 0x425858, 0x42593C,
    0x425A6C, 0x425C30, 0x42617C, 0x426188, 0x4265B0, 0x42665C, 0x4266E0, 0x4175C4,
    0x426738, 0x426808, 0x42685C, 0x42697C, 0x426A00, 0x426A84, 0x426ADC, 0x426CD4,
    0x427144, 0x427560, 0x427610, 0x427690, 0x4276AC, 0x42777C,
    0x427848, 0x427958, 0x427A88, 0x427BDC, 0x427C30, 0x427D50, 0x427E00, 0x427E90,
    0x427F1C, 0x427F60, 0x427FA8, 0x428018, 0x428068, 0x4280BC, 0x428130, 0x428154,
    0x4281D0, 0x4282A8, 0x428338, 0x4284F0, 0x428534, 0x428574, 0x4285FC, 0x428708,
    0x4288BC, 0x428AB8, 0x428D08, 0x428D14, 0x428D40, 0x428E1C, 0x428E58, 0x428FA4,
    0x4299B0, 0x42A210, 0x42A328, 0x42A374, 0x42A37C, 0x42A3D8, 0x42A3F4, 0x42A448,
    0x42A4D8, 0x42A4E8, 0x42A50C, 0x42A558, 0x42A564, 0x42A588, 0x42A5A4, 0x42A5D8,
    0x42A604, 0x42A630,
]
assert len(HANDLER_TABLE) == 176

# Operand modes for sub_40FB80: 0=number, 1=string, 2=bool/flag
# Built from IDA handlers. Variable-path opcodes use success-path operand lists.
# Format: list of mode ints; optional leading ("raw_u32", n) via RAW_BEFORE.

RAW_U32_BEFORE = {
    0xC3: 1,  # timer create: id u32 then 2 exprs
    0xC7: 1,  # timer kill: id u32
}

# Default: all FB80 calls in handler order (success path for resource ops)
OPERAND_MODES: Dict[int, List[int]] = {}

def _init_modes():
    # From handler analysis (all sub_40FB80 in order). Success-path for branched.
    data = {
        0xDA: [1],
        0xDB: [0, 0],
        0xD3: [1],
        0x80: [1],
        0x81: [0, 0],
        0x82: [0, 0],
        0x83: [0, 0, 0, 0, 0, 0, 0, 1, 0, 0],
        0x84: [0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 1, 1, 0, 0],
        0xCC: [0, 0, 0, 0],
        0xCD: [0, 0, 0, 0],
        0x86: [0, 0, 0, 0, 0],
        0x85: [0, 1],
        0x89: [0],
        0x8A: [0],
        0x8B: [0, 0, 0, 0],
        0x8C: [1, 2],
        0x8D: [0, 0, 0, 0],
        0x8E: [0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
        0x8F: [0, 0, 0, 0, 0, 0, 0, 0, 0],
        0x90: [0, 0, 0, 0, 0, 0, 0, 0],
        0x91: [0, 0, 0, 0, 0, 0, 0],
        0x92: [0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
        0x93: [0, 0, 0, 0, 0, 0, 0, 0, 0],
        0x94: [0, 1, 0, 0, 0],
        0x95: [0, 0, 0, 0, 0, 0, 0],
        0x96: [0, 0, 0, 0, 0, 0, 0, 0],
        0x98: [0, 1, 0, 0, 0, 0, 0],
        0x99: [0, 1, 0, 0, 0, 0, 0, 0],
        0x9A: [0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0],
        0x9B: [0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
        0x9C: [1, 0, 0, 0, 0],
        0x9D: [0, 1, 0, 0, 0, 0, 0],
        0x9E: [1, 0, 0, 0, 0, 0, 0, 0, 0],
        0x9F: [0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0],
        0xA0: [0, 0, 0, 0, 0, 0],
        0xA1: [0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
        0xA2: [], 0xA3: [], 0xA4: [], 0xA5: [], 0xA6: [], 0xA7: [], 0xA8: [],
        0xD6: [], 0xA9: [], 0xD7: [], 0xAA: [], 0xD8: [],
        0xAB: [0, 2],
        0xAC: [0, 2],
        0xAD: [1],
        0xAE: [],
        0xAF: [0, 1, 0],
        0xB0: [0, 0, 0],
        0xB1: [0, 0, 0],
        0xB2: [0, 0, 0],
        0xB3: [0],
        0xB4: [0, 0, 0],
        0xB5: [0, 0, 0],
        0xB6: [0, 0, 0],
        0xCB: [0],
        0xB7: [1],
        0xB8: [2],
        0xB9: [0, 0],
        0xBA: [],
        0xBB: [],
        0xD0: [0, 0, 0, 0],
        0xBC: [0, 0, 0, 0],
        0xBD: [],
        0xD2: [0],
        0xBE: [0, 2],
        0xC0: [],
        0xC1: [0],
        0xC2: [0, 0],  # may branch; default 2 from total
        0xC4: [],
        0xC5: [0],
        0xC6: [0, 0],
        0xC8: [],
        0xC9: [0],
        0xCF: [0],
        0xCA: [0, 2],
        0xDC: [], 0xDD: [], 0xDE: [],
        0xDF: [0, 0, 0, 0, 0],
        0xE0: [0, 1, 0],
        0xE1: [0],
        0xCE: [0, 0, 0],
        0xE2: [0, 0, 0, 1],
        0xE3: [0, 0, 0, 1],
        0xE4: [0, 0],
        0xE5: [0],
        0xE6: [0, 0, 0],
        0xE7: [0, 0, 0],
        0xE8: [0],
        0xE9: [],
        0xEA: [0, 0],
        0xEB: [1],
        0xEC: [1, 0],
        0xED: [0, 0, 0, 0, 0],
        0xEE: [1],
        0xEF: [1],
        0xF0: [0, 0, 0, 0, 0],
        0xF1: [0, 0, 0, 0, 0, 0, 0, 0, 0],
        0xF2: [0, 0, 0],
        0xF3: [0],
        0xF4: [],
        0xF5: [0, 0, 0, 0],
        0xF6: [0, 0],
        0xF7: [0, 0, 0],
        0xF8: [0, 1],
        0xF9: [1],
        0xFA: [0, 0, 0, 0],
        0xFB: [0, 0],
        0xFC: [],
        0xFD: [0, 0, 0, 0],
        0xD4: [0, 0, 0, 0],
        0x87: [0, 0, 0],
        0x88: [0, 0, 0, 0],
        0x97: [0, 0, 0, 1],
        0xBF: [0, 0, 0, 1],
        0xC3: [0, 0],  # after raw u32
        0xC7: [],      # after raw u32
        0xD1: [0],
        0xD5: [1, 0, 0, 0, 0],
        0xD9: [0, 1, 0, 0],
        # extended
        0x00: [0, 1, 0, 0, 0, 0, 0],
        0x01: [1, 0, 0, 0, 0, 0, 0, 0, 0],
        0x02: [0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0],
        0x03: [0],
        0x04: [1, 1, 0],
        0x05: [1],
        0x06: [],
        0x07: [0],
        0x08: [0, 0],
        0x09: [0],
        0x0A: [0, 0],
        0x0B: [0, 0, 0],
        0x0C: [0, 0],
        0x0D: [0, 1, 0],
        0x0E: [0],
        0x0F: [0, 0, 0],
        0x10: [0, 1],
        0x11: [0, 1],
        0x12: [1, 1, 0, 1],
        0x13: [0, 0],
        0x14: [0],
        0x15: [1, 0, 0],
        0x16: [0, 0, 0, 0, 0, 0, 0, 0],
        0x17: [0, 0, 0, 0, 0, 0, 0, 0],  # FE 17 handler
        0x18: [0, 0, 0, 0, 0, 0, 0],
        0x19: [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
        0x1A: [],
        0x1B: [0],
        0x1C: [0, 1],
        0x1D: [0],
        0x1E: [1, 0, 0],
        0x1F: [0, 0, 0],
        0x20: [],  # FE 20 handler has 0 fb in prefix analysis but file 4299B0 is large - check
        0x21: [],
        0x22: [0, 0, 0],
        0x23: [],
        0x24: [],
        0x25: [0],
        0x26: [],
        0x27: [0, 0, 0, 0],
        0x28: [],
        0x29: [0],
        0x2A: [0, 0, 0],
        0x2B: [],
        0x2C: [0],
        0x2D: [0],
        0x2E: [0, 0],
        0x2F: [0],
        0x30: [0],
        0x31: [0, 0, 0, 0, 0, 0, 0],
    }
    # Fix FE20 - 4299B0 had 0 fb80 in analysis (uses other paths)
    OPERAND_MODES.update(data)

_init_modes()

# Semantic mnemonics (best-effort)
MNEMONICS: Dict[int, str] = {
    0xDA: "SET_TITLE",
    0xDB: "SET_POS",
    0xD3: "LOAD_MGD",
    0x80: "SET_CAPTION",
    0xAD: "EXEC_MEG",
    0xAE: "EXIT",
    0xFF: "RET",
    0x18: "JMP",
    0x19: "CALL",
    0x17: "JTRUE_SKIP5",
    0x20: "SETCMP",
    0x21: "JNE_SKIP5",
    0xFE: "EXT",
    0xC3: "TIMER_SET",
    0xC7: "TIMER_KILL",
    0x29: "SEEK",
    0x28: "GETPOS",
    0x1A: "GETTIME",
    0xF9: "LOAD_MGS",
}

def mnemonic(op: int, extended: bool = False) -> str:
    if extended:
        return MNEMONICS.get(op, f"EXT_{op:02X}")
    if op in SPECIAL_OPS and op not in (0xFE,):
        return SPECIAL_OPS[op]
    return MNEMONICS.get(op, f"OP_{op:02X}")


def xor_crypt(data: bytes, key: bytes | None = None) -> bytes:
    """XOR with key; if key is None/empty, return data unchanged (already dumped)."""
    k = key if key is not None else XOR_KEY
    if not k:
        return data
    out = bytearray(len(data))
    n = len(k)
    for i, b in enumerate(data):
        out[i] = b ^ k[i % n]
    return bytes(out)

def set_xor_key(key: bytes | None) -> None:
    global XOR_KEY
    XOR_KEY = key


def build_opcode_index() -> Dict[int, int]:
    """Map opcode byte -> table index (first occurrence)."""
    m = {}
    for i, op in enumerate(OPCODE_TABLE):
        if op not in m:
            m[op] = i
    return m

OPCODE_INDEX = build_opcode_index()
EXT_OPCODE_SET = set(OPCODE_TABLE[126:])
PRI_OPCODE_SET = set(OPCODE_TABLE[:126])
