#!/usr/bin/env python3
"""Pack a directory into a Fortune Cookie Select .pac archive."""

from __future__ import annotations

import argparse
import os
import sys

from pac_format import pack_from_dir, parse_pac, rebuild_identical, read_pac


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Pack files into a .pac archive")
    p.add_argument("input", help="input directory, or original .pac for rebuild test")
    p.add_argument(
        "output",
        nargs="?",
        help="output .pac path (default: <input>.pac or <input>_rebuild.pac)",
    )
    p.add_argument(
        "--name-len",
        type=int,
        default=None,
        help="fixed name field width (default: from _pac_index.txt or auto)",
    )
    p.add_argument(
        "--from-pac",
        action="store_true",
        help="rebuild directly from a parsed .pac (identity round-trip)",
    )
    args = p.parse_args(argv)

    if args.from_pac or (
        os.path.isfile(args.input)
        and args.input.lower().endswith(".pac")
    ):
        archive = read_pac(args.input)
        data = rebuild_identical(archive)
        out = args.output or (os.path.splitext(args.input)[0] + "_rebuild.pac")
    else:
        if not os.path.isdir(args.input):
            print(f"not a directory: {args.input}", file=sys.stderr)
            return 1
        data = pack_from_dir(args.input, name_len=args.name_len)
        out = args.output
        if not out:
            out = args.input.rstrip("\\/") + ".pac"
            if out.endswith("_extracted.pac"):
                out = out[: -len("_extracted.pac")] + "_repack.pac"

    os.makedirs(os.path.dirname(os.path.abspath(out)) or ".", exist_ok=True)
    with open(out, "wb") as f:
        f.write(data)

    # Sanity parse
    rebuilt = parse_pac(data)
    print(
        f"wrote {out} ({len(data)} bytes, {rebuilt.entry_count} entries, "
        f"name_len={rebuilt.name_len})"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
