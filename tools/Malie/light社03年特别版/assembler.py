# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import sys

# MUST run before importing dataclasses/inspect/dis: local opcode.py shadows stdlib.
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
while _SCRIPT_DIR in sys.path:
    sys.path.remove(_SCRIPT_DIR)
# also drop cwd entry if it points here
_sys_path_clean = []
for _p in sys.path:
    if _p in ("", ".") and os.path.abspath(os.getcwd()) == _SCRIPT_DIR:
        continue
    _sys_path_clean.append(_p)
sys.path[:] = _sys_path_clean
import struct
import argparse
import re
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


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
    # restore script dir at end for relative resources if needed
    if _SCRIPT_DIR not in sys.path:
        sys.path.append(_SCRIPT_DIR)
    return mod


_opcode = _load_opcode()
EXPR_T = _opcode.EXPR_T
EXPR_U = _opcode.EXPR_U
EXPR_V = _opcode.EXPR_V
EXPR_W = _opcode.EXPR_W
expr_kind_from_name = _opcode.expr_kind_from_name
op_code = _opcode.op_code
op_info = _opcode.op_info
type_kind_from_name = _opcode.type_kind_from_name
MARKER_NAME1 = _opcode.MARKER_NAME1
MARKER_NAME2 = _opcode.MARKER_NAME2
MARKER_VOICE = _opcode.MARKER_VOICE
MARKER_RUBY = _opcode.MARKER_RUBY
MARKER_NL = _opcode.MARKER_NL
MARKER_PLAIN = _opcode.MARKER_PLAIN
MARKER_VOICED = _opcode.MARKER_VOICED
TAIL_PLAIN = _opcode.TAIL_PLAIN
TAIL_VOICED = _opcode.TAIL_VOICED
TAIL_WAIT = getattr(_opcode, "TAIL_WAIT", bytes([0x06]))
TOKEN_WAIT = getattr(_opcode, "TOKEN_WAIT", "%haato")
TOKEN_VOICED_MID = getattr(_opcode, "TOKEN_VOICED_MID", "%pv")
TOKEN_NL = getattr(_opcode, "TOKEN_NL", "$e")
TOKEN_LINE = getattr(_opcode, "TOKEN_LINE", "%p")
MARKER_MUSIC = getattr(_opcode, "MARKER_MUSIC", bytes([0xFF, 0x00]))
TOKEN_MUSIC = getattr(_opcode, "TOKEN_MUSIC", "♪")

DEFAULT_ENCODING = "cp932"
PLACEHOLDER_RE = re.compile(r"\{\{([0-9A-Fa-f]{2})(?::([0-9A-Fa-f]{2}))?\}\}")


def _normalize_encoding(encoding: str) -> str:
    enc = (encoding or "").lower().replace("-", "_")
    if enc in ("shift_jis", "shiftjis", "sjis", "ms932", "windows_31j"):
        return "cp932"
    return encoding


def encode_placeholders(text: str) -> Optional[bytes]:
    """Fast decoder for pure {{XX}} / {{XX:YY}} streams. Returns None if mixed text."""
    n = len(text)
    if n < 4 or not text.startswith("{{"):
        return None
    out = bytearray()
    j = 0
    while j < n:
        if j + 4 > n or text[j:j+2] != "{{":
            return None
        h1 = text[j+2:j+4]
        if any(c not in "0123456789abcdefABCDEF" for c in h1):
            return None
        if text.startswith("}}", j+4):
            out.append(int(h1, 16))
            j += 6
            continue
        if (
            j + 9 <= n
            and text[j+4] == ":"
            and all(c in "0123456789abcdefABCDEF" for c in text[j+5:j+7])
            and text.startswith("}}", j+7)
        ):
            out.append(int(h1, 16))
            out.append(int(text[j+5:j+7], 16))
            j += 9
            continue
        return None
    return bytes(out)


def encode_text(text: str, encoding: str) -> bytes:
    encoding = _normalize_encoding(encoding)
    out = bytearray()
    i = 0
    n = len(text)
    # Fast path for pure placeholder streams (eval blobs).
    if n >= 4 and text.startswith("{{"):
        j = 0
        tmp = bytearray()
        ok = True
        while j < n:
            if j + 4 > n or text[j] != "{" or text[j+1] != "{":
                ok = False
                break
            # XX
            h1 = text[j+2:j+4]
            if len(h1) < 2 or any(c not in "0123456789abcdefABCDEF" for c in h1):
                ok = False
                break
            if text.startswith("}}", j+4):
                tmp.append(int(h1, 16))
                j += 6
                continue
            if (
                j + 9 <= n
                and text[j+4] == ":"
                and all(c in "0123456789abcdefABCDEF" for c in text[j+5:j+7])
                and text.startswith("}}", j+7)
            ):
                tmp.append(int(h1, 16))
                tmp.append(int(text[j+5:j+7], 16))
                j += 9
                continue
            ok = False
            break
        if ok and j == n:
            return bytes(tmp)
    while i < n:
        if text.startswith("{{VOICE:", i):
            m = re.match(r"\{\{VOICE:([^}]*)\}\}", text[i:])
            if not m:
                raise ValueError("bad VOICE token near %r" % text[i:i+20])
            out.extend(MARKER_VOICE)
            out.extend(m.group(1).encode("ascii", errors="strict"))
            # m was matched against text[i:], so convert to absolute index.
            j = i + m.end()
            # Only emit voice-id terminator when more payload follows in this entry.
            # At entry end the physical pool NUL terminates the id (common 0706 0A 0708 id).
            if j < n:
                out.append(0)
            i = j
            continue
        if text.startswith("{{", i):
            m = PLACEHOLDER_RE.match(text, i)
            if not m:
                raise ValueError("bad placeholder near %r" % text[i : i + 16])
            out.append(int(m.group(1), 16))
            if m.group(2):
                out.append(int(m.group(2), 16))
            i = m.end()
            continue
        j = i
        while j < n and not text.startswith("{{", j):
            j += 1
        if j > i:
            chunk = text[i:j]
            try:
                out.extend(chunk.encode(encoding))
            except UnicodeEncodeError as e:
                bad = chunk[e.start : e.end]
                raise ValueError(
                    "cannot encode %r with %s (game pool is cp932). "
                    "Use Japanese-compatible kanji / fullwidth, or raw {{XX}} bytes. "
                    "Context: %r"
                    % (bad, encoding, chunk[max(0, e.start - 8) : e.end + 8])
                ) from e
        i = j
    return bytes(out)



