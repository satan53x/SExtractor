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
expr_kind_name = _opcode.expr_kind_name
op_info = _opcode.op_info
type_kind_name = _opcode.type_kind_name
OP_TEXT = _opcode.OP_TEXT
OP_EVAL = _opcode.OP_EVAL
OP_TEXT_A = _opcode.OP_TEXT_A
OP_TEXT_B = _opcode.OP_TEXT_B
OP_STR = _opcode.OP_STR
OP_ARG = _opcode.OP_ARG
OP_JMP = _opcode.OP_JMP
OP_JZ = _opcode.OP_JZ
OP_JNZ = _opcode.OP_JNZ
OP_NUM_A = _opcode.OP_NUM_A
OP_NUM_B = _opcode.OP_NUM_B
OP_NUM_C = _opcode.OP_NUM_C
OP_FSTORE_IMM = _opcode.OP_FSTORE_IMM
MARKER_NAME1 = _opcode.MARKER_NAME1
MARKER_NAME2 = _opcode.MARKER_NAME2
MARKER_VOICE = _opcode.MARKER_VOICE
MARKER_RUBY = _opcode.MARKER_RUBY
MARKER_NL = _opcode.MARKER_NL
MARKER_PLAIN = _opcode.MARKER_PLAIN
MARKER_VOICED = _opcode.MARKER_VOICED
MARKER_FX_PREFIX = _opcode.MARKER_FX_PREFIX
MARKER_NEST = _opcode.MARKER_NEST
MARKER_SKIP_PREFIX = _opcode.MARKER_SKIP_PREFIX
TAIL_PLAIN = _opcode.TAIL_PLAIN
TAIL_VOICED = _opcode.TAIL_VOICED
TAIL_WAIT = _opcode.TAIL_WAIT
TOKEN_WAIT = _opcode.TOKEN_WAIT
TOKEN_NL = _opcode.TOKEN_NL
TOKEN_LINE = _opcode.TOKEN_LINE
TOKEN_VOICED_MID = getattr(_opcode, 'TOKEN_VOICED_MID', '%pv')
MARKER_MUSIC = getattr(_opcode, 'MARKER_MUSIC', bytes([0xFF, 0x00]))
TOKEN_MUSIC = getattr(_opcode, 'TOKEN_MUSIC', '♪')
CTRL_LEAD = _opcode.CTRL_LEAD
CTRL_RUBY = _opcode.CTRL_RUBY
CTRL_FX = _opcode.CTRL_FX
CTRL_NL = _opcode.CTRL_NL
CTRL_SKIP = _opcode.CTRL_SKIP
CTRL_PLAIN = _opcode.CTRL_PLAIN
CTRL_NEST = _opcode.CTRL_NEST
CTRL_VOICE = _opcode.CTRL_VOICE
CTRL_VOICED = _opcode.CTRL_VOICED
CTRL_NAME = _opcode.CTRL_NAME
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
    """Decode payload bytes to semantic text (IDA sub_434A80 stream rules).

    Control lead-in 0x07:
      01 ruby   -> <rb "reading">base</rb>   (reading ends at embedded NUL; caller
                 must include bytes past that NUL when this is a logical span)
      04        -> $e
      06        -> newline(s) (mid-entry only; final tails stripped before calling here)
      08 voice  -> should be split before decode (voice id is separate semantic unit)
      09        -> {{07}}{{09}}  (mid voiced terminator; final TAIL_VOICED stripped)
      0C 01/02  -> $1 / $2
      02 / 05 / 07 -> exact placeholders / nested raw
    Bare 0x0A kept as {{0A}} only when not part of a mid 07 06 line-break run.
    """
    encoding = _normalize_encoding(encoding)
    out: List[str] = []
    i = 0
    n = len(data)
    is_sjis = encoding == "cp932"
    while i < n:
        b = data[i]
        # IDA: 0xFF is 2-byte glyph (almost always FF 00) -> source music note
        if b == 0xFF:
            out.append(TOKEN_MUSIC)
            i += 2 if i + 1 < n else 1
            continue
        # 0x07 control sequences
        if b == CTRL_LEAD and i + 1 < n:
            sub = data[i + 1]
            if sub == CTRL_RUBY:
                # 07 01 base 0A reading 00?  reading may run to end of this buffer
                # if NUL was the entry boundary already stripped, reading = rest.
                j = i + 2
                # base until 0A
                a = data.find(bytes([0x0A]), j)
                if a < 0:
                    out.append("{{07}}{{01}}")
                    i += 2
                    continue
                base = data[j:a]
                # reading until embedded NUL if present, else rest of buffer
                k = data.find(bytes([0]), a + 1)
                if k < 0:
                    reading = data[a + 1 :]
                    rest_i = n
                else:
                    reading = data[a + 1 : k]
                    rest_i = k + 1  # continue after embedded NUL (IDA does this)
                try:
                    bs = base.decode(encoding)
                    rs = reading.decode(encoding)
                except Exception:
                    out.append("{{07}}{{01}}")
                    i = a + 1
                    continue
                out.append('<rb "%s">%s</rb>' % (rs, bs))
                i = rest_i
                continue
            if sub == CTRL_NL:
                out.append(TOKEN_NL)
                i += 2
                continue
            if sub == CTRL_PLAIN:
                # Mid-entry sentence/line break (IDA sub_434A80 case 6).
                # Fold 07 06 + following bare 0A* into readable newlines:
                #   07 06        -> \n
                #   07 06 0A     -> \n
                #   07 06 0A 0A  -> \n\n
                #   07 06 0A*k   -> \n * k  (k>=2); k==1 also single \n
                i += 2
                n_lf = 0
                while i < n and data[i] == 0x0A:
                    n_lf += 1
                    i += 1
                if n_lf <= 1:
                    out.append("\n")
                else:
                    out.append("\n" * n_lf)
                continue
            if sub == CTRL_VOICED:
                # Mid-stream voiced terminator: 07 09 [07 06] [0A*]
                # Keep distinct from plain 07 06 so repack does not drop 07 09
                # (final TAIL_VOICED already stripped by analyze_pool_entry).
                i += 2
                if i + 1 < n and data[i] == CTRL_LEAD and data[i + 1] == CTRL_PLAIN:
                    i += 2
                n_lf = 0
                while i < n and data[i] == 0x0A:
                    n_lf += 1
                    i += 1
                out.append(TOKEN_VOICED_MID)
                if n_lf:
                    out.append("\n" * n_lf)
                continue
            if sub == CTRL_VOICE:
                # should normally be peeled off; keep raw if embedded
                j = i + 2
                z = data.find(bytes([0]), j)
                if z < 0:
                    vid = data[j:]
                    i = n
                else:
                    vid = data[j:z]
                    i = z + 1
                try:
                    out.append('{{VOICE:%s}}' % vid.decode("ascii", errors="replace"))
                except Exception:
                    out.append("{{07}}{{08}}")
                continue
            if sub == CTRL_NAME and i + 2 < n:
                if data[i + 2] == 0x01:
                    out.append("$1"); i += 3; continue
                if data[i + 2] == 0x02:
                    out.append("$2"); i += 3; continue
            if sub == CTRL_FX and i + 2 < n:
                out.append("{{07}}{{02}}{{%02X}}" % data[i + 2])
                i += 3
                continue
            if sub == CTRL_SKIP and i + 3 < n:
                ln = data[i + 2] | (data[i + 3] << 8)
                payload = data[i + 4 : i + 4 + ln]
                out.append("{{07}}{{05}}{{%02X}}{{%02X}}" % (data[i + 2], data[i + 3]))
                for bb in payload:
                    out.append("{{%02X}}" % bb)
                i += 4 + ln
                continue
            if sub == CTRL_NEST:
                # 07 07 nested block until 00 then cstring until 00 - emit raw
                out.append("{{07}}{{07}}")
                i += 2
                continue
            # unknown 07 XX
            out.append("{{07}}{{%02X}}" % sub)
            i += 2
            continue

        if is_sjis and ((0x81 <= b <= 0x9F) or (0xE0 <= b <= 0xFC)):
            if i + 1 < n:
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






