import json
import os
import struct
import sys
from dataclasses import dataclass
from PIL import Image


SIG_FSG = b"fSG "
SEC_CRGB = b"cRGB"


@dataclass
class SgMeta:
    section_id: str
    section_size: int
    header_size: int
    data_size: int
    mode: int
    surface_w: int
    surface_h: int
    x: int
    y: int
    width: int
    height: int
    unk_2a: int
    bpp: int
    header_extra_hex: str

    @property
    def channels(self) -> int:
        return self.bpp // 8


def _read_u16_le(buf: bytes, off: int) -> int:
    return struct.unpack_from("<H", buf, off)[0]


def _read_s16_le(buf: bytes, off: int) -> int:
    return struct.unpack_from("<h", buf, off)[0]


def _write_run_len(run: int, repeated: bool) -> bytearray:
    if run <= 0:
        raise ValueError("Run length must be > 0")
    out = bytearray()
    remaining = run
    while remaining > 0:
        chunk = min(remaining, 0x3FFF)
        lo = chunk & 0xFF
        if chunk <= 0x3F:
            ctl = chunk
        else:
            hi = chunk >> 8
            ctl = hi & 0x3F
            ctl |= 0x40
        if repeated:
            ctl |= 0x80
        out.append(ctl)
        if chunk > 0x3F:
            out.append(lo)
        remaining -= chunk
    return out


def _decode_mode3(payload: bytes, width: int, height: int, channels: int) -> bytes:
    if len(payload) < height * 4:
        raise ValueError("Truncated payload index table")
    row_offsets = struct.unpack_from(f"<{height}I", payload, 0)
    data_pos = height * 4
    row_stride = width * channels
    out = bytearray(row_stride * height)
    for y in range(height):
        src = data_pos + row_offsets[y]
        dst = y * row_stride
        x = 0
        while x < width:
            if src >= len(payload):
                raise ValueError(f"Row {y}: unexpected EOF while reading control byte")
            ctl = payload[src]
            src += 1
            count = ctl & 0x3F
            if ctl & 0x40:
                if src >= len(payload):
                    raise ValueError(f"Row {y}: unexpected EOF while reading run extension")
                count = (count << 8) | payload[src]
                src += 1
            if count <= 0:
                raise ValueError(f"Row {y}: invalid run length {count}")

            if x + count > width:
                raise ValueError(f"Row {y}: run length overflows row (x={x}, count={count}, width={width})")

            byte_count = count * channels
            if ctl & 0x80:
                if src + channels > len(payload):
                    raise ValueError(f"Row {y}: unexpected EOF while reading repeated pixel")
                px = payload[src : src + channels]
                src += channels
                for _ in range(count):
                    out[dst : dst + channels] = px
                    dst += channels
            else:
                if src + byte_count > len(payload):
                    raise ValueError(f"Row {y}: unexpected EOF while reading literal run")
                out[dst : dst + byte_count] = payload[src : src + byte_count]
                src += byte_count
                dst += byte_count
            x += count
    return bytes(out)


def _encode_mode3(raw_rows: bytes, width: int, height: int, channels: int) -> bytes:
    row_stride = width * channels
    rows_blob = bytearray()
    row_offsets = []

    for y in range(height):
        row_offsets.append(len(rows_blob))
        row = raw_rows[y * row_stride : (y + 1) * row_stride]
        x = 0
        while x < width:
            # Greedy repeat-run if it saves bytes; otherwise emit literal run.
            base = x * channels
            px = row[base : base + channels]
            run = 1
            while x + run < width and run < 0x3FFF:
                b = (x + run) * channels
                if row[b : b + channels] != px:
                    break
                run += 1

            if run >= 2:
                rows_blob.extend(_write_run_len(run, repeated=True))
                rows_blob.extend(px)
                x += run
                continue

            lit_start = x
            x += 1
            while x < width:
                base = x * channels
                px = row[base : base + channels]
                rep = 1
                while x + rep < width and rep < 2:
                    b = (x + rep) * channels
                    if row[b : b + channels] != px:
                        break
                    rep += 1
                if rep >= 2:
                    break
                if x - lit_start >= 0x3FFF:
                    break
                x += 1

            lit_count = x - lit_start
            rows_blob.extend(_write_run_len(lit_count, repeated=False))
            rows_blob.extend(row[lit_start * channels : x * channels])

    table = struct.pack(f"<{height}I", *row_offsets)
    return table + bytes(rows_blob)


def _bgr_to_png_bytes(raw_bgr_or_bgra: bytes, width: int, height: int, channels: int) -> bytes:
    if channels == 3:
        out = bytearray(len(raw_bgr_or_bgra))
        out[0::3] = raw_bgr_or_bgra[2::3]
        out[1::3] = raw_bgr_or_bgra[1::3]
        out[2::3] = raw_bgr_or_bgra[0::3]
        return bytes(out)

    out = bytearray(len(raw_bgr_or_bgra))
    out[0::4] = raw_bgr_or_bgra[2::4]
    out[1::4] = raw_bgr_or_bgra[1::4]
    out[2::4] = raw_bgr_or_bgra[0::4]
    out[3::4] = raw_bgr_or_bgra[3::4]
    return bytes(out)


