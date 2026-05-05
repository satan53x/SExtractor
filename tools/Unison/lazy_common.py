#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Softpal Lazy 引擎公用模板库
========================================

文件格式 (.VAL):
+---------------------+
| Header 9 字节       |
|   u24 size_A        |  seg_A (字节码) 字节数
|   u24 size_B        |  seg_B (字符串偏移表) 条目数
|   u24 ???           |  暂未确认
+---------------------+
| seg_A   字节码      |  引用 seg_B 索引 (u16), 不引 seg_C 偏移
+---------------------+
| seg_B   u32[size_B] |  字符串在 seg_C 中的偏移
+---------------------+
| seg_C   字符串池    |  NUL 结尾 SJIS 字符串
+---------------------+

变长注入策略:
  seg_A 不动 -> seg_B 全部重算 -> seg_C 改字符串内容
  指令流和数据 100% 解耦, 注入零风险.

opcode 表 (已确认):
  0x83 00 [u16 strIdx]                    LOAD_SCRIPT  (4 字节)  -> 加载脚本/资源, 字符串是文件名
  0x87 00 [u24 target]                    CALL         (5 字节)  -> seg_A 内子程序调用
  0xa0 00 [u16 zero] [u16 ???]            ???          (8 字节)
  0xb0 00 [u16 zero] [u16 ???]            ???          (6 字节)
  0xdd 00 [u16 type] [u16 strIdx]         DISPLAY_TEXT (6 字节)  -> 显示对话/旁白文本
  0x30..0x3F [u16 jumpDelta]              JUMP (cond)  (3 字节起) -> 相对跳转
  0x20..0x2F [u16 jumpDelta]              JUMP (cond)  (3 字节起)