def encode_semantic_text(text: str, encoding: str) -> bytes:
    """Encode dialogue with crimson markers (IDA sub_434A80/434810).

    $e -> 07 04
    %p -> 07 06 (mid-entry)
    %haato -> 0x06
    <rb "yomi">ji</rb> -> 07 01 ji 0A yomi [00 if more text follows]
    $1/$2 -> 07 0C 01/02
    {{XX}} -> raw
    """
    encoding = _normalize_encoding(encoding)
    out = bytearray()
    i = 0
    n = len(text or "")
    while i < n:
        if text.startswith("$1", i):
            out.extend(MARKER_NAME1); i += 2; continue
        if text.startswith("$2", i):
            out.extend(MARKER_NAME2); i += 2; continue
        if text.startswith(TOKEN_NL, i):
            out.extend(MARKER_NL); i += len(TOKEN_NL); continue
        if text.startswith(TOKEN_MUSIC, i):
            out.extend(MARKER_MUSIC); i += len(TOKEN_MUSIC); continue
        if text.startswith(TOKEN_VOICED_MID, i):
            # Mid voiced break: 07 09 07 06 + optional bare 0A layout from following \n
            out.extend(TAIL_VOICED)
            i += len(TOKEN_VOICED_MID)
            while i < n and text[i] == "\n":
                out.append(0x0A)
                i += 1
            continue
        if text.startswith(TOKEN_LINE, i):
            # legacy token still accepted
            out.extend(MARKER_PLAIN); i += len(TOKEN_LINE); continue
        if text[i] == "\n":
            # Readable mid-entry breaks restored as 07 06 [0A*]
            # multiple newlines -> 07 06 + same number of 0A
            # single newline    -> 07 06 0A if next starts a new visual line, else 07 06
            j = i
            while j < n and text[j] == "\n":
                j += 1
            n_nl = j - i
            out.extend(MARKER_PLAIN)
            if n_nl >= 2:
                out.extend(bytes([0x0A]) * n_nl)
            else:
                rest = text[j:]
                need_0a = False
                if rest:
                    ch0 = rest[0]
                    if ord(ch0) == 0x3000:  # ideographic space
                        need_0a = True
                    elif ch0 in "「『（":
                        need_0a = True
                    elif rest.startswith("{{") or rest.startswith("$e") or rest.startswith("<rb "):
                        need_0a = True
                if need_0a:
                    out.append(0x0A)
            i = j
            continue

        if text.startswith(TOKEN_WAIT, i):
            out.extend(TAIL_WAIT); i += len(TOKEN_WAIT); continue
        if text.startswith('<rb "', i):
            m = re.match(r'<rb "([^"]*)">([^<]*)</rb>', text[i:])
            if not m:
                raise ValueError("bad ruby tag near %r" % text[i:i+40])
            reading, base = m.group(1), m.group(2)
            out.extend(MARKER_RUBY)
            out.extend(encode_text(base, encoding))
            out.append(0x0A)
            out.extend(encode_text(reading, encoding))
            j = i + m.end()
            if j < n:
                # reading is C-string; outer text continues after NUL (IDA sub_434A80)
                out.append(0)
            i = j
            continue
        if text.startswith("{{VOICE:", i):
            m = re.match(r"\{\{VOICE:([^}]*)\}\}", text[i:])
            if not m:
                raise ValueError("bad VOICE token near %r" % text[i:i+20])
            out.extend(MARKER_VOICE)
            out.extend(m.group(1).encode("ascii", errors="strict"))
            # m was matched against text[i:], so convert to absolute index.
            j = i + m.end()
            # Only emit voice-id terminator when more payload follows in this entry.
            # At entry end the physical pool NUL terminates the id (common 0706 0A 0708 id).
            if j < n:
                out.append(0)
            i = j
            continue
        if text.startswith("{{", i):
            m = PLACEHOLDER_RE.match(text, i)
            if not m:
                raise ValueError("bad placeholder near %r" % text[i:i+16])
            out.append(int(m.group(1), 16))
            if m.group(2):
                out.append(int(m.group(2), 16))
            i = m.end(); continue
        j = i + 1
        while j < n and text[j] != "\n" and not (
            text.startswith("$1", j) or text.startswith("$2", j)
            or text.startswith(TOKEN_NL, j) or text.startswith(TOKEN_LINE, j)
            or text.startswith(TOKEN_VOICED_MID, j)
            or text.startswith(TOKEN_WAIT, j) or text.startswith("{{", j)
            or text.startswith('<rb "', j) or text.startswith(TOKEN_MUSIC, j)
        ):
            j += 1
        chunk = text[i:j].replace('""', '"')
        if chunk:
            out.extend(encode_text(chunk, encoding))
        i = j
    return bytes(out)


def encode_pool_entry(kind: str, text: str, encoding: str, tail: str = "none", voice_id: str = "", tail_hex: str = "") -> bytes:
    """Build one pool entry body (without trailing NUL)."""
    if kind == "voice":
        return MARKER_VOICE + (voice_id or text or "").encode("ascii", errors="strict")
    if kind == "raw":
        return encode_text(text or "", encoding)
    body = encode_semantic_text(text or "", encoding)
    if tail_hex:
        body = body + bytes.fromhex(tail_hex)
    elif tail == "voiced":
        body = body + TAIL_VOICED
    elif tail == "plain":
        body = body + TAIL_PLAIN
    return body




# Name window setter: FrameLayer_SendMessage with fixed template, variable cp932 name.
# Blob layout: PREFIX + 0x09 + name_bytes + 0x00 + SUFFIX
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
    payload = mid[:-1]  # strip NUL
    if payload.startswith(b"\x09"):
        payload = payload[1:]
    try:
        return payload.decode(_normalize_encoding(encoding))
    except Exception:
        try:
            return payload.decode(_normalize_encoding(encoding), errors="replace")
        except Exception:
            return "".join("{{%02X}}" % b for b in payload)


