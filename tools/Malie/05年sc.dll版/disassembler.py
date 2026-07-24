# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import sys

# MUST run before importing dataclasses/inspect/dis: local opcode.py shadows stdlib.
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
while _SCRIPT_DIR in sys.path:
    sys.path.remove(_SCRIPT_DIR)
_sys_path_clean = []
for _p in sys.path:
    if _p in ("", ".") and os.path.abspath(os.getcwd()) == _SCRIPT_DIR:
        continue
    _sys_path_clean.append(_p)
sys.path[:] = _sys_path_clean
import struct
import argparse
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field


def _load_opcode():
    import importlib.util
    path = os.path.join(_SCRIPT_DIR, "opcode.py")
    name = "popotan_vm_opcode"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    if _SCRIPT_DIR not in sys.path:
        sys.path.append(_SCRIPT_DIR)
    return mod


_opcode = _load_opcode()
EXPR_T = _opcode.EXPR_T
EXPR_U = _opcode.EXPR_U
EXPR_V = _opcode.EXPR_V
EXPR_W = _opcode.EXPR_W
EXPR_X = getattr(_opcode, "EXPR_X", 0x58)
expr_kind_name = _opcode.expr_kind_name
op_info = _opcode.op_info
type_kind_name = _opcode.type_kind_name
OP_TEXT = _opcode.OP_TEXT
OP_EVAL = _opcode.OP_EVAL
OP_JMP = _opcode.OP_JMP
OP_JZ = _opcode.OP_JZ
OP_JNZ = _opcode.OP_JNZ
OP_CALL = _opcode.OP_CALL
OP_MESSAGEOUT = _opcode.OP_MESSAGEOUT
OP_RET = _opcode.OP_RET
OP_PAGE = _opcode.OP_PAGE
OP_CLEAR = _opcode.OP_CLEAR
OP_ENDTEXT = _opcode.OP_ENDTEXT
OP_SYNC = _opcode.OP_SYNC
# Legacy aliases (older tools / soft-text helpers)
OP_TEXT_A = getattr(_opcode, "OP_TEXT_A", -1)
OP_TEXT_B = getattr(_opcode, "OP_TEXT_B", -1)
OP_STR = getattr(_opcode, "OP_STR", -1)
OP_ARG = getattr(_opcode, "OP_ARG", -1)
OP_NUM_A = getattr(_opcode, "OP_NUM_A", -1)
OP_NUM_B = getattr(_opcode, "OP_NUM_B", -1)
OP_NUM_C = getattr(_opcode, "OP_NUM_C", -1)
OP_FSTORE_IMM = getattr(_opcode, "OP_FSTORE_IMM", -1)
EFFECT_LABELS = getattr(_opcode, "EFFECT_LABELS", set())
MARKER_NAME1 = _opcode.MARKER_NAME1
MARKER_NAME2 = _opcode.MARKER_NAME2
MARKER_NAME_INSERT = getattr(_opcode, "MARKER_NAME_INSERT", bytes([0x07, 0x0C]))
MARKER_VOICE = _opcode.MARKER_VOICE
MARKER_RUBY = _opcode.MARKER_RUBY
MARKER_STYLE = _opcode.MARKER_STYLE
MARKER_NEWLINE = _opcode.MARKER_NEWLINE
MARKER_KWAIT = _opcode.MARKER_KWAIT
MARKER_COLOR = _opcode.MARKER_COLOR
MARKER_COLOR_END = _opcode.MARKER_COLOR_END
MARKER_FONT = _opcode.MARKER_FONT
MARKER_FONT_END = _opcode.MARKER_FONT_END
MARKER_SPECIAL = _opcode.MARKER_SPECIAL
RUBY_SEP = _opcode.RUBY_SEP
TAIL_PLAIN = _opcode.TAIL_PLAIN
TAIL_VOICED = _opcode.TAIL_VOICED
TAIL_WAIT = _opcode.TAIL_WAIT
TOKEN_WAIT = _opcode.TOKEN_WAIT
TOKEN_NEWLINE = _opcode.TOKEN_NEWLINE
TOKEN_KWAIT = _opcode.TOKEN_KWAIT
TOKEN_COLOR_END = _opcode.TOKEN_COLOR_END
TOKEN_FONT_END = _opcode.TOKEN_FONT_END
speaker_from_voice = _opcode.speaker_from_voice

DEFAULT_ENCODING = "cp932"


class Reader:
    def __init__(self, data: bytes):
        self.data = data
        self.pos = 0

    def remaining(self) -> int:
        return len(self.data) - self.pos

    def u8(self) -> int:
        v = self.data[self.pos]
        self.pos += 1
        return v

    def u16(self) -> int:
        v = struct.unpack_from("<H", self.data, self.pos)[0]
        self.pos += 2
        return v

    def u32(self) -> int:
        v = struct.unpack_from("<I", self.data, self.pos)[0]
        self.pos += 4
        return v

    def bytes_(self, n: int) -> bytes:
        b = self.data[self.pos : self.pos + n]
        self.pos += n
        return b

    def cstring_bytes(self) -> bytes:
        # length-prefixed (includes trailing NUL in payload)
        n = self.u32()
        return self.bytes_(n)

    def zstring_bytes(self) -> bytes:
        # raw C-string including trailing NUL
        start = self.pos
        end = self.data.find(b"\x00", start)
        if end < 0:
            raise ValueError("unterminated cstring at %d" % start)
        self.pos = end + 1
        return self.data[start : end + 1]


def _normalize_encoding(encoding: str) -> str:
    enc = (encoding or "").lower().replace("-", "_")
    if enc in ("shift_jis", "shiftjis", "sjis", "ms932", "windows_31j"):
        return "cp932"
    return encoding


def decode_payload(data: bytes, encoding: str) -> str:
    """Decode payload bytes to semantic text.

    Uses cp932 for Japanese game scripts. Undecodable / control bytes become {{XX}}.
    Double-quote is escaped as "" for asm string literals.
    Prefer decode_semantic_text() for dialogue pool entries (maps mid-text controls).
    """
    encoding = _normalize_encoding(encoding)
    out: List[str] = []
    i = 0
    is_sjis = _normalize_encoding(encoding) == "cp932"
    while i < len(data):
        b = data[i]
        if is_sjis and ((0x81 <= b <= 0x9F) or (0xE0 <= b <= 0xFC)):
            if i + 1 < len(data):
                pair = data[i : i + 2]
                try:
                    ch = pair.decode(encoding, errors="strict")
                    if ch == "{":
                        out.append("{{7B}}")
                    elif ch == "}":
                        out.append("{{7D}}")
                    else:
                        out.append(ch)
                    i += 2
                    continue
                except UnicodeDecodeError:
                    pass
            out.append("{{%02X}}" % b)
            i += 1
            continue
        if b in (0x09, 0x0A, 0x0D):
            out.append("{{%02X}}" % b)
            i += 1
            continue
        if 0x20 <= b <= 0x7E:
            ch = chr(b)
            if ch == '"':
                out.append('""')
            elif ch == "{":
                out.append("{{7B}}")
            elif ch == "}":
                out.append("{{7D}}")
            else:
                out.append(ch)
            i += 1
            continue
        if b < 0x20 or b == 0x7F:
            out.append("{{%02X}}" % b)
            i += 1
            continue
        try:
            ch = bytes([b]).decode(encoding, errors="strict")
            out.append(ch)
        except UnicodeDecodeError:
            out.append("{{%02X}}" % b)
        i += 1
    return "".join(out)


