import json
import os
import struct
import sys
from typing import Dict, List, Tuple


def rol32(v: int, count: int) -> int:
    count &= 0x1F
    return ((v << count) | (v >> (32 - count))) & 0xFFFFFFFF


def generate_keys(seed: int) -> Tuple[List[int], List[int]]:
    ctl = [0] * 32
    keys = [0] * 32
    for i in range(32):
        code = 0
        k = seed
        for _ in range(16):
            code = (((k ^ (k >> 1)) << 15) | ((code & 0xFFFF) >> 1)) & 0xFFFFFFFF
            k >>= 2
        keys[i] = seed
        ctl[i] = code & 0xFFFF
        seed = rol32(seed, 1)
    return ctl, keys


def process_data(data: bytes, seed: int, is_encrypt: bool = False) -> bytes:
    ctl, keys = generate_keys(seed)
    ints_count = len(data) // 4
    if ints_count == 0:
        return data
    ints = list(struct.unpack(f"<{ints_count}I", data[:ints_count * 4]))
    for i in range(ints_count):
        val = ints[i]
        if is_encrypt:
            val ^= keys[i & 0x1F]
        code = ctl[i & 0x1F]
        d = 0
        v3, v2, v1 = 3, 2, 1
        for _ in range(16):
            if code & 1:
                d |= ((val & v1) << 1) | ((val >> 1) & (v2 >> 1))
            else:
                d |= val & v3
            code >>= 1
            v3 = (v3 << 2) & 0xFFFFFFFF
            v2 = (v2 << 2) & 0xFFFFFFFF
            v1 = (v1 << 2) & 0xFFFFFFFF
        if not is_encrypt:
            d ^= keys[i & 0x1F]
        ints[i] = d
    res = struct.pack(f"<{ints_count}I", *ints)
    return res + data[ints_count * 4:]


def get_c_string(buf: bytes, offset: int) -> str:
    if offset < 0 or offset >= len(buf):
        return ""
    end = buf.find(b"\x00", offset)
    if end < 0:
        end = len(buf)
    return buf[offset:end].decode("cp932")

def decode_vm_text(raw: bytes) -> str:
    out = bytearray()
    i = 0
    while i < len(raw):
        b = raw[i]
        if b == 0xFF and i + 1 < len(raw):
            c = raw[i + 1]
            if c in (0x4E, 0x6E):  # FFN / FFn
                out.extend(b"\n")
                i += 2
                continue
            if c in (0x53, 0x73):  # FFS / FFs
                out.extend(b" ")
                i += 2
                continue
        out.append(b)
        i += 1
    return out.decode("cp932")

def get_vm_string(buf: bytes, offset: int) -> str:
    if offset < 0 or offset >= len(buf):
        return ""
    end = buf.find(b"\x00", offset)
    if end < 0:
        end = len(buf)
    return decode_vm_text(buf[offset:end])

def encode_vm_text(text: str) -> bytes:
    text = text.replace("\r\n", "\n").replace("\\n", "\n")
    out = bytearray()
    for ch in text:
        if ch == "\n":
            out.extend(b"\xFFn")
        elif ch == "\r":
            continue
        else:
            out.extend(ch.encode("cp932"))
    return bytes(out)


def parse_fags_sections(ocb_path: str) -> List[Dict]:
    sections = []
    with open(ocb_path, "rb") as f:
        sig = f.read(4)
        if sig != b"fAGS":
            raise ValueError(f"{ocb_path}: invalid signature {sig!r}")
        total_size = struct.unpack("<I", f.read(4))[0]
        if total_size > os.path.getsize(ocb_path):
            raise ValueError(f"{ocb_path}: invalid declared size {total_size}")

        while f.tell() < total_size:
            sec_start = f.tell()
            sec_id = f.read(4)
            if not sec_id:
                break
            sec_size, hdr_size = struct.unpack("<II", f.read(8))
            if sec_size < 12 or hdr_size < 12 or hdr_size > sec_size:
                raise ValueError(f"{ocb_path}: invalid section header at 0x{sec_start:X}")
            f.seek(sec_start)
            raw = f.read(sec_size)
            if len(raw) != sec_size:
                raise ValueError(f"{ocb_path}: truncated section at 0x{sec_start:X}")
            sections.append(
                {
                    "id": sec_id.decode("ascii"),
                    "start": sec_start,
                    "size": sec_size,
                    "hdr_size": hdr_size,
                    "raw": raw,
                }
            )
    return sections


