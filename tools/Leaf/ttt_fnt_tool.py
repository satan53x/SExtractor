#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TtT / KCAP fnt.pak bitmap font helper.

Known files:
  font12.fd0 / font24.fd0 : normal 4bpp bitmap glyph data
  font12.fk0 / font24.fk0 : bold/expanded 4bpp bitmap glyph data, first u32 = margin

The engine maps raw CP932/SJIS bytes to glyph indices with fixed tables, then
copies 4-bit pixels to a D3D surface. This tool can inspect/dump/patch those
bitmap font files. It does not contain or redistribute any font file; pass your
own TTF/TTC path when patching.
"""
from __future__ import annotations

import argparse
import csv
import json
import struct
from pathlib import Path
from typing import Any, Iterable

try:
    from PIL import Image, ImageDraw, ImageFont, ImageFilter
except Exception:  # Pillow is only needed by atlas/patch commands.
    Image = ImageDraw = ImageFont = ImageFilter = None  # type: ignore

# sub_40AAF0 constants from TtT.exe_export_for_ai.
# Single-byte / half-width ranges: (glyph_base, start_byte, end_byte, draw_flag)
# 0x20 is a spacing sentinel: engine advances but does not draw it.
HALF_RANGES: list[tuple[int, int, int, bool]] = [
    (0x0000, 0x21, 0x7E, True),
    (0x005E, 0xA1, 0xDF, True),
    (0x009D, 0x20, 0x20, False),
]

# Double-byte / full-width ranges: (glyph_base, sjis_start, sjis_end, draw_flag)
# Last 0x8140 full-width space is a spacing sentinel and has no glyph body.
FULL_RANGES: list[tuple[int, int, int, bool]] = [
    (0x0000, 0x8141, 0x81AC, True),
    (0x006C, 0x81B8, 0x81BF, True),
    (0x0074, 0x81C8, 0x81CE, True),
    (0x007B, 0x81DA, 0x81FC, True),
    (0x009E, 0x824F, 0x8258, True),
    (0x00A8, 0x8260, 0x8279, True),
    (0x00C2, 0x8281, 0x829A, True),
    (0x00DC, 0x829F, 0x82F1, True),
    (0x012F, 0x8340, 0x8396, True),
    (0x0186, 0x839F, 0x83B6, True),
    (0x019E, 0x83BF, 0x83D6, True),
    (0x01B6, 0x8440, 0x8460, True),
    (0x01D7, 0x8470, 0x8491, True),
    (0x01F9, 0x849F, 0x84BE, True),
    (0x0219, 0x8740, 0x8799, True),
    (0x0273, 0x889F, 0x88FC, True),
    (0x02D1, 0x8940, 0x89FC, True),
    (0x038E, 0x8A40, 0x8AFC, True),
    (0x044B, 0x8B40, 0x8BFC, True),
    (0x0508, 0x8C40, 0x8CFC, True),
    (0x05C5, 0x8D40, 0x8DFC, True),
    (0x0682, 0x8E40, 0x8EFC, True),
    (0x073F, 0x8F40, 0x8FFC, True),
    (0x07FC, 0x9040, 0x90FC, True),
    (0x08B9, 0x9140, 0x91FC, True),
    (0x0976, 0x9240, 0x92FC, True),
    (0x0A33, 0x9340, 0x93FC, True),
    (0x0AF0, 0x9440, 0x94FC, True),
    (0x0BAD, 0x9540, 0x95FC, True),
    (0x0C6A, 0x9640, 0x96FC, True),
    (0x0D27, 0x9740, 0x97FC, True),
    (0x0DE4, 0x9840, 0x9872, True),
    (0x0E17, 0x989F, 0x98FC, True),
    (0x0E75, 0x9940, 0x99FC, True),
    (0x0F32, 0x9A40, 0x9AFC, True),
    (0x0FEF, 0x9B40, 0x9BFC, True),
    (0x10AC, 0x9C40, 0x9CFC, True),
    (0x1169, 0x9D40, 0x9DFC, True),
    (0x1226, 0x9E40, 0x9EFC, True),
    (0x12E3, 0x9F40, 0x9FFC, True),
    (0x13A0, 0xE040, 0xE0FC, True),
    (0x145D, 0xE140, 0xE1FC, True),
    (0x151A, 0xE240, 0xE2FC, True),
    (0x15D7, 0xE340, 0xE3FC, True),
    (0x1694, 0xE440, 0xE4FC, True),
    (0x1751, 0xE540, 0xE5FC, True),
    (0x180E, 0xE640, 0xE6FC, True),
    (0x18CB, 0xE740, 0xE7FC, True),
    (0x1988, 0xE840, 0xE8FC, True),
    (0x1A45, 0xE940, 0xE9FC, True),
    (0x1B02, 0xEA40, 0xEAA4, True),
    (0x1B67, 0xF040, 0xF047, True),
    (0x1B6F, 0x8140, 0x8140, False),
]

FULL_GLYPH_COUNT = 0x1B6F  # stored/drawable full-width glyphs: indices 0..0x1B6E
HALF_GLYPH_COUNT_FK = 0x9D  # stored/drawable half-width glyphs in fk0: 0..0x9C
HALF_GLYPH_COUNT_FD_CAPACITY = 177  # fd0 contains 20 extra/padding half slots.


def row_bytes(width: int) -> int:
    return (width + 1) // 2


def glyph_bytes(width: int, height: int) -> int:
    return row_bytes(width) * height


def decode_cp932_sjis(code: int, kind: str) -> str | None:
    try:
        if kind == "half":
            return bytes([code]).decode("cp932")
        return bytes([code >> 8, code & 0xFF]).decode("cp932")
    except UnicodeDecodeError:
        return None


def glyph_for_sjis_bytes(raw: bytes) -> dict[str, Any] | None:
    if len(raw) == 1:
        b = raw[0]
        for base, start, end, draw in HALF_RANGES:
            if start <= b <= end:
                idx = base + b - start
                return {"kind": "half", "index": idx, "code": b, "draw": draw}
        return None
    if len(raw) == 2:
        code = raw[0] << 8 | raw[1]
        for base, start, end, draw in FULL_RANGES:
            if start <= code <= end:
                idx = base + code - start
                return {"kind": "full", "index": idx, "code": code, "draw": draw}
        return None
    return None


def glyph_for_char(ch: str) -> dict[str, Any] | None:
    if not ch:
        return None
    raw = ch[0].encode("cp932")
    return glyph_for_sjis_bytes(raw)


def iter_mapping_rows() -> Iterable[dict[str, Any]]:
    for base, start, end, draw in FULL_RANGES:
        for code in range(start, end + 1):
            idx = base + code - start
            ch = decode_cp932_sjis(code, "full")
            yield {
                "kind": "full",
                "index": idx,
                "sjis_hex": f"{code:04X}",
                "bytes_hex": f"{code >> 8:02X} {code & 0xFF:02X}",
                "char": ch or "",
                "draw": draw,
            }
    for base, start, end, draw in HALF_RANGES:
        for code in range(start, end + 1):
            idx = base + code - start
            ch = decode_cp932_sjis(code, "half")
            yield {
                "kind": "half",
                "index": idx,
                "sjis_hex": f"{code:02X}",
                "bytes_hex": f"{code:02X}",
                "char": ch or "",
                "draw": draw,
            }


def file_layout(size: int, kind: str, margin: int = 0) -> dict[str, int]:
    if kind == "fd0":
        full_w = full_h = size
        half_w = size // 2
        half_h = size
        header = 0
        half_count = HALF_GLYPH_COUNT_FD_CAPACITY
    elif kind == "fk0":
        full_w = full_h = size + 2 * margin
        half_w = size // 2 + 2 * margin
        half_h = size + 2 * margin
        header = 4
        half_count = HALF_GLYPH_COUNT_FK
    else:
        raise ValueError(kind)
    full_size = glyph_bytes(full_w, full_h)
    half_size = glyph_bytes(half_w, half_h)
    full_area = full_size * FULL_GLYPH_COUNT
    return {
        "header": header,
        "full_w": full_w,
        "full_h": full_h,
        "half_w": half_w,
        "half_h": half_h,
        "full_glyph_bytes": full_size,
        "half_glyph_bytes": half_size,
        "full_area_bytes": full_area,
        "half_count": half_count,
        "expected_size": header + full_area + half_size * half_count,
    }


def glyph_offset(size: int, file_kind: str, glyph_kind: str, index: int, margin: int = 0) -> tuple[int, int, int, int]:
    layout = file_layout(size, file_kind, margin)
    if glyph_kind == "full":
        if not (0 <= index < FULL_GLYPH_COUNT):
            raise IndexError(f"full glyph index out of range: {index}")
        off = layout["header"] + index * layout["full_glyph_bytes"]
        return off, layout["full_w"], layout["full_h"], layout["full_glyph_bytes"]
    if glyph_kind == "half":
        if not (0 <= index < layout["half_count"]):
            raise IndexError(f"half glyph index out of range for {file_kind}: {index}")
        off = layout["header"] + layout["full_area_bytes"] + index * layout["half_glyph_bytes"]
        return off, layout["half_w"], layout["half_h"], layout["half_glyph_bytes"]
    raise ValueError(glyph_kind)


def decode_glyph(data: bytes, offset: int, width: int, height: int, invert: bool = False):
    if Image is None:
        raise RuntimeError("Pillow is required for image output. Install pillow first.")
    rb = row_bytes(width)
    img = Image.new("L", (width, height), 255 if not invert else 0)
    pix = img.load()
    for y in range(height):
        base = offset + y * rb
        for x in range(width):
            b = data[base + x // 2]
            v = (b >> 4) & 0xF if (x & 1) else b & 0xF
            pix[x, y] = 255 - v * 17 if not invert else v * 17
    return img


def encode_glyph_from_image(img, width: int, height: int) -> bytes:
    if Image is None:
        raise RuntimeError("Pillow is required for image encoding. Install pillow first.")
    img = img.convert("L").resize((width, height))
    rb = row_bytes(width)
    out = bytearray(rb * height)
    pix = img.load()
    for y in range(height):
        for x in range(width):
            # Black => 15, white => 0, anti-aliased gray => 1..14.
            lum = pix[x, y]
            v = max(0, min(15, round((255 - lum) / 17)))
            pos = y * rb + x // 2
            if x & 1:
                out[pos] = (out[pos] & 0x0F) | (v << 4)
            else:
                out[pos] = (out[pos] & 0xF0) | v
    return bytes(out)


def load_map_pairs(path: Path, direction: str) -> list[tuple[str, str]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    pairs: list[tuple[str, str]] = []
    if isinstance(data, dict):
        for k, v in data.items():
            if not isinstance(k, str) or not isinstance(v, str) or not k or not v:
                continue
            pairs.append((k[0], v[0]))
    elif isinstance(data, list):
        for item in data:
            if not isinstance(item, dict):
                continue
            # Common styles: {"cn":"这","jp":"這"}, {"src":"这","dst":"這"}
            a = item.get("cn") or item.get("source") or item.get("src") or item.get("from")
            b = item.get("jp") or item.get("slot") or item.get("target") or item.get("dst") or item.get("to")
            if isinstance(a, str) and isinstance(b, str) and a and b:
                pairs.append((a[0], b[0]))
    else:
        raise ValueError("mapping JSON must be an object or a list")
    if direction == "slot2cn":
        pairs = [(b, a) for a, b in pairs]
    return pairs


def render_char(ch: str, ttf: Path, px_size: int, canvas_w: int, canvas_h: int, xoff: int, yoff: int, ttc_index: int = 0, bold_radius: int = 0):
    if Image is None or ImageDraw is None or ImageFont is None:
        raise RuntimeError("Pillow is required for patching. Install pillow first.")
    font = ImageFont.truetype(str(ttf), px_size, index=ttc_index)
    img = Image.new("L", (canvas_w, canvas_h), 255)
    draw = ImageDraw.Draw(img)
    # Use bbox to place visible glyph into the target canvas. This is intentionally simple;
    # tune xoff/yoff/px-size per font for best result.
    bbox = draw.textbbox((0, 0), ch, font=font)
    gw, gh = bbox[2] - bbox[0], bbox[3] - bbox[1]
    x = (canvas_w - gw) // 2 - bbox[0] + xoff
    y = (canvas_h - gh) // 2 - bbox[1] + yoff
    draw.text((x, y), ch, fill=0, font=font)
    if bold_radius > 0:
        inv = Image.eval(img, lambda p: 255 - p)
        inv = inv.filter(ImageFilter.MaxFilter(bold_radius * 2 + 1))
        img = Image.eval(inv, lambda p: 255 - p)
    return img


def cmd_info(args: argparse.Namespace) -> int:
    d = Path(args.font_dir)
    for size in (12, 24):
        fd = d / f"font{size:02d}.fd0"
        fk = d / f"font{size:02d}.fk0"
        print(f"font{size}:")
        if fd.exists():
            layout = file_layout(size, "fd0")
            print(f"  {fd.name}: actual={fd.stat().st_size} expected={layout['expected_size']} layout={layout}")
        else:
            print(f"  {fd.name}: missing")
        if fk.exists():
            raw = fk.read_bytes()[:4]
            margin = struct.unpack('<I', raw)[0] if len(raw) == 4 else 0
            layout = file_layout(size, "fk0", margin)
            print(f"  {fk.name}: actual={fk.stat().st_size} expected={layout['expected_size']} margin={margin} layout={layout}")
        else:
            print(f"  {fk.name}: missing")
    return 0


def cmd_export_map(args: argparse.Namespace) -> int:
    rows = list(iter_mapping_rows())
    out = Path(args.output_json)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.csv:
        csv_path = Path(args.csv)
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        with csv_path.open("w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["kind", "index", "sjis_hex", "bytes_hex", "char", "draw"])
            w.writeheader()
            w.writerows(rows)
    print(f"[map] rows={len(rows)} json={out}" + (f" csv={args.csv}" if args.csv else ""))
    return 0


def dump_one_atlas(data: bytes, size: int, file_kind: str, glyph_kind: str, out_path: Path, cols: int, scale: int, margin: int = 0, max_count: int | None = None) -> None:
    if Image is None:
        raise RuntimeError("Pillow is required for atlas output. Install pillow first.")
    layout = file_layout(size, file_kind, margin)
    count = FULL_GLYPH_COUNT if glyph_kind == "full" else layout["half_count"]
    if max_count:
        count = min(count, max_count)
    if glyph_kind == "full":
        w, h = layout["full_w"], layout["full_h"]
    else:
        w, h = layout["half_w"], layout["half_h"]
    rows = (count + cols - 1) // cols
    atlas = Image.new("L", (cols * w, rows * h), 255)
    for i in range(count):
        off, gw, gh, _ = glyph_offset(size, file_kind, glyph_kind, i, margin)
        if off + glyph_bytes(gw, gh) <= len(data):
            atlas.paste(decode_glyph(data, off, gw, gh), ((i % cols) * w, (i // cols) * h))
    if scale != 1:
        atlas = atlas.resize((atlas.width * scale, atlas.height * scale), Image.Resampling.NEAREST)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    atlas.save(out_path)


def cmd_dump_atlas(args: argparse.Namespace) -> int:
    font_dir = Path(args.font_dir)
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    for size in (12, 24):
        fd = font_dir / f"font{size:02d}.fd0"
        if fd.exists():
            data = fd.read_bytes()
            dump_one_atlas(data, size, "fd0", "full", out_dir / f"font{size:02d}_fd0_full.png", args.cols, args.scale)
            dump_one_atlas(data, size, "fd0", "half", out_dir / f"font{size:02d}_fd0_half.png", args.cols, args.scale)
            print(f"[atlas] {fd.name} -> {out_dir}")
        fk = font_dir / f"font{size:02d}.fk0"
        if fk.exists():
            data = fk.read_bytes()
            margin = struct.unpack('<I', data[:4])[0]
            dump_one_atlas(data, size, "fk0", "full", out_dir / f"font{size:02d}_fk0_full.png", args.cols, args.scale, margin)
            dump_one_atlas(data, size, "fk0", "half", out_dir / f"font{size:02d}_fk0_half.png", args.cols, args.scale, margin)
            print(f"[atlas] {fk.name} -> {out_dir}")
    return 0


def patch_one_file(buf: bytearray, file_size: int, file_kind: str, pairs: list[tuple[str, str]], ttf: Path, px_size: int, xoff: int, yoff: int, ttc_index: int, bold_radius: int, margin: int = 0) -> tuple[int, int]:
    patched = 0
    skipped = 0
    for draw_ch, slot_ch in pairs:
        info = glyph_for_char(slot_ch)
        if not info or not info.get("draw"):
            skipped += 1
            print(f"[patch][skip] slot char not drawable/cp932: {slot_ch!r}")
            continue
        kind = info["kind"]
        idx = int(info["index"])
        try:
            off, w, h, nbytes = glyph_offset(file_size, file_kind, kind, idx, margin)
        except Exception as e:
            skipped += 1
            print(f"[patch][skip] {slot_ch!r}: {e}")
            continue
        # For fk0 we draw inside expanded canvas; caller can use bold_radius to thicken.
        img = render_char(draw_ch, ttf, px_size, w, h, xoff, yoff, ttc_index, bold_radius)
        buf[off:off + nbytes] = encode_glyph_from_image(img, w, h)
        patched += 1
    return patched, skipped


def cmd_patch_font(args: argparse.Namespace) -> int:
    in_dir = Path(args.font_dir)
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    pairs = load_map_pairs(Path(args.map_json), args.direction)
    ttf = Path(args.ttf)
    total_patched = total_skipped = 0
    for size in (12, 24):
        fd_in = in_dir / f"font{size:02d}.fd0"
        fk_in = in_dir / f"font{size:02d}.fk0"
        px_size = args.size12 if size == 12 else args.size24
        if fd_in.exists():
            buf = bytearray(fd_in.read_bytes())
            patched, skipped = patch_one_file(buf, size, "fd0", pairs, ttf, px_size, args.xoff, args.yoff, args.ttc_index, args.bold_radius_fd, 0)
            (out_dir / fd_in.name).write_bytes(buf)
            total_patched += patched
            total_skipped += skipped
            print(f"[patch] {fd_in.name}: patched={patched} skipped={skipped}")
        if fk_in.exists() and not args.no_fk:
            buf = bytearray(fk_in.read_bytes())
            margin = struct.unpack('<I', buf[:4])[0]
            patched, skipped = patch_one_file(buf, size, "fk0", pairs, ttf, px_size, args.xoff, args.yoff, args.ttc_index, args.bold_radius_fk, margin)
            (out_dir / fk_in.name).write_bytes(buf)
            total_patched += patched
            total_skipped += skipped
            print(f"[patch] {fk_in.name}: patched={patched} skipped={skipped}")
    # Preserve manifest and zero-size marker if present.
    for extra in ("_pak_manifest.json", "ＤＦ隷書体"):
        p = in_dir / extra
        if p.exists() and not (out_dir / extra).exists():
            (out_dir / extra).write_bytes(p.read_bytes())
    print(f"[patch] total patched={total_patched} skipped={total_skipped} out={out_dir}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="TtT bitmap font inspector/dumper/patcher")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("info", help="print fd0/fk0 layout information")
    p.add_argument("font_dir")
    p.set_defaults(func=cmd_info)

    p = sub.add_parser("export-map", help="export engine SJIS -> glyph index mapping")
    p.add_argument("output_json")
    p.add_argument("--csv", help="also write CSV")
    p.set_defaults(func=cmd_export_map)

    p = sub.add_parser("dump-atlas", help="dump fd0/fk0 glyph atlases as PNG")
    p.add_argument("font_dir")
    p.add_argument("output_dir")
    p.add_argument("--cols", type=int, default=64)
    p.add_argument("--scale", type=int, default=2)
    p.set_defaults(func=cmd_dump_atlas)

    p = sub.add_parser("patch-font", help="redraw mapped glyph slots from a user-provided TTF/TTC")
    p.add_argument("font_dir", help="directory containing font12/24.fd0/fk0")
    p.add_argument("map_json", help="JSON mapping, default object style: {CN_char: SJIS_slot_char}")
    p.add_argument("output_dir")
    p.add_argument("--ttf", required=True, help="Chinese-capable TTF/TTC path; this tool does not include font files")
    p.add_argument("--direction", choices=["cn2slot", "slot2cn"], default="cn2slot")
    p.add_argument("--ttc-index", type=int, default=0)
    p.add_argument("--size12", type=int, default=12)
    p.add_argument("--size24", type=int, default=24)
    p.add_argument("--xoff", type=int, default=0)
    p.add_argument("--yoff", type=int, default=0)
    p.add_argument("--bold-radius-fd", type=int, default=0)
    p.add_argument("--bold-radius-fk", type=int, default=1)
    p.add_argument("--no-fk", action="store_true", help="patch fd0 only")
    p.set_defaults(func=cmd_patch_font)

    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