# Must match assembler.NAME_SETTER_* (FrameLayer_SendMessage name window).
NAME_SETTER_PREFIX = bytes.fromhex("0a38040000060e640e48100c")
NAME_SETTER_SUFFIX = bytes.fromhex("034672616d654c617965725f53656e644d657373616765000405")


def is_name_setter_blob(blob: bytes) -> bool:
    if not blob or not blob.startswith(NAME_SETTER_PREFIX):
        return False
    mid = blob[len(NAME_SETTER_PREFIX) :]
    if not mid.endswith(NAME_SETTER_SUFFIX):
        return False
    body = mid[: -len(NAME_SETTER_SUFFIX)]
    return len(body) >= 1 and body.endswith(b"\x00")


def extract_name_from_setter(blob: bytes, encoding: str) -> Optional[str]:
    if not is_name_setter_blob(blob):
        return None
    mid = blob[len(NAME_SETTER_PREFIX) : -len(NAME_SETTER_SUFFIX)]
    payload = mid[:-1]
    if payload.startswith(b"\x09"):
        payload = payload[1:]
    enc = encoding or "cp932"
    try:
        return payload.decode(enc)
    except Exception:
        try:
            return payload.decode(enc, errors="replace")
        except Exception:
            return "".join("{{%02X}}" % b for b in payload)