"""
import os
import struct
from typing import List, Tuple, Dict, Optional


# ============================================================
# 文件名分类 (剧情 vs 系统)
# ============================================================
#
# Yaki.VCT 中所有 .VAL 文件名首字母分布:
#   A:6  C:204  D:2  E:1  G:1  H:16  L:1  M:3  O:1  S:2  T:107  W:34
#
# **重要的教训**:
# 早期版本试图用文件名硬编码 SYSTEM_NAMES 做分类, 漏掉了 DEMO.VAL,
# HCHIKA01..05, HCHIYORI01..05, HDOUBLE01..04 等 15 个文件 (近 2000 条剧情).
# 因为这些文件名不是连续编号系列, 也不在固定系统名表里.
#
# 当前策略: 直接用"文件内容是否含日文剧情字符串"判断 -> 不会漏
#
# 兼容旧 API: classify_val(name_no_ext) 仍然返回 'story'/'system',
# 但只用于无法读文件时的兜底; 推荐用 classify_val_file(path) 或
# classify_val_data(bytes).

# 已知纯系统脚本 (不含真实剧情, 仅用于兜底)
SYSTEM_NAMES = {
    'CGM', 'DEBUG', 'GAMEEND', 'HSCENE', 'LOAD', 'MAINMENU',
    'MAKERTITLE', 'MUSICM', 'OMAKE', 'STAFFROLL', 'START',
    'CONFIG', 'OP', 'TITLE', 'ED', 'SE', 'THUM', 'LOGO',
}


def classify_val(name_no_ext: str) -> str:
    """
    按文件名做粗分类 (兜底用, 不读文件).
    name_no_ext: 不带扩展名的文件名 (大小写均可).
    返回 'story' / 'system'.

    更可靠的判断推荐用 classify_val_data(bytes), 它直接看是否含日文.
    """
    n = name_no_ext.upper()
    if n in SYSTEM_NAMES:
        return 'system'
    return 'story'


def classify_val_data(data: bytes, min_jp_strings: int = 1) -> str:
    """
    按文件内容判断: 字符串池里至少有 min_jp_strings 条剧情字符串
    (含日文假名/汉字 或 纯日式标点) 就归为 story.

    这是最可靠的判定方式, 推荐使用.
    """
    try:
        v = ValFile.parse(data)
    except Exception:
        return 'system'
    n_jp = sum(1 for s in v.strings if is_story_text(s))
    return 'story' if n_jp >= min_jp_strings else 'system'


# ============================================================
# .VAL 文件结构
# ============================================================
class ValFile:
    """
    Lazy 引擎 .VAL 脚本的内存表示.

    字段:
        header_extra: bytes(3)  -- header 后 3 字节 (size_C 推测, 暂保留原值)
        seg_a:        bytes     -- 字节码区, 不动
        strings:      List[bytes] -- seg_C 中的 SJIS 字符串 (无 NUL 结尾)

    seg_B 偏移表在 build() 时根据 strings 重新计算.
    """

    def __init__(self):
        self.header_extra: bytes = b'\x00\x00\x00'
        self.seg_a: bytes = b''
        self.strings: List[bytes] = []
        # seg_C 中超出 seg_B 索引范围的尾部数据 (某些系统脚本会在末尾追加未索引内容)
        self.tail_blob: bytes = b''

    @classmethod
    def parse(cls, data: bytes) -> 'ValFile':
        if len(data) < 9:
            raise ValueError("file too short for VAL header")
        size_A = data[0] | (data[1] << 8) | (data[2] << 16)
        size_B = data[3] | (data[4] << 8) | (data[5] << 16)
        # 头 6..8: 暂未明确含义
        header_extra = bytes(data[6:9])

        seg_a_start = 9
        seg_a_end = 9 + size_A
        seg_b_start = seg_a_end
        seg_b_end = seg_b_start + size_B * 4
        seg_c_start = seg_b_end

        if seg_b_end > len(data):
            raise ValueError(
                f"seg_B end (0x{seg_b_end:x}) exceeds file size (0x{len(data):x})"
            )

        v = cls()
        v.header_extra = header_extra
        v.seg_a = bytes(data[seg_a_start:seg_a_end])

        # 解析 seg_B + seg_C
        # 先记录每条字符串的 [start, end), end = 下一个 NUL 之后第 1 个字节
        max_end = seg_c_start
        for i in range(size_B):
            off = struct.unpack_from('<I', data, seg_b_start + i * 4)[0]
            s_start = seg_c_start + off
            s_end = s_start
            while s_end < len(data) and data[s_end] != 0:
                s_end += 1
            v.strings.append(bytes(data[s_start:s_end]))
            # 包含 NUL 的字符串结尾位置
            if s_end + 1 > max_end:
                max_end = s_end + 1
        # seg_C 末尾未被任何 seg_B 索引引用的尾部 (例如未索引的字符串、对齐填充)
        v.tail_blob = bytes(data[max_end:])
        return v

    def build(self) -> bytes:
        """重建 .VAL 字节流."""
        # 1. seg_C: 顺序拼接 + NUL 结尾, 同时记录每个字符串的偏移
        seg_c = bytearray()
        offsets: List[int] = []
        cur = 0
        for s in self.strings:
            offsets.append(cur)
            seg_c += s + b'\x00'
            cur += len(s) + 1
        # 附加未索引尾部
        seg_c += self.tail_blob

        # 2. seg_B: u32 偏移数组
        seg_b = bytearray()
        for off in offsets:
            seg_b += struct.pack('<I', off)

        # 3. header
        size_A = len(self.seg_a)
        size_B = len(self.strings)
        if size_A >= (1 << 24) or size_B >= (1 << 24):
            raise ValueError("size_A or size_B too large for u24")
        header = bytearray()
        header += bytes([
            size_A & 0xff, (size_A >> 8) & 0xff, (size_A >> 16) & 0xff,
            size_B & 0xff, (size_B >> 8) & 0xff, (size_B >> 16) & 0xff,
        ])
        header += self.header_extra

        return bytes(header) + self.seg_a + bytes(seg_b) + bytes(seg_c)


# ============================================================
# 字符串引用扫描 (seg_A 中找 opcode 引用了哪些 seg_B 索引)
# ============================================================
#
# 我们只关心两类引用:
#   0xdd 00 [u16 type] [u16 strIdx]  -> 剧情文本     (text 类)
#   0x83 00 [u16 strIdx]             -> 资源/脚本名   (asset 类)
#
# 注: 这是基于已观察的指令格式. 如果发现其他 op 也引用字符串, 在此扩展.

TEXT_OPCODE = 0xdd
TEXT_TYPE_MESSAGE = 0x0000


def scan_text_refs(seg_a: bytes, *, require_message_type: bool = True) -> List[Tuple[int, int]]:
    """
    扫描 seg_A 中 0xdd 文本显示引用, 返回 [(指令位置, 字符串索引), ...].

    已确认的正文显示格式为:
        dd 00 00 00 [u16 strIdx]

    旧版只要遇到 `dd 00` 就当成文本指令, 没有检查 type 字段。
    但 VAL 字节码里很多变长指令的立即数/参数区也会出现 `dd 00 xx xx`。
    如果这些假命中的 idx 刚好落在 seg_B 范围内, 且指向的字符串又是日文,
    就会产生“第一句/前文在后面重复提取”的问题。

    require_message_type=True 时只接受 type == 0 的 DISPLAY_TEXT,
    这是当前样本中稳定对应剧情正文的形式。
    """
    refs = []
    i = 0
    n = len(seg_a)
    while i + 6 <= n:
        if seg_a[i] == TEXT_OPCODE and seg_a[i + 1] == 0x00:
            text_type = seg_a[i + 2] | (seg_a[i + 3] << 8)
            str_idx = seg_a[i + 4] | (seg_a[i + 5] << 8)
            if (not require_message_type) or text_type == TEXT_TYPE_MESSAGE:
                refs.append((i, str_idx))
            i += 6
            continue
        i += 1
    return refs


def scan_text_refs_raw(seg_a: bytes) -> List[Tuple[int, int]]:
    """兼容调试用: 返回所有 `dd 00` 命中, 不检查 type 字段。"""
    return scan_text_refs(seg_a, require_message_type=False)


def scan_asset_refs(seg_a: bytes) -> List[Tuple[int, int]]:
    """扫描 0x83 资源加载指令. 4 字节: 83 00 [u16 strIdx]."""
    refs = []
    i = 0
    n = len(seg_a)
    while i + 4 <= n:
        if seg_a[i] == 0x83 and seg_a[i + 1] == 0x00:
            str_idx = seg_a[i + 2] | (seg_a[i + 3] << 8)
            refs.append((i, str_idx))
            i += 4
            continue
        i += 1
    return refs


# ============================================================
# 编码工具
# ============================================================
#
# 引擎用 SJIS (CP932) 解码字符串. 注入中文时用 GBK 写入,
# EXE 需要 patch 让 DBCS leadbyte 范围扩展到 0x81-0xFE.
# (这步留到注入完成、文本能跑通后再处理)

def decode_sjis(b: bytes) -> str:
    return b.decode('cp932', errors='replace')


def encode_gbk(s: str) -> bytes:
    return s.encode('gbk')


# ============================================================
# 剧情文本判定
# ============================================================
#
# 对 0xdd opcode 的命中, 即使过滤了 idx 越界, 仍然存在两类问题:
#   (1) 假阳性: 上一条变长 opcode 的尾巴恰好匹配 dd 模式 (idx 通常越界, 但偶尔合法)
#   (2) 真命中但指向资源: 引擎用 0xdd 也可以加载 CG/BGM 等
#
# 不做完整 VM 反汇编的前提下, 用"内容是否像剧情"作为最可靠的过滤.
# 剧情文本特征: 含日文假名 (Hiragana/Katakana/CJK).
# 资源名特征:    纯 ASCII (cl1225z, %N00.bmp, BGM01.WAV).
# 边界情况:      '……' '「」' 之类纯日式标点 -> 当作剧情保留.

_KANA_RANGES = (
    (0x3040, 0x309f),  # Hiragana
    (0x30a0, 0x30ff),  # Katakana
    (0x4e00, 0x9fff),  # CJK Unified
    (0xff00, 0xffef),  # 全角 ASCII / 半角假名
)

_JP_PUNCT_ONLY = set('…・「」 　〜～！？。、〝〟"\'\u3000')


def is_story_text(s_bytes: bytes) -> bool:
    """
    判断 SJIS 字节串是否像剧情文本.
    True: 含假名/汉字, 或者纯日式标点 (省略号等).
    """
    try:
        s = s_bytes.decode('cp932')
    except UnicodeDecodeError:
        return False
    if not s:
        return False
    # 含日文字符
    for c in s:
        cp = ord(c)
        for lo, hi in _KANA_RANGES:
            if lo <= cp <= hi:
                return True
    # 纯日式标点 (剧情里独立的 '……' '「」' 等)
    if all(c in _JP_PUNCT_ONLY for c in s):
        return True
    return False


# ============================================================
# 高层 API: 提取剧情文本引用
# ============================================================

def collect_story_refs(v: 'ValFile') -> List[Tuple[int, int]]:
    """
    扫描 v.seg_a 中所有 0xdd 指令, 过滤越界 idx 与非剧情内容,
    返回 [(seg_a 内偏移, seg_B idx), ...].
    """
    sB = len(v.strings)
    # scan_text_refs 默认只接受 type==0 的正文显示指令,
    # 避免把其它变长指令参数区里的 dd 00 假命中当成剧情文本。
    raw_refs = scan_text_refs(v.seg_a)
    out = []
    for site, idx in raw_refs:
        if idx >= sB:
            continue
        if is_story_text(v.strings[idx]):
            out.append((site, idx))
    return out


# ============================================================
# 自检
# ============================================================
if __name__ == '__main__':
    import sys
    if len(sys.argv) >= 2:
        fp = sys.argv[1]
        with open(fp, 'rb') as f:
            data = f.read()
        v = ValFile.parse(data)
        print(f"== {fp} ==")
        print(f"  header_extra: {v.header_extra.hex()}")
        print(f"  seg_A: {len(v.seg_a)} bytes")
        print(f"  strings: {len(v.strings)} entries")

        text_refs = scan_text_refs(v.seg_a)
        asset_refs = scan_asset_refs(v.seg_a)
        text_idx = {idx for _, idx in text_refs}
        asset_idx = {idx for _, idx in asset_refs}
        print(f"  0xdd refs:  {len(text_refs):4} sites, {len(text_idx):4} distinct idx")
        print(f"  0x83 refs:  {len(asset_refs):4} sites, {len(asset_idx):4} distinct idx")
        unref = set(range(len(v.strings))) - text_idx - asset_idx
        print(f"  unref idx:  {len(unref):4}")

        # round-trip 自检
        rebuilt = v.build()
        if rebuilt == data:
            print("  ROUND-TRIP: byte-perfect")
        else:
            print(f"  ROUND-TRIP DIFF: orig={len(data)} new={len(rebuilt)}")

        # 头几条剧情文本
        print("  --- first 5 dd refs ---")
        for site, idx in text_refs[:5]:
            print(f"    seg_a +0x{site:05x} -> str[{idx}]: {decode_sjis(v.strings[idx])[:50]!r}")

        # 头几条资源
        print("  --- first 5 83 refs ---")
        for site, idx in asset_refs[:5]:
            print(f"    seg_a +0x{site:05x} -> str[{idx}]: {decode_sjis(v.strings[idx])[:50]!r}")

        # 分类
        name_no_ext = os.path.splitext(os.path.basename(fp))[0]
        print(f"  classify: {classify_val(name_no_ext)}")
