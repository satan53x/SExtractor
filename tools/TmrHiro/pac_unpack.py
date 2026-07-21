#!/usr/bin/env python3
"""Unpack / list Fortune Cookie Select .pac archives."""

from __future__ import annotations

import argparse
import os
import sys

from pac_format import list_entries, read_pac, unpack_to_dir


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Unpack or list a .pac archive")
    p.add_argument("pac", help="path to .pac file")
    p.add_argument(
        "out_dir",
        nargs="?",
        help="output directory (default: <pacname>_extracted)",
    )
    p.add_argument(
        "-l",
        "--list",
        action="store_true",
        help="list entries only, do not extract",
    )
    p.add_argument(
        "--no-manifest",
        action="store_true",
        help="do not write _pac_index.txt",
    )
    args = p.parse_args(argv)

    archive = read_pac(args.pac)
    for line in list_entries(archive):
        print(line)

    if args.list:
        return 0

    out_dir = args.out_dir
    if not out_dir:
        base = os.path.splitext(os.path.basename(args.pac))[0]
        out_dir = base + "_extracted"

    unpack_to_dir(archive, out_dir, write_index=not args.no_manifest)
    print(f"extracted {archive.entry_count} files -> {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