def _replace_name_markers_to_tokens(data: bytes) -> bytes:
    """Map binary name markers to temporary ASCII tokens before text decode."""
    # Use rare ASCII tokens that survive cp932 decode as-is.
    out = data.replace(MARKER_NAME1, b"__D1__").replace(MARKER_NAME2, b"__D2__")
    return out


def _tokens_to_source_markers(text: str) -> str:
    return text.replace("__D1__", "$1").replace("__D2__", "$2")



def analyze_pool_entry(raw: bytes, encoding: str) -> dict:
    """Classify one logical pool span (may include embedded NULs already joined).

    Returns keys:
      kind: 'voice' | 'text' | 'voice_text'
      voice_id: str
      text: semantic text
      tail: plain|voiced|none|custom|wait
      tail_hex: hex of stripped tail
      name: speaker from voice id
    """
    voice_id = ""
    name = ""
    body = raw

    # Leading pure voice entry (only voice id, no dialogue after)
    if body.startswith(MARKER_VOICE):
        z = body.find(bytes([0]), 2)
        if z == len(body):  # impossible without nul
            pass
        # if body is exactly 07 08 id (nul already stripped by entry) -> pure voice
        if bytes([0]) not in body[2:]:
            # pure voice id entry
            vid = body[2:].decode("ascii", errors="replace")
            return {
                "kind": "voice",
                "voice_id": vid,
                "text": "",
                "tail": "none",
                "tail_hex": "",
                "name": speaker_from_voice(vid),
            }
        # logical span beginning with voice then dialogue
        vid, rest = split_voice_prefix(body if body.find(bytes([0])) >= 0 else body + bytes([0]))
        # when raw came from entry strip, voice id entry has no embedded 00.
        # logical_span join puts: 07 08 id 00 dialogue...
        if bytes([0]) in body:
            vid, rest = split_voice_prefix(body)
            voice_id = vid or ""
            name = speaker_from_voice(voice_id)
            body = rest
        else:
            vid = body[2:].decode("ascii", errors="replace")
            return {
                "kind": "voice",
                "voice_id": vid,
                "text": "",
                "tail": "none",
                "tail_hex": "",
                "name": speaker_from_voice(vid),
            }

    # strip final tails only (include trailing layout 0A after 07 06 / voiced)
    tail_raw = bytearray()
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
        if body.endswith(bytes([0x0A])):
            tail_raw[0:0] = body[-1:]
            body = body[:-1]
            continue
        if body.endswith(TAIL_WAIT) and not body.endswith(TAIL_PLAIN):
            if len(body) >= 2 and body[-2] == CTRL_LEAD:
                break
            tail_raw[0:0] = body[-1:]
            body = body[:-1]
            continue
        break

    text = decode_payload(body, encoding)
    th = bytes(tail_raw).hex()
    if th == TAIL_VOICED.hex():
        tail = "voiced"
    elif th == TAIL_PLAIN.hex():
        tail = "plain"
    elif th == "":
        tail = "none"
    elif th == TAIL_WAIT.hex():
        tail = "wait"
    else:
        tail = "custom"

    kind = "voice_text" if voice_id else "text"
    return {
        "kind": kind,
        "voice_id": voice_id,
        "text": text,
        "tail": tail,
        "tail_hex": th,
        "name": name,
    }


def build_pool_index(pool: bytes) -> Dict[int, Tuple[bytes, Optional[int]]]:
    """Map physical NUL-separated pool offsets -> (raw_without_nul, next_entry_offset|None).

    Physical packing uses bare 0x00 separators as stored in the file.
    Display/merge uses extract_logical_raw / logical_span_end which understand
    that some 0x00 are inside FF 00 / ruby / voice and should be joined for text.
    """
    idx: Dict[int, Tuple[bytes, Optional[int]]] = {}
    offs: List[int] = []
    off = 0
    n = len(pool)
    while off < n:
        end = pool.find(bytes([0]), off)
        if end < 0:
            offs.append(off)
            idx[off] = (pool[off:], None)
            break
        offs.append(off)
        idx[off] = (pool[off:end], None)
        off = end + 1
    for i, o in enumerate(offs):
        raw, _ = idx[o]
        nxt = offs[i + 1] if i + 1 < len(offs) else None
        idx[o] = (raw, nxt)
    return idx






