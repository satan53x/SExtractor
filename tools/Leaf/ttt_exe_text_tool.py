# -*- coding: utf-8 -*-
"""
TtT.exe hardcoded text extractor / in-place injector.

Target: Tears to Tiara / TtT.exe PE32.
Text encoding: CP932 / Shift-JIS.

This tool patches strings in place.  The executable contains many strings
embedded directly in .data structures, not a single relocatable script pool.
The extractor is strict for ordinary C-string zones: xref_count must be nonzero
there, while known inline table zones keep base+stride slots even with xref=0.
Injection keeps the original slot boundary by default; if the translated bytes
exceed the selected slot, the tool truncates at a safe CP932 character boundary.
Use --allow-padding only when you understand that the tool will consume the zero
padding after a string before applying the same safe truncation rule.

V3 strict audit changes:
* ordinary C-string groups still require a real VA xref;
* leading 0xFF filler/decorator bytes are no longer exposed as editable text;
  they are preserved as _prefix_hex and injection starts after the prefix;
* an audit command reports suspicious short/no-Japanese/PUA entries.
"""
from __future__ import annotations

import argparse
import json
import re
import struct
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

ENCODING = "cp932"
IMAGE_BASE_DEFAULT = 0x400000

# The real hardcoded Japanese text in this sample is concentrated here.
# Past 0x188300 the .data area contains large binary tables that decode as
# accidental CP932 garbage, so the default extractor stops before them.
DEFAULT_RANGES = [
    (0x139000, 0x188300, "data_hardcoded_text"),
]

# Useful named sub-ranges found in this executable.
# In v2 the ranges are also used as trust policy hints:
#   * xref groups: only keep strings that have real code/data references.
#   * structured groups: keep fixed-table inline string slots even when xref_count=0.
GROUP_RANGES = [
    (0x139000, 0x13B100, "system_d3d_error"),
    (0x13C500, 0x13CD00, "script_error_or_engine_msg"),
    (0x13EA00, 0x141500, "battle_base_ui_and_names"),
    (0x141500, 0x147C00, "unit_name_slots"),
    (0x14CF00, 0x14E600, "class_enemy_name_slots"),
    (0x14F000, 0x15E800, "item_name_desc_table"),
    (0x181200, 0x182900, "skill_magic_name_slots"),
    (0x183600, 0x184800, "skill_magic_descriptions"),
    (0x185000, 0x188300, "camp_shop_option_help"),
]



# Ordinary C string / pointer-string zones.
# These zones contain binary tables mixed with strings; accidental CP932 decodes
# such as "O９お" must not be extracted unless the address is actually referenced.
XREF_REQUIRED_GROUPS = {
    "system_d3d_error",
    "script_error_or_engine_msg",
    "camp_shop_option_help",
}

# Struct/table inline string zones.  Most entries here are reached by
# base+index*stride+field_offset rather than by a direct pointer to the string,
# so xref_count is normally 0 and must not be used as a rejection criterion.
STRUCTURED_INLINE_GROUPS = {
    "battle_base_ui_and_names",
    "unit_name_slots",
    "class_enemy_name_slots",
    "item_name_desc_table",
    "skill_magic_name_slots",
    "skill_magic_descriptions",
}

# Bytes that often appear when random pointers / floats are mistakenly decoded
# as CP932.  We do not ban them absolutely because the game uses a few private
# glyphs/control-looking bytes in real strings; instead they lower confidence.
BAD_CHARS = set("\uf8f0\uf8f1\uf8f2\uf8f3\uf8f4\uf8f5\uf8f6\uf8f7\uf8f8\uf8f9")


def split_leading_ff_prefix(raw: bytes, s: str) -> tuple[int, str]:
    """Return byte length of leading 0xFF filler/decorator prefix.

    Python cp932 decodes 0xFF as U+F8F3.  In this executable a few real
    strings are preceded by repeated 0xFF bytes used as table filler / marker.
    They must be preserved in the executable, but should not be exposed as
    translatable text.
    """
    n = 0
    while n < len(raw) and raw[n] == 0xFF:
        n += 1
    if n <= 0:
        return 0, s
    rest = raw[n:]
    if len(rest) < 4:
        return 0, s
    try:
        rest_s = rest.decode(ENCODING)
    except UnicodeDecodeError:
        return 0, s
    # Only strip when the remainder is a valid Japanese/message-like string.
    real = sum(1 for ch in rest_s if 0x3040 <= ord(ch) <= 0x30FF or 0x4E00 <= ord(ch) <= 0x9FFF)
    if real <= 0:
        return 0, s
    return n, rest_s