def decode_bytes(raw: bytes, encoding: str) -> str:
    data = raw[:-1] if raw.endswith(b"\x00") else raw
    return decode_payload(data, encoding)


def _escape_asm_text(s: str) -> str:
    return s.replace('"', '""')



def _is_sjis_lead(b: int) -> bool:
    return (0x81 <= b <= 0x9F) or (0xE0 <= b <= 0xFC)


def _scan_ruby_field(data: bytes, start: int, stop_at_sep: bool) -> int:
    """Scan ruby base/reading field; may embed color/font controls with NULs.

    stop_at_sep: if True, stop before 0x0A (base field). Always stops before
    bare entry-terminator style 0x00 that ends the ruby (after reading field).
    Color 01 RR GG BB may include 00 as BB; that is not field end.
    """
    n = len(data)
    i = start
    while i < n:
        b = data[i]
        if stop_at_sep and b == RUBY_SEP:
            return i
        if b == 0:
            return i
        if b == MARKER_COLOR:
            if i + 4 > n:
                return n
            i += 4
            continue
        if b == MARKER_COLOR_END:
            i += 1
            continue
        if b == MARKER_FONT:
            if i + 2 > n:
                return n
            i += 2
            continue
        if b == MARKER_FONT_END:
            i += 1
            continue
        if b == 0x07 and i + 1 < n:
            # nested controls inside ruby are rare; treat 07 xx as 2-byte
            sub = data[i + 1]
            i += 2
            if sub == 0x0C and i < n:
                i += 1
            elif sub == 0x02 and i < n:
                i += 1
            continue
        if _is_sjis_lead(b) and i + 1 < n:
            i += 2
            continue
        i += 1
    return i



def pool_string_end(pool: bytes, start: int) -> int:
    """Return exclusive end offset of one pool C-string starting at start.

    Respects mid-text control sequences that embed 0x00 (color 01..00, ruby 07 01,
    mid-line voice 07 08). Based on Waitress.exe sub_4361B0 text scanner.
    """
    n = len(pool)
    i = start
    while i < n:
        b = pool[i]
        if b == 0:
            return i
        if b == MARKER_COLOR:
            # 01 RR GG BB  (BB may be 0x00)
            if i + 4 > n:
                return n
            i += 4
            continue
        if b == MARKER_COLOR_END:
            i += 1
            continue
        if b == MARKER_FONT:
            if i + 2 > n:
                return n
            i += 2
            continue
        if b == MARKER_FONT_END:
            i += 1
            continue
        if b == MARKER_SPECIAL:
            # lone 0x06 wait (multi-chunk) OR 0x06 XX special glyph
            if i + 1 >= n:
                return i + 1
            # If this is the final byte before entry NUL, treat as wait terminator body byte.
            # Special glyph always has a following payload byte that is not a string terminator.
            # Heuristic: if next is 0x00, this 06 is part of content ending... but 06 00 is rare
            # special; multi-chunk wait is "....06" then entry NUL. Scanner should stop at NUL
            # after consuming 06 as plain if it is last content byte.
            # Engine path: n2==6 consumes 2 bytes as special. Multi-chunk wait uses 0x06 as
            # last body byte then separate pool entry boundary (NUL). So 06 at end-1 before
            # NUL is TAIL_WAIT, still part of this entry body; consume 1 only when next is 0.
            if pool[i + 1] == 0:
                i += 1
                continue
            i += 2
            continue
        if b == 0x07:
            if i + 1 >= n:
                return n
            sub = pool[i + 1]
            i += 2
            if sub == 0x01:
                # ruby: base... 0A reading... 00  (base/reading may embed color NULs)
                i = _scan_ruby_field(pool, i, stop_at_sep=True)
                if i < n and pool[i] == RUBY_SEP:
                    i += 1
                i = _scan_ruby_field(pool, i, stop_at_sep=False)
                if i < n and pool[i] == 0:
                    i += 1  # embedded ruby terminator, NOT pool entry end
                continue
            if sub == 0x02:
                if i < n:
                    i += 1
                continue
            if sub in (0x03, 0x04, 0x06, 0x09):
                continue
            if sub == 0x05:
                if i + 2 > n:
                    return n
                skip = pool[i] | (pool[i + 1] << 8)
                i += 2 + skip
                continue
            if sub == 0x07:
                # skip nested stream then a C-string
                # nested scanner is complex; consume until double-NUL-ish: next C-string
                # Practical: skip bytes until 0 then +1 (string), used rarely in pool.
                while i < n and pool[i] != 0:
                    i += 1
                if i < n:
                    i += 1
                while i < n and pool[i] != 0:
                    i += 1
                if i < n:
                    i += 1
                continue
            if sub == 0x08:
                # Voice id: 07 08 "v_xxx" 00
                # - whole entry (starts at 07 08): NUL ends the pool entry
                # - mid-text $E voice (MLS $E(v_xxx)): NUL is field end, continue
                voice_cmd_at = i - 2
                while i < n and pool[i] != 0:
                    i += 1
                if voice_cmd_at == start:
                    return i
                if i < n and pool[i] == 0:
                    i += 1
                continue
            if sub == 0x0C:
                if i < n:
                    i += 1
                continue
            # unknown 07 xx: no extra payload
            continue
        if b == 0x0A:
            # hard line break byte (rare as lone control in pool)
            i += 1
            continue
        if _is_sjis_lead(b):
            if i + 1 < n:
                i += 2
            else:
                i += 1
            continue
        i += 1
    return n


def pool_get_zstring(pool: bytes, off: int) -> bytes:
    if off < 0 or off >= len(pool):
        raise ValueError("string pool offset out of range: %d" % off)
    end = pool_string_end(pool, off)
    if end < off:
        raise ValueError("bad pool string at %d" % off)
    if end < len(pool) and pool[end] == 0:
        return pool[off : end + 1]
    return pool[off:end]