def encode_name_setter(name: str, encoding: str) -> bytes:
    """Build the exact FrameLayer_SendMessage name-setter eval blob."""
    # Engine stores a leading 0x09 (tab) before the visible name bytes.
    payload = bytes([0x09]) + encode_text(name or "", encoding)
    return NAME_SETTER_PREFIX + payload + bytes([0]) + NAME_SETTER_SUFFIX





def expand_wait_chain_bodies(unit: "AsmUnit") -> None:
    """Split multi-chunk bodies into consecutive pool entry bodies.

    - `%haato` -> wait-boundary chunks (legacy)
    - `<rb ...></rb>` mid-text -> IDA ruby split: head entry ends after reading;
      continuation is the next physical pool entry (sub_434A80 continues past 00)
    """
    if not unit.pool_entries:
        return
    ordered = sorted(unit.pool_entries.keys())

    def _split_parts(body: str):
        if not body:
            return [body]
        # First split haato
        if TOKEN_WAIT in body:
            return body.split(TOKEN_WAIT)
        # Split after each complete ruby if more text follows
        parts = []
        i = 0
        n = len(body)
        last = 0
        while i < n:
            if body.startswith('<rb "', i):
                m = re.match(r'<rb "[^"]*">[^<]*</rb>', body[i:])
                if not m:
                    i += 1
                    continue
                end = i + m.end()
                if end < n:
                    # head includes ruby; rest is next entry
                    parts.append(body[last:end])
                    last = end
                    i = end
                    continue
                i = end
            else:
                i += 1
        parts.append(body[last:])
        return parts if len(parts) > 1 else [body]

    heads = []
    for off, body in list(unit.pool_bodies.items()):
        if not body:
            continue
        if TOKEN_WAIT in body or ("</rb>" in body and body.find("</rb>") + 5 < len(body)):
            heads.append(off)
    heads.sort()
    for off in heads:
        body = unit.pool_bodies.get(off, "")
        parts = _split_parts(body or "")
        if len(parts) <= 1:
            continue
        try:
            i0 = ordered.index(off)
        except ValueError:
            continue
        chain = []
        j = i0
        while j < len(ordered) and len(chain) < len(parts):
            o = ordered[j]
            meta = unit.pool_entries.get(o, {})
            if isinstance(meta, dict) and meta.get("kind") == "voice":
                break
            chain.append(o)
            j += 1
        if len(chain) != len(parts):
            # not enough physical slots: keep merged (repack may change layout)
            # Prefer keeping on head only rather than crash
            continue
        for o, part in zip(chain, parts):
            unit.pool_bodies[o] = part
            meta = unit.pool_entries.get(o)
            if isinstance(meta, dict) and meta.get("kind") != "voice":
                meta["kind"] = "text"
                unit.pool_entries[o] = meta


def build_pool_and_remap(unit: "AsmUnit") -> Tuple[bytes, Dict[int, int]]:
    """Pack pool entries contiguously and return (pool_bytes, old_off->new_off).

    Fixed-offset write was the cause of in-game text pileup when translations
    grew: longer entries overwrote neighbors. Always repack in old-offset order.
    """
    expand_wait_chain_bodies(unit)
    encoding = unit.encoding
    entries = dict(unit.pool_entries)
    for off, body in unit.pool_bodies.items():
        if off not in entries:
            entries[off] = {
                "kind": "text",
                "text": body,
                "tail": "plain",
                "tail_hex": "",
                "voice_id": "",
            }

    if not entries:
        if unit.pool_blob is not None:
            return unit.pool_blob, {}
        return b"", {}

    items = sorted(entries.items(), key=lambda kv: kv[0])
    out = bytearray()
    remap: Dict[int, int] = {}
    for old_off, meta in items:
        if isinstance(meta, dict):
            kind = meta.get("kind", "text")
            body = unit.pool_bodies.get(old_off, meta.get("text", ""))
            if kind == "voice":
                body = ""
            raw = encode_pool_entry(
                kind,
                body,
                encoding,
                meta.get("tail", "none"),
                meta.get("voice_id", ""),
                meta.get("tail_hex", ""),
            )
        else:
            body = unit.pool_bodies.get(old_off, str(meta))
            raw = encode_text(body, encoding)
        new_off = len(out)
        remap[old_off] = new_off
        out.extend(raw)
        out.append(0)
    return bytes(out), remap

def write_u32(buf: bytearray, v: int) -> None:
    buf.extend(struct.pack("<I", v & 0xFFFFFFFF))


def write_len_string(buf: bytearray, text: str, encoding: str) -> None:
    payload = encode_text(text, encoding) + b"\x00"
    write_u32(buf, len(payload))
    buf.extend(payload)


@dataclass
class TypeNode:
    kind: int
    value: int
    next: Optional["TypeNode"] = None


@dataclass
class GlobalVar:
    name: str
    typ: Optional[TypeNode]
    flags: int
    reserved: int
    offset: int


@dataclass
class LabelDef:
    index: int
    name: str
    offset: int


@dataclass
class ExprNode:
    kind: int
    text: Optional[str] = None
    value: Optional[int] = None
    left: Optional["ExprNode"] = None
    right: Optional["ExprNode"] = None


@dataclass
class Instr:
    mnemonic: str
    kind: str = "none"
    text: Optional[str] = None
    imm: Optional[int] = None
    label: Optional[str] = None
    expr_index: Optional[int] = None
    labels_here: List[str] = field(default_factory=list)
    raw: Optional[bytes] = None


@dataclass
class AsmUnit:
    encoding: str = DEFAULT_ENCODING
    data_size: int = 0
    globals: List[GlobalVar] = field(default_factory=list)
    label_defs: List[LabelDef] = field(default_factory=list)
    label_name_to_index: Dict[str, int] = field(default_factory=dict)
    exprs: Dict[int, ExprNode] = field(default_factory=dict)
    instrs: List[Instr] = field(default_factory=list)
    pool_blob: Optional[bytes] = None
    pool_entries: Dict[int, dict] = field(default_factory=dict)
    pool_bodies: Dict[int, str] = field(default_factory=dict)  # editable bodies from code text
    pool_size: int = 0


