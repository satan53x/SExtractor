# -*- coding: utf-8 -*-
"""AGSI SB2 情况 A 文本提取工具。

只从 CODE 指令流中提取可翻译项：
- Mess$is / MessC$s：正文
- Cmd1$s ~ Cmd5$s：选项

不提取 Talk$s、Voice$s、Change$s、Map$ii、资源名等。
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from agsi_common import (
    CHOICE_APIS,
    DEFAULT_ENCODING,
    MAP_APIS,
    JUMP_APIS,
    RESOURCE_APIS,
    TALK_APIS,
    TEXT_APIS,
    VOICE_APIS,
    get_cstr_count,
    iter_call_events,
    parse_api_table,
    prev_push_int_before_str,
    prev_push_str,
    read_cstr_decode,
)


def should_keep_text(s: str, keep_empty: bool = False) -> bool:
    if s == "":
        return keep_empty
    # 跳转函数/资源名会通过 API 过滤；这里仅做最低限度过滤。
    return True


def extract(dump_dir: Path, encoding: str = DEFAULT_ENCODING, keep_empty: bool = False) -> list[dict]:
    cstr_entries = read_cstr_decode(dump_dir, encoding=encoding)
    cstr_count = get_cstr_count(dump_dir)
    code = (dump_dir / "CODE.bin").read_bytes()
    _apis, api_by_addr = parse_api_table(dump_dir / "FTBL_1.bin", encoding=encoding)

    results: list[dict] = []
    current_talk = None
    current_talk_api = None
    current_voice = None
    select_group = 0

    for ev in iter_call_events(code, api_by_addr):
        api = ev.api
        ps = prev_push_str(code, ev.call_off, cstr_count)

        if api in TALK_APIS:
            if ps:
                _push_off, sid = ps
                current_talk = cstr_entries[sid].text
                current_talk_api = api
            elif api == "TalkC$":
                current_talk = None
                current_talk_api = api
            continue

        if api in VOICE_APIS:
            if ps:
                _push_off, sid = ps
                current_voice = cstr_entries[sid].text
            continue

        if api == "SelectClr$i":
            select_group += 1
            continue

        if api in TEXT_APIS:
            if not ps:
                continue
            push_off, sid = ps
            text = cstr_entries[sid].text
            if not should_keep_text(text, keep_empty=keep_empty):
                continue
            msg_no_info = prev_push_int_before_str(code, push_off)
            item = {
                "_kind": TEXT_APIS[api],
                "_api": api,
                "_cstr_id": sid,
                "_code_off": f"0x{ev.call_off:08x}",
                "_push_off": f"0x{push_off:08x}",
                "scr_msg": text,
                "message": text,
            }
            if msg_no_info is not None:
                item["_msg_no"] = msg_no_info[1]
            if current_voice:
                item["_voice"] = current_voice
            if current_talk:
                item["_talk"] = current_talk
                item["_talk_api"] = current_talk_api
            results.append(item)
            continue

        if api in CHOICE_APIS:
            if not ps:
                continue
            push_off, sid = ps
            text = cstr_entries[sid].text
            if not should_keep_text(text, keep_empty=keep_empty):
                continue
            results.append({
                "_kind": "choice",
                "_api": api,
                "_select_group": select_group,
                "_cstr_id": sid,
                "_code_off": f"0x{ev.call_off:08x}",
                "_push_off": f"0x{push_off:08x}",
                "scr_msg": text,
                "message": text,
            })
            continue

        # 以下 API 明确不进入翻译文本；保留在这里便于后续扩展 trace 输出。
        if api in RESOURCE_APIS or api in JUMP_APIS or api in MAP_APIS:
            continue

    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="AGSI SB2 CODE 驱动文本提取器")
    parser.add_argument("dump_dir", help="agsi_sb_tool.py unpack 得到的目录")
    parser.add_argument("output_json", help="输出 JSON")
    parser.add_argument("--encoding", default=DEFAULT_ENCODING, help="字符串编码，默认 cp932")
    parser.add_argument("--keep-empty", action="store_true", help="保留空字符串项，默认不保留")
    args = parser.parse_args()

    dump_dir = Path(args.dump_dir)
    items = extract(dump_dir, encoding=args.encoding, keep_empty=args.keep_empty)
    Path(args.output_json).write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "dump_dir": str(dump_dir),
        "output_json": args.output_json,
        "entries": len(items),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
