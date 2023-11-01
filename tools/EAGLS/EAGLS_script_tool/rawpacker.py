#!/usr/bin/env python

import glob
import os

from scpacker import *

idx_file = "*PACK.idx"
pak_file = "*PACK.pak"


def main() -> None:
    parser = argparse.ArgumentParser(description="""
EAGLS raw idx/pak archive repacking and extraction tool
supports CGPACK, SCPACK and WAVEPACK
no decompression/decryption on .pak done"""
                                     , formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("command", choices=["pack", "unpack"], help="operation mode")
    parser.add_argument("arc_path", type=input_filepath, help="folder with *PACK.{idx,pak}")
    parser.add_argument("data_path", nargs="?", help="folder for extracted files")
    args = parser.parse_args()

    args.arc_path = os.path.realpath(args.arc_path)
    if not args.arc_path.endswith(os.sep):
        args.arc_path += os.sep
    try:
        arc_idx_path = glob.glob(args.arc_path + idx_file)[0]
        arc_pak_path = glob.glob(args.arc_path + pak_file)[0]
    except IndexError:
        sys.exit(f"Archive files not found")
    if not os.path.isfile(arc_idx_path):
        sys.exit(f"{arc_idx_path} not found")
    if not os.path.isfile(arc_pak_path):
        sys.exit(f"{arc_pak_path} not found")
    if not args.data_path:
        args.data_path = args.arc_path
        if args.data_path.endswith(os.sep):
            args.data_path = args.data_path[:-1]
        args.data_path += ".out"
    args.data_path = os.path.realpath(args.data_path)
    if not args.data_path.endswith(os.sep):
        args.data_path += os.sep
    if args.command == "unpack":
        if not os.path.exists(args.data_path):
            os.makedirs(args.data_path)
        arc_unpack(arc_idx_path, arc_pak_path, args.data_path)
    elif args.command == "pack":
        arc_pack(arc_idx_path, arc_pak_path, args.data_path)


def arc_unpack(arc_idx_path: str, arc_pak_path: str, data_dir: str) -> None:
    with open(arc_idx_path, mode="rb") as idx_file:
        idx_bin = bytearray(idx_file.read())
    long_offsets = True if (len(idx_bin) / 10000) >= 40 else False
    idx_key = find_idx_key(idx_bin)
    idx_bin = decrypt_idx(idx_bin, idx_key)
    data_table = get_data_table(idx_bin, long_offsets)
    with open(arc_pak_path, mode="rb") as pak_file:
        str_data_table_len = str(len(data_table))
        for i, (filename, size) in enumerate(data_table, start=1):
            data = pak_file.read(size)
            out_path = os.path.join(data_dir, filename)
            with open(out_path, mode="wb") as arc_file:
                print(f"[{str(i).rjust(len(str_data_table_len))}/{str_data_table_len}] Create: {out_path}")
                arc_file.write(data)
    print("Finished extracting files!")


def arc_pack(arc_idx_path: str, arc_pak_path: str, data_dir: str) -> None:
    with open(arc_idx_path, mode="rb") as idx_file:
        idx_bin = bytearray(idx_file.read())
    long_offsets = True if (len(idx_bin) / 10000) >= 40 else False
    idx_key = find_idx_key(idx_bin)
    idx_bin = decrypt_idx(idx_bin, idx_key)
    data_table = []
    ext = (".dat", ".gr", ".ogg", ".wav")
    filelist = [fn for fn in os.listdir(data_dir) if fn.lower().endswith(ext)]
    # sorting like original archive
    filelist = [file.replace("_", "\xff") for file in filelist]
    filelist = sorted(filelist, key=str.casefold)
    filelist = [file.replace("\xff", "_") for file in filelist]
    for filename in filelist:
        in_path = os.path.join(data_dir, filename)
        size = os.path.getsize(in_path)
        data_table.append((filename, size))
    idx_bin = update_index(idx_bin, data_table, long_offsets, idx_key)
    with open(arc_idx_path, mode="wb") as new_idx_file:
        new_idx_file.write(idx_bin)
    with open(arc_pak_path, mode="wb") as new_pak_file:
        str_data_table_len = str(len(data_table))
        for i, filename in enumerate(filelist, start=1):
            in_path = os.path.join(data_dir, filename)
            with open(in_path, mode="rb") as in_file:
                print(f"[{str(i).rjust(len(str_data_table_len))}/{str_data_table_len}] Read: {in_path}")
                new_pak_file.write(in_file.read())
    print("Finished replacing files!")


def get_data_table(idx_bin: bytearray, long_offsets: bool) -> list:
    name_size = 24 if long_offsets else 20
    idx_buf = io.BytesIO(idx_bin)
    data_table = []
    while True:
        filename_bytes = idx_buf.read(name_size)
        zero_idx = filename_bytes[0]
        if not zero_idx:
            break
        filename = filename_bytes.decode().split("\x00", 1)[0]
        if long_offsets:
            idx_buf.seek(8, 1)
            size = read_int64(idx_buf)
        else:
            idx_buf.seek(4, 1)
            size = read_uint32(idx_buf)
        data_table.append((filename, size))
    return data_table


def update_index(idx_bin: bytearray, data_table: list, long_offsets: bool, idx_key: str) -> bytes:
    name_size = 24 if long_offsets else 20
    idx_buf = io.BytesIO(idx_bin)
    new_idx_buf = io.BytesIO()
    idx_buf.seek(name_size, 1)
    base_address = read_int64(idx_buf) if long_offsets else read_uint32(idx_buf)
    offset = 0
    for filename, size in data_table:
        filename_bytes = filename.encode()
        remaining = name_size - len(filename_bytes)
        new_idx_buf.write(filename_bytes)
        new_idx_buf.write(remaining * b"\x00")
        if long_offsets:
            write_int64(new_idx_buf, offset + base_address)
            write_int64(new_idx_buf, size)
        else:
            write_uint32(new_idx_buf, offset + base_address)
            write_uint32(new_idx_buf, size)
        offset += size
    remaining = len(idx_bin) - new_idx_buf.tell() - 4
    new_idx_buf.write(remaining * b"\x00")
    idx_buf.seek(-4, 2)
    new_idx_buf.write(idx_buf.read())
    new_idx_bin = decrypt_idx(bytearray(new_idx_buf.getvalue()), idx_key)
    return bytes(new_idx_bin)


if __name__ == "__main__":
    main()