def strip_comment(line: str) -> str:
    out = []
    in_str = False
    i = 0
    while i < len(line):
        c = line[i]
        if in_str:
            out.append(c)
            if c == '"':
                if i + 1 < len(line) and line[i + 1] == '"':
                    out.append('"')
                    i += 2
                    continue
                in_str = False
            i += 1
            continue
        if c == '"':
            in_str = True
            out.append(c)
            i += 1
            continue
        if c == ";":
            break
        out.append(c)
        i += 1
    return "".join(out).rstrip()


def parse_quoted(s: str, start: int = 0) -> Tuple[str, int]:
    if start >= len(s) or s[start] != '"':
        raise ValueError("expected quote: %r" % s[start:])
    i = start + 1
    out = []
    while i < len(s):
        if s[i] == '"':
            if i + 1 < len(s) and s[i + 1] == '"':
                out.append('"')
                i += 2
                continue
            return "".join(out), i + 1
        out.append(s[i])
        i += 1
    raise ValueError("unterminated string")


def parse_type_spec(spec: str) -> Optional[TypeNode]:
    spec = spec.strip()
    if not spec or spec == "void:0":
        return None
    head = None
    tail = None
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        k_s, v_s = part.split(":", 1)
        node = TypeNode(type_kind_from_name(k_s.strip()), int(v_s.strip(), 0))
        if head is None:
            head = tail = node
        else:
            tail.next = node
            tail = node
    return head


class ExprParser:
    def __init__(self, s: str):
        self.s = s
        self.i = 0

    def skip(self) -> None:
        while self.i < len(self.s) and self.s[self.i].isspace():
            self.i += 1

    def parse(self) -> ExprNode:
        self.skip()
        if self.s.startswith("T", self.i) and (
            self.i + 1 >= len(self.s) or not (self.s[self.i + 1].isalnum() or self.s[self.i + 1] == "_")
        ):
            self.i += 1
            return ExprNode(EXPR_T)
        if self.s[self.i] != "(":
            raise ValueError("expected ( : %r" % self.s[self.i :])
        self.i += 1
        self.skip()
        j = self.i
        while j < len(self.s) and (self.s[j].isalnum() or self.s[j] == "_"):
            j += 1
        kname = self.s[self.i : j]
        self.i = j
        kind = expr_kind_from_name(kname)
        self.skip()
        if kind == EXPR_T:
            if self.i < len(self.s) and self.s[self.i] == ")":
                self.i += 1
            return ExprNode(EXPR_T)
        if kind in (EXPR_U, EXPR_W):
            text, ni = parse_quoted(self.s, self.i)
            self.i = ni
            self.skip()
            if self.i >= len(self.s) or self.s[self.i] != ")":
                raise ValueError("expected )")
            self.i += 1
            return ExprNode(kind, text=text)
        if kind == EXPR_V:
            j = self.i
            if self.s[j : j + 2].lower() == "0x":
                j += 2
                while j < len(self.s) and self.s[j] in "0123456789abcdefABCDEF":
                    j += 1
            else:
                if self.s[j] == "-":
                    j += 1
                while j < len(self.s) and self.s[j].isdigit():
                    j += 1
            val = int(self.s[self.i : j], 0) & 0xFFFFFFFF
            self.i = j
            self.skip()
            if self.i >= len(self.s) or self.s[self.i] != ")":
                raise ValueError("expected )")
            self.i += 1
            return ExprNode(kind, value=val)
        left = self.parse()
        self.skip()
        right = self.parse()
        self.skip()
        if self.i >= len(self.s) or self.s[self.i] != ")":
            raise ValueError("expected ) after binary")
        self.i += 1
        return ExprNode(kind, left=left, right=right)




def _iter_logical_asm_lines(text: str):
    """Yield (lineno_start, logical_line), joining multi-line double-quoted strings."""
    lines = text.splitlines()
    i = 0
    n = len(lines)

    def still_in_string(s: str) -> bool:
        in_s = False
        j = 0
        while j < len(s):
            c = s[j]
            if in_s:
                if c == '"':
                    if j + 1 < len(s) and s[j + 1] == '"':
                        j += 2
                        continue
                    in_s = False
                j += 1
                continue
            if c == '"':
                in_s = True
            elif c == ';' and not in_s:
                break
            j += 1
        return in_s

    while i < n:
        start_no = i + 1
        buf = lines[i]
        while still_in_string(buf) and i + 1 < n:
            i += 1
            buf = buf + chr(10) + lines[i]
        yield start_no, buf
        i += 1


