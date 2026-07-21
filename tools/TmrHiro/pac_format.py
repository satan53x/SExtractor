"""Fortune Cookie Select (.pac) archive format helpers.

Header layout (little-endian), from sub_40E2E0:

  offset  size  field
  0       2     entry_count (u16)
  2       1     name_len    (u8)  # fixed-width name field size
  3       4     data_base   (u32) # absolute offset of first payload byte
  7       N     directory   # entry_count * (name_len + 4)

Each directory entry:
  name[name_len]   null-padded ASCII (engine lowercases for strcmp)
  rel_offset (u32) absolute = data_base + rel_offset

Payload sizes are implied by successive absolute offsets; last file ends at EOF.
No compression on the container layer itself.
"""

from __future__ import annotations

import os
import struct
from dataclasses import dataclass
from typing import BinaryIO, Iterable, List, Optional, Sequence, Tuple


HEADER_SIZE = 7  # u16 + u8 + u32
ENTRY_NAME_MAX = 255


@dataclass
class PacEntry:
    name: str
    name_raw: bytes  # exact name field bytes (length == name_len)
    rel_offset: int
    abs_offset: int
    size: int
    data: bytes = b""


@dataclass
class PacArchive:
    entry_count: int
    name_len: int
    data_base: int
    entries: List[PacEntry]
    raw: bytes = b""

    @property
    def index_size(self) -> int:
        return HEADER_SIZE + self.entry_count * (self.name_len + 4)


def _decode_name(name_raw: bytes) -> str:
    return name_raw.split(b"\x00", 1)[0].decode("ascii", errors="replace")


def parse_pac(data: bytes) -> PacArchive:
    if len(data) < HEADER_SIZE:
        raise ValueError(f"PAC too small: {len(data)} bytes")

    entry_count, name_len, data_base = struct.unpack_from("<HBI", data, 0)
    if name_len == 0 or name_len > ENTRY_NAME_MAX:
        raise ValueError(f"invalid name_len={name_len}")
    if entry_count == 0:
        raise ValueError("entry_count is 0")

    index_end = HEADER_SIZE + entry_count * (name_len + 4)
    if index_end > len(data):
        raise ValueError(
            f"directory overflows file: need {index_end}, have {len(data)}"
        )
    if data_base != index_end:
        # Game code still works if data_base is larger (padding), but warn via exception
        # only when data_base is smaller than directory end (corrupt).
        if data_base < index_end:
            raise ValueError(
                f"data_base 0x{data_base:X} < directory end 0x{index_end:X}"
            )

    entries: List[PacEntry] = []
    pos = HEADER_SIZE
    for _ in range(entry_count):
        name_raw = data[pos : pos + name_len]
        pos += name_len
        rel_offset = struct.unpack_from("<I", data, pos)[0]
        pos += 4
        abs_offset = data_base + rel_offset
        if abs_offset > len(data):
            raise ValueError(
                f"entry {_decode_name(name_raw)!r} abs_offset 0x{abs_offset:X} past EOF"
            )
        entries.append(
            PacEntry(
                name=_decode_name(name_raw),
                name_raw=name_raw,
                rel_offset=rel_offset,
                abs_offset=abs_offset,
                size=0,
            )
        )

    # Compute sizes from next absolute offset / EOF. Entries may not be sorted in
    # the directory; sort by offset only for size calculation, then map back.
    order = sorted(range(len(entries)), key=lambda i: entries[i].abs_offset)
    for rank, idx in enumerate(order):
        start = entries[idx].abs_offset
        if rank + 1 < len(order):
            end = entries[order[rank + 1]].abs_offset
        else:
            end = len(data)
        if end < start:
            raise ValueError(
                f"negative size for {entries[idx].name!r}: {start:#x}..{end:#x}"
            )
        entries[idx].size = end - start
        entries[idx].data = data[start:end]

    return PacArchive(
        entry_count=entry_count,
        name_len=name_len,
        data_base=data_base,
        entries=entries,
        raw=data,
    )


def read_pac(path: str) -> PacArchive:
    with open(path, "rb") as f:
        return parse_pac(f.read())


def encode_name(name: str, name_len: int, name_raw: Optional[bytes] = None) -> bytes:
    if name_raw is not None:
        if len(name_raw) != name_len:
            raise ValueError(
                f"name_raw length {len(name_raw)} != name_len {name_len}"
            )
        return name_raw
    raw = name.encode("ascii")
    if len(raw) >= name_len:
        # Keep room for at least one NUL like the original 8-byte fields.
        if len(raw) > name_len:
            raise ValueError(f"name {name!r} longer than name_len={name_len}")
        return raw[:name_len]
    return raw + b"\x00" * (name_len - len(raw))


