# -*- coding: utf-8 -*-
"""AGSI SB2 文本提取/注入共用模块。

当前策略只覆盖“情况 A”：
- 不动 CODE.bin；
- 不增删 CSTR index；
- 只替换已有 CSTR 条目的内容；
- 重新生成 CSTR.bin 的 offset/size 表和字符串池。

注意：本模块不会把 Talk$s/Voice$s 当作 name 正式输出，只作为调试标签。
"""
from __future__ import annotations

import json
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

DUMP_FORMAT = "AGSI_SB2_DUMP_SIMPLE_V1"
DEFAULT_ENCODING = "cp932"

TEXT_APIS = {"Mess$is": "message", "MessC$s": "message_c"}
CHOICE_APIS = {
    "Cmd1$s": "choice",
    "Cmd2$s": "choice",
    "Cmd3$s": "choice",
    "Cmd4$s": "choice",
    "Cmd5$s": "choice",
}
TALK_APIS = {"Talk$s", "Talk2$s", "TalkC$"}
VOICE_APIS = {"Voice$s", "PlayVoiceC$s"}
RESOURCE_APIS = {
    "Cg$s", "Face$s", "PlayBgm$s", "PlaySe$s", "PlaySeWait$s", "Voice$s",
    "Char$s", "CgChar$ss", "CharTwin$ss", "CharL$s", "CharR$s", "CgCharTwin$sss",
    "PlaySeLoop$s", "CgHsb$sii", "CgCharTwinHsb$sssii", "PlayMovie$s",
    "ImageC$s", "PlayBgmC$s", "PlayVoiceC$s", "Change$s",
}
JUMP_APIS = {"Change$s"}
MAP_APIS = {"Map$ii", "MapEnd$"}


def u32(data: bytes, off: int) -> int:
    return struct.unpack_from("<I", data, off)[0]


def swap_nibble_bytes(buf: bytes) -> bytes:
    """CSTR 字符串池的高低 4bit 交换；该操作自反。"""
    return bytes((((b >> 4) | ((b & 0x0F) << 4)) & 0xFF) for b in buf)


def load_manifest(dump_dir: Path) -> dict:
    manifest_path = dump_dir / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"manifest.json not found: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("format") != DUMP_FORMAT:
        raise ValueError(f"unsupported dump format: {manifest.get('format')!r}")
    return manifest


def get_cstr_count(dump_dir: Path) -> int:
    manifest = load_manifest(dump_dir)
    for seg in manifest.get("segments", []):
        if seg.get("tag") == "CSTR" and seg.get("file") == "CSTR.bin":
            if "cstr_count" in seg:
                return int(seg["cstr_count"])
    hv = manifest.get("header_values")
    if isinstance(hv, list) and len(hv) > 9:
        return int(hv[9])
    raise ValueError("cannot find CSTR count")


@dataclass
class CStrEntry:
    index: int
    offset: int
    size: int
    raw: bytes       # 包含结尾 \0 的明文字节
    text: str        # 去掉结尾 \0 后按 cp932 解码


@dataclass
class ApiEntry:
    index: int
    name: str
    address: int
    argc: int
    unknown: int


@dataclass
class CallEvent:
    call_off: int
    address: int
    api: str
    argc: int


def split_cstr_payload(data: bytes, count: int) -> Tuple[bytes, bytes]:
    table_size = count * 8
    if len(data) < table_size:
        raise ValueError(f"CSTR payload too small: size={len(data)}, table_size={table_size}")
    return data[:table_size], data[table_size:]


def read_cstr_decode(dump_dir: Path, encoding: str = DEFAULT_ENCODING) -> List[CStrEntry]:
    """读取 CSTR_decode.bin；若不存在，则从 CSTR.bin 临时解码。"""
    count = get_cstr_count(dump_dir)
    decoded_path = dump_dir / "CSTR_decode.bin"
    if decoded_path.exists():
        data = decoded_path.read_bytes()
    else:
        obf_path = dump_dir / "CSTR.bin"
        if not obf_path.exists():
            raise FileNotFoundError(f"CSTR.bin not found: {obf_path}")
        obf = obf_path.read_bytes()
        table, pool_obf = split_cstr_payload(obf, count)
        data = table + swap_nibble_bytes(pool_obf)
    table, pool = split_cstr_payload(data, count)
    entries: List[CStrEntry] = []
    total_size = 0
    for i in range(count):
        off, size = struct.unpack_from("<II", table, i * 8)
        total_size += size
        if off + size > len(pool):
            raise ValueError(f"CSTR entry out of range: id={i}, off={off}, size={size}, pool={len(pool)}")
        raw = pool[off:off + size]
        body = raw[:-1] if raw.endswith(b"\x00") else raw
        text = body.decode(encoding, errors="replace")
        entries.append(CStrEntry(i, off, size, raw, text))
    if total_size != len(pool):
        raise ValueError(f"CSTR pool size mismatch: expected={total_size}, actual={len(pool)}")
    return entries