def parse_asm(text: str) -> AsmUnit:
    unit = AsmUnit()
    last_text_off = None  # for textp continuations
    for line in text.splitlines():
        m = re.match(r";\s*encoding:\s*(\S+)", line.strip())
        if m:
            unit.encoding = m.group(1)
            break

    pending: List[str] = []
    max_expr = -1
    for lineno, raw in _iter_logical_asm_lines(text):
        line = strip_comment(raw).strip()
        if not line:
            continue
        if line.endswith(":") and not line.startswith("."):
            pending.append(line[:-1].strip())
            continue
        if line.startswith(".data_size"):
            unit.data_size = int(line.split(None, 1)[1], 0)
            continue
        if line.startswith(".global"):
            body = line[len(".global") :].strip()
            name, pos = parse_quoted(body, 0)
            rest = body[pos:].lstrip().lstrip(",").strip()
            # type may contain commas (type=array:10,int:4); split on known keys
            fields = {"type": "", "flags": "0", "reserved": "0", "offset": "0"}
            key_re = re.compile(r"(?:^|,\s*)(type|flags|reserved|offset)=")
            matches = list(key_re.finditer(rest))
            for i, m in enumerate(matches):
                key = m.group(1)
                start = m.end()
                end = matches[i + 1].start() if i + 1 < len(matches) else len(rest)
                fields[key] = rest[start:end].strip().rstrip(",").strip()
            unit.globals.append(
                GlobalVar(
                    name,
                    parse_type_spec(fields.get("type", "")),
                    int(fields.get("flags", "0"), 0),
                    int(fields.get("reserved", "0"), 0),
                    int(fields.get("offset", "0"), 0),
                )
            )
            continue
        if line.startswith(".label_def"):
            body = line[len(".label_def") :].strip()
            m = re.match(r"(\d+)\s*,\s*", body)
            if not m:
                raise ValueError("line %d: bad label_def" % lineno)
            idx = int(m.group(1))
            body2 = body[m.end() :]
            name, pos = parse_quoted(body2, 0)
            rest = body2[pos:].lstrip().lstrip(",").strip()
            off = 0
            if rest.startswith("offset="):
                off = int(rest.split("=", 1)[1], 0)
            unit.label_defs.append(LabelDef(idx, name, off))
            unit.label_name_to_index[name] = idx
            continue
        if line.startswith(".pool_blob"):
            body = line[len(".pool_blob") :].strip()
            if not (body.startswith('"') and body.endswith('"') and len(body) >= 2):
                raise ValueError("line %d: .pool_blob needs quoted payload" % lineno)
            text = body[1:-1].replace('""', '"')
            unit.pool_blob = encode_text(text, unit.encoding)
            unit.pool_size = len(unit.pool_blob)
            continue
        if line.startswith(".pool_size"):
            body = line[len(".pool_size") :].strip()
            unit.pool_size = int(body, 0)
            continue
        if line.startswith(".pool"):
            body = line[len(".pool") :].strip()
            m = re.match(r"(\d+)\s*,\s*", body)
            if not m:
                raise ValueError("line %d: bad .pool" % lineno)
            off = int(m.group(1))
            rest = body[m.end() :].lstrip()
            # strip trailing comments
            if " ;" in rest:
                rest = rest.split(" ;", 1)[0].rstrip()
            kind = "text"
            tail = "none"
            tail_hex = ""
            voice_id = ""
            payload = ""
            # forms (reference-only preferred):
            #   voice "v_xxx"
            #   text, tail=plain|voiced
            #   text, tail_hex=...
            #   text "body", tail=...   (legacy with body)
            #   raw "..."
            if rest.startswith("voice"):
                kind = "voice"
                rest2 = rest[5:].lstrip()
                if rest2.startswith('"'):
                    payload, _ = parse_quoted(rest2, 0)
                    voice_id = payload
                else:
                    # voice v_xxx without quotes
                    voice_id = rest2.split()[0].strip()
                    payload = voice_id
            elif rest.startswith("text"):
                kind = "text"
                rest2 = rest[4:].lstrip().lstrip(",").strip()
                if rest2.startswith('"'):
                    payload, pos = parse_quoted(rest2, 0)
                    more = rest2[pos:].strip().lstrip(",").strip()
                else:
                    payload = ""
                    more = rest2
                if more.startswith("tail_hex="):
                    tail_hex = more.split("=", 1)[1].strip().split()[0]
                elif more.startswith("tail="):
                    tail = more.split("=", 1)[1].strip().split()[0]
            elif rest.startswith("raw"):
                kind = "raw"
                rest2 = rest[3:].lstrip()
                if not rest2.startswith('"'):
                    raise ValueError("line %d: bad raw pool" % lineno)
                payload, _ = parse_quoted(rest2, 0)
            elif rest.startswith('"'):
                payload, pos = parse_quoted(rest, 0)
                more = rest[pos:].strip().lstrip(",").strip()
                if more.startswith("tail_hex="):
                    tail_hex = more.split("=", 1)[1].strip().split()[0]
                elif more.startswith("tail="):
                    tail = more.split("=", 1)[1].strip().split()[0]
            else:
                # bare: text / text, tail=...
                if rest.startswith("text") or rest == "" or rest.startswith("tail"):
                    kind = "text"
                    more = rest[4:].lstrip().lstrip(",").strip() if rest.startswith("text") else rest
                    if more.startswith("tail_hex="):
                        tail_hex = more.split("=", 1)[1].strip().split()[0]
                    elif more.startswith("tail="):
                        tail = more.split("=", 1)[1].strip().split()[0]
                else:
                    raise ValueError("line %d: bad .pool body: %s" % (lineno, rest[:60]))
            unit.pool_entries[off] = {
                "kind": kind,
                "text": payload,  # optional legacy body; code text overrides via pool_bodies
                "tail": tail,
                "tail_hex": tail_hex,
                "voice_id": voice_id,
            }
            if payload and kind == "text":
                unit.pool_bodies.setdefault(off, payload)
            if payload and kind == "voice":
                unit.pool_bodies.setdefault(off, "")  # voice body not used
            continue
        if line.startswith(".expr"):
            body = line[len(".expr") :].strip()
            m = re.match(r"(\d+)\s+", body)
            if not m:
                raise ValueError("line %d: bad expr" % lineno)
            idx = int(m.group(1))
            unit.exprs[idx] = ExprParser(body[m.end() :]).parse()
            if idx > max_expr:
                max_expr = idx
            continue
        m = re.match(r"(\S+)(?:\s+(.*))?$", line)
        if not m:
            raise ValueError("line %d: bad instr" % lineno)
        mnem = m.group(1)
        arg = (m.group(2) or "").strip()
        ins = Instr(mnemonic=mnem, labels_here=list(pending))
        pending.clear()
        if mnem == "name":
            # Emits FrameLayer_SendMessage name-setter eval blob on assemble.
            if not arg.startswith('"'):
                raise ValueError("line %d: name needs quoted speaker" % lineno)
            ins.kind = "name"
            ins.text, _ = parse_quoted(arg, 0)
            unit.instrs.append(ins)
            continue
        if mnem == "say":
            # Legacy annotation form: say <voice_off>, <text_off>, "body"
            # Convert to soft text on text_off.
            m_say = re.match(
                r"(-?\d+|0x[0-9A-Fa-f]+)\s*,\s*(-?\d+|0x[0-9A-Fa-f]+)\s*,\s*(\".*)$",
                arg,
            )
            if not m_say:
                raise ValueError("line %d: say needs <voice_off>, <text_off>, \"body\"" % lineno)
            text_off = int(m_say.group(2), 0) & 0xFFFFFFFF
            body, _ = parse_quoted(m_say.group(3), 0)
            unit.pool_bodies[text_off] = body
            ins.mnemonic = "text"
            ins.kind = "pool_soft"
            ins.imm = text_off
            ins.text = body
            unit.instrs.append(ins)
            continue
        if mnem == "voice":
            # voice <off>, "v_xxx" [, soft] -> OP_TEXT pool_off + voice pool meta
            # soft: pool meta only (no code OP_TEXT). Used for continuation voices
            # that only appear inside a previous hard OP_TEXT logical walk.
            soft = False
            arg2 = arg
            if arg2.rstrip().endswith(", soft") or arg2.rstrip().endswith(" soft"):
                soft = True
                arg2 = re.sub(r",?\s*soft\s*$", "", arg2).rstrip()
            m_pool = re.match(r"(-?\d+|0x[0-9A-Fa-f]+)\s*,\s*(\".*)$", arg2)
            if not m_pool:
                # allow: voice <off>, v_xxx
                m_pool2 = re.match(r"(-?\d+|0x[0-9A-Fa-f]+)\s*,\s*(\S+)$", arg2)
                if not m_pool2:
                    raise ValueError("line %d: voice needs <off>, \"id\" [, soft]" % lineno)
                off = int(m_pool2.group(1), 0) & 0xFFFFFFFF
                vid = m_pool2.group(2).strip().strip('"')
            else:
                off = int(m_pool.group(1), 0) & 0xFFFFFFFF
                vid, _ = parse_quoted(m_pool.group(2), 0)
            ins.mnemonic = "text"
            ins.kind = "pool_soft" if soft else "pool"
            ins.imm = off
            ins.text = vid
            # ensure pool meta
            meta = unit.pool_entries.get(off, {"kind": "voice", "text": "", "tail": "none", "tail_hex": "", "voice_id": ""})
            meta["kind"] = "voice"
            meta["voice_id"] = vid
            unit.pool_entries[off] = meta
            unit.instrs.append(ins)
            continue
        if mnem == "textp":
            # Continuation of previous text/soft body for mid-entry 07 06 breaks.
            # Does not emit OP_TEXT; joins with real newline into same pool body.
            if last_text_off is None:
                raise ValueError("line %d: textp without preceding text" % lineno)
            body = arg
            if body.startswith('"'):
                body, _ = parse_quoted(body, 0)
            else:
                raise ValueError('line %d: textp needs "body"' % lineno)
            prev = unit.pool_bodies.get(last_text_off, "")
            unit.pool_bodies[last_text_off] = (prev or "") + chr(10) + body
            continue
        if mnem == "text":
            # text <off>, "body" [, soft]
            soft = False
            arg2 = arg
            if arg2.rstrip().endswith(", soft") or arg2.rstrip().endswith(" soft"):
                soft = True
                arg2 = re.sub(r",?\s*soft\s*$", "", arg2).rstrip()
            m_pool = re.match(r"(-?\d+|0x[0-9A-Fa-f]+)\s*,\s*(\".*)$", arg2)
            if not m_pool:
                raise ValueError('line %d: text needs <off>, "body" [, soft]' % lineno)
            off = int(m_pool.group(1), 0) & 0xFFFFFFFF
            body, _ = parse_quoted(m_pool.group(2), 0)
            ins.kind = "pool_soft" if soft else "pool"
            ins.imm = off
            ins.text = body
            unit.pool_bodies[off] = body
            last_text_off = off
            meta = unit.pool_entries.get(off, {"kind": "text", "text": "", "tail": "none", "tail_hex": "", "voice_id": ""})
            if meta.get("kind") != "voice":
                meta["kind"] = "text"
            unit.pool_entries[off] = meta
            unit.instrs.append(ins)
            continue
        if not arg:
            ins.kind = "none"
        elif arg.startswith("expr_"):
            ins.kind = "expr"
            ins.expr_index = int(arg[5:], 0)
        elif arg.startswith('"'):
            ins.kind = "str"
            ins.text, _ = parse_quoted(arg, 0)
        else:
            m_pool = re.match(r"(-?\d+|0x[0-9A-Fa-f]+)\s*,\s*(\".*)$", arg)
            if m_pool:
                ins.kind = "pool"
                ins.imm = int(m_pool.group(1), 0) & 0xFFFFFFFF
                ins.text, _ = parse_quoted(m_pool.group(2), 0)
                unit.pool_bodies[ins.imm] = ins.text or ""
            elif re.fullmatch(r"-?\d+|0x[0-9A-Fa-f]+", arg):
                ins.kind = "int"
                ins.imm = int(arg, 0) & 0xFFFFFFFF
            else:
                ins.kind = "label"
                ins.label = arg
        unit.instrs.append(ins)

    if pending:
        unit.instrs.append(Instr(mnemonic="__eof__", kind="none", labels_here=list(pending)))

    for i in range(max_expr + 1):
        if i not in unit.exprs:
            unit.exprs[i] = ExprNode(EXPR_T)

    if unit.label_defs:
        unit.label_defs.sort(key=lambda x: x.index)
        unit.label_name_to_index = {ld.name: ld.index for ld in unit.label_defs}
    return unit


