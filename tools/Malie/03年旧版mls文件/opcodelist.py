# -*- coding: utf-8 -*-
"""
Malie Scenario (.mls) opcode / format definition.

.mls on-disk layout (from bokudvd.exe / sub_42E6F0):
  [0:13]  magic  = b"MalieScenario"
  [13:]   zlib  = zlib.compress(script_bytes, level=6)   # CMF/FLG = 78 9C

The decompressed payload is a CP932 (Shift_JIS) Malie scenario *source* stream,
not a classic fixed-length bytecode VM image. The game tokenizes this text
(sub_42ED30 / sub_423850) and compiles it to an internal bytecode buffer
(sub_4292F0). For zero-mutation tooling we treat the decompressed source as the
canonical instruction stream and model each source line as one semantic unit.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

MAGIC = b"MalieScenario"
MAGIC_LEN = 13
ZLIB_LEVEL = 6
DEFAULT_ENCODING = "cp932"
DEFAULT_NEWLINE = "\r\n"

# ---------------------------------------------------------------------------
# Token / statement classes emitted by the source-level disassembler
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class OpcodeDef:
    opcode: str
    bytecode: int
    length: str
    operands: Tuple[str, ...]
    description: str


# Source-level "opcodes" (one statement / line unit). Numeric ids are stable
# labels used only for documentation; they are not stored in .mls files.
OPCODES: Dict[str, OpcodeDef] = {
    "EMPTY": OpcodeDef("EMPTY", 0x00, "0 (blank line)", (), "Blank line (CRLF only)."),
    "LABEL": OpcodeDef("LABEL", 0x01, "var", ("name",), "Label definition: name:"),
    "CMD": OpcodeDef(
        "CMD",
        0x02,
        "var",
        ("name", "args*", "term"),
        "Command statement: &name [args...][term]. term is usually ' ;'.",
    ),
    "DIALOG": OpcodeDef(
        "DIALOG",
        0x03,
        "var",
        ("channel", "speaker", "voice?", "text"),
        "Speaker line: #channel speaker [(voice)] text",
    ),
    "TEXT": OpcodeDef(
        "TEXT",
        0x04,
        "var",
        ("text",),
        "Narrative / free text line (may contain inline $e page mark).",
    ),
    "GOTO": OpcodeDef(
        "GOTO",
        0x05,
        "var",
        ("target",),
        "Jump command alias for &goto target ; (label-aware).",
    ),
    "COMMENT": OpcodeDef(
        "COMMENT",
        0x06,
        "var",
        ("text",),
        "/* ... */ comment block collapsed to one unit (rare in shipped .mls).",
    ),
    "RAW": OpcodeDef(
        "RAW",
        0xFF,
        "var",
        ("bytes",),
        "Fallback for undecodable byte runs; uses {{XX}} placeholders.",
    ),
}

# Compiler &-commands (binary search table off_467BCC, indices 1..39).
COMPILER_COMMANDS: Tuple[str, ...] = (
    "bgm",
    "call",
    "charclear",
    "charshow",
    "clear",
    "cmp",
    "end",
    "fadd",
    "fcall",
    "fjump",
    "fload",
    "fmax",
    "fpop",
    "fpush",
    "fselect",
    "fselect_time",
    "fstore",
    "gcall",
    "handler",
    "handler_clear",
    "handler_jump",
    "handler_set",
    "handler_wait",
    "image",
    "image_cache",
    "jump",
    "mask",
    "ol",
    "page",
    "pause",
    "play",
    "screen_set",
    "screen_take",
    "sound",
    "system_menu",
    "timer_clear",
    "timer_wait",
    "tjump",
    "voice",
)

# High-level Malie source macros / keywords used by the decompiler dump path
# (off_468338, tokens 101..212) and observed in scenario/*.mls.
SOURCE_KEYWORDS: Tuple[str, ...] = (
    "CG",
    "CG_BG",
    "FO",
    "IF",
    "PARAMATER",
    "PARAMATAR",
    "PARAMETER",
    "GOTO",
    "JUMP",
    "CJUMP",
    "SOUND",
    "SOUNDSTOP",
    "SE",
    "WAIT",
    "CHAR",
    "CHARCLEAR",
    "GOTOTEXT",
    "JUMPTEXT",
    "FONTSIZE",
    "FONTPOSITION",
    "SOUND_CTRL",
    "TEXTMODE",
    "TEXTSPEED",
    "THEN",
    "SLOW",
    "NORMAL",
    "LOOP",
    "OFF",
    "ON",
    "CLEAR",
    "DAY",
    "FI",
    "SABUN",
    "AUTO",
    "SL",
    "SOUNDSTOPO",
    "ENDING",
    "BADEND",
    "SUONDSTOP",
    "HIRUYASUMI",
    "FO_WHITE",
    "OL",
    "SOUNYUUKA",
    "ALIAS",
    "MACRO",
    "WO",
    "CUT",
    "SHAKE",
    "FLASH",
    "FACE",
    "MAP",
    "BREAK",
    "TIME",
    "TIMECLEAR",
    "END",
    "FL",
    "CHARMODE",
    "VOICE",
    "SYNC",
    "PAUSE",
    "SHADEFO",
    "CALL",
    "SAVEINFO",
    "CJUMPTEXT",
    "LO",
    "L",
    "C",
    "R",
    "RO",
    "LBO",
    "LB",
    "CB",
    "RB",
    "RBO",
    "CHARMOVE",
    "MAPRETURN",
    "MAPPOS",
    "STATUS",
    "MAPLINK",
    "MAPEND",
    "RNDJUMP",
    "WAITMS",
    "CHANGE",
    "CHECK",
    "TIMERCLEAR",
    "TIMERWAIT",
    "TIMER",
    "CANCELJUMP",
    "PRIVATE",
    "LEFT_TOP",
    "LEFT_CENTER",
    "LEFT_DOWN",
    "CENTER_TOP",
    "CENTER",
    "CENTER_DOWN",
    "RIGHT_TOP",
    "RIGHT_CENTER",
    "RIGHT_DOWN",
    "CG_H",
    "BU",
    "TD",
    "FONTCOLOR",
    "FS",
    "FC",
    "BLACK",
    "BLUE",
    "RED",
    "GREEN",
    "YELLOW",
    "WHITE",
    "SCENE_BEGIN",
    "SCENE_END",
)

# Commands observed in shipped scenario/*.mls (lower-case source form).
SCENARIO_COMMANDS: Tuple[str, ...] = (
    "char",
    "cg",
    "wait",
    "sound",
    "soundstop",
    "cg_bg",
    "charclear",
    "charmode",
    "fo",
    "se",
    "goto",
    "fontsize",
    "fontposition",
    "cg_h",
    "textmode",
    "textspeed",
    "sound_ctrl",
    "waitms",
    "end",
)

# Commands that transfer control; targets are label-ized in asm.
JUMP_COMMANDS = frozenset(
    {
        "goto",
        "jump",
        "cjump",
        "fjump",
        "tjump",
        "rndjump",
        "gototext",
        "jumptext",
        "cjumptext",
        "handler_jump",
        "canceljump",
        "call",
        "fcall",
        "gcall",
    }
)

# ---------------------------------------------------------------------------
# Safe text codec helpers ({{XX}} / {{XX:YY:...}} placeholders)
# ---------------------------------------------------------------------------

# Printable enough to keep as text. Spec: keep backslash and fullwidth space.
_KEEP_CTRL = {0x09}  # TAB only; CR/LF are line structure, not string content


def is_safe_text_byte(b: int) -> bool:
    if b in _KEEP_CTRL:
        return True
    if 0x20 <= b <= 0x7E:
        return True
    # Lead/trail bytes of CP932 are handled at decode level; single unsafe
    # C0/C1 controls (except TAB) become placeholders.
    if b < 0x20 or b == 0x7F:
        return False
    return True


def bytes_to_display(data: bytes, encoding: str = DEFAULT_ENCODING) -> str:
    """Decode script bytes to a semantic string with {{XX}} placeholders."""
    out: List[str] = []
    i = 0
    n = len(data)
    while i < n:
        b = data[i]
        # CRLF / LF should not appear inside a line payload.
        if b in (0x0A, 0x0D):
            out.append(f"{{{{{b:02X}}}}}")
            i += 1
            continue
        if b < 0x20 and b not in _KEEP_CTRL:
            out.append(f"{{{{{b:02X}}}}}")
            i += 1
            continue
        if b == 0x7F:
            out.append("{{7F}}")
            i += 1
            continue
        # Try CP932 multi-byte
        if b >= 0x80:
            # CP932: lead 0x81-0x9F / 0xE0-0xFC, trail 0x40-0x7E / 0x80-0xFC
            if i + 1 < n and (
                (0x81 <= b <= 0x9F) or (0xE0 <= b <= 0xFC)
            ):
                pair = data[i : i + 2]
                try:
                    ch = pair.decode(encoding)
                    # decoded length 1 (or rare 2) is fine
                    out.append(ch)
                    i += 2
                    continue
                except UnicodeDecodeError:
                    out.append(f"{{{{{pair[0]:02X}}}}}")
                    i += 1
                    continue
            # single high byte that is not a valid lead
            out.append(f"{{{{{b:02X}}}}}")
            i += 1
            continue
        # ASCII
        out.append(chr(b))
        i += 1
    return "".join(out)


def display_to_bytes(text: str, encoding: str = DEFAULT_ENCODING) -> bytes:
    """Encode semantic string back to bytes, expanding {{XX}} / {{XX:YY}}."""
    out = bytearray()
    i = 0
    n = len(text)
    while i < n:
        if text.startswith("{{", i):
            end = text.find("}}", i + 2)
            if end < 0:
                raise ValueError(f"Unclosed placeholder near: {text[i:i+16]!r}")
            body = text[i + 2 : end]
            if not body:
                raise ValueError("Empty placeholder {{}}")
            parts = body.split(":")
            for part in parts:
                part = part.strip()
                if len(part) != 2:
                    raise ValueError(f"Bad placeholder byte: {part!r}")
                out.append(int(part, 16))
            i = end + 2
            continue
        # accumulate a run of normal chars
        j = i
        while j < n and not text.startswith("{{", j):
            j += 1
        chunk = text[i:j]
        out.extend(chunk.encode(encoding))
        i = j
    return bytes(out)


def quote_asm_string(s: str) -> str:
    """Quote a string for asm.txt. No \\x escapes; only \" and \\ doubling."""
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def unquote_asm_string(token: str) -> str:
    if len(token) < 2 or token[0] != '"' or token[-1] != '"':
        raise ValueError(f"Expected quoted string, got: {token!r}")
    body = token[1:-1]
    out: List[str] = []
    i = 0
    while i < len(body):
        if body[i] == "\\" and i + 1 < len(body):
            nxt = body[i + 1]
            if nxt in ('\\', '"'):
                out.append(nxt)
                i += 2
                continue
            # Spec: ordinary backslash is kept as text, not \\xNN.
            out.append("\\")
            i += 1
            continue
        out.append(body[i])
        i += 1
    return "".join(out)