def decode_semantic_text(data: bytes, encoding: str) -> str:
    """Map pool dialogue body bytes to readable source tokens.

    Control mapping (IDA sub_4361B0):
      01 RR GG BB -> $c{RRGGBB}
      02          -> $c
      03 NN       -> $f{NN}
      04          -> $f
      07 01 ...   -> $r{base|reading}
      07 02 NN    -> $s{NN}
      07 04       -> $e
      07 06       -> $k   (only when mid-body; end tails stripped before call)
      07 0C NN    -> $N (runtime insert slot 0-255)
      06 (chunk)  -> handled as multi-entry %haato outside this function
    """
    encoding = _normalize_encoding(encoding)
    out: List[str] = []
    i = 0
    n = len(data)
    plain = bytearray()

    def flush_plain() -> None:
        nonlocal plain
        if plain:
            out.append(_escape_asm_text(decode_payload(bytes(plain), encoding)))
            plain = bytearray()

    while i < n:
        b = data[i]
        if b == MARKER_COLOR and i + 4 <= n:
            flush_plain()
            rr, gg, bb = data[i + 1], data[i + 2], data[i + 3]
            out.append("$c{%02X%02X%02X}" % (rr, gg, bb))
            i += 4
            continue
        if b == MARKER_COLOR_END:
            flush_plain()
            out.append(TOKEN_COLOR_END)
            i += 1
            continue
        if b == MARKER_FONT and i + 2 <= n:
            flush_plain()
            out.append("$f{%d}" % data[i + 1])
            i += 2
            continue
        if b == MARKER_FONT_END:
            flush_plain()
            out.append(TOKEN_FONT_END)
            i += 1
            continue
        if b == 0x07 and i + 1 < n:
            sub = data[i + 1]
            if sub == 0x01:
                # ruby: base may itself contain color/font controls
                j = _scan_ruby_field(data, i + 2, stop_at_sep=True)
                base = data[i + 2 : j]
                reading = b""
                if j < n and data[j] == RUBY_SEP:
                    k = _scan_ruby_field(data, j + 1, stop_at_sep=False)
                    reading = data[j + 1 : k]
                    j = k
                if j < n and data[j] == 0:
                    j += 1
                flush_plain()
                base_s = decode_semantic_text(base, encoding)
                read_s = decode_semantic_text(reading, encoding)
                out.append("$r{%s|%s}" % (base_s, read_s))
                i = j
                continue
            if sub == 0x02 and i + 2 < n:
                flush_plain()
                out.append("$s{%d}" % data[i + 2])
                i += 3
                continue
            if sub == 0x04:
                flush_plain()
                out.append(TOKEN_NEWLINE)
                i += 2
                continue
            if sub == 0x06:
                flush_plain()
                out.append(TOKEN_KWAIT)
                i += 2
                continue
            if sub == 0x0C and i + 2 < n:
                # Runtime insert slot: 07 0C NN -> $N
                # $1/$2 player names; SLG battle scripts also use $3+ (item/skill/etc).
                flush_plain()
                out.append("$%d" % data[i + 2])
                i += 3
                continue
            if sub == 0x08:
                # mid-text voice switch (MLS $E(v_xxx))
                j = i + 2
                while j < n and data[j] != 0:
                    j += 1
                vid = data[i + 2 : j].decode("ascii", errors="replace")
                if j < n and data[j] == 0:
                    j += 1
                flush_plain()
                out.append("$v{%s}" % vid)
                i = j
                continue
            if sub == 0x09:
                flush_plain()
                out.append("$E")
                i += 2
                continue
            # unknown 07 xx
            flush_plain()
            out.append("{{07}}{{%02X}}" % sub)
            i += 2
            continue
        if b == MARKER_SPECIAL:
            # 0x06 as multi-chunk wait is stripped as tail; mid 06 XX rare glyph
            if i + 1 < n and data[i + 1] != 0:
                flush_plain()
                out.append("{{06}}{{%02X}}" % data[i + 1])
                i += 2
                continue
            flush_plain()
            out.append(TOKEN_WAIT)
            i += 1
            continue
        # ordinary byte / SJIS lead kept in plain buffer
        plain.append(b)
        i += 1
    flush_plain()
    return "".join(out)


# sc.dll MALIE_NAME setter (eval blob):
#   push malie(1080); load; push 100; push 0x48; add; push0; push_estr <name>; call; ...; ret
# Voice-play setter is the same shape with 0x2A instead of 0x48 (handled separately).
NAME_SETTER_PREFIX = bytes.fromhex("0e3804000007126412481410")
NAME_SETTER_SUFFIX = bytes.fromhex("04230406")
VOICE_SETTER_PREFIX = bytes.fromhex("0e38040000071264122a1410")


def _parse_estr_push(mid: bytes) -> Optional[int]:
    """Decode push_estr operand: 0A u8 | 0B u16 | 0D u32."""
    if not mid:
        return None
    op = mid[0]
    if op == 0x0A and len(mid) == 2:
        return mid[1]
    if op == 0x0B and len(mid) == 3:
        return struct.unpack_from("<H", mid, 1)[0]
    if op == 0x0D and len(mid) == 5:
        return struct.unpack_from("<I", mid, 1)[0]
    return None


def _encode_estr_push(off: int) -> bytes:
    if off < 0:
        raise ValueError("estr offset negative")
    if off <= 0xFF:
        return bytes([0x0A, off & 0xFF])
    if off <= 0xFFFF:
        return bytes([0x0B]) + struct.pack("<H", off & 0xFFFF)
    return bytes([0x0D]) + struct.pack("<I", off & 0xFFFFFFFF)


def is_name_setter_blob(blob: bytes) -> bool:
    if not blob or not blob.startswith(NAME_SETTER_PREFIX):
        return False
    if not blob.endswith(NAME_SETTER_SUFFIX):
        return False
    mid = blob[len(NAME_SETTER_PREFIX) : -len(NAME_SETTER_SUFFIX)]
    return _parse_estr_push(mid) is not None


def is_voice_setter_blob(blob: bytes) -> bool:
    if not blob or not blob.startswith(VOICE_SETTER_PREFIX):
        return False
    if not blob.endswith(NAME_SETTER_SUFFIX):
        return False
    mid = blob[len(VOICE_SETTER_PREFIX) : -len(NAME_SETTER_SUFFIX)]
    return _parse_estr_push(mid) is not None


def _estr_c_string(estr_pool: bytes, off: int, encoding: str) -> str:
    if off < 0 or off >= len(estr_pool):
        return ""
    end = estr_pool.find(b"\x00", off)
    if end < 0:
        end = len(estr_pool)
    payload = estr_pool[off:end]
    enc = _normalize_encoding(encoding or "cp932")
    try:
        return payload.decode(enc)
    except Exception:
        try:
            return payload.decode(enc, errors="replace")
        except Exception:
            return "".join("{{%02X}}" % b for b in payload)


def extract_name_from_setter(
    blob: bytes,
    encoding: str,
    estr_pool: Optional[bytes] = None,
) -> Optional[str]:
    """Return speaker name from MALIE_NAME eval blob (looks up estr pool)."""
    if not is_name_setter_blob(blob):
        return None
    if estr_pool is None:
        return None
    mid = blob[len(NAME_SETTER_PREFIX) : -len(NAME_SETTER_SUFFIX)]
    off = _parse_estr_push(mid)
    if off is None:
        return None
    return _estr_c_string(estr_pool, off, encoding)


