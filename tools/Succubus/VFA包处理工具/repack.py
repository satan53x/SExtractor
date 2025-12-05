import json
import struct
from pathlib import Path

SRC = Path("grp.vfa")
OUT_DIR = Path("extracted")
INDEX = Path("index.json")
DST = Path("grp_repack.vfa")

idx = json.loads(INDEX.read_text(encoding="utf-8"))
entries = idx["entries"]

file_datas = []
cur = 0
for e in entries:
    if e["type"] == "file":
        full = e["dir"] + e["name"]
        content = (OUT_DIR / Path(full)).read_bytes()
        file_datas.append((e, cur, content))
        cur += len(content)

data_bytes = b"".join(content for _, _, content in file_datas)

dent_parts = []
for e in entries:
    if e["type"] == "dir":
        name_bytes = e["name"].encode("utf-16le") + b"\x00\x00"
        size = len(name_bytes)
        dent_parts.append(b"dir " + struct.pack("<I", size) + name_bytes)
    else:
        name_bytes = e["name"].encode("utf-16le") + b"\x00\x00"
        fe, offset, content = file_datas.pop(0)
        meta = struct.pack("<4I", offset, len(content), fe["stamp"], fe["flags"])
        size = len(name_bytes) + 16
        dent_parts.append(b"file" + struct.pack("<I", size) + name_bytes + meta)

dent_payload = b"".join(dent_parts)
dent_chunk = b"dent" + struct.pack("<I", len(dent_payload)) + dent_payload

hdri_payload = struct.pack("<II4s4s", 0x00010000, 0x00000001, b"dent", b"data")
hdri_chunk = b"hdri" + struct.pack("<I", len(hdri_payload)) + hdri_payload

data_chunk = b"data" + struct.pack("<I", len(data_bytes)) + bytes(data_bytes)

riff_size = 4 + len(hdri_chunk) + len(data_chunk) + len(dent_chunk)
result = b"RIFF" + struct.pack("<I", riff_size) + b"VFA1" + hdri_chunk + data_chunk + dent_chunk

DST.write_bytes(result)

orig = SRC.read_bytes()
rebuilt = DST.read_bytes()
print("equal:", orig == rebuilt, "orig:", len(orig), "rebuilt:", len(rebuilt))
