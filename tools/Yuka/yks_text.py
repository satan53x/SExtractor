#!/usr/bin/env python3
"""
yks_text.py - Yuka Engine YKS002 脚本文本提取/注入工具
セミラミスの天秤 (Semiramis no Tenbin)

用法:
  python yks_text.py extract  input.yks  output.json             # 单文件提取
  python yks_text.py inject   input.yks  trans.json  output.yks  # 单文件注入
  python yks_text.py extract  yks_dir/   json_dir/               # 批量提取
  python yks_text.py inject   yks_dir/   json_dir/   out_dir/    # 批量注入
  python yks_text.py verify   input.yks                          # round-trip验证

JSON 格式 (UTF-8):
  [
    { "name": "玲児",  "message": "「……どうも」", "id": 472, "name_id": 469 },
    { "name": "",      "message": "旁白文本",       "id": 489 },
    { "name": "",      "message": "选项文本",       "id": 17018, "type": "select" }
  ]

  name    = 角色名 (可翻译, 空=旁白)
  message = 对话/选项文本 (可翻译)
  id      = S3节点索引 (不可改)
  name_id = 角色名S3节点索引 (不可改, 用于注入角色名)
"""

import struct
import sys
import os


# ======================================================================
# YKS002 解析
# ======================================================================

class YKS002:
    """YKS002 文件解析器"""

    # S3 节点类型 → (f1含义, f2含义)
    # 'T' = TEXT_OFF(字符串), 'B' = TEXT_OFF(8字节二进制), 'I' = 索引, 'L' = 字面值, '-' = 未使用(FFFF)
    TYPE_SCHEMA = {
        0x01: ('T', 'I'),   # CMD:    f1=命令名,     f2=S2索引
        0x02: ('T', '-'),   # EXPR:   f1=运算符
        0x03: ('T', 'I'),   # BLOCK:  f1=括号,       f2=S1索引(跳转)
        0x04: ('T', 'I'),   # LABEL:  f1=标签名,     f2=S1索引(跳转)
        0x05: ('-', 'B'),   # INT:    f2=8字节二进制(2×u32)
        0x06: ('-', 'B'),   # FLOAT:  f2=8字节二进制(double)
        0x07: ('-', 'T'),   # STRING: f2=对话/路径
        0x08: ('T', 'I'),   # PARAM:  f1=空标记,     f2=S2索引
        0x09: ('-', 'L'),   # LIT:    f2=字面值
        0x0a: ('T', '-'),   # CG:     f1=CG名
        0x0b: ('T', '-'),   # VAR:    f1=变量名
    }

    def __init__(self, data):
        self.data = bytearray(data)
        self._parse_header()
        self._parse_sections()

    def _parse_header(self):
        if self.data[:6] != b'YKS002':
            raise ValueError(f"不是 YKS002 文件: {self.data[:8]}")

        hdr = struct.unpack_from('<8s 10I', self.data, 0)
        self.hdr_size  = hdr[1]   # 0x30
        self.s1_off    = hdr[2]
        self.s1_size   = hdr[3]
        self.s2_off    = hdr[4]
        self.s2_size   = hdr[5]
        self.s3_off    = hdr[6]
        self.s3_size   = hdr[7]
        self.s4_off    = hdr[8]
        self.s4_size   = hdr[9]
        self.flags     = hdr[10]

    def _parse_sections(self):
        # S1: u32[] 命令表
        self.s1_count = self.s1_size // 4
        self.s1 = list(struct.unpack_from(f'<{self.s1_count}I', self.data, self.s1_off))

        # S2: u32[] 操作数表
        self.s2_count = self.s2_size // 4
        self.s2 = list(struct.unpack_from(f'<{self.s2_count}I', self.data, self.s2_off))

        # S3: {type, f1, f2}[] 节点表
        self.s3_count = self.s3_size // 0xC
        self.s3 = []
        for i in range(self.s3_count):
            t, f1, f2 = struct.unpack_from('<3I', self.data, self.s3_off + i * 0xC)
            self.s3.append([t, f1, f2])

        # S4: 原始字节
        self.s4 = bytearray(self.data[self.s4_off:self.s4_off + self.s4_size])

    def get_string(self, offset):
        """从文本池读取 null 终止 UTF-8 字符串"""
        if offset >= len(self.s4):
            return ""
        end = self.s4.index(0, offset) if 0 in self.s4[offset:] else len(self.s4)
        return self.s4[offset:end].decode('utf-8', errors='replace')

    def get_binary(self, offset):
        """从文本池读取 8 字节二进制数据"""
        return bytes(self.s4[offset:offset + 8])

    def build_text_pool_map(self):
        """
        构建文本池完整映射: 按偏移排序的条目列表
        每个条目: (offset, kind, s3_idx, field, raw_size)
          kind: 'str' = null终止字符串, 'bin' = 8字节二进制
        """
        entries = {}  # offset → (kind, s3_idx, field)

        for i, (typ, f1, f2) in enumerate(self.s3):
            schema = self.TYPE_SCHEMA.get(typ)
            if not schema:
                continue

            # f1
            if schema[0] == 'T' and f1 != 0xFFFFFFFF and f1 < len(self.s4):
                if f1 not in entries:
                    entries[f1] = ('str', i, 'f1')
            # f2
            if schema[1] == 'T' and f2 != 0xFFFFFFFF and f2 < len(self.s4):
                if f2 not in entries:
                    entries[f2] = ('str', i, 'f2')
            elif schema[1] == 'B' and f2 != 0xFFFFFFFF and f2 < len(self.s4):
                if f2 not in entries:
                    entries[f2] = ('bin', i, 'f2')

        # 按偏移排序
        sorted_entries = []
        for off in sorted(entries):
            kind, s3_idx, field = entries[off]
            if kind == 'str':
                end = self.s4.index(0, off) if 0 in self.s4[off:] else len(self.s4)
                raw_size = end - off + 1  # 含 null
            else:
                raw_size = 8
            sorted_entries.append((off, kind, s3_idx, field, raw_size))

        return sorted_entries

    def serialize(self):
        """序列化为完整 YKS 文件"""
        # 重算偏移
        s1_off = 0x30
        s1_size = self.s1_count * 4
        s2_off = s1_off + s1_size
        s2_size = self.s2_count * 4
        s3_off = s2_off + s2_size
        s3_size = self.s3_count * 0xC
        s4_off = s3_off + s3_size
        s4_size = len(self.s4)

        out = bytearray()

        # Header
        out += b'YKS002\x00\x00'
        out += struct.pack('<10I',
            0x30,
            s1_off, s1_size,
            s2_off, s2_size,
            s3_off, s3_size,
            s4_off, s4_size,
            self.flags
        )

        # S1
        for v in self.s1:
            out += struct.pack('<I', v)

        # S2
        for v in self.s2:
            out += struct.pack('<I', v)

        # S3
        for typ, f1, f2 in self.s3:
            out += struct.pack('<3I', typ, f1, f2)

        # S4
        out += self.s4

        return bytes(out)


