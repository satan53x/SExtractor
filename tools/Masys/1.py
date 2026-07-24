# -*- coding: utf-8 -*-
"""
从 Megu.exe 按代码特征提取字符串 XOR 密钥，并对 MEG dump/import。

用法:
  python 1.py key Megu.exe
  python 1.py dump Megu.exe meg out
  python 1.py import Megu.exe new out
  python 1.py Megu.exe new out
"""


from __future__ import annotations

import re
import struct
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

HEADER_SIZE = 32
MAGIC = b"MEG"

EXPR_ATOM = {
    0x50: "u16", 0x51: "u16", 0x52: "u16",
    0x53: "", 0x54: "", 0x55: "",
    0x57: "", 0x58: "", 0x59: "", 0x5A: "", 0x5B: "", 0x5C: "",
    0x60: "i32", 0x61: "b10", 0x62: "str",
}
EXPR_OPS = {
    0x03, 0x04, 0x05, 0x06, 0x07, 0x08, 0x09, 0x0A, 0x0B,
    0x0D, 0x0E, 0x0F, 0x10, 0x11, 0x12, 0x13, 0x14, 0x15, 0x16,
}

# ---- embedded opcode operand tables (game-independent walker) ----
OPERAND_MODES = {
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
    0x17: [0, 0, 0, 0, 0, 0, 0, 0],
    0x18: [0, 0, 0, 0, 0, 0, 0],
    0x19: [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
    0x1A: [],
    0x1B: [0],
    0x1C: [0, 1],
    0x1D: [0],
    0x1E: [1, 0, 0],
    0x1F: [0, 0, 0],
    0x20: [],
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
    0x80: [1],
    0x81: [0, 0],
    0x82: [0, 0],
    0x83: [0, 0, 0, 0, 0, 0, 0, 1, 0, 0],
    0x84: [0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 1, 1, 0, 0],
    0x85: [0, 1],
    0x86: [0, 0, 0, 0, 0],
    0x87: [0, 0, 0],
    0x88: [0, 0, 0, 0],
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
    0x97: [0, 0, 0, 1],
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
    0xA2: [],
    0xA3: [],
    0xA4: [],
    0xA5: [],
    0xA6: [],
    0xA7: [],
    0xA8: [],
    0xA9: [],
    0xAA: [],
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
    0xB7: [1],
    0xB8: [2],
    0xB9: [0, 0],
    0xBA: [],
    0xBB: [],
    0xBC: [0, 0, 0, 0],
    0xBD: [],
    0xBE: [0, 2],
    0xBF: [0, 0, 0, 1],
    0xC0: [],
    0xC1: [0],
    0xC2: [0, 0],
    0xC3: [0, 0],
    0xC4: [],
    0xC5: [0],
    0xC6: [0, 0],
    0xC7: [],
    0xC8: [],
    0xC9: [0],
    0xCA: [0, 2],
    0xCB: [0],
    0xCC: [0, 0, 0, 0],
    0xCD: [0, 0, 0, 0],
    0xCE: [0, 0, 0],
    0xCF: [0],
    0xD0: [0, 0, 0, 0],
    0xD1: [0],
    0xD2: [0],
    0xD3: [1],
    0xD4: [0, 0, 0, 0],
    0xD5: [1, 0, 0, 0, 0],
    0xD6: [],
    0xD7: [],
    0xD8: [],
    0xD9: [0, 1, 0, 0],
    0xDA: [1],
    0xDB: [0, 0],
    0xDC: [],
    0xDD: [],
    0xDE: [],
    0xDF: [0, 0, 0, 0, 0],
    0xE0: [0, 1, 0],
    0xE1: [0],
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
}
RAW_U32_BEFORE = {
    0xC3: 1,
    0xC7: 1,
}
OPCODE_INDEX = {
    0xDA: 0,
    0xDB: 1,
    0xD3: 2,
    0x80: 3,
    0x81: 4,
    0x82: 5,
    0x83: 6,
    0x84: 7,
    0xCC: 8,
    0xCD: 9,
    0x86: 10,
    0x85: 11,
    0x89: 12,
    0x8A: 13,
    0x8B: 14,
    0x8C: 15,
    0x8D: 16,
    0x8E: 17,
    0x8F: 18,
    0x90: 19,
    0x91: 20,
    0x92: 21,
    0x93: 22,
    0x94: 23,
    0x95: 24,
    0x96: 25,
    0x98: 26,
    0x99: 27,
    0x9A: 28,
    0x9B: 29,
    0x9C: 30,
    0x9D: 31,
    0x9E: 32,
    0x9F: 33,
    0xA0: 34,
    0xA1: 35,
    0xA2: 36,
    0xA3: 37,
    0xA4: 38,
    0xA5: 39,
    0xA6: 40,
    0xA7: 41,
    0xA8: 42,
    0xD6: 43,
    0xA9: 44,
    0xD7: 45,
    0xAA: 46,
    0xD8: 47,
    0xAB: 48,
    0xAC: 49,
    0xAD: 50,
    0xAE: 51,
    0xAF: 52,
    0xB0: 53,
    0xB1: 54,
    0xB2: 55,
    0xB3: 56,
    0xB4: 57,
    0xB5: 58,
    0xB6: 59,
    0xCB: 60,
    0xB7: 61,
    0xB8: 62,
    0xB9: 63,
    0xBA: 64,
    0xBB: 65,
    0xD0: 66,
    0xBC: 67,
    0xBD: 68,
    0xD2: 69,
    0xBE: 70,
    0xC0: 71,
    0xC1: 72,
    0xC2: 73,
    0xC4: 74,
    0xC5: 75,
    0xC6: 76,
    0xC8: 77,
    0xC9: 78,
    0xCF: 79,
    0xCA: 80,
    0xDC: 81,
    0xDD: 82,
    0xDE: 83,
    0xDF: 84,
    0xE0: 85,
    0xE1: 86,
    0xCE: 87,
    0xE2: 88,
    0xE3: 89,
    0xE4: 90,
    0xE5: 91,
    0xE6: 92,
    0xE7: 93,
    0xE8: 94,
    0xE9: 95,
    0xEA: 96,
    0xEB: 97,
    0xEC: 98,
    0xED: 99,
    0xEE: 100,
    0xEF: 101,
    0xF0: 102,
    0xF1: 103,
    0xF2: 104,
    0xF3: 105,
    0xF4: 106,
    0xF5: 107,
    0xF6: 108,
    0xF7: 109,
    0xF8: 110,
    0xF9: 111,
    0xFA: 112,
    0xFB: 113,
    0xFC: 114,
    0xFD: 115,
    0xD4: 116,
    0x87: 117,
    0x88: 118,
    0x97: 119,
    0xBF: 120,
    0xC3: 121,
    0xC7: 122,
    0xD1: 123,
    0xD5: 124,
    0xD9: 125,
    0x00: 126,
    0x01: 127,
    0x02: 128,
    0x03: 129,
    0x04: 130,
    0x05: 131,
    0x06: 132,
    0x07: 133,
    0x08: 134,
    0x09: 135,
    0x0A: 136,
    0x0B: 137,
    0x0C: 138,
    0x0D: 139,
    0x0E: 140,
    0x0F: 141,
    0x10: 142,
    0x11: 143,
    0x12: 144,
    0x13: 145,
    0x14: 146,
    0x15: 147,
    0x16: 148,
    0x17: 149,
    0x18: 150,
    0x19: 151,
    0x1A: 152,
    0x1B: 153,
    0x1C: 154,
    0x1D: 155,
    0x1E: 156,
    0x1F: 157,
    0x20: 158,
    0x21: 159,
    0x22: 160,
    0x23: 161,
    0x24: 162,
    0x25: 163,
    0x26: 164,
    0x27: 165,
    0x28: 166,
    0x29: 167,
    0x2A: 168,
    0x2B: 169,
    0x2C: 170,
    0x2D: 171,
    0x2E: 172,
    0x2F: 173,
    0x30: 174,
    0x31: 175,
}

try:
    _HERE = Path(__file__).resolve().parent
    if str(_HERE) not in sys.path:
        sys.path.insert(0, str(_HERE))
    from opcodelist import OPERAND_MODES as _OM, RAW_U32_BEFORE as _RB, OPCODE_INDEX as _OI  # type: ignore
    OPERAND_MODES = _OM
    RAW_U32_BEFORE = _RB
    OPCODE_INDEX = _OI
except Exception:
    pass  # use embedded tables above


# ===================== PE =====================

def _u16(d: bytes, o: int) -> int:
    return struct.unpack_from("<H", d, o)[0]


def _u32(d: bytes, o: int) -> int:
    return struct.unpack_from("<I", d, o)[0]


def parse_pe(data: bytes) -> Tuple[int, List[dict]]:
    if data[:2] != b"MZ":
        raise ValueError("not PE (MZ)")
    e_lfanew = _u32(data, 0x3C)
    if data[e_lfanew : e_lfanew + 4] != b"PE\0\0":
        raise ValueError("not PE signature")
    coff = e_lfanew + 4
    nsec = _u16(data, coff + 2)
    opt_size = _u16(data, coff + 16)
    opt = coff + 20
    magic = _u16(data, opt)
    if magic == 0x10B:
        image_base = _u32(data, opt + 28)
    elif magic == 0x20B:
        image_base = struct.unpack_from("<Q", data, opt + 24)[0]
    else:
        raise ValueError(f"bad optional magic {magic:#x}")
    sec_off = opt + opt_size
    secs = []
    for i in range(nsec):
        o = sec_off + i * 40
        name = data[o : o + 8].split(b"\0", 1)[0].decode("latin1", errors="replace")
        secs.append(
            {
                "name": name,
                "vsize": _u32(data, o + 8),
                "va": _u32(data, o + 12),
                "raw_size": _u32(data, o + 16),
                "raw": _u32(data, o + 20),
            }
        )
    return int(image_base), secs


def va_to_off(va: int, image_base: int, secs: List[dict]) -> Optional[int]:
    rva = (va - image_base) & 0xFFFFFFFF
    for s in secs:
        span = max(s["vsize"], s["raw_size"], 1)
        if s["va"] <= rva < s["va"] + span:
            off = s["raw"] + (rva - s["va"])
            return off
    return None


def read_cstr(data: bytes, off: int, maxlen: int = 64) -> Optional[bytes]:
    if off < 0 or off >= len(data):
        return None
    end = data.find(b"\0", off, min(len(data), off + maxlen))
    if end < 0:
        return None
    s = data[off:end]
    if len(s) < 4 or len(s) > 48:
        return None
    if not all(0x20 <= b < 0x7F for b in s):
        return None
    return s


# ===================== 特征找密钥 =====================
#
# 目标函数形态 (sub_410C98):
#   mov ebx, dword ptr [imm32]     ; 8B 1D xx xx xx xx  -> imm32 是 *指向密钥串的指针*
#   mov bl,  [ebx+edx]             ; 8A 1C 13  (SIB: ebx+edx)
#   xor [eax], bl                  ; 32 18
#   cmp edx, keylen-1              ; 83 FA nn
#   mov [eax], bl                  ; 88 18
#   jnz ...
#   or  edx, -1                    ; 83 CA FF  (wrap index)
#
# 更宽松：允许 SIB 索引寄存器变化、cmp 操作数寄存器变化。

# 主特征: mov r32,[imm32] + mov r8,[base+index] + xor [reg],r8 + cmp index,imm8
_SIG_MAIN = re.compile(
    rb"\x8B\x1D(?P<ptr>.{4})"   # mov ebx, [ptr]
    rb"\x8A\x1C(?P<sib>.)"      # mov bl,  [ebx+?]
    rb"\x32\x18"                # xor [eax], bl
    rb"\x83\xFA(?P<last>.)"     # cmp edx, imm8  (key_len-1)
    rb"\x88\x18"                # mov [eax], bl
)

# 宽松特征: 不绑定 ebx/edx/eax，用通用 modrm
_SIG_LOOSE = re.compile(
    rb"\x8B[\x05\x0D\x15\x1D\x25\x2D\x35\x3D](?P<ptr>.{4})"  # mov r32, [imm32]
    rb".{0,8}?"
    rb"\x32[\x00-\x3F]"                                     # xor r/m8, r8
    rb".{0,6}?"
    rb"\x83[\xF8-\xFF](?P<last>.)"                          # cmp r32, imm8
)

# 回退: mov reg,[imm] 后紧跟 8A 1C ?? 32 ?? 83 FA
_SIG_ALT = re.compile(
    rb"\x8B\x1D(?P<ptr>.{4})\x8A\x1C.\x32.\x83\xFA(?P<last>.)"
)


def _resolve_key_from_ptr_va(
    data: bytes, image_base: int, secs: List[dict], ptr_va: int, last_idx: int
) -> Optional[Tuple[bytes, str]]:
    """ptr_va 是存放密钥串指针的地址（如 off_47C4FC）。"""
    p_off = va_to_off(ptr_va, image_base, secs)
    if p_off is None or p_off + 4 > len(data):
        return None
    str_va = _u32(data, p_off)
    s_off = va_to_off(str_va, image_base, secs)
    if s_off is None:
        return None
    # 用 cmp imm 作为长度提示: keylen = last_idx+1
    expect_len = (last_idx & 0xFF) + 1
    # 优先读定长（无 NUL 也可），再回退 cstring
    if 4 <= expect_len <= 48 and s_off + expect_len <= len(data):
        raw = data[s_off : s_off + expect_len]
        if all(0x20 <= b < 0x7F for b in raw):
            return raw, (
                f"sig: mov [ptr={ptr_va:#x}]->str_va={str_va:#x} "
                f"file={s_off:#x} len={expect_len} key={raw!r}"
            )
    s = read_cstr(data, s_off)
    if s is None:
        return None
    # 若 cstring 长度与 cmp 不一致，仍以可打印串为准，但标记
    note = ""
    if len(s) != expect_len:
        note = f" (cstr_len={len(s)} cmp_len={expect_len})"
    return s, (
        f"sig: mov [ptr={ptr_va:#x}]->str_va={str_va:#x} "
        f"file={s_off:#x}{note} key={s!r}"
    )


def extract_key_from_exe(exe_path: Path) -> Tuple[bytes, str]:
    """按代码特征提取密钥，禁止依赖固定文件偏移。"""
    data = exe_path.read_bytes()
    image_base, secs = parse_pe(data)

    # 1) 精确特征（本游戏实际编译结果）
    hits = list(_SIG_MAIN.finditer(data))
    if not hits:
        hits = list(_SIG_ALT.finditer(data))

    results = []
    for m in hits:
        ptr_va = struct.unpack_from("<I", m.group("ptr"))[0]
        last = m.group("last")[0]
        got = _resolve_key_from_ptr_va(data, image_base, secs, ptr_va, last)
        if got:
            results.append(got)

    if results:
        # 选最长可打印密钥（通常 15 字节 Powerd...）
        results.sort(key=lambda x: len(x[0]), reverse=True)
        return results[0]

    # 2) 宽松特征
    for m in _SIG_LOOSE.finditer(data):
        ptr_va = struct.unpack_from("<I", m.group("ptr"))[0]
        last = m.group("last")[0]
        # 过滤明显不在映像内的指针
        if not (image_base <= ptr_va < image_base + 0x200000):
            continue
        got = _resolve_key_from_ptr_va(data, image_base, secs, ptr_va, last)
        if got:
            return got[0], "loose-" + got[1]

    # 3) 最后手段：在数据区找“被代码以 8B 1D 引用、且 cmp 邻域有 0x0E/0x0B 的指针表”
    #    扫描 .text 里所有 mov ebx,[imm32]，imm 指向一个指针，指针指向可打印串，
    #    且后 16 字节内有 32 ?? 与 83 FA
    text_ranges = []
    for s in secs:
        if s["name"].startswith(".text") or s["name"] == "CODE":
            text_ranges.append((s["raw"], s["raw"] + s["raw_size"]))
    if not text_ranges:
        text_ranges = [(0, len(data))]

    scored: Dict[bytes, Tuple[int, str]] = {}
    for start, end in text_ranges:
        chunk = data[start:end]
        for m in re.finditer(rb"\x8B\x1D(?P<ptr>.{4})", chunk):
            win = chunk[m.start() : m.start() + 24]
            if b"\x32" not in win or b"\x83\xFA" not in win:
                continue
            # extract last imm after 83 FA
            j = win.find(b"\x83\xFA")
            if j < 0 or j + 3 > len(win):
                continue
            last = win[j + 2]
            ptr_va = struct.unpack_from("<I", m.group("ptr"))[0]
            got = _resolve_key_from_ptr_va(data, image_base, secs, ptr_va, last)
            if not got:
                continue
            key, why = got
            # score: prefer near 32 18 exact xor [eax],bl
            score = 10 + len(key)
            if b"\x32\x18" in win:
                score += 50
            if b"\x8A\x1C" in win:
                score += 20
            prev = scored.get(key)
            if prev is None or score > prev[0]:
                scored[key] = (score, f"scan-text@{start + m.start():#x} " + why)

    if scored:
        best = max(scored.items(), key=lambda kv: kv[1][0])
        return best[0], best[1][1]

    raise ValueError(
        "未能按 XOR 特征从 exe 提取密钥。"
        "期望形态: mov ebx,[ptr]; mov bl,[ebx+idx]; xor [dst],bl; cmp idx,len-1"
    )


# ===================== MEG 加解密 =====================

class WalkerError(Exception):
    pass


def xor_inplace(buf: bytearray, start: int, length: int, key: bytes) -> None:
    n = len(key)
    for i in range(length):
        buf[start + i] ^= key[i % n]


def walk_and_crypt(body: bytearray, key: bytes) -> int:
    pos = 0
    n = len(body)
    count = 0

    def need(k: int):
        if pos + k > n:
            raise WalkerError(f"EOF at {pos:#x}, need {k}")

    def u8() -> int:
        nonlocal pos
        need(1)
        b = body[pos]
        pos += 1
        return b

    def skip(k: int):
        nonlocal pos
        need(k)
        pos += k

    def walk_expr():
        nonlocal pos, count
        start = pos
        first = True
        while True:
            if pos >= n:
                raise WalkerError(f"unterminated expr @{start:#x}")
            b = u8()
            if b == 0x00:
                if first:
                    raise WalkerError(f"empty expr @{start:#x}")
                break
            first = False
            if b in EXPR_ATOM:
                kind = EXPR_ATOM[b]
                if kind == "u16":
                    skip(2)
                elif kind == "i32":
                    skip(4)
                elif kind == "b10":
                    skip(10)
                elif kind == "str":
                    need(2)
                    ln = struct.unpack_from("<H", body, pos)[0]
                    pos += 2
                    need(ln)
                    xor_inplace(body, pos, ln, key)
                    count += 1
                    pos += ln
            elif b in EXPR_OPS:
                continue
            else:
                raise WalkerError(f"bad expr token {b:#x} @{pos-1:#x}")

    while pos < n:
        op = u8()
        if op == 0xFF:
            continue
        if op == 0xFE:
            sub = u8()
            for _ in range(RAW_U32_BEFORE.get(sub, 0)):
                skip(4)
            for _ in OPERAND_MODES.get(sub, []):
                walk_expr()
            continue
        if op in (0x18, 0x19):
            skip(4)
            continue
        if op in (0x17, 0x20, 0x21):
            walk_expr()
            continue
        if OPERAND_MODES and (op in OPERAND_MODES or op in OPCODE_INDEX):
            for _ in range(RAW_U32_BEFORE.get(op, 0)):
                skip(4)
            for _ in OPERAND_MODES.get(op, []):
                walk_expr()
            continue
        pos -= 1
        walk_expr()
    return count


def script_body_limit(body: bytes) -> int:
    """Walkable VM region length inside MEG body.

    Ver ~300 packs append an 8-byte footer after the final RET (0xFF):
      00 | u32 | u8 | 0xBF | 0x01
    (often 3F BF 01; Story10 uses 3E BF 01). Ver 150 ends on 0xFF with no footer.
    """
    if (
        len(body) >= 9
        and body[-9] == 0xFF
        and body[-8] == 0x00
        and body[-2] == 0xBF
        and body[-1] == 0x01
    ):
        return len(body) - 8
    return len(body)


def process_meg(data: bytes, key: bytes) -> Tuple[bytes, int]:
    if len(data) < HEADER_SIZE or data[:3] != MAGIC:
        raise WalkerError("not a MEG file")
    body = bytearray(data[HEADER_SIZE:])
    lim = script_body_limit(body)
    core = bytearray(body[:lim])
    cnt = walk_and_crypt(core, key)
    body[:lim] = core
    return data[:HEADER_SIZE] + bytes(body), cnt


def iter_megs(path: Path) -> List[Path]:
    if path.is_file():
        return [path]
    files = sorted(path.glob("*.MEG")) + sorted(path.glob("*.meg"))
    seen, out = set(), []
    for f in files:
        k = f.name.lower()
        if k not in seen:
            seen.add(k)
            out.append(f)
    return out


def find_default_meg_dir(exe: Path) -> Path:
    for c in (exe.parent / "meg", Path("meg"), exe.parent):
        if c.is_dir() and (list(c.glob("*.MEG")) or list(c.glob("*.meg"))):
            return c
    raise FileNotFoundError("找不到 meg 目录，请指定输入路径")


def batch(exe: Path, src: Path, dst: Path, mode_name: str) -> int:
    key, why = extract_key_from_exe(exe)
    print(f"[key] {key!r}")
    print(f"[how] {why}")
    files = iter_megs(src)
    if not files:
        print(f"无 MEG: {src}", file=sys.stderr)
        return 1
    multi = src.is_dir() or len(files) > 1
    if multi:
        dst.mkdir(parents=True, exist_ok=True)
    rc = 0
    for f in files:
        try:
            new, cnt = process_meg(f.read_bytes(), key)
            target = (dst / f.name) if multi else dst
            if not multi:
                target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(new)
            print(f"OK {mode_name} {f.name} -> {target}  strings={cnt}")
        except Exception as e:
            print(f"FAIL {f.name}: {e}", file=sys.stderr)
            rc = 1
    return rc


def main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(__doc__)
        return 0

    # python 1.py key <exe>
    if argv[0] == "key":
        if len(argv) != 2:
            print("usage: python 1.py key <exe>", file=sys.stderr)
            return 2
        key, why = extract_key_from_exe(Path(argv[1]))
        print(key.decode("latin1", errors="replace"))
        print(f"# {why}", file=sys.stderr)
        print(f"# hex: {key.hex()}", file=sys.stderr)
        return 0

    # python 1.py dump <exe> <meg|dir> <out>
    if argv[0] == "dump":
        if len(argv) != 4:
            print("usage: python 1.py dump <exe> <meg> <out>", file=sys.stderr)
            return 2
        return batch(Path(argv[1]), Path(argv[2]), Path(argv[3]), "dump")

    # python 1.py import <exe> <new> <out>
    if argv[0] == "import":
        if len(argv) != 4:
            print("usage: python 1.py import <exe> <new> <out>", file=sys.stderr)
            return 2
        return batch(Path(argv[1]), Path(argv[2]), Path(argv[3]), "import")

    # python 1.py <exe> <new> <out>
    if len(argv) == 3 and Path(argv[0]).suffix.lower() == ".exe":
        return batch(Path(argv[0]), Path(argv[1]), Path(argv[2]), "import")

    print(__doc__)
    print("????:", argv, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