def logical_span_end(pool: bytes, start: int) -> int:
    """Return end offset (exclusive) of logical text span starting at start.

    Implements IDA sub_434A80 walk rules for embedded NULs:
      - bare 0x00 terminates the span
      - 07 01 ... 0A reading 00  : consume NUL and continue
      - 07 08 voice_id 00        : consume NUL and continue
      - 07 07 nest 00 cstr 00    : consume and continue
    Returns position of the terminating bare NUL, or len(pool).
    """
    i = start
    n = len(pool)
    while i < n:
        b = pool[i]
        if b == 0:
            return i
        # IDA sub_434A80: 0xFF is a 2-byte glyph (trail often 0x00) — NOT a string end
        if b == 0xFF:
            i += 2 if i + 1 < n else 1
            continue
        if b == CTRL_LEAD and i + 1 < n:
            sub = pool[i + 1]
            if sub == CTRL_RUBY:
                # skip 07 01, base until 0A, reading until 00, then CONTINUE past 00
                j = i + 2
                a = pool.find(bytes([0x0A]), j)
                if a < 0:
                    i += 2
                    continue
                z = pool.find(bytes([0]), a + 1)
                if z < 0:
                    return n
                i = z + 1
                continue
            if sub == CTRL_VOICE:
                z = pool.find(bytes([0]), i + 2)
                if z < 0:
                    return n
                i = z + 1
                continue
            if sub == CTRL_NEST:
                # 07 07 block until 00, then cstring until 00
                z = pool.find(bytes([0]), i + 2)
                if z < 0:
                    return n
                z2 = pool.find(bytes([0]), z + 1)
                if z2 < 0:
                    return n
                i = z2 + 1
                continue
            if sub == CTRL_SKIP and i + 3 < n:
                ln = pool[i + 2] | (pool[i + 3] << 8)
                i += 4 + ln
                continue
            if sub == CTRL_FX and i + 2 < n:
                i += 3
                continue
            if sub == CTRL_NAME and i + 2 < n:
                i += 3
                continue
            # 04/06/09 and other 2-byte controls
            i += 2
            continue
        # SJIS lead
        if (0x81 <= b <= 0x9F) or (0xE0 <= b <= 0xFC):
            i += 2 if i + 1 < n else 1
        else:
            i += 1
    return n


def extract_logical_raw(pool: bytes, start: int) -> Tuple[bytes, int]:
    """Return (raw_without_final_nul, end_exclusive_of_final_nul)."""
    end = logical_span_end(pool, start)
    return pool[start:end], end




def iter_span_segments(pool: bytes, start: int, end: int):
    """Yield (kind, offset, payload) for a logical span [start,end).

    kind: 'voice' with payload=voice_id str
          'text'  with payload=raw bytes (may include ruby embedded NULs already expanded in range)
    Splits on top-level 07 08 voice markers (IDA continues past them, but we surface them).
    """
    i = start
    text_start = None
    while i < end:
        b = pool[i]
        if b == 0xFF:
            if text_start is None:
                text_start = i
            i += 2 if i + 1 < end else 1
            continue
        if b == CTRL_LEAD and i + 1 < end and pool[i + 1] == CTRL_VOICE:
            if text_start is not None and text_start < i:
                yield ("text", text_start, pool[text_start:i])
                text_start = None
            z = pool.find(bytes([0]), i + 2, end + 1 if end < len(pool) else len(pool))
            # voice id ends at first 00 at or before end
            if z < 0 or z >= end:
                # no terminator in span
                vid = pool[i + 2 : end].decode("ascii", errors="replace")
                yield ("voice", i, vid)
                return
            vid = pool[i + 2 : z].decode("ascii", errors="replace")
            yield ("voice", i, vid)
            i = z + 1
            continue
        if text_start is None:
            text_start = i
        # advance one element so we don't mis-detect
        if b == CTRL_LEAD and i + 1 < end:
            sub = pool[i + 1]
            if sub == CTRL_RUBY:
                a = pool.find(bytes([0x0A]), i + 2, end)
                if a < 0:
                    i += 2
                    continue
                z = pool.find(bytes([0]), a + 1, end + (1 if end < len(pool) else 0))
                if z < 0 or z >= end:
                    # reading runs to end of span
                    i = end
                else:
                    i = z + 1
                continue
            if sub == CTRL_SKIP and i + 3 < end:
                ln = pool[i + 2] | (pool[i + 3] << 8)
                i += 4 + ln
                continue
            if sub == CTRL_FX and i + 2 < end:
                i += 3
                continue
            if sub == CTRL_NAME and i + 2 < end:
                i += 3
                continue
            i += 2
            continue
        if (0x81 <= b <= 0x9F) or (0xE0 <= b <= 0xFC):
            i += 2 if i + 1 < end else 1
        else:
            i += 1
    if text_start is not None and text_start < end:
        yield ("text", text_start, pool[text_start:end])