def extract_voice_from_setter(
    blob: bytes,
    encoding: str,
    estr_pool: Optional[bytes] = None,
) -> Optional[str]:
    """Return voice id from MALIE _voice() eval blob (estr pool)."""
    if not is_voice_setter_blob(blob):
        return None
    if estr_pool is None:
        return None
    mid = blob[len(VOICE_SETTER_PREFIX) : -len(NAME_SETTER_SUFFIX)]
    off = _parse_estr_push(mid)
    if off is None:
        return None
    return _estr_c_string(estr_pool, off, encoding)



def _setter_push_meta(blob: bytes, prefix: bytes) -> Optional[Tuple[int, int]]:
    """Return (estr_off, push_width_bytes) for a name/voice setter blob."""
    if not blob or not blob.startswith(prefix) or not blob.endswith(NAME_SETTER_SUFFIX):
        return None
    mid = blob[len(prefix) : -len(NAME_SETTER_SUFFIX)]
    off = _parse_estr_push(mid)
    if off is None:
        return None
    width = {0x0A: 1, 0x0B: 2, 0x0D: 4}.get(mid[0])
    if width is None:
        return None
    return off, width



def analyze_pool_entry(raw: bytes, encoding: str) -> dict:
    """Classify one NUL-stripped pool entry into semantic form.

    Returns keys:
      kind: 'voice' | 'text'
      voice_id: str
      text: semantic text (no line-tails; $N/$e/$c/... restored)
      tail: 'plain' | 'voiced' | 'none' | 'custom'
      tail_hex: exact stripped tail bytes as hex (for zero-mutation)
      name: speaker name guess for voice entries
    """
    if raw.startswith(MARKER_VOICE):
        vid = raw[len(MARKER_VOICE):].decode("ascii", errors="replace")
        return {
            "kind": "voice",
            "voice_id": vid,
            "text": "",
            "tail": "none",
            "tail_hex": "",
            "name": speaker_from_voice(vid),
        }

    body = raw
    tail_raw = bytearray()
    # Strip known line terminators from the end (may be repeated / lone 0x06).
    while body:
        if body.endswith(TAIL_VOICED):
            n = len(TAIL_VOICED)
            tail_raw[0:0] = body[-n:]
            body = body[:-n]
            continue
        if body.endswith(TAIL_PLAIN):
            n = len(TAIL_PLAIN)
            tail_raw[0:0] = body[-n:]
            body = body[:-n]
            continue
        if body.endswith(bytes([6])):
            # lone 0x06 wait only if not special-glyph 06 XX already consumed
            tail_raw[0:0] = body[-1:]
            body = body[:-1]
            continue
        break

    text = decode_semantic_text(body, encoding)
    th = bytes(tail_raw).hex()
    if th == TAIL_VOICED.hex():
        tail = "voiced"
    elif th == TAIL_PLAIN.hex():
        tail = "plain"
    elif th == "":
        tail = "none"
    else:
        tail = "custom"
    return {
        "kind": "text",
        "voice_id": "",
        "text": text,
        "tail": tail,
        "tail_hex": th,
        "name": "",
    }


def build_pool_index(pool: bytes) -> Dict[int, Tuple[bytes, Optional[int]]]:
    """Map pool offset -> (raw_without_nul, next_entry_offset|None).

    Uses control-aware string ends so embedded NULs in color/ruby do not split entries.
    """
    idx: Dict[int, Tuple[bytes, Optional[int]]] = {}
    offs: List[int] = []
    off = 0
    n = len(pool)
    while off < n:
        end = pool_string_end(pool, off)
        offs.append(off)
        if end >= n:
            idx[off] = (pool[off:], None)
            break
        idx[off] = (pool[off:end], None)
        off = end + 1
    for i, o in enumerate(offs):
        raw, _ = idx[o]
        nxt = offs[i + 1] if i + 1 < len(offs) else None
        idx[o] = (raw, nxt)
    return idx


def _ends_with_wait_only(raw: bytes) -> bool:
    """True if entry ends with lone 0x06 wait (not 07 06 / 07 09 07 06)."""
    return raw.endswith(TAIL_WAIT) and not raw.endswith(TAIL_PLAIN) and not raw.endswith(TAIL_VOICED)


def collect_text_chain(
    pool_index: Dict[int, Tuple[bytes, Optional[int]]],
    start_off: int,
    encoding: str,
    referenced: Optional[set] = None,
) -> List[Tuple[int, bytes, dict]]:
    """Collect multi-chunk dialogue starting at start_off.

    Pattern (common for long voiced lines / some hard lines):
      chunk0 ... 0x06 [NUL]
      chunk1 ... 0x06 [NUL]
      final  ... (plain/voiced tail, often just 「」)
    Intermediate chunks are almost never OP_TEXT-referenced; they are auto-shown.
    """
    if start_off not in pool_index:
        return []
    raw0, nxt = pool_index[start_off]
    if raw0.startswith(MARKER_VOICE):
        return []
    info0 = analyze_pool_entry(raw0, encoding)
    if info0.get("kind") != "text":
        return []

    chain: List[Tuple[int, bytes, dict]] = [(start_off, raw0, info0)]
    # Only extend if first chunk is a wait-boundary chunk.
    if not _ends_with_wait_only(raw0):
        return chain

    off = nxt
    while off is not None and off in pool_index:
        raw, nxt2 = pool_index[off]
        if raw.startswith(MARKER_VOICE):
            break
        # do not swallow another hard OP_TEXT head
        if referenced is not None and off in referenced and off != start_off:
            break
        info = analyze_pool_entry(raw, encoding)
        if info.get("kind") != "text":
            break
        chain.append((off, raw, info))
        if _ends_with_wait_only(raw):
            off = nxt2
            continue
        # final non-wait chunk
        break
    return chain


def merge_chain_text(chain: List[Tuple[int, bytes, dict]]) -> str:
    """Join chain chunk bodies with %haato for wait boundaries."""
    if not chain:
        return ""
    parts: List[str] = []
    for i, (_off, raw, info) in enumerate(chain):
        parts.append(info.get("text", "") or "")
        if i < len(chain) - 1:
            parts.append(TOKEN_WAIT)
        elif _ends_with_wait_only(raw):
            # chain ended without a non-wait final; keep trailing wait visible
            parts.append(TOKEN_WAIT)
    return "".join(parts)


