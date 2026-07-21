"""Script line encrypt/decrypt and file container codec.

File stores encrypted line payloads terminated by 0x0A.
On load, sub_40E1E0 decrypts each byte until 0x0A:

  plain = nibble_swap(enc ^ 0x0A)

where nibble_swap(x) = ((x & 0x0F) << 4) | ((x >> 4) & 0x0F)

Inverse (for packing):

  enc = nibble_swap(plain) ^ 0x0A

File layout (srp.pac entry / .sct):
  u32le line_count
  for each line:
      encrypt(line_bytes) + 0x0A
"""

from __future__ import annotations

import struct
from typing import List


def nibble_swap(b: int) -> int:
    b &= 0xFF
    return ((b & 0x0F) << 4) | ((b >> 4) & 0x0F)


def decrypt_byte(enc: int) -> int:
    return nibble_swap(enc ^ 0x0A)


def encrypt_byte(plain: int) -> int:
    return nibble_swap(plain) ^ 0x0A


def decrypt_line(data: bytes) -> bytes:
    return bytes(decrypt_byte(b) for b in data)


def encrypt_line(data: bytes) -> bytes:
    return bytes(encrypt_byte(b) for b in data)


def decode_script(data: bytes) -> List[bytes]:
    if len(data) < 4:
        raise ValueError("script too small")
    count = struct.unpack_from("<I", data, 0)[0]
    pos = 4
    lines: List[bytes] = []
    for i in range(count):
        end = data.find(b"\n", pos)
        if end < 0:
            raise ValueError(f"missing newline for line {i} (count={count})")
        enc = data[pos:end]
        lines.append(decrypt_line(enc))
        pos = end + 1
    if pos != len(data):
        raise ValueError(f"trailing {len(data) - pos} bytes after last line")
    return lines


def encode_script(lines: List[bytes]) -> bytes:
    out = bytearray()
    out += struct.pack("<I", len(lines))
    for line in lines:
        if b"\n" in line:
            raise ValueError("line payload must not contain 0x0A")
        out += encrypt_line(line)
        out += b"\n"
    return bytes(out)


def load_script_file(path: str) -> List[bytes]:
    with open(path, "rb") as f:
        return decode_script(f.read())


def save_script_file(path: str, lines: List[bytes]) -> None:
    with open(path, "wb") as f:
        f.write(encode_script(lines))
