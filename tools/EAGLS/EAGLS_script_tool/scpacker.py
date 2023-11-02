#!/usr/bin/env python
import argparse
import io
import math
import struct
import sys
from pathlib import Path
from typing import Tuple


IDX_FILE = "SCPACK.idx"
PAK_FILE = "SCPACK.pak"

MIN_PYTHON = (3, 8)
if sys.version_info < MIN_PYTHON:
    sys.exit("python %s.%s or later is required" % MIN_PYTHON)


def main() -> None:
    parser = argparse.ArgumentParser(description="EAGLS/ALIS Script idx/pak archive repacking and extraction tool")
    parser.add_argument("command", choices=["detect", "pack", "unpack"], help="operation mode")
    parser.add_argument("script_path", type=input_filepath, help="folder with SCPACK.{idx,pak}")
    parser.add_argument("data_path", nargs="?", help="folder for extracted files")
    parser.add_argument("-a", "--alis", action="store_true", default=False, help="use ALIS encryption variant")
    parser.add_argument("-r", "--rebuild", action="store_true", default=False, help="rebuild label offsets from file")
    parser.add_argument("-f", "--force", action="store_true", default=False, help="force packing")
    args = parser.parse_args()
    #args = parser.parse_args(["pack", ".\Script", ".\Script.txt"])

    script_idx_path = args.script_path.joinpath(IDX_FILE)
    script_pak_path = args.script_path.joinpath(PAK_FILE)
    if not script_idx_path.is_file():
        sys.exit(f"{script_idx_path} not found")
    if not script_pak_path.is_file():
        sys.exit(f"{script_pak_path} not found")
    if args.command == "detect":
        sc_detect(script_idx_path, script_pak_path, args.alis)
        print("Finished detecting parameters!")
        sys.exit()
    if not args.data_path:
        args.data_path = args.script_path.with_suffix(".txt")
    else:
        args.data_path = Path(args.data_path).resolve()
    if args.command == "unpack":
        args.data_path.mkdir(exist_ok=True)
        sc_unpack(script_idx_path, script_pak_path, args.data_path, args.alis)
    elif args.command == "pack":
        sc_pack(script_idx_path, script_pak_path, args.data_path, args.alis, args.rebuild, args.force)


def sc_detect(
    script_idx_path: Path, script_pak_path: Path, alis: bool
) -> Tuple[bytearray, bool, str, dict, int, dict, int, str, int]:
    idx_bin = bytearray(script_idx_path.read_bytes())
    pak_bin = bytearray(script_pak_path.read_bytes())
    long_offsets = True if (len(idx_bin) / 10000) >= 40 else False
    print(f"long_offsets: {long_offsets}")
    idx_key = find_idx_key(idx_bin)
    print(f"idx_key: {idx_key}")
    idx_bin = decrypt_idx(idx_bin, idx_key)
    data_dict = get_data(idx_bin, pak_bin, long_offsets)
    if alis:
        label_size = 136
        label_dict = get_labels_alis(data_dict, label_size)
        text_offset = 136000
    else:
        label_size = 36
        label_dict, text_offset = get_labels_and_textoffset(data_dict, label_size)
    print(f"text_offset: {text_offset}")
    pak_key, version = find_pak_key(data_dict, label_dict, text_offset)
    print(f"pak_key: {pak_key}")
    if alis:
        print("version: ALIS")
    else:
        print(f"version: EAGLS Ver {version}.X")
    return idx_bin, long_offsets, idx_key, data_dict, label_size, label_dict, text_offset, pak_key, version


def sc_unpack(script_idx_path: Path, script_pak_path: Path, data_dir: Path, alis: bool) -> None:
    _, _, _, data_dict, _, _, text_offset, pak_key, version = sc_detect(script_idx_path, script_pak_path, alis)
    for filename, data in data_dict.items():
        data = decrypt_slice(data, text_offset, pak_key, version)
        filename = filename.rsplit(".", 1)[0] + ".txt"
        with open(data_dir.joinpath(filename), "w", newline="", encoding="cp932") as txt_file:
            txt_file.write(data[text_offset:-version].decode("cp932"))
    print("Finished extracting files!")