def split_voice_prefix(raw: bytes) -> Tuple[Optional[str], bytes]:
    """If raw starts with 07 08 voice\\0, return (voice_id, remainder_including_after_nul)."""
    if not raw.startswith(MARKER_VOICE):
        return None, raw
    z = raw.find(bytes([0]), 2)
    if z < 0:
        vid = raw[2:].decode("ascii", errors="replace")
        return vid, b""
    vid = raw[2:z].decode("ascii", errors="replace")
    return vid, raw[z + 1 :]


def _ends_with_wait_only(raw: bytes) -> bool:
    """True if entry ends with lone 0x06 wait (not 07 06 / 07 09 07 06)."""
    return raw.endswith(TAIL_WAIT) and not raw.endswith(TAIL_PLAIN) and not raw.endswith(TAIL_VOICED)



def _ruby_reading_to_entry_end(raw: bytes) -> bool:
    """True if physical entry ends on a ruby reading (entry NUL = reading terminator).

    IDA sub_434A80: after 07 01 base 0A reading 00, outer text continues.
    The game packer often places that reading-NUL as the *pool entry* terminator,
    so the next physical entry is mid-sentence continuation after </rb>.
    Display must join them; assembler re-splits after </rb> on repack.
    """
    if not raw or MARKER_RUBY not in raw:
        return False
    p = raw.rfind(MARKER_RUBY)
    if p < 0:
        return False
    a = raw.find(bytes([0x0A]), p + 2)
    if a < 0:
        return False
    # Any embedded 00 after 0A means reading already ended inside this entry.
    return raw.find(bytes([0]), a + 1) < 0


def merge_ruby_continuation_chain(
    pool_index: Dict[int, Tuple[bytes, Optional[int]]],
    start_off: int,
    encoding: str,
    referenced: Optional[set] = None,
) -> Tuple[str, List[int], dict]:
    """Join physical entries split only by ruby reading-NUL boundaries.

    Returns (merged_text, chain_offs, last_entry_info).
    """
    if start_off not in pool_index:
        return "", [], {"kind": "text", "text": "", "tail": "none", "tail_hex": "", "voice_id": "", "name": ""}
    offs: List[int] = []
    parts: List[str] = []
    last_info: dict = {}
    off: Optional[int] = start_off
    while off is not None and off in pool_index:
        if referenced is not None and off != start_off and off in referenced:
            break
        raw, nxt = pool_index[off]
        if raw.startswith(MARKER_VOICE):
            break
        info = analyze_pool_entry(raw, encoding)
        if info.get("kind") == "voice":
            break
        parts.append(info.get("text", "") or "")
        offs.append(off)
        last_info = info
        if _ruby_reading_to_entry_end(raw):
            off = nxt
            continue
        break
    if not last_info:
        last_info = {"kind": "text", "text": "", "tail": "none", "tail_hex": "", "voice_id": "", "name": ""}
    return "".join(parts), offs, last_info


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






def format_text_with_textp(off: int, body: str, soft: str = "") -> List[str]:
    """Emit text head + textp lines for mid-entry 07 06 breaks.

    Internal blank lines (from 07 06 0A 0A) remain as textp "".
    Trailing empty segments are dropped; final 07 06 is kept in pool tail meta.
    """
    text = body if body is not None else ""
    parts = text.split(chr(10))
    if not parts:
        parts = [""]
    while len(parts) > 1 and parts[-1] == "":
        parts.pop()
    lines: List[str] = []
    lines.append('    text %d, "%s"%s' % (off, parts[0], soft))
    for part in parts[1:]:
        lines.append('    textp "%s"' % part)
    return lines




