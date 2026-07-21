"""Opcode definitions for Fortune Cookie Select script VM (sub_40A4D0).

Architecture
------------
- Line-oriented Harvard-like script machine.
- Each decrypted line is ONE instruction: first byte = opcode, remainder = operand payload.
- There is no multi-byte instruction stream; PC is a line index (this+1712).
- Jump targets are label names (ASCII) looked up by scanning lines with opcode 0x21 / related.

Operand payload conventions used by the engine
----------------------------------------------
- ASCII / Shift-JIS (CP932) text is stored raw in the payload after fixed control bytes.
- Comma ',' (0x2C) is the primary field separator (sub_40E040).
- Space ' ' (0x20) is used as a secondary group separator on some complex ops (0x25, 0xC8).
- Many numeric immediates are stored as 3 hex ASCII digits (decoded by sub_40D670 mode 100).
- Some control bytes are stored as raw integers with offset encoding (value + 20, etc.).

Text presentation
-----------------
- CP932-decodable runs are shown as text.
- Bytes that cannot be safely represented use {{XX}} placeholders (two hex digits).
- Labels: lines with opcode 0x21 ("!") define loc names; jumps reference them.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Sequence, Tuple


# ---------------------------------------------------------------------------
# Opcode table
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class OpcodeInfo:
    code: int
    mnemonic: str
    summary: str
    # operand_schema is documentary; actual parse is in disassembler helpers.
    operand_schema: str
    # True if this opcode defines a label name taken from payload
    is_label: bool = False
    # True if payload contains jump/call target label names
    has_label_refs: bool = False


OPCODES: Dict[int, OpcodeInfo] = {}


def _op(
    code: int,
    mnemonic: str,
    summary: str,
    operand_schema: str = "raw",
    is_label: bool = False,
    has_label_refs: bool = False,
) -> None:
    OPCODES[code] = OpcodeInfo(
        code=code,
        mnemonic=mnemonic,
        summary=summary,
        operand_schema=operand_schema,
        is_label=is_label,
        has_label_refs=has_label_refs,
    )


# Text / dialogue (0x14-0x1B)
_op(0x14, "TEXT", "Narration / plain text line", "text_cp932")
_op(0x15, "VOICE_TEXT", "Voice-tagged text: voice_id,text", "csv:voice,text")
_op(0x16, "NAME_TEXT", "Named line without voice: name,text", "csv:name,text")
_op(0x17, "VOICE_NAME_TEXT", "Voice + speaker + text: voice,name,text", "csv:voice,name,text")
_op(0x18, "TEXT_ALT0", "Text variant family (+0) with optional name/color fields", "text_fields")
_op(0x19, "TEXT_ALT1", "Text variant family (+1)", "text_fields")
_op(0x1A, "TEXT_ALT2", "Text variant family (+2)", "text_fields")
_op(0x1B, "TEXT_ALT3", "Text variant family (+3)", "text_fields")

# Control flow
_op(0x1E, "CALL_OR_JUMP", "Script call/jump. payload[0]=mode(1=goto label,2=load script), payload[1]=flag, rest=name[,ret]", "u8 mode; u8 flag; names", has_label_refs=True)
_op(0x1F, "CALL_SAVEPOS", "Like 0x1E but saves return position first", "u8 mode; u8 flag; names", has_label_refs=True)
_op(0x20, "RETURN", "Pop script call stack / return", "none")
_op(0x21, "LABEL", "Label definition (name follows)", "name", is_label=True)
_op(0x5D, "LABEL_ALT1", "Label-class no-op marker", "name?", is_label=True)
_op(0x5E, "LABEL_ALT2", "Label-class no-op marker", "name?", is_label=True)
_op(0x5F, "LABEL_ALT3", "Label-class no-op marker", "name?", is_label=True)
_op(0x75, "LABEL_ALT4", "Label-class no-op marker", "name?", is_label=True)

# Conditions / choices
_op(0x22, "IF", "Conditional branch on variables. layout: cmp_mode, lhs_mode, rhs_mode, fields...", "cond_fields", has_label_refs=True)
_op(0x23, "SELECT", "Player choice menu. payload[0]=count_enc, payload[1]=layout, then choice entries", "select_entries", has_label_refs=True)

# Layer / CG / character graphics
_op(0x24, "CGMODE_SETUP0", "CG/omake setup variant 0", "complex")
_op(0x25, "CGMODE_SETUP1", "CG/omake / multi-button setup (menu buttons)", "complex", has_label_refs=True)
_op(0x26, "WAIT_CLICK0", "Wait / advance group 0", "none")
_op(0x27, "WAIT_CLICK1", "Wait / advance group 1", "none")
_op(0x28, "WAIT_CLICK2", "Wait / advance group 2", "none")

_op(0x32, "BG_LOAD", "Load background image. payload[0]=effect_enc, rest=name", "u8 effect; name")
_op(0x33, "BG_LOAD_EX", "Load background with extra param byte", "u8 a; u8 b; name")
_op(0x34, "BG_CLEAR", "Clear / swap background using name after 1 control byte", "u8; name")
_op(0x35, "BG_CLEAR_EX", "Background clear/load extended", "u8; u8; name")
_op(0x36, "BG_POS", "Background with position (hex pairs)", "u8; hex3; hex3; name")
_op(0x37, "BG_POS_EX", "Background position extended", "u8; u8; hex3; hex3; name")
_op(0x38, "BG_MOVE", "Background move (two hex coords + name)", "u8; hex3; hex3; name")
_op(0x39, "BG_MOVE_EX", "Background move extended", "u8; u8; hex3; hex3; name")
_op(0x3A, "BG_RECT", "Background rect/params (4x hex3 + name)", "u8; 4*hex3; name")
_op(0x3B, "BG_RECT_EX", "Background rect extended", "u8; u8; 4*hex3; name")
_op(0x3C, "BG_RECT2", "Background multi-param load", "u8; 4*hex3; name; extra")
_op(0x3D, "BG_RECT2_EX", "Background multi-param load extended", "u8; u8; 4*hex3; name; extra")

_op(0x46, "LAYER_IMG", "Load image to layer. payload[0]=fade, payload[1]=layer_sel, rest=name|null", "u8 fade; u8 layer; name")
_op(0x47, "LAYER_IMG_EX", "Layer image extended", "u8; u8; u8; name")
_op(0x48, "LAYER_IMG_POS", "Layer image with position params", "complex")
_op(0x49, "LAYER_IMG_POS_EX", "Layer image position extended", "complex")

_op(0x50, "CHR_SET", "Set character sprites (up to 4 names, space sep after mode)", "u8 mode; names_space_or_csv")
_op(0x51, "CHR_SET_EX", "Character set with extra control byte", "u8; u8; names")

# Effects / fades / quake
_op(0x5A, "EFFECT_STR", "Named effect string (sub_416510)", "string")
_op(0x5B, "FADE_COLOR", "Fade/color effect: 3*hex2 + control bytes", "hex; params")
_op(0x5C, "FADE_MODE", "Fade mode select", "u8 mode")

# Audio
_op(0x64, "BGM_PLAY", "Play BGM. payload[0]=vol_enc, payload[1]=param, rest=name", "u8 vol; u8 p; name")
_op(0x65, "BGM_VOL", "Set BGM volume (encoded)", "u8 vol_enc")
_op(0x66, "BGM_STOP", "Stop BGM", "none")
_op(0x69, "SE_PLAY", "Play SE (i). payload[0]=ch_enc, rest=name", "u8 ch; name")
_op(0x6A, "SE_PLAY_VOL", "Play SE with volume", "u8 ch; u8 vol; name")
_op(0x6B, "SE_STOP", "Stop SE channel group i", "none")
_op(0x6E, "VOICE_PLAY", "Play voice (n)", "u8; name")
_op(0x6F, "VOICE_STOP", "Stop voice", "none")
_op(0x73, "SND_PLAY", "Play sound type s", "u8; name")
_op(0x74, "SND_PLAY_VOL", "Play sound with volume", "u8; u8; name")
_op(0x76, "SND_STOP", "Stop sound type v", "none")
_op(0x78, "AUDIO_STOP_ALL", "Stop BGM + all SE/voice", "none")

# Variables
_op(0x82, "VAR_SET", "Assign variable. payload[0]=op_mode, payload[1]=rhs_mode, rest=lhs,rhs", "u8; u8; names")
_op(0x83, "VAR_SYNC", "Variable / system sync (sub_412920 mode1)", "none")

# Flags / system toggles
_op(0x8C, "FLAG_AA02", "Toggle byte_44AA02 (1/2)", "u8")
_op(0x8D, "WINDOW_MODE", "Window/fullscreen related", "u8")
_op(0x8E, "FLAG_AA04", "Toggle byte_44AA04", "u8")
_op(0x8F, "SKIP_FLAG", "Toggle skip flag byte_44AA00", "u8")
_op(0x90, "SYS_CALL", "System call sub_411B60(1)", "none")

# Wait / delay
_op(0x96, "WAIT_HEX", "Wait using hex duration (mode0)", "hex_digits")
_op(0x97, "WAIT_HEX1", "Wait hex duration mode1", "hex_digits")
_op(0x98, "WAIT_HEX2", "Wait hex duration mode2", "hex_digits")
_op(0x99, "WAIT_MODE3", "Wait mode3 no arg", "none")
_op(0x9A, "WAIT_MODE4", "Wait mode4", "none")
_op(0x9B, "WAIT_MODE5", "Wait mode5", "none")
_op(0x9C, "WAIT_MODE6", "Wait mode6", "none")

# Script meta
_op(0xA0, "SCRIPT_ID", "Script numeric id (atoi); also read at load for word_445044", "decimal_ascii")
_op(0xA1, "SCRIPT_TITLE", "Script title string", "text_cp932")
_op(0xA2, "MODE_SET2", "Set internal mode = 2", "none")
_op(0xA3, "MODE_SET99", "Set internal mode = 99", "none")
_op(0xA4, "MODE_CALL0", "sub_413D60(0)", "none")
_op(0xA5, "MODE_CALL1", "sub_413D60(1)", "none")

# Special UI
_op(0xC8, "CG_GALLERY", "CG gallery page definition (complex fixed+csv)", "complex", has_label_refs=True)
_op(0xD2, "RAND_GLO", "Randomize $glo000 slot 0..4", "none")


MNEMONIC_TO_OPCODE: Dict[str, int] = {info.mnemonic: code for code, info in OPCODES.items()}


def get_opcode(code: int) -> OpcodeInfo:
    if code in OPCODES:
        return OPCODES[code]
    return OpcodeInfo(
        code=code,
        mnemonic=f"OP_{code:02X}",
        summary="Unknown / unhandled opcode (still preserved raw)",
        operand_schema="raw",
    )


# ---------------------------------------------------------------------------
# Text encode / decode for asm presentation
# ---------------------------------------------------------------------------

DEFAULT_ENCODING = "cp932"


def bytes_to_display(data: bytes, encoding: str = DEFAULT_ENCODING) -> str:
    """Convert raw operand bytes to asm-display text.

    Rules (per 逆向规范.md):
    - Prefer encoding-decoded characters when the full sequence is valid.
    - Ordinary printable ASCII and encoding-valid multibyte text shown as-is.
    - Backslash and fullwidth space kept literal.
    - Non-decodable / non-printable bytes become {{XX}}.
    - '{' sequences that would collide with placeholders are escaped as {{7B}}.
    """
    if not data:
        return ""

    out: List[str] = []
    i = 0
    n = len(data)
    while i < n:
        b = data[i]
        # Try to consume a valid encoding character starting at i.
        consumed = 0
        ch = None
        # Attempt 1..4 byte sequences (CP932 uses 1 or 2).
        for L in (1, 2, 3, 4):
            if i + L > n:
                break
            chunk = data[i : i + L]
            try:
                s = chunk.decode(encoding)
            except UnicodeDecodeError:
                continue
            # Reject if re-encoding is not identical (avoid lossy)
            try:
                if s.encode(encoding) != chunk:
                    continue
            except UnicodeEncodeError:
                continue
            # Only accept if all codepoints are "display-safe".
            if not _is_display_safe_str(s):
                continue
            ch = s
            consumed = L
            break

        if ch is not None:
            for c in ch:
                if c == "{":
                    # prevent ambiguity with placeholders
                    out.append("{{7B}}")
                elif c == "}":
                    out.append("{{7D}}")
                else:
                    out.append(c)
            i += consumed
            continue

        # Fallback: single raw byte placeholder
        out.append(f"{{{{{b:02X}}}}}")
        i += 1
    return "".join(out)


def _is_display_safe_str(s: str) -> bool:
    for c in s:
        o = ord(c)
        if c in "\t\r":
            return False
        if c == "\n":
            return False
        # Allow space and typical printable + fullwidth
        if o < 0x20:
            return False
        # Allow DEL? no
        if o == 0x7F:
            return False
    return True


def display_to_bytes(text: str, encoding: str = DEFAULT_ENCODING) -> bytes:
    """Inverse of bytes_to_display."""
    out = bytearray()
    i = 0
    n = len(text)
    while i < n:
        if text.startswith("{{", i):
            end = text.find("}}", i + 2)
            if end < 0:
                raise ValueError(f"unclosed placeholder at {i}: {text[i:i+20]!r}")
            body = text[i + 2 : end]
            if len(body) == 2 and all(c in "0123456789abcdefABCDEF" for c in body):
                out.append(int(body, 16))
                i = end + 2
                continue
            # multi-byte hex like XX:YY not used for single-byte form
            if ":" in body:
                parts = body.split(":")
                for p in parts:
                    if len(p) != 2:
                        raise ValueError(f"bad placeholder {body!r}")
                    out.append(int(p, 16))
                i = end + 2
                continue
            raise ValueError(f"bad placeholder {{{{{body}}}}}")
        # take one unicode char and encode
        c = text[i]
        try:
            out += c.encode(encoding)
        except UnicodeEncodeError as e:
            raise ValueError(f"cannot encode {c!r} with {encoding}") from e
        i += 1
    return bytes(out)


def is_label_opcode(code: int) -> bool:
    return get_opcode(code).is_label


def extract_label_name(line: bytes) -> Optional[str]:
    """If line defines a label, return its name (ASCII/cp932 decoded payload)."""
    if not line:
        return None
    op = line[0]
    if not is_label_opcode(op):
        return None
    payload = line[1:]
    if not payload:
        return None
    # Labels in this game are pure ASCII identifiers.
    try:
        name = payload.decode("ascii")
    except UnicodeDecodeError:
        name = bytes_to_display(payload, "cp932")
    return name


def find_label_refs(line: bytes) -> List[str]:
    """Best-effort extraction of label/script name references for annotation."""
    if not line:
        return []
    op = line[0]
    info = get_opcode(op)
    if not info.has_label_refs:
        return []
    payload = line[1:]
    refs: List[str] = []

    if op in (0x1E, 0x1F):
        # mode, flag, then name[,retname]
        if len(payload) >= 3:
            rest = payload[2:]
            for part in rest.split(b","):
                if part and all(32 <= b < 127 for b in part):
                    refs.append(part.decode("ascii"))
    elif op == 0x21:
        pass
    elif op == 0x22:
        # last field often target
        parts = payload.split(b" ")
        # structure messy; pick ASCII tokens that look like labels
        for tok in _ascii_tokens(payload):
            if tok and tok[0].isalpha():
                refs.append(tok)
    elif op == 0x23:
        # choice entries contain ,label
        for tok in _ascii_tokens(payload):
            if tok and tok[0].isalpha() and not tok.startswith("$"):
                refs.append(tok)
    elif op in (0x25, 0xC8):
        for tok in _ascii_tokens(payload):
            if tok and tok[0].isalpha() and not tok.startswith("$") and len(tok) >= 3:
                refs.append(tok)
    return refs


def _ascii_tokens(data: bytes) -> List[str]:
    out: List[str] = []
    cur = bytearray()
    for b in data:
        if 48 <= b <= 57 or 65 <= b <= 90 or 97 <= b <= 122 or b in (0x5F,):
            cur.append(b)
        else:
            if cur:
                out.append(cur.decode("ascii"))
                cur.clear()
    if cur:
        out.append(cur.decode("ascii"))
    return out