def sc_pack(
    script_idx_path: Path, script_pak_path: Path, data_dir: Path, alis: bool, rebuild: bool, force: bool
) -> None:
    idx_bin, long_offsets, idx_key, data_dict_old, label_size, label_dict, text_offset, pak_key, version = sc_detect(
        script_idx_path, script_pak_path, alis
    )
    data_dict = {}
    for entry, data_old in data_dict_old.items():
        filename = entry
        data_old = decrypt_slice(data_old, text_offset, pak_key, version)
        try:
            filename = filename.rsplit(".", 1)[0] + ".txt"
            header = data_old[:text_offset]
            with open(data_dir.joinpath(filename), mode="rb") as txt_file:
                body = txt_file.read()
            footer = data_old[-version:]
            data_dict[entry] = b"".join([header, body, footer])
        except FileNotFoundError:
            print(f"Ignoring missing file {filename}")
            data_dict[entry] = data_old
    data_dict = (
        rebuild_offsets(data_dict, label_size, text_offset, version)
        if rebuild
        else fix_offsets(data_dict, label_dict, label_size, text_offset, version)
    )
    if data_dict_old == data_dict and not force:
        print("Skip packing!")
        sys.exit()
    idx_bin, pak_bin = encrypt(idx_bin, data_dict, long_offsets, text_offset, idx_key, pak_key, version)
    script_idx_path.write_bytes(idx_bin)
    script_pak_path.write_bytes(pak_bin)
    print("Finished replacing files!")


def find_idx_key(idx_bin: bytearray) -> str:
    def try_finding_idx_key(key_len: int) -> str:
        rnd = MSVCRTRand(seed)
        known_key = bytearray(key_len)
        key = bytearray(key_len)
        for i in range(start, len(idx_bin) - 4):
            b = idx_bin[i]
            a = rnd.rand()
            a %= key_len
            if known_key[a] == 0:
                known_key[a] = 1
                key[a] = b
            elif key[a] != b:
                return ""
        if any(b == 0 for b in known_key):
            print("Not enough data to extract idx_key")
            print(f"Best guess: {bytes(key)}")
            sys.exit(1)
        return key.decode()

    idx_buf = io.BytesIO(idx_bin)
    idx_buf.seek(-4, 2)
    seed = read_uint32(idx_buf)
    rnd = MSVCRTRand(seed)
    start = len(idx_bin) - 4 - 8192
    for _ in range(start):
        rnd.rand()
    seed = rnd.seed
    for key_len in range(1, 1024):
        if detected_key := try_finding_idx_key(key_len):
            return detected_key
    print("Could not find idx_key")
    sys.exit(1)


def decrypt_idx(idx_bin: bytearray, idx_key: str) -> bytearray:
    idx_buf = io.BytesIO(idx_bin)
    idx_buf.seek(-4, 2)
    seed = read_uint32(idx_buf)
    rnd = MSVCRTRand(seed)
    key = idx_key.encode()
    for i in range(len(idx_bin) - 4):
        a = rnd.rand()
        a = a % len(key)
        idx_bin[i] ^= key[a]
    return idx_bin


def get_data(idx_bin: bytearray, pak_bin: bytearray, long_offsets: bool) -> dict:
    name_size = 24 if long_offsets else 20
    idx_buf = io.BytesIO(idx_bin)
    pak_buf = io.BytesIO(pak_bin)
    data_dict = {}
    while True:
        filename_bytes = idx_buf.read(name_size)
        zero_idx = filename_bytes[0]
        if not zero_idx:
            break
        filename = filename_bytes.decode().split("\x00", 1)[0]
        if long_offsets:
            idx_buf.seek(8, 1)
            length = read_int64(idx_buf)
        else:
            idx_buf.seek(4, 1)
            length = read_uint32(idx_buf)
        data_dict[filename] = bytearray(pak_buf.read(length))
    return data_dict


def get_labels_and_textoffset(data_dict: dict, label_size: int) -> Tuple[dict, int]:
    label_dict = {}
    textoffsets = []
    for entry, data in data_dict.items():
        data_buf = io.BytesIO(data)
        label_list = []
        while True:
            label_bytes = data_buf.read(label_size - 4)
            zero_idx = label_bytes[0]
            if not zero_idx:
                data_buf.seek(4, 1)
                break
            label = label_bytes.split(b"\0", 1)[0]
            offset = read_uint32(data_buf)
            label_list.append((label, offset))
        while True:
            label_bytes = data_buf.read(label_size)
            if any(b != 0 for b in label_bytes):
                size = data_buf.tell() - label_size
                nearest_offset = int(math.ceil(size / 100.0)) * 100
                break
        label_dict[entry] = label_list
        textoffsets.append(nearest_offset)
    if textoffsets.count(textoffsets[0]) == len(textoffsets):
        return label_dict, textoffsets[0]
    print("Could not find text_offset")
    sys.exit(1)