def entry_suspicion_reasons(e: dict[str, Any]) -> list[str]:
    s = str(e.get("scr_msg", ""))
    reasons: list[str] = []
    pua = sum(1 for ch in s if 0xE000 <= ord(ch) <= 0xF8FF)
    jp = sum(1 for ch in s if 0x3040 <= ord(ch) <= 0x30FF or 0x4E00 <= ord(ch) <= 0x9FFF)
    kana = sum(1 for ch in s if 0x3040 <= ord(ch) <= 0x30FF)
    cjk = sum(1 for ch in s if 0x4E00 <= ord(ch) <= 0x9FFF)
    half = sum(1 for ch in s if 0xFF61 <= ord(ch) <= 0xFF9F)
    if pua:
        reasons.append(f"pua={pua}")
    if len(s) <= 6 and jp == 0 and not re.search(r"%[0-9.]*[sdifxX]|[A-Za-z]", s):
        reasons.append("short-no-jp")
    if half >= 3 and kana == 0 and cjk == 0:
        # Often real Windows mixer device names, but worth auditing.
        reasons.append("halfwidth-only")
    if e.get("_group") in XREF_REQUIRED_GROUPS and int(e.get("_xref_count", 0)) == 0:
        reasons.append("xref-required-but-zero")
    return reasons


def read_u16(data: bytes, off: int) -> int:
    return struct.unpack_from("<H", data, off)[0]


def read_u32(data: bytes, off: int) -> int:
    return struct.unpack_from("<I", data, off)[0]


@dataclass
class Section:
    name: str
    va: int
    vsize: int
    raw: int
    raw_size: int

    def file_to_va(self, off: int, image_base: int) -> int | None:
        if self.raw <= off < self.raw + self.raw_size:
            return image_base + self.va + (off - self.raw)
        return None


@dataclass
class Entry:
    scr_msg: str
    message: str
    _file: str
    _index: int
    _offset: int
    _raw_offset: int
    _prefix_hex: str
    _rva: int
    _va: str
    _size: int
    _capacity_zero: int
    _encoding: str
    _type: str
    _group: str
    _xref_count: int
    _policy: str = "in_place"

    def to_json(self) -> dict[str, Any]:
        return asdict(self)


def parse_pe(data: bytes) -> tuple[int, list[Section]]:
    if data[:2] != b"MZ":
        raise ValueError("not a PE/MZ executable")
    peoff = read_u32(data, 0x3C)
    if data[peoff:peoff + 4] != b"PE\0\0":
        raise ValueError("invalid PE signature")
    coff = peoff + 4
    nsects = read_u16(data, coff + 2)
    opt_size = read_u16(data, coff + 16)
    opt = coff + 20
    magic = read_u16(data, opt)
    if magic != 0x10B:
        raise ValueError(f"expected PE32 optional header, got magic={magic:#x}")
    image_base = read_u32(data, opt + 28)
    sh = opt + opt_size
    sections: list[Section] = []
    for i in range(nsects):
        off = sh + i * 40
        name = data[off:off + 8].split(b"\0", 1)[0].decode("ascii", "replace")
        vsize, va, raw_size, raw = struct.unpack_from("<IIII", data, off + 8)
        sections.append(Section(name, va, vsize, raw, raw_size))
    return image_base, sections


def section_for_file(sections: list[Section], off: int) -> Section | None:
    for sec in sections:
        if sec.raw <= off < sec.raw + sec.raw_size:
            return sec
    return None


def group_for_offset(off: int) -> str:
    for lo, hi, name in GROUP_RANGES:
        if lo <= off < hi:
            return name
    return "hardcoded_text"


def jp_score(s: str) -> int:
    score = 0
    for ch in s:
        o = ord(ch)
        if 0x3040 <= o <= 0x30FF:      # kana
            score += 2
        elif 0x4E00 <= o <= 0x9FFF:    # CJK
            score += 2
        elif 0xFF00 <= o <= 0xFFEF:    # full-width / half-width kana
            score += 1
        elif ch in "、。「」『』（）！？ー…―・％＋－＝＜＞：；／＼￥　":
            score += 1
    return score