# ======================================================================
# 提取
# ======================================================================

def is_resource_path(text):
    """判断是否为资源路径"""
    if not text:
        return True
    if '\\' in text or '/' in text:
        return True
    if text.endswith(('.ogg', '.png', '.jpg', '.yks', '.bmp')):
        return True
    return False


def is_control_code(text):
    """判断是否为纯控制码字符串 (如 @f(10)@u+(67)@f(0))"""
    import re
    if not text:
        return True
    stripped = re.sub(r'@[a-zA-Z][+\-]?\([^)]*\)', '', text)
    return stripped.strip() == ''


def is_select_text(yks, s3_idx):
    """判断一个 type=0x07 节点是否是选择肢文本"""
    for j in range(s3_idx + 1, min(s3_idx + 4, len(yks.s3))):
        typ, f1, f2 = yks.s3[j]
        if typ == 0x0b and f1 != 0xFFFFFFFF:
            if yks.get_string(f1).startswith('Select.Text'):
                return True
            break
        if typ in (0x07, 0x03, 0x04):
            break
    return False


def get_gto_role(yks, s3_idx):
    """
    判断 type=0x07 节点在 GraphicTextOut 中的角色:
      'name' / 'message' / None
    """
    if s3_idx + 1 >= len(yks.s3):
        return None
    next_typ, next_f1, _ = yks.s3[s3_idx + 1]
    if next_typ != 0x01 or next_f1 == 0xFFFFFFFF:
        return None
    if yks.get_string(next_f1) != 'GraphicTextOut':
        return None

    for j in range(s3_idx - 1, max(s3_idx - 4, -1), -1):
        typ, f1, f2 = yks.s3[j]
        if typ == 0x08 and f2 != 0xFFFFFFFF:
            bin_count = 0
            k = f2
            while k < len(yks.s2):
                sv = yks.s2[k]
                if sv == 0xFFFFFFFF:
                    break
                if sv < len(yks.s3):
                    st, _, sf2 = yks.s3[sv]
                    if st == 0x05 and sf2 != 0xFFFFFFFF and sf2 + 4 <= len(yks.s4):
                        v0 = struct.unpack_from('<I', yks.s4, sf2)[0]
                        bin_count += 1
                        if bin_count == 2:
                            return 'name' if v0 == 1 else 'message'
                k += 1
            return None
        if typ == 0x07:
            break
    return None