def get_labels_alis(data_dict: dict, label_size: int) -> dict:
    label_dict = {}
    for entry, data in data_dict.items():
        data_buf = io.BytesIO(data)
        label_list = []
        while True:
            label_bytes = data_buf.read(label_size - 4)
            zero_idx = label_bytes[0]
            if not zero_idx:
                data_buf.seek(4, 1)
                break
            label = label_bytes.split(b"\0", 1)[0]
            offset = read_uint32(data_buf)
            label_list.append((label, offset))
        label_dict[entry] = label_list
    return label_dict


def find_pak_key(data_dict: dict, label_dict: dict, text_offset: int) -> Tuple[str, int]:
    def try_finding_pak_key_v1(key_len: int) -> str:
        known_key = bytearray(key_len)
        key = bytearray(key_len)
        for entry, data in data_dict.items():
            for label, offset in label_dict[entry]:
                label = b"$" + label
                for i in range(len(label)):
                    a = offset + i
                    a %= key_len
                    b = label[i]
                    b ^= data[text_offset + offset + i]
                    if known_key[a] == 0:
                        known_key[a] = 1
                        key[a] = b
                    elif key[a] != b:
                        return ""
        if any(b == 0 for b in known_key):
            print("Not enough data to extract pak_key")
            print(f"Best guess: {bytes(key)}")
            sys.exit(1)
        return key.decode()

    def try_finding_pak_key_v2(key_len: int) -> str:
        known_key = bytearray(key_len)
        key = bytearray(key_len)
        rnd = MSVCRTRand()
        for entry, data in data_dict.items():
            index = 0
            seed = uint8_to_int8(data[-1])
            rnd.seed = seed
            for label, offset in label_dict[entry]:
                label = b"$" + label
                for _ in range(index, offset, 2):
                    rnd.rand()
                    index += 2
                if offset % 2:
                    offset += 1
                    label = label[1:]
                for i in range(0, len(label), 2):
                    a = rnd.rand()
                    index += 2
                    a %= key_len
                    b = label[i]
                    b ^= data[text_offset + offset + i]
                    if known_key[a] == 0:
                        known_key[a] = 1
                        key[a] = b
                    elif key[a] != b:
                        return ""
        if any(b == 0 for b in known_key):
            print("Not enough data to extract pak_key")
            print(f"Best guess: {bytes(key)}")
            sys.exit(1)
        return key.decode()

    for key_len in range(1, 1024):
        if detected_key := try_finding_pak_key_v1(key_len):
            return detected_key, 1
    for key_len in range(1, 1024):
        if detected_key := try_finding_pak_key_v2(key_len):
            return detected_key, 2
    print("Could not find pak_key")
    sys.exit(1)


def decrypt_slice(data: bytearray, text_offset: int, pak_key: str, version: int) -> bytearray:
    key = pak_key.encode()
    if version == 1:
        for i in range(text_offset, len(data)):
            a = (i - text_offset) % len(key)
            data[i] ^= key[a]
        return data
    if version == 2:
        seed = uint8_to_int8(data[-1])
        rnd = MSVCRTRand(seed)
        for i in range(text_offset, len(data) - 1, 2):
            a = rnd.rand()
            a = a % len(key)
            data[i] ^= key[a]
        return data
    return data


def fix_offsets(data_dict: dict, label_dict: dict, label_size: int, text_offset: int, version: int) -> dict:
    for entry, data in data_dict.items():
        data_buf = io.BytesIO(data)
        script = data[text_offset:-version]
        index = 0
        for label, offset in label_dict[entry]:
            data_buf.seek(label_size, 1)
            new_offset = script.index(b"$" + label, index)
            if offset != new_offset:
                label_name = label.decode("shift-jis-2004")
                print(f"Fixing offset for ${label_name} in {entry}")
                data_buf.seek(-4, 1)
                write_uint32(data_buf, new_offset)
            index = new_offset + 1
        data_dict[entry] = bytearray(data_buf.getvalue())
    return data_dict