# ---------------------------------------------------------------------------
# Line classification helpers
# ---------------------------------------------------------------------------

import re

_RE_LABEL = re.compile(r"^([A-Za-z_][A-Za-z0-9_@\$]*)\s*:\s*$")
_RE_CMD = re.compile(r"^&([A-Za-z0-9_]+)(.*)$")
_RE_DIALOG = re.compile(
    r"^#(\d+)(.*)$"
)
_RE_VOICE = re.compile(
    r"^(?P<speaker>.*?)\s*\((?P<voice>[^)]+)\)(?P<text>.*)$"
)


def split_script_lines(script_text: str) -> Tuple[List[str], bool]:
    """Split on CRLF. Returns (lines_without_terminators, ends_with_newline)."""
    if not script_text:
        return [], False
    parts = script_text.split("\r\n")
    if parts and parts[-1] == "":
        return parts[:-1], True
    return parts, False


def join_script_lines(lines: Sequence[str], ends_with_newline: bool) -> str:
    text = "\r\n".join(lines)
    if ends_with_newline:
        text += "\r\n"
    return text


def parse_command_line(line: str) -> Optional[dict]:
    m = _RE_CMD.match(line)
    if not m:
        return None
    name = m.group(1)
    rest = m.group(2)
    # Detect terminator forms used by this game's scripts.
    term = ""
    body = rest
    if body.endswith(" ; "):
        term = " ; "
        body = body[: -len(term)]
    elif body.endswith(" ;"):
        term = " ;"
        body = body[: -len(term)]
    elif body.endswith(";"):
        term = ";"
        body = body[: -len(term)]
    # body is usually " arg1 arg2" or empty
    args = body.strip()
    # Preserve exact leading spacing of args for zero-mutation by storing
    # the raw middle (between name and term).
    raw_middle = rest[: len(rest) - len(term)] if term else rest
    return {
        "name": name,
        "args": args,
        "raw_middle": raw_middle,
        "term": term,
    }


