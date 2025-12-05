import json
import struct
from pathlib import Path

SRC = Path("grp.vfa")
OUT_DIR = Path("extracted")
INDEX = Path("index.json")

data = SRC.read_bytes()
pos = 0

riff_magic = data[pos:pos + 4]
riff_size = struct.unpack("<I", data[pos + 4:pos + 8])[0]
form = data[pos + 8:pos + 12]
pos += 12

tag = data[pos:pos + 4]
hdri_size = struct.unpack("<I", data[pos + 4:pos + 8])[0]
hdri_payload = data[pos + 8:pos + 8 + hdri_size]
pos += 8 + hdri_size

tag = data[pos:pos + 4]
data_size = struct.unpack("<I", data[pos + 4:pos + 8])[0]
data_payload_start = pos + 8
data_payload = data[data_payload_start:data_payload_start + data_size]
pos += 8 + data_size

tag = data[pos:pos + 4]
dent_size = struct.unpack("<I", data[pos + 4:pos + 8])[0]
dent_payload = data[pos + 8:pos + 8 + dent_size]

OUT_DIR.mkdir(parents=True, exist_ok=True)

entries = []
current_dir = ""
off = 0
while off < dent_size:
    tag = dent_payload[off:off + 4]
    size = struct.unpack("<I", dent_payload[off + 4:off + 8])[0]
    payload = dent_payload[off + 8:off + 8 + size]
    if tag == b"dir ":
        name = payload.decode("utf-16le").rstrip("\x00")
        current_dir = name
        entries.append({"type": "dir", "name": name})
    else:
        nul = next(i for i in range(0, len(payload), 2) if payload[i:i + 2] == b"\x00\x00")
        name_bytes = payload[:nul]
        rest = payload[nul + 2:]
        name = name_bytes.decode("utf-16le")
        offset, length, stamp, flags = struct.unpack("<4I", rest[:16])
        full = current_dir + name
        path = OUT_DIR / Path(full)
        path.parent.mkdir(parents=True, exist_ok=True)
        content = data_payload[offset:offset + length]
        path.write_bytes(content)
        entries.append(
            {
                "type": "file",
                "dir": current_dir,
                "name": name,
                "offset": offset,
                "length": length,
                "stamp": stamp,
                "flags": flags,
            }
        )
    off += 8 + size

index = {
    "riff_size": riff_size,
    "form": form.decode("ascii"),
    "hdri": {
        "v1": struct.unpack("<I", hdri_payload[0:4])[0],
        "v2": struct.unpack("<I", hdri_payload[4:8])[0],
        "dent": hdri_payload[8:12].decode("ascii"),
        "data": hdri_payload[12:16].decode("ascii"),
    },
    "data_size": data_size,
    "dent_size": dent_size,
    "entries": entries,
}

INDEX.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