def decode_ctex_from_raw(raw: bytes) -> Tuple[int, int, bytes]:
    hdr_size = struct.unpack("<I", raw[8:12])[0]
    key = struct.unpack("<I", raw[12:16])[0]
    payload = raw[hdr_size:]
    return hdr_size, key, process_data(payload, key, False)


def decode_ccod_from_raw(raw: bytes) -> Dict:
    hdr_size = struct.unpack("<I", raw[8:12])[0]
    bytecode_size_field = struct.unpack("<I", raw[12:16])[0]
    key = struct.unpack("<I", raw[16:20])[0]
    script_id = struct.unpack("<I", raw[20:24])[0]
    jump_count = struct.unpack("<I", raw[24:28])[0]

    payload_dec = process_data(raw[hdr_size:], key, False)
    bytecode_len = bytecode_size_field - hdr_size
    if bytecode_len < 0 or bytecode_len > len(payload_dec):
        raise ValueError(
            f"Invalid cCOD bytecode size field: field=0x{bytecode_size_field:X}, "
            f"hdr=0x{hdr_size:X}, payload={len(payload_dec)}"
        )
    table_bytes = jump_count * 4
    if bytecode_len + table_bytes > len(payload_dec):
        raise ValueError(
            f"Invalid cCOD jump table range: bytecode={bytecode_len}, "
            f"count={jump_count}, payload={len(payload_dec)}"
        )
    jump_table = list(struct.unpack(f"<{jump_count}I", payload_dec[bytecode_len:bytecode_len + table_bytes]))
    tail = payload_dec[bytecode_len + table_bytes:]
    return {
        "hdr_size": hdr_size,
        "bytecode_size_field": bytecode_size_field,
        "bytecode_len": bytecode_len,
        "key": key,
        "script_id": script_id,
        "jump_count": jump_count,
        "payload_dec": payload_dec,
        "bytecode": bytearray(payload_dec[:bytecode_len]),
        "jump_table": jump_table,
        "tail": tail,
    }