def _png_to_bgr_bytes(img: Image.Image, bpp: int) -> bytes:
    if bpp == 24:
        rgb = img.convert("RGB").tobytes()
        out = bytearray(len(rgb))
        out[0::3] = rgb[2::3]
        out[1::3] = rgb[1::3]
        out[2::3] = rgb[0::3]
        return bytes(out)

    rgba = img.convert("RGBA").tobytes()
    out = bytearray(len(rgba))
    out[0::4] = rgba[2::4]
    out[1::4] = rgba[1::4]
    out[2::4] = rgba[0::4]
    out[3::4] = rgba[3::4]
    return bytes(out)


def read_sg(path: str) -> tuple[SgMeta, bytes]:
    with open(path, "rb") as f:
        data = f.read()
    if len(data) < 52:
        raise ValueError("File too small for SG")
    if data[:4] != SIG_FSG:
        raise ValueError("Not an a valid SG file!")
    section_id = data[8:12]
    if section_id != SEC_CRGB:
        raise NotImplementedError(f"Unsupported SG section: {section_id!r} (only cRGB is supported)")
    section_size = struct.unpack_from("<I", data, 12)[0]
    header_size = struct.unpack_from("<I", data, 16)[0]
    data_size = struct.unpack_from("<I", data, 20)[0]
    if header_size < 44:
        raise ValueError(f"Unexpected cRGB header size: {header_size}")
    if 8 + section_size > len(data):
        raise ValueError("Section size exceeds file size")
    header = data[8 : 8 + header_size]
    mode = struct.unpack_from("<I", header, 16)[0]
    surface_w = _read_u16_le(header, 20)
    surface_h = _read_u16_le(header, 22)
    x = _read_s16_le(header, 24)
    y = _read_s16_le(header, 26)
    width = _read_u16_le(header, 28)
    height = _read_u16_le(header, 30)
    unk_2a = _read_u16_le(header, 32)
    bpp = _read_u16_le(header, 34)

    if bpp not in (24, 32):
        raise NotImplementedError(f"Unsupported bpp: {bpp}")
    payload_off = 8 + header_size
    payload = data[payload_off : payload_off + data_size]
    if len(payload) != data_size:
        raise ValueError("Truncated SG payload")

    meta = SgMeta(
        section_id="cRGB",
        section_size=section_size,
        header_size=header_size,
        data_size=data_size,
        mode=mode,
        surface_w=surface_w,
        surface_h=surface_h,
        x=x,
        y=y,
        width=width,
        height=height,
        unk_2a=unk_2a,
        bpp=bpp,
        header_extra_hex=header[36:].hex() if header_size > 44 else "",
    )
    return meta, payload


def _meta_path_from_sg(sg_path: str, out_dir: str) -> str:
    base = os.path.splitext(os.path.basename(sg_path))[0]
    return os.path.join(out_dir, f"{base}.meta.json")


def _meta_path_from_png(png_path: str) -> str:
    base = os.path.splitext(os.path.basename(png_path))[0]
    return os.path.join(os.path.dirname(png_path), f"{base}.meta.json")


def decode_sg_to_png(sg_path: str, png_path: str) -> None:
    meta, payload = read_sg(sg_path)
    channels = meta.channels
    if meta.mode != 3:
        raise NotImplementedError(f"Unsupported cRGB mode {meta.mode}. This tool currently supports mode 3 only.")

    raw_bgr = _decode_mode3(payload, meta.width, meta.height, channels)
    raw_png = _bgr_to_png_bytes(raw_bgr, meta.width, meta.height, channels)
    img_mode = "RGBA" if channels == 4 else "RGB"
    img = Image.frombytes(img_mode, (meta.width, meta.height), raw_png)
    img.save(png_path)
    print(f"Wrote PNG: {png_path}")

    meta_path = _meta_path_from_sg(sg_path, os.path.dirname(png_path))
    meta_obj = {
        "section_id": meta.section_id,
        "header_size": meta.header_size,
        "mode": meta.mode,
        "surface_w": meta.surface_w,
        "surface_h": meta.surface_h,
        "x": meta.x,
        "y": meta.y,
        "width": meta.width,
        "height": meta.height,
        "unk_2a": meta.unk_2a,
        "bpp": meta.bpp,
        "header_extra_hex": meta.header_extra_hex,
    }
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta_obj, f, ensure_ascii=False, indent=2)
    print(f"Wrote meta: {meta_path}")