def emit_type(buf: bytearray, t: Optional[TypeNode]) -> None:
    cur = t
    while cur is not None:
        write_u32(buf, cur.kind)
        write_u32(buf, cur.value)
        cur = cur.next
    write_u32(buf, 0)


def emit_expr(buf: bytearray, node: ExprNode, encoding: str) -> None:
    write_u32(buf, node.kind)
    if node.kind == EXPR_T:
        return
    if node.kind in (EXPR_U, EXPR_W):
        write_len_string(buf, node.text or "", encoding)
        return
    if node.kind == EXPR_V:
        write_u32(buf, node.value or 0)
        return
    emit_expr(buf, node.left or ExprNode(EXPR_T), encoding)
    emit_expr(buf, node.right or ExprNode(EXPR_T), encoding)



# Inline source tokens embedded in `text "..."` that expand back to ops.
INLINE_TOKEN_RE = re.compile(r"(\$1|\$2|%haato)")
HAATO_EXPR_NEEDLE_DOT = "(DOT (INT 100) (INT 68))"


def _format_expr_for_match(node: "ExprNode") -> str:
    def rec(n: "ExprNode") -> str:
        if n is None:
            return "T"
        if n.kind == EXPR_T:
            return "T"
        if n.kind == EXPR_U:
            return '(ID "%s")' % (n.text or "")
        if n.kind == EXPR_W:
            return '(STR "%s")' % (n.text or "")
        if n.kind == EXPR_V:
            return "(INT %d)" % (n.value or 0)
        names = {
            88: "CALL", 89: "ARG", 101: "ADD", 102: "COMMA", 103: "SUB",
            104: "DOT", 105: "DIV", 108: "LT", 109: "LE", 110: "GT", 111: "GE",
            112: "EQ", 113: "NE", 120: "ASSIGN", 95: "BNOT",
        }
        kn = names.get(n.kind, "N%d" % n.kind)
        if n.left is None and n.right is None:
            return "(%s)" % kn
        return "(%s %s %s)" % (kn, rec(n.left), rec(n.right))
    return rec(node)