def format_text_opcode_lines(
    off: int,
    raw: bytes,
    encoding: str,
    pool: Optional[bytes] = None,
    pool_index: Optional[Dict[int, Tuple[bytes, Optional[int]]]] = None,
    referenced: Optional[set] = None,
    consumed_chain_offs: Optional[set] = None,
) -> list:
    """Emit code-side lines for one OP_TEXT.

    Critical: only the OP_TEXT head offset emits a hard code op.
    Logical-span continuations (follow-up dialogue / mid-stream voice glyphs that
    are NOT independent pool entries) are soft pool edits only.

    Emitting extra hard voice/text for non-head logical segments inserts
    phantom OP_TEXT into the code stream and desyncs page/wait/voice timing.
    """
    lines = []

    def mark_consumed(a: int, b: int) -> None:
        if consumed_chain_offs is None or pool is None:
            return
        p = a
        while p < b:
            consumed_chain_offs.add(p)
            z = pool.find(bytes([0]), p)
            if z < 0 or z >= b:
                break
            p = z + 1

    # Offsets absorbed into a previous text line via ruby-continuation join.
    ruby_merged_offs: set = set()

    def emit_head_physical(head_off: int, head_raw: bytes) -> None:
        info = analyze_pool_entry(head_raw, encoding)
        if info["kind"] == "voice" or (
            head_raw.startswith(MARKER_VOICE) and bytes([0]) not in head_raw[2:]
        ):
            vid = info.get("voice_id") or head_raw[2:].decode("ascii", errors="replace")
            lines.append('    voice %d, "%s"%s' % (head_off, vid, _name_annot(vid)))
            return
        if pool_index is not None and head_off in pool_index:
            body, chain_offs, _last = merge_ruby_continuation_chain(
                pool_index, head_off, encoding, referenced
            )
            lines.extend(format_text_with_textp(head_off, body, ""))
            for co in chain_offs[1:]:
                ruby_merged_offs.add(co)
                if consumed_chain_offs is not None:
                    consumed_chain_offs.add(co)
            return
        lines.extend(format_text_with_textp(head_off, info.get("text", ""), ""))

    def emit_soft_physical(seg_off: int) -> None:
        if pool_index is None or seg_off not in pool_index:
            return
        if seg_off in ruby_merged_offs:
            return
        if referenced is not None and seg_off in referenced:
            return
        sraw, _ = pool_index[seg_off]
        # Pure voice physical entries that are only continuations of a previous
        # hard OP_TEXT walk stay soft (pool meta only).
        if sraw.startswith(MARKER_VOICE) and bytes([0]) not in sraw[2:]:
            vid = sraw[2:].decode("ascii", errors="replace")
            lines.append('    voice %d, "%s", soft%s' % (seg_off, vid, _name_annot(vid)))
            return
        info = analyze_pool_entry(sraw, encoding)
        if info.get("kind") == "voice":
            lines.append(
                '    voice %d, "%s", soft%s'
                % (seg_off, info.get("voice_id", ""), _name_annot(info.get("voice_id", "")))
            )
            return
        # Join ruby-split continuations into one editable soft body.
        body, chain_offs, _last = merge_ruby_continuation_chain(
            pool_index, seg_off, encoding, referenced
        )
        lines.extend(format_text_with_textp(seg_off, body, ", soft"))
        for co in chain_offs[1:]:
            ruby_merged_offs.add(co)
            if consumed_chain_offs is not None:
                consumed_chain_offs.add(co)

    if pool is not None and 0 <= off < len(pool):
        span, end = extract_logical_raw(pool, off)
        mark_consumed(off, end)
        # Prefer physical entry body so end-of-entry embedded voice (07 08 id with
        # entry-NUL as terminator) round-trips as {{VOICE:id}} inside the head text.
        # Ruby reading-NULs that are also entry boundaries are re-joined for display.
        if pool_index is not None and off in pool_index:
            emit_head_physical(off, pool_index[off][0])
        else:
            emit_head_physical(off, raw)

        # Soft-edit following physical entries covered by the same logical walk.
        # Walk via pool_index next links (O(span entries)), not full pool sort.
        if pool_index is not None and off in pool_index:
            _raw0, nxt = pool_index[off]
            cur = nxt
            while cur is not None and cur < end:
                emit_soft_physical(cur)
                _r, nxt2 = pool_index.get(cur, (b"", None))
                if nxt2 is None or nxt2 <= cur:
                    break
                cur = nxt2
        return lines

    # Fallback single entry
    info = analyze_pool_entry(raw, encoding)
    if info["kind"] == "voice":
        lines.append('    voice %d, "%s"%s' % (off, info["voice_id"], _name_annot(info["voice_id"])))
        if pool_index is not None:
            pair = paired_dialogue_for_voice(pool_index, off, encoding, referenced)
            if pair is not None:
                poff, pinfo, chain_offs = pair
                if referenced is None or poff not in referenced:
                    lines.extend(format_text_with_textp(poff, pinfo.get("text", ""), ", soft"))
                    if consumed_chain_offs is not None:
                        consumed_chain_offs.update(chain_offs)
        return lines
    lines.extend(format_text_with_textp(off, info.get("text", ""), ""))
    return lines