def scan_text_sites(bytecode: bytes, ctex_dec: bytes) -> Tuple[List[Dict], List[Dict]]:
    simple_entries = []
    meta_entries = []
    pos = 0
    while pos + 4 <= len(bytecode):
        op_type, op_len = struct.unpack_from("<HH", bytecode, pos)
        if op_len == 0 or pos + op_len > len(bytecode):
            raise ValueError(f"Invalid opcode length at 0x{pos:X}: type=0x{op_type:02X}, len=0x{op_len:X}")

        if op_type == 0x01 and op_len >= 0x0C:
            ptr = struct.unpack_from("<I", bytecode, pos + 8)[0]
            simple_entries.append(
                {"message": get_vm_string(ctex_dec, ptr)}
            )
            meta_entries.append(
                {
                    "kind": "message",
                    "op_pos": pos,
                    "op_type": op_type,
                    "op_len": op_len,
                    "field_offset": 8,
                    "ptr": ptr,
                }
            )
        elif op_type == 0x02 and op_len >= 0x14:
            name_ptr, msg_ptr = struct.unpack_from("<II", bytecode, pos + 8)
            simple_entries.append(
                {
                    "name": get_vm_string(ctex_dec, name_ptr),
                    "message": get_vm_string(ctex_dec, msg_ptr),
                }
            )
            meta_entries.append(
                {
                    "kind": "name_message",
                    "op_pos": pos,
                    "op_type": op_type,
                    "op_len": op_len,
                    "name_field_offset": 8,
                    "name_ptr": name_ptr,
                    "msg_field_offset": 12,
                    "msg_ptr": msg_ptr,
                }
            )
        elif op_type == 0x09 and op_len >= 0x14:
            count = struct.unpack_from("<I", bytecode, pos + 12)[0]
            for i in range(count):
                field_off = 20 + i * 12
                if pos + field_off + 4 <= pos + op_len:
                    ptr = struct.unpack_from("<I", bytecode, pos + field_off)[0]
                    simple_entries.append(
                        {"choice": get_vm_string(ctex_dec, ptr)}
                    )
                    meta_entries.append(
                        {
                            "kind": "choice",
                            "op_pos": pos,
                            "op_type": op_type,
                            "op_len": op_len,
                            "field_offset": field_off,
                            "ptr": ptr,
                        }
                    )
        elif op_type == 0x2F and op_len >= 0x08:
            ptr = struct.unpack_from("<I", bytecode, pos + 4)[0]
            simple_entries.append(
                {"message": get_vm_string(ctex_dec, ptr)}
            )
            meta_entries.append(
                {
                    "kind": "title",
                    "op_pos": pos,
                    "op_type": op_type,
                    "op_len": op_len,
                    "field_offset": 4,
                    "ptr": ptr,
                }
            )

        pos += op_len
    return simple_entries, meta_entries