def paired_dialogue_for_voice(
    pool_index: Dict[int, Tuple[bytes, Optional[int]]],
    voice_off: int,
    encoding: str,
    referenced: Optional[set] = None,
) -> Optional[Tuple[int, dict, List[int]]]:
    """For a voice pool entry, return (first_text_off, merged_info, chain_offs)."""
    if voice_off not in pool_index:
        return None
    raw, nxt = pool_index[voice_off]
    if not raw.startswith(MARKER_VOICE) or nxt is None:
        return None
    nraw, _ = pool_index[nxt]
    if nraw.startswith(MARKER_VOICE):
        return None
    chain = collect_text_chain(pool_index, nxt, encoding, referenced)
    if not chain:
        return None
    first_off, first_raw, first_info = chain[0]
    merged = dict(first_info)
    merged["text"] = merge_chain_text(chain)
    # final tail wins for display classification
    merged["tail"] = chain[-1][2].get("tail", first_info.get("tail"))
    merged["tail_hex"] = chain[-1][2].get("tail_hex", first_info.get("tail_hex"))
    chain_offs = [o for o, _, _ in chain]
    return first_off, merged, chain_offs


def format_pool_directive(off: int, raw: bytes, encoding: str) -> str:
    """Reference-only pool entry (no editable body). Bodies live in code `text`."""
    info = analyze_pool_entry(raw, encoding)
    if info["kind"] == "voice":
        return '.pool %d, voice "%s"' % (off, info["voice_id"])
    if info["tail"] in ("plain", "voiced"):
        return '.pool %d, text, tail=%s' % (off, info["tail"])
    if info.get("tail_hex"):
        return '.pool %d, text, tail_hex=%s' % (off, info["tail_hex"])
    return '.pool %d, text' % off


def format_text_opcode_lines(
    off: int,
    raw: bytes,
    encoding: str,
    pool_index: Optional[Dict[int, Tuple[bytes, Optional[int]]]] = None,
    referenced: Optional[set] = None,
    consumed_chain_offs: Optional[set] = None,
) -> list:
    """Emit code-side lines for OP_TEXT / paired dialogue.

    hard text  -> emits OP_TEXT on assemble
    soft text  -> updates pool body only (auto-paired voiced dialogue / unreferenced entries)
    Multi-chunk lines (split by 0x06 wait) are merged with %haato.
    """
    info = analyze_pool_entry(raw, encoding)
    lines = []
    if info["kind"] == "voice":
        # Real speaker name comes from preceding name-setter eval, not voice id.
        lines.append('    voice %d, "%s"' % (off, info["voice_id"]))
        if pool_index is not None:
            pair = paired_dialogue_for_voice(pool_index, off, encoding, referenced)
            if pair is not None:
                poff, pinfo, chain_offs = pair
                if referenced is None or poff not in referenced:
                    body = (pinfo.get("text", "") or "").replace('\\', '\\\\').replace('"', '\\"')
                    # fix escaping below in post
                    lines.append('    text %d, "%s", soft' % (poff, pinfo.get("text", "")))
                    if consumed_chain_offs is not None:
                        consumed_chain_offs.update(chain_offs)
        return lines
    # hard text: merge multi-chunk chain if present
    if pool_index is not None and _ends_with_wait_only(raw):
        chain = collect_text_chain(pool_index, off, encoding, referenced)
        if len(chain) > 1:
            merged = merge_chain_text(chain)
            lines.append('    text %d, "%s"' % (off, merged))
            if consumed_chain_offs is not None:
                consumed_chain_offs.update(o for o, _, _ in chain)
            return lines
    lines.append('    text %d, "%s"' % (off, info["text"]))
    return lines



@dataclass
class TypeNode:
    kind: int
    value: int = 0
    next: Optional["TypeNode"] = None


@dataclass
class GlobalVar:
    name: str
    typ: Optional[TypeNode]
    flags: int
    reserved: int
    offset: int


@dataclass
class Label:
    name: str
    offset: int
    index: int


@dataclass
class ExprNode:
    kind: int
    text: Optional[str] = None
    value: Optional[int] = None
    left: Optional["ExprNode"] = None
    right: Optional["ExprNode"] = None


@dataclass
class Instr:
    pc: int
    opcode: int
    mnemonic: str
    operand_kind: str
    imm: Optional[int] = None
    text: Optional[str] = None
    label_name: Optional[str] = None
    expr_index: Optional[int] = None
    raw: Optional[bytes] = None  # eval blob / raw operand bytes


@dataclass
class Script:
    globals: List[GlobalVar] = field(default_factory=list)
    data_size: int = 0
    linked_funcs: List[str] = field(default_factory=list)
    labels: List[Label] = field(default_factory=list)
    exprs: List[ExprNode] = field(default_factory=list)
    code: bytes = b""
    string_pool: bytes = b""  # msg pool (OP_TEXT targets)
    estr_pool: bytes = b""    # expression string pool (eval push_estr*)
    instrs: List[Instr] = field(default_factory=list)
    encoding: str = DEFAULT_ENCODING


def parse_type(r: Reader) -> Optional[TypeNode]:
    kind = r.u32()
    if kind == 0:
        return None
    value = r.u32()
    return TypeNode(kind, value, parse_type(r))


def parse_expr(r: Reader, encoding: str) -> ExprNode:
    """ExpressionTree_CreateFromFILE (sc.dll): kind is a single byte.

    U (0x55): empty/null node
    V (0x56) / X (0x58): LenString
    W (0x57): u32 int
    other: binary node with left/right recursively
    """
    kind = r.u8()
    if kind == EXPR_U:  # 'U'
        return ExprNode(kind)
    if kind in (EXPR_V, EXPR_X):  # 'V'/'X' string
        raw = r.cstring_bytes()
        return ExprNode(kind, text=decode_bytes(raw, encoding))
    if kind == EXPR_W:  # 'W' int
        return ExprNode(kind, value=r.u32())
    left = parse_expr(r, encoding)
    right = parse_expr(r, encoding)
    return ExprNode(kind, left=left, right=right)