def parse_dialog_line(line: str) -> Optional[dict]:
    m = _RE_DIALOG.match(line)
    if not m:
        return None
    channel = int(m.group(1))
    rest = m.group(2)
    voice = None
    speaker = ""
    text = rest
    vm = _RE_VOICE.match(rest)
    if vm:
        speaker = vm.group("speaker")
        voice = vm.group("voice")
        text = vm.group("text")
    else:
        # "#0恭生 「...」" — speaker is run of non-space / non-「 chars? Keep
        # simple: split on first fullwidth/half space before quote, else take
        # non-quote prefix.
        # Most lines: speaker then space? Actually "#0恭生 「" no space.
        # Pattern: optional speaker then dialog text starting with 「 or "
        mq = re.match(r"^(?P<speaker>[^「\"“]*)(?P<text>[「\"“].*)$", rest)
        if mq:
            speaker = mq.group("speaker")
            text = mq.group("text")
        else:
            speaker = rest
            text = ""
    return {
        "channel": channel,
        "speaker": speaker,
        "voice": voice,
        "text": text,
    }


def is_jump_command(name: str) -> bool:
    return name.lower() in JUMP_COMMANDS


def label_name_for_offset(offset: int) -> str:
    return f"loc_{offset:08X}"


def container_pack(script_bytes: bytes) -> bytes:
    import zlib

    return MAGIC + zlib.compress(script_bytes, ZLIB_LEVEL)


def container_unpack(data: bytes) -> bytes:
    import zlib

    if len(data) < MAGIC_LEN:
        raise ValueError("File too small for MalieScenario header")
    if data[:MAGIC_LEN] != MAGIC:
        # allow raw decompressed payload for debugging
        if data[:2] in (b"\x78\x9c", b"\x78\x01", b"\x78\xda"):
            return zlib.decompress(data)
        # bare source
        if data[:1] in (b"&", b"#", b"\x81", b"\x82", b"\x83") or b"\r\n" in data[:200]:
            return data
        raise ValueError(
            f"Bad magic: {data[:MAGIC_LEN]!r}, expected {MAGIC!r}"
        )
    return zlib.decompress(data[MAGIC_LEN:])