def is_printable_text(s: str) -> bool:
    return all((ord(ch) >= 0x20 and ch != "\x7f") or ch in "\r\n\t" for ch in s)


def is_candidate_string(raw: bytes, s: str, min_score: int = 2) -> bool:
    if not raw or len(raw) < 4:
        return False
    if not is_printable_text(s):
        return False
    score = jp_score(s)
    if score < min_score:
        return False
    # Filter common false positives: mostly PUA/half-width garbage with no kana/CJK.
    bad = sum(1 for ch in s if ch in BAD_CHARS or 0xE000 <= ord(ch) <= 0xF8FF)
    real = sum(1 for ch in s if 0x3040 <= ord(ch) <= 0x30FF or 0x4E00 <= ord(ch) <= 0x9FFF)
    if bad >= 2 and real == 0:
        return False
    # Accidental decoded pointer chunks often end in X/S/L-like address bytes and
    # have almost no punctuation/kana/CJK.  Keep short real names like はい/職業.
    if len(s) <= 3 and real == 0:
        return False
    return True


def trailing_zero_capacity(data: bytes, off: int, raw_len: int) -> int:
    """Return max byte count including terminating NUL, using only following NUL padding."""
    end = off + raw_len + 1
    p = end
    while p < len(data) and data[p] == 0:
        p += 1
    return p - off


def count_xrefs(data: bytes, va: int) -> int:
    pat = struct.pack("<I", va)
    return sum(1 for _ in re.finditer(re.escape(pat), data))


def scan_strings(data: bytes, exe_name: str, ranges: list[tuple[int, int, str]]) -> list[Entry]:
    image_base, sections = parse_pe(data)
    entries: list[Entry] = []
    idx = 0
    for lo, hi, _range_name in ranges:
        lo = max(0, lo)
        hi = min(len(data), hi)
        pos = lo
        while pos < hi:
            nul = data.find(b"\0", pos, hi)
            if nul < 0:
                break
            raw = data[pos:nul]
            if len(raw) >= 4:
                try:
                    s = raw.decode(ENCODING)
                except UnicodeDecodeError:
                    s = ""
                if s and is_candidate_string(raw, s):
                    prefix_len, visible_s = split_leading_ff_prefix(raw, s)
                    text_pos = pos + prefix_len
                    text_raw_len = len(raw) - prefix_len
                    if not visible_s or not is_candidate_string(raw[prefix_len:], visible_s):
                        pos = nul + 1
                        continue
                    sec = section_for_file(sections, pos)
                    if sec is not None:
                        va_raw = sec.file_to_va(pos, image_base)
                        va_text = sec.file_to_va(text_pos, image_base)
                        rva = va_text - image_base if va_text is not None else text_pos
                    else:
                        va_raw = image_base + pos
                        va_text = image_base + text_pos
                        rva = text_pos
                    cap_full = trailing_zero_capacity(data, pos, len(raw))
                    # Reference may point either at the leading filler marker or directly at text.
                    xrefs = count_xrefs(data, va_raw or 0) + (count_xrefs(data, va_text or 0) if va_text != va_raw else 0)
                    group = group_for_offset(pos)
                    # Strict policy for non-structured zones: binary lookup tables
                    # in the D3D/font area can decode as short CP932 garbage.
                    # Keep ordinary C strings only when IDA/PE-style VA xref exists.
                    if group in XREF_REQUIRED_GROUPS and xrefs == 0:
                        pos = nul + 1
                        continue
                    editable_cap = max(cap_full - 1 - prefix_len, text_raw_len)
                    entries.append(Entry(
                        scr_msg=visible_s,
                        message=visible_s,
                        _file=exe_name,
                        _index=idx,
                        _offset=text_pos,
                        _raw_offset=pos,
                        _prefix_hex=raw[:prefix_len].hex(),
                        _rva=rva,
                        _va=f"0x{(va_text or 0):08X}",
                        _size=text_raw_len,
                        _capacity_zero=editable_cap,  # editable bytes, not including final NUL
                        _encoding=ENCODING,
                        _type="exe_hardcoded_string",
                        _group=group,
                        _xref_count=xrefs,
                    ))
                    idx += 1
            pos = nul + 1
    return entries