def build_pac(
    files: Sequence[Tuple[str, bytes, Optional[bytes]]],
    name_len: Optional[int] = None,
    pad_between_index_and_data: int = 0,
) -> bytes:
    """Build a PAC archive.

    files: sequence of (name, data, optional exact name_raw)
    """
    if not files:
        raise ValueError("no files to pack")

    if name_len is None:
        # Prefer original-style width: max name length + 1 (NUL), at least 8.
        max_name = max(len(n.encode("ascii")) for n, _, _ in files)
        name_len = max(8, max_name + 1)
    if not (1 <= name_len <= ENTRY_NAME_MAX):
        raise ValueError(f"invalid name_len={name_len}")

    for name, _, name_raw in files:
        if name_raw is None and len(name.encode("ascii")) > name_len:
            raise ValueError(f"name {name!r} exceeds name_len={name_len}")
        if name_raw is not None and len(name_raw) != name_len:
            raise ValueError(f"name_raw for {name!r} has wrong length")

    count = len(files)
    index_end = HEADER_SIZE + count * (name_len + 4)
    data_base = index_end + pad_between_index_and_data

    out = bytearray()
    out += struct.pack("<HBI", count, name_len, data_base)

    # First pass: directory with relative offsets in given order.
    rel = 0
    payloads: List[bytes] = []
    for name, data, name_raw in files:
        out += encode_name(name, name_len, name_raw)
        out += struct.pack("<I", rel)
        payloads.append(data)
        rel += len(data)

    if pad_between_index_and_data:
        out += b"\x00" * pad_between_index_and_data

    for data in payloads:
        out += data

    return bytes(out)


def rebuild_identical(archive: PacArchive) -> bytes:
    """Rebuild from a parsed archive, preserving name fields and order."""
    # Preserve possible gap between directory end and data_base.
    index_end = HEADER_SIZE + archive.entry_count * (archive.name_len + 4)
    pad = archive.data_base - index_end
    files = [
        (e.name, e.data, e.name_raw) for e in archive.entries
    ]
    return build_pac(files, name_len=archive.name_len, pad_between_index_and_data=pad)


def list_entries(archive: PacArchive) -> List[str]:
    lines = [
        f"entry_count={archive.entry_count} name_len={archive.name_len} "
        f"data_base=0x{archive.data_base:X} ({archive.data_base})"
    ]
    for i, e in enumerate(archive.entries):
        lines.append(
            f"{i:04d}  {e.name:<{archive.name_len}s}  "
            f"rel=0x{e.rel_offset:08X}  abs=0x{e.abs_offset:08X}  size={e.size}"
        )
    return lines


def safe_filename(name: str) -> str:
    # PAC names are already simple ASCII identifiers.
    bad = '<>:"/\\|?*'
    out = "".join("_" if c in bad else c for c in name)
    return out or "_"


def unpack_to_dir(archive: PacArchive, out_dir: str, write_index: bool = True) -> None:
    os.makedirs(out_dir, exist_ok=True)
    for e in archive.entries:
        path = os.path.join(out_dir, safe_filename(e.name))
        with open(path, "wb") as f:
            f.write(e.data)

    if write_index:
        # Manifest preserves order + exact name field bytes for round-trip packing.
        man_path = os.path.join(out_dir, "_pac_index.txt")
        with open(man_path, "w", encoding="utf-8", newline="\n") as f:
            f.write(f"# PAC index manifest\n")
            f.write(f"name_len={archive.name_len}\n")
            f.write(f"data_base={archive.data_base}\n")
            f.write(f"# order name name_raw_hex size\n")
            for e in archive.entries:
                f.write(
                    f"{e.name}\t{e.name_raw.hex()}\t{e.size}\n"
                )


def load_manifest(dir_path: str) -> Tuple[int, Optional[int], List[Tuple[str, Optional[bytes]]]]:
    man_path = os.path.join(dir_path, "_pac_index.txt")
    if not os.path.isfile(man_path):
        return 0, None, []
    name_len = 0
    data_base: Optional[int] = None
    items: List[Tuple[str, Optional[bytes]]] = []
    with open(man_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("name_len="):
                name_len = int(line.split("=", 1)[1])
                continue
            if line.startswith("data_base="):
                data_base = int(line.split("=", 1)[1])
                continue
            parts = line.split("\t")
            if len(parts) < 2:
                continue
            name = parts[0]
            name_raw = bytes.fromhex(parts[1]) if parts[1] else None
            items.append((name, name_raw))
    return name_len, data_base, items


def pack_from_dir(dir_path: str, name_len: Optional[int] = None) -> bytes:
    man_name_len, man_data_base, man_items = load_manifest(dir_path)

    files: List[Tuple[str, bytes, Optional[bytes]]] = []
    if man_items:
        for name, name_raw in man_items:
            path = os.path.join(dir_path, safe_filename(name))
            if not os.path.isfile(path):
                raise FileNotFoundError(f"missing file for index entry: {path}")
            with open(path, "rb") as f:
                data = f.read()
            files.append((name, data, name_raw))
        use_name_len = name_len or man_name_len or None
        pad = 0
        if man_data_base is not None and use_name_len:
            index_end = HEADER_SIZE + len(files) * (use_name_len + 4)
            if man_data_base >= index_end:
                pad = man_data_base - index_end
        return build_pac(files, name_len=use_name_len, pad_between_index_and_data=pad)

    # No manifest: pack all regular files except the manifest itself, sorted by name.
    names = sorted(
        n
        for n in os.listdir(dir_path)
        if os.path.isfile(os.path.join(dir_path, n)) and n != "_pac_index.txt"
    )
    if not names:
        raise ValueError(f"no files in {dir_path}")
    for name in names:
        with open(os.path.join(dir_path, name), "rb") as f:
            data = f.read()
        files.append((name, data, None))
    return build_pac(files, name_len=name_len)