def _name_annot(voice_id: str) -> str:
    nm = speaker_from_voice(voice_id)
    if not nm:
        return ""
    return '  ; name "%s"' % nm


def pool_get_zstring(pool: bytes, off: int) -> bytes:
    if off < 0 or off >= len(pool):
        raise ValueError("string pool offset out of range: %d" % off)
    end = pool.find(b"\x00", off)
    if end < 0:
        return pool[off:]
    return pool[off : end + 1]


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
    labels: List[Label] = field(default_factory=list)
    exprs: List[ExprNode] = field(default_factory=list)
    code: bytes = b""
    string_pool: bytes = b""
    instrs: List[Instr] = field(default_factory=list)
    encoding: str = DEFAULT_ENCODING


def parse_type(r: Reader) -> Optional[TypeNode]:
    kind = r.u32()
    if kind == 0:
        return None
    value = r.u32()
    return TypeNode(kind, value, parse_type(r))


def parse_expr(r: Reader, encoding: str) -> ExprNode:
    # Legacy AST format: kind as u32. Kept for files that still ship expr pools.
    kind = r.u32()
    if kind == EXPR_T:
        return ExprNode(kind)
    if kind in (EXPR_U, EXPR_W):
        raw = r.cstring_bytes()
        return ExprNode(kind, text=decode_bytes(raw, encoding))
    if kind == EXPR_V:
        return ExprNode(kind, value=r.u32())
    left = parse_expr(r, encoding)
    right = parse_expr(r, encoding)
    return ExprNode(kind, left=left, right=right)


def parse_exec(data: bytes, encoding: str) -> Script:
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
    sc.code = r.bytes_(csize)
    # New format: trailing string pool used by OP_TEXT (u32 offset).
    if r.remaining() >= 4:
        psize = r.u32()
        if psize > r.remaining():
            raise ValueError(
                "string pool size %d exceeds remaining %d" % (psize, r.remaining())
            )
        sc.string_pool = r.bytes_(psize)
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