def parse_exec(data: bytes, encoding: str) -> Script:
    """Parse sc.dll ScenarioProcessor_LoadExecImage / SaveExecImage layout.

    IdentScope (globals + data_size)
    u32 linked_func_count; LenString[linked_func_count]
    u32 label_count; Label[label_count]  (name + code_offset)
    u32 expr_count; ExpressionTree[expr_count]  (byte-kind AST)
    u32 code_size; code[code_size]
    u32 msg_size;  msg[msg_size]     # OP_TEXT string pool
    u32 estr_size; estr[estr_size]   # expression string pool
    """
    r = Reader(data)
    sc = Script(encoding=encoding)
    gcount = r.u32()
    for _ in range(gcount):
        raw = r.cstring_bytes()
        name = decode_bytes(raw, encoding)
        typ = parse_type(r)
        flags = r.u32()
        reserved = r.u32()
        offset = r.u32()
        sc.globals.append(GlobalVar(name, typ, flags, reserved, offset))
    sc.data_size = r.u32()

    fcount = r.u32()
    for _ in range(fcount):
        raw = r.cstring_bytes()
        sc.linked_funcs.append(decode_bytes(raw, encoding))

    lcount = r.u32()
    for i in range(lcount):
        raw = r.cstring_bytes()
        name = decode_bytes(raw, encoding)
        off = r.u32()
        sc.labels.append(Label(name, off, i))

    ecount = r.u32()
    sys.setrecursionlimit(max(10000, sys.getrecursionlimit()))
    for _ in range(ecount):
        sc.exprs.append(parse_expr(r, encoding))

    csize = r.u32()
    if csize > r.remaining():
        raise ValueError("code size %d exceeds remaining %d" % (csize, r.remaining()))
    sc.code = r.bytes_(csize)

    if r.remaining() < 4:
        raise ValueError("missing msg pool size")
    msize = r.u32()
    if msize > r.remaining():
        raise ValueError("msg pool size %d exceeds remaining %d" % (msize, r.remaining()))
    sc.string_pool = r.bytes_(msize)

    if r.remaining() < 4:
        raise ValueError("missing estr pool size")
    esize = r.u32()
    if esize > r.remaining():
        raise ValueError("estr pool size %d exceeds remaining %d" % (esize, r.remaining()))
    sc.estr_pool = r.bytes_(esize)

    if r.remaining() != 0:
        raise ValueError("trailing %d bytes after exec.dat parse" % r.remaining())
    return sc


def disassemble_code(sc: Script) -> None:
    code = sc.code
    n = len(code)
    pc = 0
    instrs: List[Instr] = []
    label_by_index = {lab.index: lab for lab in sc.labels}

    while pc < n:
        op = code[pc]
        start = pc
        pc += 1
        info = op_info(op)
        imm = None
        text = None
        label_name = None
        expr_index = None
        raw = None
        operand_kind = info.operand

        if info.operand == "cstr":
            end = code.find(b"\x00", pc)
            if end < 0:
                raise ValueError("unterminated cstring operand at pc=%d op=%d" % (start, op))
            raw = code[pc : end + 1]
            text = decode_bytes(raw, sc.encoding)
            pc = end + 1
        elif info.operand == "pool_off":
            if pc + 4 > n:
                raise ValueError("truncated pool offset at pc=%d" % start)
            imm = struct.unpack_from("<I", code, pc)[0]
            pc += 4
            try:
                z = pool_get_zstring(sc.string_pool, imm)
                text = decode_bytes(z, sc.encoding)
            except ValueError:
                text = "{{BAD_POOL_OFF:%d}}" % imm
        elif info.operand == "eval_blob":
            if pc + 2 > n:
                raise ValueError("truncated eval length at pc=%d" % start)
            ln = struct.unpack_from("<H", code, pc)[0]
            pc += 2
            if pc + ln > n:
                raise ValueError("truncated eval blob at pc=%d len=%d" % (start, ln))
            raw = code[pc : pc + ln]
            pc += ln
            # Keep semantic-ish dump: hex placeholders, no raw \x.
            text = "".join("{{%02X}}" % b for b in raw)
        elif info.operand in ("u32", "u32_label", "u32_expr"):
            if pc + 4 > n:
                raise ValueError("truncated u32 operand at pc=%d op=%d" % (start, op))
            imm = struct.unpack_from("<I", code, pc)[0]
            pc += 4
            if info.operand == "u32_label":
                lab = label_by_index.get(imm)
                if lab is not None:
                    label_name = lab.name
            elif info.operand == "u32_expr":
                expr_index = imm
                operand_kind = "u32_expr"
        elif info.operand == "none":
            pass
        else:
            # Unknown operand scheme: treat as bare opcode.
            operand_kind = "none"

        instrs.append(
            Instr(
                pc=start,
                opcode=op,
                mnemonic=info.mnemonic,
                operand_kind=operand_kind,
                imm=imm,
                text=text,
                label_name=label_name,
                expr_index=expr_index,
                raw=raw,
            )
        )

    sc.instrs = instrs


def format_type(t: Optional[TypeNode]) -> str:
    parts: List[str] = []
    cur = t
    while cur is not None:
        parts.append("%s:%d" % (type_kind_name(cur.kind), cur.value))
        cur = cur.next
    return ", ".join(parts) if parts else "void:0"


def format_expr(e: ExprNode) -> str:
    if e.kind == EXPR_T:
        return "T"
    if e.kind == EXPR_U:
        return '(ID "%s")' % (e.text or "")
    if e.kind == EXPR_W:
        return '(STR "%s")' % (e.text or "")
    if e.kind == EXPR_V:
        return "(INT %d)" % (e.value or 0)
    kn = expr_kind_name(e.kind)
    left = format_expr(e.left) if e.left is not None else "T"
    right = format_expr(e.right) if e.right is not None else "T"
    return "(%s %s %s)" % (kn, left, right)


def _is_mergeable_text(ins: Instr) -> bool:
    return ins.opcode in (OP_TEXT, OP_TEXT_A, OP_TEXT_B) and ins.text is not None