def find_name_for_msg(yks, msg_idx):
    """
    从 msg_idx 往前找角色名。支持两种模式:
      1. 独立 NAME 节点: 0x07(角色名) + GraphicTextOut, 前面PARAM的第2个BIN=1
      2. 嵌入 PARAM:     0x08(PARAM含BIN(1)+角色名TEXT) + GraphicTextOut
    返回 (name_str, name_s3_idx)
      name_s3_idx: 模式1 = 0x07节点索引, 模式2 = PARAM操作数链中TEXT节点的S3索引
    """
    for j in range(msg_idx - 1, max(msg_idx - 20, -1), -1):
        typ, f1, f2 = yks.s3[j]

        # 遇到 KeyWait 说明跨了一轮对话
        if typ == 0x01 and f1 != 0xFFFFFFFF and yks.get_string(f1) == 'KeyWait':
            break

        # 模式1: 独立 0x07 NAME 节点
        if typ == 0x07 and f2 != 0xFFFFFFFF and f2 < len(yks.s4):
            role = get_gto_role(yks, j)
            if role == 'name':
                return yks.get_string(f2), j

        # 模式2: PARAM 嵌入 NAME (0x08 + GraphicTextOut, 第2个BIN=1)
        if typ == 0x08 and f2 != 0xFFFFFFFF:
            # 后面必须是 GraphicTextOut
            if j + 1 >= len(yks.s3):
                continue
            nt, nf1, _ = yks.s3[j + 1]
            if nt != 0x01 or nf1 == 0xFFFFFFFF or yks.get_string(nf1) != 'GraphicTextOut':
                continue

            # 扫描操作数链: 检查第2个BIN是否=1, 同时记录最后一个TEXT
            bin_count = 0
            is_name_param = False
            last_text = ''
            last_text_s3 = -1
            k = f2
            while k < len(yks.s2):
                sv = yks.s2[k]
                if sv == 0xFFFFFFFF:
                    break
                if sv < len(yks.s3):
                    st, _, sf2 = yks.s3[sv]
                    if st == 0x05 and sf2 != 0xFFFFFFFF and sf2 + 4 <= len(yks.s4):
                        v0 = struct.unpack_from('<I', yks.s4, sf2)[0]
                        bin_count += 1
                        if bin_count == 2 and v0 == 1:
                            is_name_param = True
                    if st == 0x07 and sf2 != 0xFFFFFFFF:
                        last_text = yks.get_string(sf2)
                        last_text_s3 = sv
                k += 1

            if is_name_param and last_text:
                return last_text, last_text_s3

    return '', -1


def extract(yks_path, out_path):
    import json

    with open(yks_path, 'rb') as f:
        yks = YKS002(f.read())

    entries = []

    for i, (typ, f1, f2) in enumerate(yks.s3):
        if typ != 0x07 or f2 == 0xFFFFFFFF or f2 >= len(yks.s4):
            continue

        text = yks.get_string(f2)
        if is_resource_path(text):
            continue
        if is_control_code(text):
            continue

        # 选择肢
        if is_select_text(yks, i):
            entries.append({
                "name": "",
                "message": text,
                "id": i,
                "type": "select"
            })
            continue

        role = get_gto_role(yks, i)

        # 跳过独立 NAME 节点（角色名通过 find_name_for_msg 获取）
        if role == 'name':
            continue

        if role == 'message':
            name, name_id = find_name_for_msg(yks, i)
            entries.append({
                "name": name,
                "message": text,
                "id": i,
                "name_id": name_id
            })
            continue

        # 非 GraphicTextOut 的文本
        if not (all(ord(c) < 0x80 for c in text) and len(text) < 40):
            entries.append({
                "name": "",
                "message": text,
                "id": i
            })

    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(entries, f, ensure_ascii=False, indent=4)

    n_named = sum(1 for e in entries if e.get("name"))
    n_narr  = sum(1 for e in entries if not e.get("name") and e.get("type") != "select")
    n_sel   = sum(1 for e in entries if e.get("type") == "select")
    print(f"提取完成: {out_path}")
    print(f"  有名对话: {n_named}  旁白: {n_narr}  选项: {n_sel}")
    print(f"  合计: {len(entries)} 条")


# ======================================================================
# 注入
# ======================================================================