def emit_asm(sc: Script) -> str:
    lines: List[str] = []
    lines.append("; encoding: %s" % sc.encoding)
    lines.append("; format: sispara2 exec.dat (string pool)")
    lines.append("; globals=%d data_size=%d labels=%d exprs=%d code=%d pool=%d instrs=%d"
                 % (len(sc.globals), sc.data_size, len(sc.labels), len(sc.exprs),
                    len(sc.code), len(sc.string_pool), len(sc.instrs)))
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
    lines.append("; Labels")
    lines.append("; ============================================================")
    for lab in sc.labels:
        lines.append('.label_def %d, "%s", offset=%d' % (lab.index, lab.name, lab.offset))
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
        lines.append("; String pool (REFERENCE ONLY: voice id / tail metadata; bodies in code text)")
        lines.append(";   voice v_xxx                 <- 07 08 + id (no body)")
        lines.append(";   text, tail=plain|voiced     <- tail only; body is code `text <off>`")
        lines.append(";   $1/$2                       <- 07 0C 01 / 07 0C 02")
        lines.append(";   %haato                          <- 0x06 wait (multi-chunk boundary)")
        lines.append("; ============================================================")
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
            for ln in format_text_opcode_lines(off, raw, sc.encoding, sc.string_pool, pool_index, referenced_text_offs, consumed_chain_offs):
                lines.append(ln)
        elif ins.operand_kind == "eval_blob":
            # Name window setter -> semantic name "..." (editable).
            raw = ins.raw
            if raw is None and ins.text:
                try:
                    import re as _re
                    raw = bytes(int(x, 16) for x in _re.findall(r"\{\{([0-9A-Fa-f]{2})\}\}", ins.text or ""))
                except Exception:
                    raw = None
            nm = extract_name_from_setter(raw, sc.encoding) if raw else None
            if nm is not None:
                safe = nm.replace("\\", "\\\\").replace('"', '\\"')
                lines.append('    name "%s"' % safe)
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
    # hard OP_TEXT refs + their logical spans (ruby/voice continuations)
    for ins in sc.instrs:
        if ins.opcode == OP_TEXT and ins.imm is not None:
            off = ins.imm
            emitted_body_offs.add(off)
            if sc.string_pool and 0 <= off < len(sc.string_pool):
                span, end = extract_logical_raw(sc.string_pool, off)
                p = off
                while p < end:
                    emitted_body_offs.add(p)
                    z = sc.string_pool.find(bytes([0]), p)
                    if z < 0 or z >= end:
                        break
                    p = z + 1
            else:
                raw, _ = pool_index.get(off, (b"", None))
                if raw.startswith(MARKER_VOICE):
                    pair = paired_dialogue_for_voice(pool_index, off, sc.encoding, referenced_text_offs)
                    if pair is not None:
                        emitted_body_offs.update(pair[2])
                elif raw and _ends_with_wait_only(raw):
                    chain = collect_text_chain(pool_index, off, sc.encoding, referenced_text_offs)
                    emitted_body_offs.update(o for o, _, _ in chain)
    # Also mark pure ruby-continuation physical members of already-emitted heads.
    for off in list(emitted_body_offs):
        if off not in pool_index:
            continue
        raw, _ = pool_index[off]
        if _ruby_reading_to_entry_end(raw):
            _body, chain_offs, _info = merge_ruby_continuation_chain(
                pool_index, off, sc.encoding, referenced_text_offs
            )
            emitted_body_offs.update(chain_offs)

    leftover = []
    for off in sorted(pool_index.keys()):
        if off in emitted_body_offs:
            continue
        raw, _ = pool_index[off]
        if raw.startswith(MARKER_VOICE) and bytes([0]) not in raw:
            # pure voice ids not referenced (rare)
            continue
        # rebuild logical span for unreferenced heads only
        if sc.string_pool and 0 <= off < len(sc.string_pool):
            span, end = extract_logical_raw(sc.string_pool, off)
            # mark physical entries consumed
            p = off
            while p < end:
                emitted_body_offs.add(p)
                z = sc.string_pool.find(bytes([0]), p)
                if z < 0 or z >= end:
                    break
                p = z + 1
            for kind, seg_off, payload in iter_span_segments(sc.string_pool, off, end):
                if seg_off in emitted_body_offs and seg_off != off:
                    continue
                if kind == "voice":
                    leftover.append((seg_off, None, payload))  # voice marker
                else:
                    # Prefer physical merge so ruby splits stay one editable body.
                    if pool_index and seg_off in pool_index:
                        body, chain_offs, _info = merge_ruby_continuation_chain(
                            pool_index, seg_off, sc.encoding, referenced_text_offs
                        )
                        leftover.append((seg_off, body, None))
                        emitted_body_offs.update(chain_offs)
                    else:
                        info = analyze_pool_entry(payload, sc.encoding)
                        leftover.append((seg_off, info.get("text", ""), None))
        else:
            info = analyze_pool_entry(raw, sc.encoding)
            if info.get("kind") == "voice":
                continue
            leftover.append((off, info.get("text", ""), None))
    if leftover:
        lines.append("")
        lines.append("; ============================================================")
        lines.append("; Soft texts (pool bodies not OP_TEXT-referenced; edit these bodies)")
        lines.append("; soft => updates .pool body only, does not emit code bytes")
        lines.append("; controls: $e=07 04; mid 07 06(+0A*) => textp lines; <rb \"yomi\">kanji</rb>=07 01")
        lines.append("; ============================================================")
        for item in leftover:
            if len(item) == 2:
                off, body = item
                lines.extend(format_text_with_textp(off, body, ", soft"))
            else:
                off, body, voice = item
                if voice is not None:
                    lines.append('    voice %d, "%s"%s' % (off, voice, _name_annot(voice)))
                else:
                    lines.extend(format_text_with_textp(off, body or "", ", soft"))

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
    text = emit_asm(sc)
    out_dir = os.path.dirname(os.path.abspath(out_path))
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    with open(out_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    text_count = sum(1 for ins in sc.instrs if ins.opcode == OP_TEXT)
    print("[ok] %s -> %s" % (in_path, out_path))
    print(
        "     globals=%d labels=%d exprs=%d code=%d pool=%d instrs=%d texts=%d"
        % (
            len(sc.globals),
            len(sc.labels),
            len(sc.exprs),
            len(sc.code),
            len(sc.string_pool),
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
    ap = argparse.ArgumentParser(description="Disassemble sispara2/Popotan exec.dat")
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