def rebuild_cstr_files(dump_dir: Path, entries_raw: List[bytes], make_backup: bool = True) -> dict:
    """用明文字节列表重建 CSTR_decode.bin 与混淆后的 CSTR.bin。"""
    if not entries_raw:
        raise ValueError("empty CSTR entries")
    decoded_path = dump_dir / "CSTR_decode.bin"
    cstr_path = dump_dir / "CSTR.bin"
    if make_backup:
        for p in (decoded_path, cstr_path):
            if p.exists():
                bak = p.with_suffix(p.suffix + ".bak")
                if not bak.exists():
                    bak.write_bytes(p.read_bytes())
    table = bytearray()
    pool = bytearray()
    for raw in entries_raw:
        if not raw.endswith(b"\x00"):
            raw = raw + b"\x00"
        table += struct.pack("<II", len(pool), len(raw))
        pool += raw
    decoded = bytes(table + pool)
    decoded_path.write_bytes(decoded)
    cstr_path.write_bytes(bytes(table) + swap_nibble_bytes(bytes(pool)))
    return {
        "count": len(entries_raw),
        "table_size": len(table),
        "pool_size": len(pool),
        "cstr_decode_size": decoded_path.stat().st_size,
        "cstr_size": cstr_path.stat().st_size,
    }


def parse_api_table(ftbl1_path: Path, encoding: str = DEFAULT_ENCODING) -> Tuple[List[ApiEntry], Dict[int, ApiEntry]]:
    data = ftbl1_path.read_bytes()
    pos = 0
    out: List[ApiEntry] = []
    idx = 0
    while pos < len(data):
        if pos + 4 > len(data):
            raise ValueError(f"bad FTBL_1 at 0x{pos:x}")
        n = u32(data, pos)
        pos += 4
        raw_name = data[pos:pos + n]
        pos += n
        if pos + 12 > len(data):
            raise ValueError(f"bad FTBL_1 record at index={idx}")
        unknown, addr, argc = struct.unpack_from("<III", data, pos)
        pos += 12
        name = raw_name.rstrip(b"\x00").decode(encoding, errors="replace")
        out.append(ApiEntry(idx, name, addr, argc, unknown))
        idx += 1
    return out, {x.address: x for x in out}


def iter_call_events(code: bytes, api_by_addr: Dict[int, ApiEntry]) -> Iterable[CallEvent]:
    """扫描 CALL 指令。

    已确认 CALL 编码为：C6 + u32(function_addr)。
    这里按字节扫描，只接受地址命中 FTBL_1 的 CALL，能避开大部分误判。
    """
    end = len(code) - 5
    i = 0
    while i <= end:
        if code[i] == 0xC6:
            addr = u32(code, i + 1)
            api = api_by_addr.get(addr)
            if api is not None:
                yield CallEvent(i, addr, api.name, api.argc)
                i += 5
                continue
        i += 1


def prev_push_str(code: bytes, call_off: int, cstr_count: int) -> Optional[Tuple[int, int]]:
    """取 CALL 前紧邻的 PUSH_STR。

    PUSH_STR 编码：82 + u32(CSTR_index)。
    返回：(push_offset, cstr_id)。
    """
    off = call_off - 5
    if off < 0 or code[off] != 0x82:
        return None
    idx = u32(code, off + 1)
    if idx >= cstr_count:
        return None
    return off, idx


def prev_push_int_before_str(code: bytes, push_str_off: int) -> Optional[Tuple[int, int]]:
    """取 PUSH_STR 前紧邻的 PUSH_INT。PUSH_INT 编码：7E + u32。"""
    off = push_str_off - 5
    if off < 0 or code[off] != 0x7E:
        return None
    return off, u32(code, off + 1)


def load_char_map(path: Optional[Path]) -> Dict[str, str]:
    if path is None:
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("char map must be a JSON object")
    return {str(k): str(v) for k, v in data.items()}


def apply_char_map(s: str, char_map: Dict[str, str]) -> str:
    if not char_map:
        return s
    return "".join(char_map.get(ch, ch) for ch in s)


def encode_text_checked(text: str, cstr_id: int, encoding: str, char_map: Dict[str, str]) -> bytes:
    mapped = apply_char_map(text, char_map)
    try:
        raw = mapped.encode(encoding)
    except UnicodeEncodeError as e:
        bad = mapped[e.start:e.end]
        raise UnicodeEncodeError(
            e.encoding, e.object, e.start, e.end,
            f"CSTR[{cstr_id}] contains unencodable char {bad!r}; provide --char-map or keep text {encoding}-encodable"
        ) from e
    return raw + b"\x00"