def _load_meta(meta_path: str, width: int, height: int, bpp_hint: int | None) -> SgMeta:
    with open(meta_path, "r", encoding="utf-8") as f:
        m = json.load(f)
    bpp = int(m.get("bpp", bpp_hint or 32))
    return SgMeta(
        section_id=str(m.get("section_id", "cRGB")),
        section_size=0,
        header_size=int(m.get("header_size", 44)),
        data_size=0,
        mode=int(m.get("mode", 3)),
        surface_w=int(m.get("surface_w", width)),
        surface_h=int(m.get("surface_h", height)),
        x=int(m.get("x", 0)),
        y=int(m.get("y", 0)),
        width=int(m.get("width", width)),
        height=int(m.get("height", height)),
        unk_2a=int(m.get("unk_2a", 72)),
        bpp=bpp,
        header_extra_hex=str(m.get("header_extra_hex", "")),
    )


def encode_png_to_sg(
    png_path: str,
    sg_path: str,
) -> None:
    img = Image.open(png_path)
    width, height = img.size

    sg_meta_path = _meta_path_from_sg(sg_path, os.path.dirname(sg_path))
    png_meta_path = _meta_path_from_png(png_path)

    if os.path.isfile(sg_meta_path):
        meta = _load_meta(sg_meta_path, width, height, None)
        print(f"Using meta: {sg_meta_path}")
    elif os.path.isfile(png_meta_path):
        meta = _load_meta(png_meta_path, width, height, None)
        print(f"Using meta: {png_meta_path}")
    else:
        guessed_bpp = 32 if ("A" in img.getbands()) else 24
        meta = SgMeta(
            section_id="cRGB",
            section_size=0,
            header_size=44,
            data_size=0,
            mode=3,
            surface_w=width,
            surface_h=height,
            x=0,
            y=0,
            width=width,
            height=height,
            unk_2a=72,
            bpp=guessed_bpp,
            header_extra_hex="",
        )
        print("Meta not found, using PNG defaults.")

    if meta.mode != 3:
        raise NotImplementedError(f"Unsupported cRGB mode {meta.mode}. This tool currently writes mode 3 only.")
    if meta.bpp not in (24, 32):
        raise ValueError("bpp must be 24 or 32")
    if meta.width != width or meta.height != height:
        raise ValueError(
            f"PNG size {width}x{height} does not match meta size {meta.width}x{meta.height}. "
            "Update meta or use a matching image."
        )
    if meta.header_size < 44:
        raise ValueError("header_size must be >= 44")

    raw_bgr = _png_to_bgr_bytes(img, meta.bpp)
    payload = _encode_mode3(raw_bgr, meta.width, meta.height, meta.channels)
    data_size = len(payload)
    pad = (-data_size) & 3
    section_size = meta.header_size + data_size + pad
    total_size = 8 + section_size

    header = bytearray(meta.header_size)
    header[0:4] = SEC_CRGB
    struct.pack_into("<I", header, 4, section_size)
    struct.pack_into("<I", header, 8, meta.header_size)
    struct.pack_into("<I", header, 12, data_size)
    struct.pack_into("<I", header, 16, 3)
    struct.pack_into("<H", header, 20, meta.surface_w)
    struct.pack_into("<H", header, 22, meta.surface_h)
    struct.pack_into("<h", header, 24, meta.x)
    struct.pack_into("<h", header, 26, meta.y)
    struct.pack_into("<H", header, 28, meta.width)
    struct.pack_into("<H", header, 30, meta.height)
    struct.pack_into("<H", header, 32, meta.unk_2a)
    struct.pack_into("<H", header, 34, meta.bpp)
    if meta.header_size > 44 and meta.header_extra_hex:
        extra = bytes.fromhex(meta.header_extra_hex)
        header[36 : 36 + min(len(extra), meta.header_size - 36)] = extra[: meta.header_size - 36]

    with open(sg_path, "wb") as f:
        f.write(SIG_FSG)
        f.write(struct.pack("<I", total_size))
        f.write(header)
        f.write(payload)
        if pad:
            f.write(b"\x00" * pad)
    print(f"Wrote SG: {sg_path}")


def main() -> None:
    if len(sys.argv) < 4:
        print("Usage:")
        print("  Decode: sg.py -d <input_sg> <output_png>")
        print("  Encode: sg.py -e <input_png> <output_sg>")
        sys.exit(1)

    mode = sys.argv[1].lower()
    src = sys.argv[2]
    dst = sys.argv[3]
    rest = sys.argv[4:]
    if rest:
        raise ValueError(f"Unknown extra arguments: {' '.join(rest)}")

    if mode in ("decode", "-d"):
        decode_sg_to_png(src, dst)
        return

    if mode in ("encode", "-e"):
        encode_png_to_sg(src, dst)
        return

    print(f"Invalid mode: {sys.argv[1]}")
    sys.exit(1)


if __name__ == "__main__":
    main()