def _expr_is_haato_asm(node: "ExprNode") -> bool:
    s = _format_expr_for_match(node)
    return (
        "FrameLayer_SendMessage" in s
        and HAATO_EXPR_NEEDLE_DOT in s
        and ("{{01}}" in s or "\uf8f3" in s)
    )


def _collect_haato_expr_indices(unit: "AsmUnit") -> List[int]:
    if not unit.exprs:
        return []
    out: List[int] = []
    for i in sorted(unit.exprs.keys()):
        if _expr_is_haato_asm(unit.exprs[i]):
            out.append(i)
    return out


def emit_eval_blob(code: bytearray, text: str, encoding: str) -> None:
    """Emit OP_EVAL as u16-len + raw bytes (placeholders allowed)."""
    blob = encode_text(text or "", encoding)
    if len(blob) > 0xFFFF:
        raise ValueError("eval blob too large: %d" % len(blob))
    code.append(op_code("eval") & 0xFF)
    code.extend(struct.pack("<H", len(blob)))
    code.extend(blob)


def emit_text_ops(
    code: bytearray,
    opc: int,
    text: str,
    encoding: str,
    haato_q: List[int],
    haato_pos: List[int],
) -> None:
    """Emit one or more ops for a cstr instruction, expanding $1/$2/%haato."""
    parts = INLINE_TOKEN_RE.split(text or "")
    if len(parts) == 1:
        code.append(opc & 0xFF)
        code.extend(encode_text(text or "", encoding))
        code.append(0)
        return
    for part in parts:
        if part == "$1":
            code.append(op_code("num_c") & 0xFF)
            write_u32(code, 1)
        elif part == "$2":
            code.append(op_code("num_c") & 0xFF)
            write_u32(code, 2)
        elif part == "%haato":
            if haato_pos[0] >= len(haato_q):
                raise ValueError(
                    "not enough %haato expr slots in .expr pool "
                    "(need more FrameLayer_SendMessage 100.68)"
                )
            idx = haato_q[haato_pos[0]]
            haato_pos[0] += 1
            # legacy AST-index form is not used in sispara2; keep as raw eval if present
            code.append(op_code("eval") & 0xFF)
            write_u32(code, idx)
        elif part:
            code.append(opc & 0xFF)
            code.extend(encode_text(part, encoding))
            code.append(0)


