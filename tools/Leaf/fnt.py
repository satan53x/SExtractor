#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Full-redraw tool for TtT KCAP bitmap fonts.

It redraws every drawable CP932/SJIS glyph slot in font12/font24 fd0/fk0.
Mapping JSON format is {"简体": "CP932槽位"}; mapped slots are rendered with
Simplified Chinese glyphs, while all other slots are rendered as their original
CP932 decoded characters using the supplied TTF/TTC.

The supplied TTF/TTC is not embedded or redistributed by this script.
"""
from __future__ import annotations

import argparse
import json
import math
import shutil
import struct
import unicodedata
from pathlib import Path
from typing import Any, Iterable

from PIL import Image, ImageDraw, ImageFont, ImageFilter

# Same mapping constants as ttt_fnt_tool.py, derived from the engine table.
HALF_RANGES: list[tuple[int, int, int, bool]] = [
    (0x0000, 0x21, 0x7E, True),
    (0x005E, 0xA1, 0xDF, True),
    (0x009D, 0x20, 0x20, False),
]
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
FULL_GLYPH_COUNT = 0x1B6F
HALF_GLYPH_COUNT_FK = 0x9D
HALF_GLYPH_COUNT_FD_CAPACITY = 177

PUNCT_EXTRA = set("，。？！、；：…—―・·～〜「」『』（）()《》〈〉【】[]〔〕——")


def row_bytes(width: int) -> int:
    return (width + 1) // 2


def glyph_bytes(width: int, height: int) -> int:
    return row_bytes(width) * height


def decode_code(code: int, kind: str) -> str | None:
    try:
        raw = bytes([code]) if kind == "half" else bytes([code >> 8, code & 0xFF])
        return raw.decode("cp932")
    except UnicodeDecodeError:
        return None


def file_layout(size: int, kind: str, margin: int = 0) -> dict[str, int]:
    if kind == "fd0":
        header = 0
        full_w = full_h = size
        half_w = size // 2
        half_h = size
        half_count = HALF_GLYPH_COUNT_FD_CAPACITY
    elif kind == "fk0":
        header = 4
        full_w = full_h = size + margin * 2
        half_w = size // 2 + margin * 2
        half_h = size + margin * 2
        half_count = HALF_GLYPH_COUNT_FK
    else:
        raise ValueError(kind)
    full_gb = glyph_bytes(full_w, full_h)
    half_gb = glyph_bytes(half_w, half_h)
    full_area = full_gb * FULL_GLYPH_COUNT
    return {
        "header": header,
        "full_w": full_w,
        "full_h": full_h,
        "half_w": half_w,
        "half_h": half_h,
        "full_glyph_bytes": full_gb,
        "half_glyph_bytes": half_gb,
        "full_area_bytes": full_area,
        "half_count": half_count,
        "expected_size": header + full_area + half_gb * half_count,
    }


def glyph_offset(size: int, file_kind: str, glyph_kind: str, index: int, margin: int = 0) -> tuple[int, int, int, int]:
    lay = file_layout(size, file_kind, margin)
    if glyph_kind == "full":
        off = lay["header"] + index * lay["full_glyph_bytes"]
        return off, lay["full_w"], lay["full_h"], lay["full_glyph_bytes"]
    off = lay["header"] + lay["full_area_bytes"] + index * lay["half_glyph_bytes"]
    return off, lay["half_w"], lay["half_h"], lay["half_glyph_bytes"]


def iter_drawable_slots() -> Iterable[dict[str, Any]]:
    for base, start, end, draw in FULL_RANGES:
        for code in range(start, end + 1):
            idx = base + code - start
            if draw and idx < FULL_GLYPH_COUNT:
                yield {"kind": "full", "index": idx, "code": code, "char": decode_code(code, "full")}
    for base, start, end, draw in HALF_RANGES:
        for code in range(start, end + 1):
            idx = base + code - start
            if draw and idx < HALF_GLYPH_COUNT_FK:
                yield {"kind": "half", "index": idx, "code": code, "char": decode_code(code, "half")}


def encode_glyph_from_image(img: Image.Image, width: int, height: int) -> bytes:
    img = img.convert("L").resize((width, height))
    rb = row_bytes(width)
    out = bytearray(rb * height)
    pix = img.load()
    for y in range(height):
        for x in range(width):
            lum = pix[x, y]
            v = max(0, min(15, round((255 - lum) / 17)))
            p = y * rb + x // 2
            if x & 1:
                out[p] = (out[p] & 0x0F) | (v << 4)
            else:
                out[p] = (out[p] & 0xF0) | v
    return bytes(out)


def decode_glyph(data: bytes, offset: int, width: int, height: int) -> Image.Image:
    rb = row_bytes(width)
    im = Image.new("L", (width, height), 255)
    pix = im.load()
    for y in range(height):
        p = offset + y * rb
        for x in range(width):
            b = data[p + x // 2]
            v = (b >> 4) & 0xF if (x & 1) else b & 0xF
            pix[x, y] = 255 - v * 17
    return im


def is_punct(ch: str) -> bool:
    if ch in PUNCT_EXTRA:
        return True
    return bool(ch) and unicodedata.category(ch[0]).startswith("P")


class FontRenderer:
    def __init__(self, ttf: Path, size12: int, size24: int, ttc_index: int = 0, punct_dx24: int = 2, punct_dy24: int = 1, punct_dx12: int = 1, punct_dy12: int = 1):
        self.ttf = Path(ttf)
        self.ttc_index = ttc_index
        self.sizes = {12: size12, 24: size24}
        self.cache: dict[int, ImageFont.FreeTypeFont] = {}
        self.punct_offset = {12: (punct_dx12, punct_dy12), 24: (punct_dx24, punct_dy24)}

    def font(self, px: int) -> ImageFont.FreeTypeFont:
        if px not in self.cache:
            self.cache[px] = ImageFont.truetype(str(self.ttf), px, index=self.ttc_index)
        return self.cache[px]

    def _bbox(self, ch: str, font: ImageFont.FreeTypeFont) -> tuple[int, int, int, int]:
        return ImageDraw.Draw(Image.new("L", (1, 1))).textbbox((0, 0), ch, font=font)

    def render_full(self, ch: str, size: int, w: int, h: int, bold_radius: int = 0, extra_xoff: int = 0, extra_yoff: int = 0) -> Image.Image:
        px = self.sizes[size]
        font = self.font(px)
        ref = "国"
        rb = self._bbox(ref, font)
        rw, rh = rb[2] - rb[0], rb[3] - rb[1]
        origin_x = (w - rw) // 2 - rb[0] + extra_xoff
        origin_y = (h - rh) // 2 - rb[1] + extra_yoff
        if is_punct(ch):
            dx, dy = self.punct_offset[size]
            origin_x += dx
            origin_y += dy
        img = Image.new("L", (w, h), 255)
        ImageDraw.Draw(img).text((origin_x, origin_y), ch, font=font, fill=0)
        if bold_radius > 0:
            inv = Image.eval(img, lambda p: 255 - p)
            inv = inv.filter(ImageFilter.MaxFilter(bold_radius * 2 + 1))
            img = Image.eval(inv, lambda p: 255 - p)
        return img

    def render_half(self, ch: str, size: int, w: int, h: int, bold_radius: int = 0, extra_xoff: int = 0, extra_yoff: int = 0) -> Image.Image:
        # Half-width slots are narrow. Start from the nominal font size and shrink
        # until the glyph bbox fits the slot, then align it on a common baseline.
        nominal = self.sizes[size]
        px = nominal
        while px >= max(7, nominal // 2):
            font = self.font(px)
            bb = self._bbox(ch, font)
            bw, bh = bb[2] - bb[0], bb[3] - bb[1]
            if bw <= max(1, w - 1) and bh <= max(1, h - 1):
                break
            px -= 1
        font = self.font(px)
        bb = self._bbox(ch, font)
        bw, bh = bb[2] - bb[0], bb[3] - bb[1]
        # Reference baseline from 'A' for ASCII-like half chars, but center glyphs
        # that still have unusual metrics. This keeps Latin/kana readable.
        x = (w - bw) // 2 - bb[0] + extra_xoff
        y = (h - bh) // 2 - bb[1] + extra_yoff
        img = Image.new("L", (w, h), 255)
        ImageDraw.Draw(img).text((x, y), ch, font=font, fill=0)
        if bold_radius > 0:
            inv = Image.eval(img, lambda p: 255 - p)
            inv = inv.filter(ImageFilter.MaxFilter(bold_radius * 2 + 1))
            img = Image.eval(inv, lambda p: 255 - p)
        return img

    def render(self, ch: str, size: int, glyph_kind: str, w: int, h: int, bold_radius: int = 0, xoff: int = 0, yoff: int = 0) -> Image.Image:
        if glyph_kind == "half":
            return self.render_half(ch, size, w, h, bold_radius, xoff, yoff)
        return self.render_full(ch, size, w, h, bold_radius, xoff, yoff)


def load_slot_to_draw_map(map_json: Path) -> tuple[dict[str, str], dict[str, Any]]:
    data = json.loads(map_json.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("mapping JSON must be an object: {CN_char: CP932_slot_char}")
    slot_to_cn: dict[str, str] = {}
    duplicate_slots: list[tuple[str, str, str]] = []
    bad_slots: list[tuple[str, str]] = []
    for cn, slot in data.items():
        if not isinstance(cn, str) or not isinstance(slot, str) or not cn or not slot:
            continue
        cn_ch = cn[0]
        slot_ch = slot[0]
        try:
            slot_ch.encode("cp932")
        except UnicodeEncodeError:
            bad_slots.append((cn_ch, slot_ch))
            continue
        if slot_ch in slot_to_cn:
            duplicate_slots.append((slot_ch, slot_to_cn[slot_ch], cn_ch))
        slot_to_cn[slot_ch] = cn_ch
    return slot_to_cn, {
        "mapping_entries": len(data),
        "unique_slots": len(slot_to_cn),
        "duplicate_slots": duplicate_slots,
        "bad_slots": bad_slots,
    }


def redraw_one_file(in_path: Path, out_path: Path, size: int, file_kind: str, renderer: FontRenderer, slot_to_cn: dict[str, str], xoff: int = 0, yoff: int = 0) -> dict[str, Any]:
    src = in_path.read_bytes()
    margin = 0
    if file_kind == "fk0":
        margin = struct.unpack_from("<I", src, 0)[0]
    lay = file_layout(size, file_kind, margin)
    if len(src) != lay["expected_size"]:
        raise ValueError(f"unexpected file size for {in_path}: actual={len(src)} expected={lay['expected_size']}")

    # Full redraw: start from blank data, not from original glyph data.
    out = bytearray(b"\x00" * lay["expected_size"])
    if file_kind == "fk0":
        struct.pack_into("<I", out, 0, margin)
    bold_radius = 0 if file_kind == "fd0" else max(1, margin)

    stats = {
        "file": in_path.name,
        "size": size,
        "kind": file_kind,
        "margin": margin,
        "drawn_slots": 0,
        "mapped_slots": 0,
        "fallback_original_slots": 0,
        "undecodable_slots": 0,
        "blank_padding_half_slots": 0,
    }

    for slot in iter_drawable_slots():
        glyph_kind = slot["kind"]
        idx = int(slot["index"])
        # fd0 has more half capacity than the engine draw table; only drawable
        # half slots are regenerated. Extra padding slots remain blank.
        if glyph_kind == "half" and idx >= lay["half_count"]:
            continue
        ch = slot["char"]
        if not ch:
            stats["undecodable_slots"] += 1
            continue
        draw_ch = slot_to_cn.get(ch, ch)
        if draw_ch != ch:
            stats["mapped_slots"] += 1
        else:
            stats["fallback_original_slots"] += 1
        off, w, h, nbytes = glyph_offset(size, file_kind, glyph_kind, idx, margin)
        img = renderer.render(draw_ch, size, glyph_kind, w, h, bold_radius=bold_radius, xoff=xoff, yoff=yoff)
        out[off:off + nbytes] = encode_glyph_from_image(img, w, h)
        stats["drawn_slots"] += 1

    if file_kind == "fd0":
        # fd0 has 20 unused/padding half slots after the actual half-width table.
        stats["blank_padding_half_slots"] = HALF_GLYPH_COUNT_FD_CAPACITY - HALF_GLYPH_COUNT_FK
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(out)
    return stats


def dump_sample_sheet(font_dir: Path, out_path: Path, title: str = "") -> None:
    # Decode selected glyphs from font24.fd0/fk0 and produce a quick visual check sheet.
    samples = "国這这説说為为們们，。？！……—·「」『』（）１２Ａあア"
    cell = 32
    rows = []
    labels = []
    for fname, file_kind, size in [("font24.fd0", "fd0", 24), ("font24.fk0", "fk0", 24), ("font12.fd0", "fd0", 12), ("font12.fk0", "fk0", 12)]:
        p = font_dir / fname
        if not p.exists():
            continue
        data = p.read_bytes()
        margin = struct.unpack_from("<I", data, 0)[0] if file_kind == "fk0" else 0
        lay = file_layout(size, file_kind, margin)
        row = Image.new("L", (cell * len(samples), cell), 255)
        for i, ch in enumerate(samples):
            try:
                raw = ch.encode("cp932")
            except UnicodeEncodeError:
                continue
            info = None
            if len(raw) == 1:
                b = raw[0]
                for base, start, end, draw in HALF_RANGES:
                    if draw and start <= b <= end:
                        info = ("half", base + b - start)
                        break
            elif len(raw) == 2:
                code = raw[0] << 8 | raw[1]
                for base, start, end, draw in FULL_RANGES:
                    if draw and start <= code <= end:
                        info = ("full", base + code - start)
                        break
            if not info:
                continue
            try:
                off, w, h, _ = glyph_offset(size, file_kind, info[0], info[1], margin)
                g = decode_glyph(data, off, w, h).resize((w * (24 // size), h * (24 // size)), Image.Resampling.NEAREST)
                row.paste(g, (i * cell + (cell - g.width) // 2, (cell - g.height) // 2))
            except Exception:
                pass
        rows.append(row.convert("RGB"))
        labels.append(fname)
    if not rows:
        return
    label_w = 120
    h = cell * len(rows)
    sheet = Image.new("RGB", (label_w + rows[0].width, h), "white")
    draw = ImageDraw.Draw(sheet)
    try:
        lf = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 14)
    except Exception:
        lf = None
    for r, img in enumerate(rows):
        draw.text((4, r * cell + 8), labels[r], fill="black", font=lf)
        sheet.paste(img, (label_w, r * cell))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out_path)


def cmd_full_redraw(args: argparse.Namespace) -> int:
    in_dir = Path(args.font_dir)
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    slot_to_cn, map_stats = load_slot_to_draw_map(Path(args.map_json))
    renderer = FontRenderer(
        Path(args.ttf), args.size12, args.size24, args.ttc_index,
        args.punct_dx24, args.punct_dy24, args.punct_dx12, args.punct_dy12,
    )
    all_stats: list[dict[str, Any]] = []
    for size in (12, 24):
        for file_kind, ext in [("fd0", "fd0"), ("fk0", "fk0")]:
            src = in_dir / f"font{size:02d}.{ext}"
            if not src.exists():
                print(f"[skip] missing {src}")
                continue
            dst = out_dir / src.name
            st = redraw_one_file(src, dst, size, file_kind, renderer, slot_to_cn, args.xoff, args.yoff)
            all_stats.append(st)
            print(f"[redraw] {src.name}: drawn={st['drawn_slots']} mapped={st['mapped_slots']} fallback={st['fallback_original_slots']} undecodable={st['undecodable_slots']}")
    for extra in ("_pak_manifest.json", "ＤＦ隷書体"):
        p = in_dir / extra
        if p.exists():
            shutil.copy2(p, out_dir / extra)
    report = {
        "mode": "full-redraw",
        "note": "Every drawable CP932/SJIS slot was regenerated from the supplied TTF/TTC. Mapped slots render CN glyphs; unmapped slots render their original CP932 characters. fd0/fk0 both rebuilt; fk0 uses dilated mask radius equal to margin.",
        "map_stats": map_stats,
        "render_params": {
            "size12": args.size12,
            "size24": args.size24,
            "ttc_index": args.ttc_index,
            "xoff": args.xoff,
            "yoff": args.yoff,
            "punct_dx24": args.punct_dx24,
            "punct_dy24": args.punct_dy24,
            "punct_dx12": args.punct_dx12,
            "punct_dy12": args.punct_dy12,
            "fk0_bold_radius": "margin",
        },
        "files": all_stats,
    }
    (out_dir / "full_redraw_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    dump_sample_sheet(out_dir, out_dir / "sample_sheet.png")
    print(f"[done] out={out_dir}")
    print(f"[done] report={out_dir / 'full_redraw_report.json'}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="Full redraw TtT fd0/fk0 bitmap fonts")
    p.add_argument("font_dir")
    p.add_argument("map_json")
    p.add_argument("output_dir")
    p.add_argument("--ttf", required=True)
    p.add_argument("--ttc-index", type=int, default=0)
    p.add_argument("--size12", type=int, default=12)
    p.add_argument("--size24", type=int, default=24)
    p.add_argument("--xoff", type=int, default=0)
    p.add_argument("--yoff", type=int, default=0)
    p.add_argument("--punct-dx24", type=int, default=2)
    p.add_argument("--punct-dy24", type=int, default=1)
    p.add_argument("--punct-dx12", type=int, default=1)
    p.add_argument("--punct-dy12", type=int, default=1)
    return cmd_full_redraw(p.parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