def emit_asm(sc: Script, pool_file: str | None = None, estr_file: str | None = None) -> str:
    lines: List[str] = []
    lines.append("; encoding: %s" % sc.encoding)
    lines.append("; format: malie sc.dll exec.dat (msg + estr pools)")
    lines.append(
        "; globals=%d data_size=%d linked_funcs=%d labels=%d exprs=%d code=%d msg=%d estr=%d instrs=%d"
        % (
            len(sc.globals),
            sc.data_size,
            len(sc.linked_funcs),
            len(sc.labels),
            len(sc.exprs),
            len(sc.code),
            len(sc.string_pool),
            len(sc.estr_pool),
            len(sc.instrs),
        )
    )
    lines.append("")
    lines.append("; ============================================================")
    lines.append("; Globals")
    lines.append("; ============================================================")
    lines.append(".data_size %d" % sc.data_size)
    for g in sc.globals:
        lines.append(
            '.global "%s", type=%s, flags=%d, reserved=%d, offset=%d'
            % (g.name, format_type(g.typ), g.flags, g.reserved, g.offset)
        )
    lines.append("")
    lines.append("; ============================================================")
    lines.append("; Linked host functions (FunctionMan table)")
    lines.append("; ============================================================")
    for i, name in enumerate(sc.linked_funcs):
        lines.append('.linked_func %d, "%s"' % (i, name))
    lines.append("")
    lines.append("; ============================================================")
    lines.append("; Labels")
    lines.append("; ============================================================")
    for lab in sc.labels:
        tag = ""
        bare = lab.name
        if bare in EFFECT_LABELS:
            tag = "  ; effect"
        elif bare and not bare.startswith("$L") and "@" not in bare:
            if bare.isupper() or "_" in bare:
                tag = "  ; special"
        lines.append('.label_def %d, "%s", offset=%d%s' % (lab.index, lab.name, lab.offset, tag))
    lines.append("")
    if sc.exprs:
        lines.append("; ============================================================")
        lines.append("; Expressions (legacy AST pool)")
        lines.append("; ============================================================")
        for i, e in enumerate(sc.exprs):
            lines.append(".expr %d %s" % (i, format_expr(e)))
        lines.append("")
    if sc.string_pool:
        lines.append("; ============================================================")
        lines.append("; Msg string pool (OP_TEXT targets; voice id / tail metadata; bodies in code text)")
        lines.append(";   voice v_xxx                 <- 07 08 + id (no body)")
        lines.append(";   text, tail=plain|voiced     <- tail only; body is code `text <off>`")
        lines.append(";   $1/$2                       <- 07 0C 01 / 07 0C 02")
        lines.append(";   %haato                          <- 0x06 wait (multi-chunk boundary)")
        lines.append("; ============================================================")
        if pool_file:
            lines.append('.pool_file "%s"' % pool_file)
            lines.append("; pool_size %d (exact binary sidecar; edit code text / .pool meta, not the raw blob)" % len(sc.string_pool))
        else:
            lines.append(".pool_size %d" % len(sc.string_pool))
        pool = sc.string_pool
        local_index = build_pool_index(pool)
        ref_offs = set(ins.imm for ins in sc.instrs if ins.opcode == OP_TEXT and ins.imm is not None)
        # reverse: dialogue_off -> voice_off for auto-paired lines
        auto_from_voice: Dict[int, int] = {}
        chain_member_of: Dict[int, int] = {}  # off -> chain head
        for voff in ref_offs:
            pair = paired_dialogue_for_voice(local_index, voff, sc.encoding, ref_offs)
            if pair is not None and pair[0] not in ref_offs:
                head, _info, chain_offs = pair
                auto_from_voice[head] = voff
                for co in chain_offs:
                    chain_member_of[co] = head
        # hard multi-chunk chains (OP_TEXT points at wait-head)
        for hoff in ref_offs:
            raw, _ = local_index.get(hoff, (b"", None))
            if raw.startswith(MARKER_VOICE):
                continue
            if not _ends_with_wait_only(raw):
                continue
            chain = collect_text_chain(local_index, hoff, sc.encoding, ref_offs)
            if len(chain) > 1:
                head = chain[0][0]
                for co, _, _ in chain:
                    chain_member_of[co] = head
        for off in sorted(local_index.keys()):
            raw, _ = local_index[off]
            line = format_pool_directive(off, raw, sc.encoding)
            if off in ref_offs:
                line += "  ; used"
            if raw.startswith(MARKER_VOICE) and off in ref_offs:
                pair = paired_dialogue_for_voice(local_index, off, sc.encoding, ref_offs)
                if pair is not None and pair[0] not in ref_offs:
                    line += "  ; shows@%d" % pair[0]
            if off in auto_from_voice:
                line += "  ; auto_from_voice@%d (body in code text soft)" % auto_from_voice[off]
            if off in chain_member_of:
                head = chain_member_of[off]
                if off == head:
                    line += "  ; chain_head"
                else:
                    line += "  ; chain@%d" % head
            lines.append(line)
        lines.append("")

    if sc.estr_pool:
        lines.append("; ============================================================")
        lines.append("; Expression string pool (eval push_estr* / name / vset)")
        lines.append("; ============================================================")
        if estr_file:
            lines.append('.estr_file "%s"' % estr_file)
            lines.append("; estr_size %d (exact binary sidecar)" % len(sc.estr_pool))
        else:
            # Fallback only: chunked placeholders (never one giant line)
            lines.append(".estr_size %d" % len(sc.estr_pool))
            blob = sc.estr_pool
            chunk = 32
            for i in range(0, len(blob), chunk):
                part = blob[i : i + chunk]
                hx = "".join("{{%02X}}" % b for b in part)
                lines.append('.estr_blob "%s"' % hx)
        lines.append("")

    lines.append("; ============================================================")
    lines.append("; Code")
    lines.append("; ============================================================")
    pool_index: Dict[int, Tuple[bytes, Optional[int]]] = (
        build_pool_index(sc.string_pool) if sc.string_pool else {}
    )
    referenced_text_offs = set(
        ins.imm for ins in sc.instrs if ins.opcode == OP_TEXT and ins.imm is not None
    )
    consumed_chain_offs: set = set()
    # pool offsets that are auto-paired dialogue after a referenced voice
    paired_dialogue_offs = set()
    for off in referenced_text_offs:
        if off in pool_index and pool_index[off][0].startswith(MARKER_VOICE):
            pair = paired_dialogue_for_voice(pool_index, off, sc.encoding, referenced_text_offs)
            if pair is not None and pair[0] not in referenced_text_offs:
                paired_dialogue_offs.add(pair[0])
                consumed_chain_offs.update(pair[2])

    labels_by_off: Dict[int, List[Label]] = {}
    for lab in sc.labels:
        labels_by_off.setdefault(lab.offset, []).append(lab)

    for ins in sc.instrs:
        if ins.pc in labels_by_off:
            lines.append("")
            for lab in labels_by_off[ins.pc]:
                lines.append("%s:" % lab.name)

        if ins.operand_kind == "none":
            lines.append("    %s" % ins.mnemonic)
        elif ins.operand_kind == "cstr":
            lines.append('    %s "%s"' % (ins.mnemonic, ins.text or ""))
        elif ins.operand_kind == "pool_off":
            off = ins.imm if ins.imm is not None else 0
            try:
                z = pool_get_zstring(sc.string_pool, off)
                raw = z[:-1] if z.endswith(bytes([0])) else z
            except Exception:
                raw = b""
            for ln in format_text_opcode_lines(off, raw, sc.encoding, pool_index, referenced_text_offs, consumed_chain_offs):
                lines.append(ln)
        elif ins.operand_kind == "eval_blob":
            # Name window setter -> semantic name "..." (editable, above text).
            # Voice-play setter  -> semantic vset "v_xxx" (editable).
            raw = ins.raw
            if raw is None and ins.text:
                try:
                    import re as _re
                    raw = bytes(int(x, 16) for x in _re.findall(r"\{\{([0-9A-Fa-f]{2})\}\}", ins.text or ""))
                except Exception:
                    raw = None
            meta = _setter_push_meta(raw, NAME_SETTER_PREFIX) if raw else None
            if meta is not None:
                eoff, pwidth = meta
                nm = extract_name_from_setter(raw, sc.encoding, sc.estr_pool) or ""
                safe = nm.replace("\\", "\\\\").replace('"', '\\"')
                pw = {1: "u8", 2: "u16", 4: "u32"}[pwidth]
                lines.append('    name %d, "%s", push=%s' % (eoff, safe, pw))
            else:
                meta = _setter_push_meta(raw, VOICE_SETTER_PREFIX) if raw else None
                if meta is not None:
                    eoff, pwidth = meta
                    vid = extract_voice_from_setter(raw, sc.encoding, sc.estr_pool) or ""
                    safe = vid.replace("\\", "\\\\").replace('"', '\\"')
                    pw = {1: "u8", 2: "u16", 4: "u32"}[pwidth]
                    sp = speaker_from_voice(vid)
                    if sp:
                        lines.append('    vset %d, "%s", push=%s  ; name %s' % (eoff, safe, pw, sp))
                    else:
                        lines.append('    vset %d, "%s", push=%s' % (eoff, safe, pw))
                else:
                    # Keep blob as placeholder string so assembler can rebuild exact bytes.
                    lines.append('    %s "%s"' % (ins.mnemonic, ins.text or ""))

        elif ins.operand_kind == "u32":
            lines.append("    %s %d" % (ins.mnemonic, ins.imm if ins.imm is not None else 0))
        elif ins.operand_kind == "u32_label":
            if ins.label_name is not None:
                lines.append("    %s %s" % (ins.mnemonic, ins.label_name))
            else:
                lines.append("    %s %d" % (ins.mnemonic, ins.imm if ins.imm is not None else 0))
        elif ins.operand_kind == "u32_expr":
            lines.append("    %s expr_%d" % (ins.mnemonic, ins.expr_index if ins.expr_index is not None else 0))
        else:
            lines.append("    %s" % ins.mnemonic)

    # Emit remaining unreferenced non-voice pool texts as soft texts so code section
    # contains ALL editable pool bodies (except pure voice ids / multi-chunk members).
    emitted_body_offs = set(consumed_chain_offs)
    # hard OP_TEXT refs + their multi-chunk members
    for ins in sc.instrs:
        if ins.opcode == OP_TEXT and ins.imm is not None:
            emitted_body_offs.add(ins.imm)
            if ins.imm in pool_index and pool_index[ins.imm][0].startswith(MARKER_VOICE):
                pair = paired_dialogue_for_voice(pool_index, ins.imm, sc.encoding, referenced_text_offs)
                if pair is not None:
                    emitted_body_offs.update(pair[2])
            else:
                raw, _ = pool_index.get(ins.imm, (b"", None))
                if raw and _ends_with_wait_only(raw):
                    chain = collect_text_chain(pool_index, ins.imm, sc.encoding, referenced_text_offs)
                    emitted_body_offs.update(o for o, _, _ in chain)
    leftover = []
    for off in sorted(pool_index.keys()):
        if off in emitted_body_offs:
            continue
        raw, _ = pool_index[off]
        if raw.startswith(MARKER_VOICE):
            continue
        info = analyze_pool_entry(raw, sc.encoding)
        if info.get("kind") != "text":
            continue
        # if this is a wait-head of an unreferenced multi-chunk, merge it
        if _ends_with_wait_only(raw):
            chain = collect_text_chain(pool_index, off, sc.encoding, referenced_text_offs)
            if len(chain) > 1:
                leftover.append((off, merge_chain_text(chain)))
                emitted_body_offs.update(o for o, _, _ in chain)
                continue
        leftover.append((off, info.get("text", "")))
    if leftover:
        lines.append("")
        lines.append("; ============================================================")
        lines.append("; Soft texts (pool bodies not OP_TEXT-referenced; edit these bodies)")
        lines.append("; soft => updates .pool body only, does not emit code bytes")
        lines.append("; multi-chunk lines use %haato for 0x06 wait boundaries")
        lines.append("; ============================================================")
        for off, body in leftover:
            lines.append('    text %d, "%s", soft' % (off, body))

    end_pc = len(sc.code)
    if end_pc in labels_by_off:
        lines.append("")
        for lab in labels_by_off[end_pc]:
            lines.append("%s:" % lab.name)
    lines.append("")
    return "\n".join(lines)