def inject(yks_path, txt_path, out_path):
    import json

    with open(yks_path, 'rb') as f:
        yks = YKS002(f.read())

    # 读取翻译 JSON
    with open(txt_path, 'r', encoding='utf-8') as f:
        entries = json.load(f)

    # 建立替换表: s4_offset → new_utf8_bytes
    replace_map = {}  # old_s4_offset → new_bytes
    name_replace = 0
    msg_replace = 0

    for entry in entries:
        s3_idx = entry.get("id")
        if s3_idx is None or s3_idx >= len(yks.s3):
            continue

        typ, f1, f2 = yks.s3[s3_idx]

        # message → f2
        new_msg = entry.get("message", "")
        if typ == 0x07 and f2 != 0xFFFFFFFF:
            replace_map[f2] = new_msg.encode('utf-8')
            msg_replace += 1

        # name → name_id 节点的 f2
        name_id = entry.get("name_id", -1)
        new_name = entry.get("name", "")
        if name_id >= 0 and name_id < len(yks.s3) and new_name:
            nt, nf1, nf2 = yks.s3[name_id]
            if nt == 0x07 and nf2 != 0xFFFFFFFF:
                if nf2 not in replace_map:
                    replace_map[nf2] = new_name.encode('utf-8')
                    name_replace += 1

    if not replace_map:
        print("错误: 没有找到可注入的翻译文本")
        return

    # 重建 S4
    pool_map = yks.build_text_pool_map()
    old_s4 = yks.s4
    new_s4 = bytearray()
    offset_remap = {}

    for entry in pool_map:
        old_off, kind, s3_idx, field, raw_size = entry
        new_off = len(new_s4)
        offset_remap[old_off] = new_off

        if kind == 'bin':
            new_s4 += old_s4[old_off:old_off + 8]
        else:
            if old_off in replace_map:
                new_s4 += replace_map[old_off]
                new_s4 += b'\x00'
            else:
                new_s4 += old_s4[old_off:old_off + raw_size]

    # 更新 S3 中的 TEXT_OFF
    for i, (typ, f1, f2) in enumerate(yks.s3):
        schema = yks.TYPE_SCHEMA.get(typ)
        if not schema:
            continue

        new_f1 = f1
        new_f2 = f2

        if schema[0] in ('T',) and f1 != 0xFFFFFFFF and f1 in offset_remap:
            new_f1 = offset_remap[f1]
        if schema[1] in ('T', 'B') and f2 != 0xFFFFFFFF and f2 in offset_remap:
            new_f2 = offset_remap[f2]

        yks.s3[i] = [typ, new_f1, new_f2]

    yks.s4 = new_s4

    out_data = yks.serialize()
    with open(out_path, 'wb') as f:
        f.write(out_data)

    print(f"注入完成: {out_path}")
    print(f"  角色名: {name_replace} 条  对话: {msg_replace} 条")
    print(f"  文本池: {len(old_s4)} → {len(new_s4)} 字节 ({len(new_s4) - len(old_s4):+d})")


# ======================================================================
# Round-trip 验证
# ======================================================================

def verify(yks_path):
    """无修改 round-trip 验证: 提取→原文注入→对比"""
    with open(yks_path, 'rb') as f:
        original = f.read()

    yks = YKS002(original)
    rebuilt = yks.serialize()

    if original == rebuilt:
        print(f"验证通过: round-trip 完全一致 ({len(original)} bytes)")
    else:
        print(f"验证失败: 原始 {len(original)} bytes, 重建 {len(rebuilt)} bytes")
        # 找第一个差异
        for i in range(min(len(original), len(rebuilt))):
            if original[i] != rebuilt[i]:
                print(f"  首个差异位置: 0x{i:08x} (原始=0x{original[i]:02x}, 重建=0x{rebuilt[i]:02x})")
                break


# ======================================================================
# 批量处理
# ======================================================================

def find_yks_files(input_dir):
    """递归查找目录下所有 .yks 文件"""
    yks_files = []
    for root, dirs, files in os.walk(input_dir):
        for fn in sorted(files):
            if fn.lower().endswith('.yks'):
                yks_files.append(os.path.join(root, fn))
    return yks_files