def load_json(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as f:
        obj = json.load(f)
    if not isinstance(obj, list):
        raise ValueError("JSON root must be a list")
    return obj


def save_json(path: Path, entries: list[Entry]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as f:
        json.dump([e.to_json() for e in entries], f, ensure_ascii=False, indent=2)


def load_cn_jp_map(path: Path | None) -> dict[str, str]:
    if path is None:
        return {}
    with path.open("r", encoding="utf-8") as f:
        obj = json.load(f)
    if not isinstance(obj, dict):
        raise ValueError("map JSON root must be an object")
    return {str(k): str(v) for k, v in obj.items()}


def apply_map(text: str, table: dict[str, str]) -> str:
    if not table:
        return text
    return "".join(table.get(ch, ch) for ch in text)


def encode_text(text: str) -> bytes:
    return text.encode(ENCODING)


def truncate_cp932_to_limit(text: str, limit: int) -> tuple[bytes, bool]:
    """Encode text to CP932, truncating without splitting a multibyte character."""
    if limit < 0:
        limit = 0
    out = bytearray()
    for i, ch in enumerate(text):
        b = ch.encode(ENCODING)
        if len(out) + len(b) > limit:
            return bytes(out), True
        out += b
    return bytes(out), False


def cmd_extract(args: argparse.Namespace) -> int:
    exe = Path(args.exe)
    data = exe.read_bytes()
    entries = scan_strings(data, exe.name, DEFAULT_RANGES)
    if args.group:
        entries = [e for e in entries if e._group == args.group]
    save_json(Path(args.json), entries)
    groups: dict[str, int] = {}
    for e in entries:
        groups[e._group] = groups.get(e._group, 0) + 1
    print(f"[extract] entries={len(entries)} output={args.json}")
    for k in sorted(groups):
        print(f"[extract] {k}: {groups[k]}")
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    table = load_cn_jp_map(Path(args.map) if args.map else None)
    entries = load_json(Path(args.json))
    over_size = 0
    over_padding = 0
    enc_fail = 0
    for e in entries:
        msg = e.get("message")
        if not isinstance(msg, str):
            continue
        msg2 = apply_map(msg, table)
        try:
            raw = encode_text(msg2)
        except UnicodeEncodeError:
            enc_fail += 1
            print(f"[check][encoding-fail] index={e.get('_index')} off={e.get('_offset')} msg={msg!r}")
            continue
        size = int(e.get("_size", 0))
        cap = int(e.get("_capacity_zero", size))
        if len(raw) > size:
            over_size += 1
            level = "will-use-padding" if len(raw) <= cap else "will-truncate"
            print(f"[check][{level}] index={e.get('_index')} off=0x{int(e.get('_offset')):X} len={len(raw)} size={size} cap={cap} msg={msg[:60]!r}")
            if len(raw) > cap:
                over_padding += 1
    print(f"[check] entries={len(entries)} encoding_fail={enc_fail} over_original_size={over_size} over_zero_padding_or_truncate={over_padding}")
    return 1 if enc_fail else 0



def cmd_audit(args: argparse.Namespace) -> int:
    entries = load_json(Path(args.json))
    suspicious: list[tuple[dict[str, Any], list[str]]] = []
    groups: dict[str, int] = {}
    prefix_count = 0
    xref_zero_bad = 0
    for e in entries:
        groups[str(e.get("_group"))] = groups.get(str(e.get("_group")), 0) + 1
        if e.get("_prefix_hex"):
            prefix_count += 1
        reasons = entry_suspicion_reasons(e)
        if "xref-required-but-zero" in reasons:
            xref_zero_bad += 1
        # Leading 0xFF prefix has been normalized; do not report preserved prefix as bad.
        if reasons:
            suspicious.append((e, reasons))
    print(f"[audit] entries={len(entries)} groups={len(groups)} normalized_prefix_entries={prefix_count}")
    for k in sorted(groups):
        print(f"[audit] {k}: {groups[k]}")
    print(f"[audit] xref_required_zero={xref_zero_bad}")
    print(f"[audit] suspicious_for_manual_review={len(suspicious)}")
    for e, reasons in suspicious[:args.limit]:
        print(f"[audit][suspect] index={e.get('_index')} group={e.get('_group')} off=0x{int(e.get('_offset')):X} size={e.get('_size')} xref={e.get('_xref_count')} reasons={','.join(reasons)} msg={str(e.get('scr_msg'))[:80]!r}")
    return 1 if xref_zero_bad else 0

def cmd_inject(args: argparse.Namespace) -> int:
    exe = Path(args.exe)
    out = Path(args.out)
    table = load_cn_jp_map(Path(args.map) if args.map else None)
    data = bytearray(exe.read_bytes())
    entries = load_json(Path(args.json))
    patched = failed = skipped = truncated = 0
    for e in entries:
        try:
            off = int(e["_offset"])
            size = int(e["_size"])
            cap = int(e.get("_capacity_zero", size))
            scr = str(e["scr_msg"])
            msg = str(e["message"])
        except Exception as ex:
            failed += 1
            print(f"[inject][bad-entry] {ex}: {e}")
            continue
        try:
            old_raw = encode_text(scr)
        except UnicodeEncodeError:
            failed += 1
            print(f"[inject][bad-scr-encoding] index={e.get('_index')} {scr!r}")
            continue
        if bytes(data[off:off + len(old_raw)]) != old_raw:
            failed += 1
            got = bytes(data[off:off + min(len(old_raw), 32)])
            print(f"[inject][verify-fail] index={e.get('_index')} off=0x{off:X} scr={scr[:60]!r} got={got.hex()}")
            continue
        mapped_msg = apply_map(msg, table)
        try:
            full_raw = encode_text(mapped_msg)
        except UnicodeEncodeError as ex:
            failed += 1
            print(f"[inject][encoding-fail] index={e.get('_index')} off=0x{off:X} {ex} msg={msg[:60]!r}")
            continue
        limit = cap if args.allow_padding else size
        if len(full_raw) > limit:
            try:
                new_raw, was_truncated = truncate_cp932_to_limit(mapped_msg, limit)
            except UnicodeEncodeError as ex:
                failed += 1
                print(f"[inject][encoding-fail] index={e.get('_index')} off=0x{off:X} {ex} msg={msg[:60]!r}")
                continue
            truncated += 1
            print(f"[inject][truncate] index={e.get('_index')} off=0x{off:X} len={len(full_raw)} -> {len(new_raw)} limit={limit} size={size} cap={cap} msg={msg[:60]!r}")
        else:
            new_raw = full_raw
            was_truncated = False
        if msg == scr and not was_truncated:
            skipped += 1
            continue
        # Write C string and clear the rest of the selected slot.  In default mode
        # this clears only original raw byte length; with --allow-padding it also
        # clears zero padding that follows the original string.  Overlong text is
        # truncated at a CP932 character boundary instead of being skipped.
        data[off:off + limit + 1] = new_raw + b"\0" + b"\0" * (limit - len(new_raw))
        patched += 1
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(data)
    print(f"[inject] patched={patched} truncated={truncated} skipped={skipped} failed={failed} output={out}")
    return 1 if failed else 0


def cmd_list_groups(args: argparse.Namespace) -> int:
    for lo, hi, name in GROUP_RANGES:
        print(f"{name:28s} 0x{lo:06X}-0x{hi:06X}")
    return 0


def build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Extract/inject hardcoded CP932 text in TtT.exe")
    sub = p.add_subparsers(dest="cmd", required=True)

    q = sub.add_parser("extract", help="extract hardcoded text to JSON")
    q.add_argument("exe")
    q.add_argument("json")
    q.add_argument("--group", help="only extract one _group")
    q.set_defaults(func=cmd_extract)

    q = sub.add_parser("check", help="check translated JSON length and CP932 encoding")
    q.add_argument("json")
    q.add_argument("--map", help="optional simplified->CP932 proxy map, e.g. subs_cn_jp.json")
    q.set_defaults(func=cmd_check)

    q = sub.add_parser("audit", help="audit extracted JSON for suspicious/garbled entries")
    q.add_argument("json")
    q.add_argument("--limit", type=int, default=80)
    q.set_defaults(func=cmd_audit)

    q = sub.add_parser("inject", help="inject translated JSON back into exe, truncating overlong text in place")
    q.add_argument("exe")
    q.add_argument("json")
    q.add_argument("out")
    q.add_argument("--map", help="optional simplified->CP932 proxy map, e.g. subs_cn_jp.json")
    q.add_argument("--allow-padding", action="store_true", help="allow using zero padding after the original string")
    q.set_defaults(func=cmd_inject)

    q = sub.add_parser("groups", help="print known group ranges")
    q.set_defaults(func=cmd_list_groups)
    return p


def main() -> int:
    p = build_argparser()
    args = p.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