def disassemble_file(in_path: str, out_path: str, encoding: str) -> None:
    with open(in_path, "rb") as f:
        data = f.read()
    sc = parse_exec(data, encoding)
    disassemble_code(sc)
    out_dir = os.path.dirname(os.path.abspath(out_path))
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    # Exact binary sidecars: avoid editor-truncating multi-hundred-KB hex lines,
    # and keep zero-mutation even when semantic pool rebuild is imperfect.
    base = os.path.basename(out_path)
    pool_name = base + ".msg.bin"
    estr_name = base + ".estr.bin"
    pool_path = os.path.join(out_dir, pool_name) if out_dir else pool_name
    estr_path = os.path.join(out_dir, estr_name) if out_dir else estr_name
    if sc.string_pool:
        with open(pool_path, "wb") as f:
            f.write(sc.string_pool)
    if sc.estr_pool:
        with open(estr_path, "wb") as f:
            f.write(sc.estr_pool)

    text = emit_asm(
        sc,
        pool_file=pool_name if sc.string_pool else None,
        estr_file=estr_name if sc.estr_pool else None,
    )
    with open(out_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    text_count = sum(1 for ins in sc.instrs if ins.opcode == OP_TEXT)
    print("[ok] %s -> %s" % (in_path, out_path))
    print(
        "     globals=%d linked=%d labels=%d exprs=%d code=%d msg=%d estr=%d instrs=%d texts=%d"
        % (
            len(sc.globals),
            len(sc.linked_funcs),
            len(sc.labels),
            len(sc.exprs),
            len(sc.code),
            len(sc.string_pool),
            len(sc.estr_pool),
            len(sc.instrs),
            text_count,
        )
    )


def batch_bin_to_txt(bin_dir: str, txt_dir: str, encoding: str) -> None:
    os.makedirs(txt_dir, exist_ok=True)
    files = [n for n in os.listdir(bin_dir) if os.path.isfile(os.path.join(bin_dir, n))]
    for name in files:
        disassemble_file(
            os.path.join(bin_dir, name),
            os.path.join(txt_dir, name + ".asm.txt"),
            encoding,
        )


def main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) >= 2 and not argv[0].startswith("-") and not argv[1].startswith("-"):
        if os.path.isdir(argv[0]):
            encoding = DEFAULT_ENCODING
            if "--encoding" in argv:
                encoding = argv[argv.index("--encoding") + 1]
            batch_bin_to_txt(argv[0], argv[1], encoding)
            return 0
    ap = argparse.ArgumentParser(description="Disassemble Malie sc.dll exec.dat")
    ap.add_argument("input")
    ap.add_argument("output", nargs="?")
    ap.add_argument("-o", dest="out_file")
    ap.add_argument("--encoding", default=DEFAULT_ENCODING)
    args = ap.parse_args(argv)
    if os.path.isdir(args.input):
        batch_bin_to_txt(args.input, args.output or args.out_file or "txt", args.encoding)
        return 0
    out = args.out_file or args.output or (os.path.basename(args.input) + ".asm.txt")
    disassemble_file(args.input, out, args.encoding)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