def rebuild_offsets(data_dict: dict, label_size: int, text_offset: int, version: int) -> dict:
    for entry, data in data_dict.items():
        header_buf = io.BytesIO()
        script = data[text_offset:-version]
        labels = script.count(b"$")
        offset = 0
        numerals = tuple(str(x).encode() for x in range(10))
        for _ in range(labels):
            offset = script.index(b"$", offset)
            label_name = script[offset:]
            label_name = label_name.split(b"\n", 1)[0]
            label_name = label_name.split(b"\r", 1)[0]
            label_name = label_name.split(b":", 1)[0]
            if label_name.count(b"("):
                label_name = label_name.split(b"(", 1)[0]
                while label_name.endswith(numerals):
                    label_name = label_name[:-1]
            label_name = label_name[1:]
            label_len = len(label_name)
            if label_len > label_size - 4:
                label_name = label_name.decode("shift-jis-2004")
                print(f"Label ${label_name} in {entry} too long")
                sys.exit(1)
            if not label_len:
                print(f"Bad label in {entry}")
                sys.exit(1)
            header_buf.write(label_name)
            header_buf.seek(label_size - label_len - 4, 1)
            write_uint32(header_buf, offset)
            offset += 1
            label_name = label_name.decode("shift-jis-2004")
            print(f"Found ${label_name} in {entry}")
        if header_buf.tell() >= text_offset:
            print(f"Too many labels in {entry}")
            sys.exit(1)
        header_buf.write((text_offset - labels * label_size) * b"\0")
        data_dict[entry] = bytearray(header_buf.getvalue() + data[text_offset:])
    return data_dict


def encrypt(
    idx_bin: bytearray, data_dict: dict, long_offsets: bool, text_offset: int, idx_key: str, pak_key: str, version: int
) -> Tuple[bytes, bytes]:
    base_address = 0
    name_size = 24 if long_offsets else 20
    idx_buf = io.BytesIO(idx_bin)
    new_idx_buf = io.BytesIO()
    new_pak_buf = io.BytesIO()
    while True:
        filename_bytes = idx_buf.read(name_size)
        zero_idx = filename_bytes[0]
        if not zero_idx:
            break
        filename = filename_bytes.decode().split("\x00", 1)[0]
        new_data = data_dict[filename]
        new_idx_buf.write(filename_bytes)
        if long_offsets:
            if not base_address:
                base_address = read_int64(idx_buf)
                idx_buf.seek(8, 1)
            else:
                idx_buf.seek(16, 1)
            write_int64(new_idx_buf, new_pak_buf.tell() + base_address)
            write_int64(new_idx_buf, len(new_data))
        else:
            if not base_address:
                base_address = read_uint32(idx_buf)
                idx_buf.seek(4, 1)
            else:
                idx_buf.seek(8, 1)
            write_uint32(new_idx_buf, new_pak_buf.tell() + base_address)
            write_uint32(new_idx_buf, len(new_data))
        new_pak_buf.write(decrypt_slice(new_data, text_offset, pak_key, version))
    new_idx_buf.write(filename_bytes)
    new_idx_buf.write(idx_buf.read())
    new_idx_bin = decrypt_idx(bytearray(new_idx_buf.getvalue()), idx_key)
    return bytes(new_idx_bin), new_pak_buf.getvalue()


class MSVCRTRand:
    __seed: int

    def __init__(self, seed: int = 0) -> None:
        self.__seed = seed

    @property
    def seed(self) -> int:
        return self.__seed

    @seed.setter
    def seed(self, seed: int) -> None:
        self.__seed = seed

    def rand(self) -> int:
        self.__seed = (214013 * self.__seed + 2531011) & 0x7FFFFFFF
        return self.seed >> 16


def uint8_to_int8(value: int) -> int:
    return struct.unpack("<b", struct.pack("<B", value))[0]


def read_uint32(buffer: io.BytesIO) -> int:
    return struct.unpack("<I", buffer.read(4))[0]


def write_uint32(buffer: io.BytesIO, value: int) -> None:
    buffer.write(struct.pack("<I", value))


def read_int64(buffer: io.BytesIO) -> int:
    return struct.unpack("<q", buffer.read(8))[0]


def write_int64(buffer: io.BytesIO, value: int) -> None:
    buffer.write(struct.pack("<q", value))


def input_filepath(path: str) -> Path:
    resolved = Path(path).resolve()
    if not resolved.exists():
        raise argparse.ArgumentError
    return resolved


if __name__ == "__main__":
    main()