def assemble(unit: AsmUnit) -> bytes:
    encoding = unit.encoding
    # Build pool first so OP_TEXT offsets can be remapped when entry sizes change.
    if unit.pool_blob is not None and not unit.pool_entries:
        pool = unit.pool_blob
        remap: Dict[int, int] = {}
    else:
        pool, remap = build_pool_and_remap(unit)

    code = bytearray()
    label_offsets: Dict[str, int] = {}
    real = [ins for ins in unit.instrs if ins.mnemonic != "__eof__"]
    eof_labels: List[str] = []
    for ins in unit.instrs:
        if ins.mnemonic == "__eof__":
            eof_labels.extend(ins.labels_here)

    haato_q = _collect_haato_expr_indices(unit)
    haato_pos = [0]

    for ins in real:
        for lb in ins.labels_here:
            label_offsets[lb] = len(code)
        # soft/say: pool body only, no code bytes
        if ins.kind in ("pool_soft", "say") or (
            ins.mnemonic in ("say",) and ins.kind != "name"
        ):
            continue
        # name: emit real name-setter eval (not annotation-only)
        if ins.mnemonic == "name" or ins.kind == "name":
            blob = encode_name_setter(ins.text or "", encoding)
            if len(blob) > 0xFFFF:
                raise ValueError("name setter blob too large: %d" % len(blob))
            code.append(op_code("eval") & 0xFF)
            code.extend(struct.pack("<H", len(blob)))
            code.extend(blob)
            continue
        opc = op_code(ins.mnemonic)
        info = op_info(opc)
        if info.operand == "cstr":
            if ins.kind != "str":
                raise ValueError("%s needs string" % ins.mnemonic)
            # Expand inline $1/$2/%haato inside dialogue text back to original ops.
            if INLINE_TOKEN_RE.search(ins.text or ""):
                emit_text_ops(code, opc, ins.text or "", encoding, haato_q, haato_pos)
            else:
                code.append(opc & 0xFF)
                payload = ins.raw if ins.raw is not None else encode_text(ins.text or "", encoding)
                code.extend(payload)
                code.append(0)
            continue
        if info.operand == "eval_blob":
            if ins.kind != "str":
                raise ValueError("%s needs quoted blob" % ins.mnemonic)
            if ins.raw is not None:
                blob = ins.raw
            else:
                blob = encode_placeholders(ins.text or "")
                if blob is None:
                    blob = encode_text(ins.text or "", encoding)
            if len(blob) > 0xFFFF:
                raise ValueError("eval blob too large: %d" % len(blob))
            code.append(opc & 0xFF)
            code.extend(struct.pack("<H", len(blob)))
            code.extend(blob)
            continue
        if info.operand == "pool_off":
            # Prefer explicit offset from `text <off>, "..."` / `voice <off>, "..."`;
            # remap through packed pool so longer translations do not clobber neighbors.
            if ins.kind == "pool":
                old = ins.imm or 0
                new = remap.get(old, old)
                code.append(opc & 0xFF)
                write_u32(code, new)
            elif ins.kind == "int":
                old = ins.imm or 0
                new = remap.get(old, old)
                code.append(opc & 0xFF)
                write_u32(code, new)
            elif ins.kind == "str":
                payload = encode_text(ins.text or "", encoding) + b"\x00"
                off = None
                if pool:
                    found = pool.find(payload)
                    if found >= 0:
                        off = found
                if off is None and unit.pool_entries:
                    for k, v in unit.pool_entries.items():
                        body = unit.pool_bodies.get(k, v.get("text", "") if isinstance(v, dict) else v)
                        if body == (ins.text or ""):
                            off = remap.get(k, k)
                            break
                if off is None:
                    raise ValueError("text string not found in pool: %r" % (ins.text or "")[:40])
                code.append(opc & 0xFF)
                write_u32(code, off)
            else:
                raise ValueError("%s needs pool offset or string" % ins.mnemonic)
            continue
        code.append(opc & 0xFF)
        if info.operand == "none":
            pass
        elif info.operand == "u32":
            if ins.kind != "int":
                raise ValueError("%s needs int" % ins.mnemonic)
            write_u32(code, ins.imm or 0)
        elif info.operand == "u32_label":
            if ins.kind == "label":
                idx = unit.label_name_to_index.get(ins.label)
                if idx is None:
                    raise ValueError("unknown label %s" % ins.label)
                write_u32(code, idx)
            elif ins.kind == "int":
                write_u32(code, ins.imm or 0)
            else:
                raise ValueError("%s needs label" % ins.mnemonic)
        elif info.operand == "u32_expr":
            if ins.kind == "expr":
                write_u32(code, ins.expr_index or 0)
            elif ins.kind == "int":
                write_u32(code, ins.imm or 0)
            else:
                raise ValueError("%s needs expr_N" % ins.mnemonic)
        else:
            raise ValueError("bad operand %s" % info.operand)

    if haato_pos[0] != 0 and haato_pos[0] != len(haato_q):
        # Only enforce exact consumption when at least one %haato was expanded.
        pass

    end_off = len(code)
    for lb in eof_labels:
        label_offsets[lb] = end_off

    out = bytearray()
    write_u32(out, len(unit.globals))
    for g in unit.globals:
        write_len_string(out, g.name, encoding)
        emit_type(out, g.typ)
        write_u32(out, g.flags)
        write_u32(out, g.reserved)
        write_u32(out, g.offset)
    write_u32(out, unit.data_size)

    if unit.label_defs:
        max_i = max(ld.index for ld in unit.label_defs)
        arr: List[Optional[LabelDef]] = [None] * (max_i + 1)
        for ld in unit.label_defs:
            arr[ld.index] = ld
        write_u32(out, len(arr))
        for i, ld in enumerate(arr):
            if ld is None:
                write_len_string(out, "$MISSING_%d" % i, encoding)
                write_u32(out, 0)
            else:
                off = label_offsets.get(ld.name, ld.offset)
                write_len_string(out, ld.name, encoding)
                write_u32(out, off)
    else:
        write_u32(out, 0)

    if unit.exprs:
        max_e = max(unit.exprs.keys())
        write_u32(out, max_e + 1)
        for i in range(max_e + 1):
            emit_expr(out, unit.exprs.get(i, ExprNode(EXPR_T)), encoding)
    else:
        write_u32(out, 0)

    write_u32(out, len(code))
    out.extend(code)

    if pool is None:
        pool = b""
    write_u32(out, len(pool))
    out.extend(pool)
    return bytes(out)



def assemble_file(in_path: str, out_path: str, encoding: Optional[str] = None) -> None:
    with open(in_path, "r", encoding="utf-8") as f:
        text = f.read()
    unit = parse_asm(text)
    if encoding:
        unit.encoding = encoding
    data = assemble(unit)
    out_dir = os.path.dirname(os.path.abspath(out_path))
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    with open(out_path, "wb") as f:
        f.write(data)
    print("[ok] %s -> %s (%d bytes)" % (in_path, out_path, len(data)))


def batch_txt_to_bin(txt_dir: str, bin_dir: str, encoding: Optional[str] = None) -> None:
    os.makedirs(bin_dir, exist_ok=True)
    for name in os.listdir(txt_dir):
        in_path = os.path.join(txt_dir, name)
        if not os.path.isfile(in_path):
            continue
        if not (name.endswith(".asm.txt") or name.endswith(".txt")):
            continue
        base = name
        if base.endswith(".asm.txt"):
            base = base[: -len(".asm.txt")]
        elif base.endswith(".txt"):
            base = base[: -len(".txt")]
        assemble_file(in_path, os.path.join(bin_dir, base + ".rebuild"), encoding)


def main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) >= 2 and not argv[0].startswith("-") and not argv[1].startswith("-"):
        if os.path.isdir(argv[0]):
            encoding = None
            if "--encoding" in argv:
                encoding = argv[argv.index("--encoding") + 1]
            batch_txt_to_bin(argv[0], argv[1], encoding)
            return 0
    ap = argparse.ArgumentParser(description="Assemble Popotan exec.dat asm")
    ap.add_argument("input")
    ap.add_argument("output", nargs="?")
    ap.add_argument("-o", dest="out_file")
    ap.add_argument("--encoding", default=None)
    args = ap.parse_args(argv)
    if os.path.isdir(args.input):
        batch_txt_to_bin(args.input, args.output or args.out_file or "bin", args.encoding)
        return 0
    out = args.out_file or args.output
    if not out:
        base = os.path.basename(args.input)
        if base.endswith(".asm.txt"):
            base = base[: -len(".asm.txt")]
        out = base + ".rebuild"
    assemble_file(args.input, out, args.encoding)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