def export_ocb(ocb_path: str, outdir: str) -> None:
    os.makedirs(outdir, exist_ok=True)
    sections = parse_fags_sections(ocb_path)
    by_id = {s["id"]: s for s in sections}
    if "cTEX" not in by_id or "cCOD" not in by_id:
        raise ValueError("Missing cTEX or cCOD section")

    for sec in sections:
        with open(os.path.join(outdir, f'{sec["id"]}.bin'), "wb") as f:
            f.write(sec["raw"])

    _, _, ctex_dec = decode_ctex_from_raw(by_id["cTEX"]["raw"])
    ccod = decode_ccod_from_raw(by_id["cCOD"]["raw"])
    simple_entries, meta_entries = scan_text_sites(ccod["bytecode"], ctex_dec)
    for idx, e in enumerate(meta_entries):
        e["entry_id"] = idx
        e["op_type_hex"] = f'0x{e["op_type"]:02X}'

    meta = {
        "version": 1,
        "source_file": os.path.basename(ocb_path),
        "encoding": "cp932",
        "ctex_terminator": "double_null",
        "ccod": {
            "header_size": ccod["hdr_size"],
            "bytecode_size_field": ccod["bytecode_size_field"],
            "bytecode_len": ccod["bytecode_len"],
            "jump_table_count": ccod["jump_count"],
            "tail_size": len(ccod["tail"]),
            "text_site_count": len(meta_entries),
        },
        "entries": meta_entries,
    }
    base_name = os.path.splitext(os.path.basename(ocb_path))[0]
    json_name = f"{base_name}.json"
    meta_name = f"{base_name}.meta.json"

    with open(os.path.join(outdir, json_name), "w", encoding="utf-8") as f:
        json.dump(simple_entries, f, ensure_ascii=False, indent=2)
    with open(os.path.join(outdir, meta_name), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    print(f"Exported {len(meta_entries)} text sites to {os.path.join(outdir, json_name)}")

def resolve_json_pair(indir: str) -> Tuple[str, str]:
    meta_candidates = sorted(
        x for x in os.listdir(indir) if x.lower().endswith(".meta.json")
    )
    if meta_candidates:
        if len(meta_candidates) > 1:
            raise ValueError(
                f"Multiple *.meta.json files found in {indir}. Keep only one pair."
            )
        meta_name = meta_candidates[0]
        base = meta_name[:-len(".meta.json")]
        json_name = f"{base}.json"
        json_path = os.path.join(indir, json_name)
        if not os.path.isfile(json_path):
            raise ValueError(
                f"Missing paired json file for {meta_name}: expected {json_name}"
            )
        return json_path, os.path.join(indir, meta_name)

    raise ValueError(
        f"No valid json/meta pair found in {indir}. Expected <base>.json + <base>.meta.json"
    )

def append_text_double_null(ctex: bytearray, text: str) -> int:
    if len(ctex) & 1:
        ctex.append(0)
    off = len(ctex)
    ctex.extend(encode_vm_text(text) + b"\x00\x00")
    return off


def import_ocb(indir: str, out_ocb: str) -> None:
    json_path, meta_path = resolve_json_pair(indir)
    ctex_path = os.path.join(indir, "cTEX.bin")
    ccod_path = os.path.join(indir, "cCOD.bin")
    if not os.path.isfile(ctex_path) or not os.path.isfile(ccod_path):
        raise ValueError("Need cTEX.bin and cCOD.bin in input directory")

    with open(json_path, "r", encoding="utf-8") as f:
        simple_entries = json.load(f)
    with open(meta_path, "r", encoding="utf-8") as f:
        meta_doc = json.load(f)
    meta_entries = meta_doc.get("entries", [])
    if len(simple_entries) != len(meta_entries):
        raise ValueError(
            f"Entry count mismatch between json ({len(simple_entries)}) and meta ({len(meta_entries)})"
        )

    with open(ctex_path, "rb") as f:
        raw_ctex = bytearray(f.read())
    ctex_hdr_size = struct.unpack("<I", raw_ctex[8:12])[0]
    ctex_key = struct.unpack("<I", raw_ctex[12:16])[0]
    old_ctex = process_data(bytes(raw_ctex[ctex_hdr_size:]), ctex_key, False)
    new_ctex = bytearray(old_ctex)

    ptr_remap_by_entry: Dict[Tuple[int, str], int] = {}
    new_ptr_by_text: Dict[str, int] = {}
    for i, meta in enumerate(meta_entries):
        entry = simple_entries[i]
        kind = meta["kind"]
        entry_id = meta["entry_id"]

        if kind == "name_message":
            fields = [
                ("name", meta["name_ptr"]),
                ("message", meta["msg_ptr"]),
            ]
        elif kind == "choice":
            fields = [("choice", meta["ptr"])]
        else:
            fields = [("message", meta["ptr"])]

        for field_name, old_ptr in fields:
            if field_name not in entry:
                raise ValueError(f"Entry {i} missing field '{field_name}' required by metadata")
            new_text = entry[field_name]
            old_text = get_vm_string(old_ctex, old_ptr)

            if new_text == old_text:
                ptr_remap_by_entry[(entry_id, field_name)] = old_ptr
                continue

            if new_text in new_ptr_by_text:
                ptr_remap_by_entry[(entry_id, field_name)] = new_ptr_by_text[new_text]
                continue

            try:
                new_ptr = append_text_double_null(new_ctex, new_text)
            except UnicodeEncodeError as ex:
                raise ValueError(
                    f"Entry {i} field '{field_name}' contains characters not encodable in cp932: {new_text!r}"
                ) from ex
            new_ptr_by_text[new_text] = new_ptr
            ptr_remap_by_entry[(entry_id, field_name)] = new_ptr

    while len(new_ctex) % 4:
        new_ctex.append(0)

    with open(ccod_path, "rb") as f:
        raw_ccod = bytearray(f.read())
    ccod = decode_ccod_from_raw(raw_ccod)
    bytecode = ccod["bytecode"]

    for meta in meta_entries:
        op_pos = meta["op_pos"]
        op_type = meta["op_type"]
        op_len = meta["op_len"]
        entry_id = meta["entry_id"]
        kind = meta["kind"]

        if op_pos + 4 > len(bytecode):
            raise ValueError(f"Entry {entry_id} points outside bytecode (op_pos=0x{op_pos:X})")
        cur_type, cur_len = struct.unpack_from("<HH", bytecode, op_pos)
        if cur_type != op_type or cur_len != op_len:
            raise ValueError(
                f"Entry {entry_id} opcode mismatch at 0x{op_pos:X}: "
                f"expected type=0x{op_type:02X},len=0x{op_len:X} "
                f"got type=0x{cur_type:02X},len=0x{cur_len:X}"
            )
        if kind == "name_message":
            for field_name, field_off in (("name", meta["name_field_offset"]), ("message", meta["msg_field_offset"])):
                if field_off + 4 > cur_len:
                    raise ValueError(
                        f"Entry {entry_id} field offset out of range: op_len=0x{cur_len:X}, off=0x{field_off:X}"
                    )
                struct.pack_into("<I", bytecode, op_pos + field_off, ptr_remap_by_entry[(entry_id, field_name)])
        else:
            field_name = "choice" if kind == "choice" else "message"
            field_off = meta["field_offset"]
            if field_off + 4 > cur_len:
                raise ValueError(
                    f"Entry {entry_id} field offset out of range: op_len=0x{cur_len:X}, off=0x{field_off:X}"
                )
            struct.pack_into("<I", bytecode, op_pos + field_off, ptr_remap_by_entry[(entry_id, field_name)])

    new_ccod_payload = bytes(bytecode) + struct.pack(f"<{ccod['jump_count']}I", *ccod["jump_table"]) + ccod["tail"]
    if len(new_ccod_payload) != len(ccod["payload_dec"]):
        raise ValueError("Internal error: cCOD payload size changed unexpectedly")

    os.makedirs(os.path.dirname(os.path.abspath(out_ocb)), exist_ok=True)
    with open(out_ocb, "wb") as outf:
        outf.write(b"fAGS\x00\x00\x00\x00")

        all_bins = [x for x in os.listdir(indir) if x.endswith(".bin")]
        preferred = ["cTEX.bin", "cFNM.bin", "cCOD.bin"]
        order = [x for x in preferred if x in all_bins] + [x for x in all_bins if x not in preferred]

        for name in order:
            with open(os.path.join(indir, name), "rb") as f:
                raw = bytearray(f.read())
            sec_id = raw[:4]
            hdr_size = struct.unpack("<I", raw[8:12])[0]

            if sec_id == b"cTEX":
                enc = process_data(bytes(new_ctex), ctex_key, True)
                struct.pack_into("<I", raw, 4, hdr_size + len(enc))
                outf.write(raw[:hdr_size])
                outf.write(enc)
            elif sec_id == b"cCOD":
                enc = process_data(new_ccod_payload, ccod["key"], True)
                struct.pack_into("<I", raw, 4, hdr_size + len(enc))
                outf.write(raw[:hdr_size])
                outf.write(enc)
            else:
                outf.write(raw)

        final_size = outf.tell()
        outf.seek(4)
        outf.write(struct.pack("<I", final_size))
    print(f"Packed {out_ocb} with {len(meta_entries)} text sites")


def main() -> None:
    if len(sys.argv) != 4:
        print("Usage:")
        print("  Decompile: python ocb.py -d <input.ocb> <output_dir>")
        print("  Compile:   python ocb.py -c <input_dir> <output.ocb>")
        sys.exit(1)

    mode = sys.argv[1].lower()
    src = sys.argv[2]
    dst = sys.argv[3]

    if mode in ("-d", "--decompile"):
        export_ocb(src, dst)
    elif mode in ("-c", "--compile"):
        import_ocb(src, dst)
    else:
        print(f"Unknown mode: {mode}")
        sys.exit(1)


if __name__ == "__main__":
    main()