def batch_extract(input_dir, output_dir):
    """批量提取: 输入目录下所有 .yks → 输出目录下对应 .txt"""
    os.makedirs(output_dir, exist_ok=True)
    yks_files = find_yks_files(input_dir)

    if not yks_files:
        print(f"错误: {input_dir} 下没有找到 .yks 文件")
        return

    total_dialogue = 0
    total_select = 0
    success = 0
    skipped = 0

    for yks_path in yks_files:
        rel = os.path.relpath(yks_path, input_dir)
        txt_name = os.path.splitext(rel)[0] + '.json'
        txt_path = os.path.join(output_dir, txt_name)
        os.makedirs(os.path.dirname(txt_path), exist_ok=True)

        try:
            with open(yks_path, 'rb') as f:
                header = f.read(8)
            if header[:6] != b'YKS002':
                skipped += 1
                continue

            extract(yks_path, txt_path)

            # 统计
            import json as _json
            with open(txt_path, 'r', encoding='utf-8') as f:
                _entries = _json.load(f)
                for e in _entries:
                    if e.get("type") == "select":
                        total_select += 1
                    else:
                        total_dialogue += 1
            success += 1

        except Exception as e:
            print(f"  跳过 {rel}: {e}")
            skipped += 1

    print(f"\n{'='*50}")
    print(f"批量提取完成")
    print(f"  成功: {success} 文件")
    print(f"  跳过: {skipped} 文件 (非YKS002或出错)")
    print(f"  对话: {total_dialogue} 条")
    print(f"  选项: {total_select} 条")
    print(f"  合计: {total_dialogue + total_select} 条可翻译文本")


def batch_inject(yks_dir, txt_dir, output_dir):
    """批量注入: yks原始目录 + txt翻译目录 → 输出目录"""
    os.makedirs(output_dir, exist_ok=True)
    yks_files = find_yks_files(yks_dir)

    if not yks_files:
        print(f"错误: {yks_dir} 下没有找到 .yks 文件")
        return

    success = 0
    skipped = 0
    copied = 0
    total_replaced = 0

    for yks_path in yks_files:
        rel = os.path.relpath(yks_path, yks_dir)
        txt_name = os.path.splitext(rel)[0] + '.json'
        txt_path = os.path.join(txt_dir, txt_name)
        out_path = os.path.join(output_dir, rel)
        os.makedirs(os.path.dirname(out_path), exist_ok=True)

        if not os.path.exists(txt_path):
            # 无翻译文件，原样复制
            with open(yks_path, 'rb') as f:
                data = f.read()
            with open(out_path, 'wb') as f:
                f.write(data)
            copied += 1
            continue

        try:
            with open(yks_path, 'rb') as f:
                header = f.read(8)
            if header[:6] != b'YKS002':
                with open(yks_path, 'rb') as f:
                    data = f.read()
                with open(out_path, 'wb') as f:
                    f.write(data)
                copied += 1
                continue

            inject(yks_path, txt_path, out_path)
            success += 1

            # 统计替换数
            import json as _json
            with open(txt_path, 'r', encoding='utf-8') as f:
                _entries = _json.load(f)
                total_replaced += len(_entries)

        except Exception as e:
            print(f"  出错 {rel}: {e}")
            # 出错时原样复制
            with open(yks_path, 'rb') as f:
                data = f.read()
            with open(out_path, 'wb') as f:
                f.write(data)
            skipped += 1

    print(f"\n{'='*50}")
    print(f"批量注入完成")
    print(f"  注入: {success} 文件")
    print(f"  原样复制: {copied} 文件 (无翻译)")
    print(f"  出错: {skipped} 文件")
    print(f"  替换文本: {total_replaced} 条")


# ======================================================================
# main
# ======================================================================

def usage():
    print("yks_text.py - Yuka Engine YKS002 文本提取/注入工具")
    print()
    print("单文件:")
    print("  python yks_text.py extract  input.yks   output.json")
    print("  python yks_text.py inject   input.yks   trans.json   output.yks")
    print("  python yks_text.py verify   input.yks")
    print()
    print("批量:")
    print("  python yks_text.py extract  yks_dir/    json_dir/")
    print("  python yks_text.py inject   yks_dir/    json_dir/    output_dir/")
    sys.exit(1)


if __name__ == '__main__':
    if len(sys.argv) < 3:
        usage()

    cmd = sys.argv[1].lower()

    if cmd == 'extract' and len(sys.argv) == 4:
        src, dst = sys.argv[2], sys.argv[3]
        if os.path.isdir(src):
            batch_extract(src, dst)
        else:
            extract(src, dst)
    elif cmd == 'inject' and len(sys.argv) == 5:
        src, txt, out = sys.argv[2], sys.argv[3], sys.argv[4]
        if os.path.isdir(src):
            batch_inject(src, txt, out)
        else:
            inject(src, txt, out)
    elif cmd == 'verify' and len(sys.argv) == 3:
        verify(sys.argv[2])
    else:
        usage()
