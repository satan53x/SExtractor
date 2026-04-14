#!/usr/bin/env python3
"""
yks_text.py — Yuka Engine YKS001 脚本文本提取/导入工具
目标游戏: 恋×恋＝∞ ～恋する乙女にできること～ (KoiKoi)
引擎: Yuka Engine (YKS001 format)

用法:
  python yks_text.py extract <input.yks> [output.json]
  python yks_text.py inject  <orig.yks> <trans.json> [output.yks]
  python yks_text.py batch_e <yks_dir> <out_dir>
  python yks_text.py batch_r <yks_dir> <json_dir> <out_dir>

JSON格式:
  [
    {
      "name": "楓真",              // 角色名(null=旁白)
      "name_id": 180,             // name STR节点的S2索引(旁白时无此字段)
      "message": "おはよう",       // 对话文本
      "message_id": 181           // message STR节点的S2索引
    }, ...
  ]

注音格式保留: 漢字@r(offset,ルビテキスト) — 引擎原生控制码
"""

import struct, sys, os, json, argparse, glob

MAGIC = b'YKS001\x00\x00'
HEADER_SIZE = 0x30
TYPE_FUNC, TYPE_OP, TYPE_INT, TYPE_STR, TYPE_VAR, TYPE_SPEC = 0, 1, 4, 5, 8, 0xA


class YKS001:
    def __init__(self):
        self.version = 0
        self.unknown_08 = 0
        self.s3_count = 0
        self.unknown_2c = 0
        self.s1 = []
        self.s2 = []
        self.s4 = b''

    @staticmethod
    def load(filepath):
        yks = YKS001()
        with open(filepath, 'rb') as f:
            data = f.read()
        if data[:6] != b'YKS001':
            raise ValueError(f"非YKS001: {data[:8]}")
        yks.version = struct.unpack_from('<H', data, 0x06)[0]
        yks.unknown_08 = struct.unpack_from('<Q', data, 0x08)[0]
        s1_off, s1_n, s2_off, s2_n, s4_off, s4_sz, s3_n, u2c = struct.unpack_from('<8I', data, 0x10)
        yks.s3_count, yks.unknown_2c = s3_n, u2c
        raw = bytearray(data)
        if yks.version == 1:
            for i in range(s4_sz):
                raw[s4_off + i] ^= 0xAA
        yks.s1 = list(struct.unpack_from(f'<{s1_n}I', raw, s1_off))
        for i in range(s2_n):
            yks.s2.append(list(struct.unpack_from('<IIII', raw, s2_off + i * 0x10)))
        yks.s4 = bytes(raw[s4_off:s4_off + s4_sz])
        return yks

    def save(self, filepath, encrypt=False):
        s1_off = HEADER_SIZE
        s2_off = s1_off + len(self.s1) * 4
        s4_off = s2_off + len(self.s2) * 0x10
        buf = bytearray(s4_off + len(self.s4))
        buf[0:8] = MAGIC
        struct.pack_into('<H', buf, 0x06, 1 if encrypt else 0)
        struct.pack_into('<Q', buf, 0x08, self.unknown_08)
        struct.pack_into('<8I', buf, 0x10, s1_off, len(self.s1), s2_off, len(self.s2),
                         s4_off, len(self.s4), self.s3_count, self.unknown_2c)
        for i, v in enumerate(self.s1):
            struct.pack_into('<I', buf, s1_off + i * 4, v)
        for i, e in enumerate(self.s2):
            struct.pack_into('<IIII', buf, s2_off + i * 0x10, *e)
        s4d = bytearray(self.s4)
        if encrypt:
            for i in range(len(s4d)): s4d[i] ^= 0xAA
        buf[s4_off:s4_off + len(s4d)] = s4d
        with open(filepath, 'wb') as f:
            f.write(buf)

    def s4_str(self, off, enc='cp932'):
        if off < 0 or off >= len(self.s4): return None
        end = self.s4.find(b'\x00', off)
        if end < 0: end = len(self.s4)
        try: return self.s4[off:end].decode(enc)
        except: return None

    def get_all_s4_refs(self):
        refs = []
        for i, (t, f1, f2, f3) in enumerate(self.s2):
            if t == TYPE_FUNC:   refs += [(i, 1, f1), (i, 2, f2)]
            elif t == TYPE_OP:   refs += [(i, 1, f1), (i, 2, f2)]
            elif t == TYPE_INT:  refs.append((i, 2, f2))  # f2=S4偏移(指向u32常量)
            elif t == TYPE_STR:  refs.append((i, 2, f2))
            elif t == TYPE_VAR:  refs.append((i, 1, f1))
        return refs


# ============================================================
#  提取
# ============================================================
def extract_dialogue(yks, encoding='cp932'):
    """提取对话(Yuka YKS001)。
    
    调用约定: Yuka VM并非严格的"FUNC即参数边界"。
    很多无参helper FUNC(GraphicShow/LF/PF/DrawStop/KeyWait等)会出现在
    StrOut/StrOutNWC的参数槽中间,但不消费参数。
    
    实际模式(festival01_Ai为典型):
      FUNC StrOut
        FUNC GraphicShow   ← 无参helper,夹在中间
        STR "「対話文」"    ← 真正的参数
      FUNC LF              ← 后续无参helper
      FUNC KeyWait
      FUNC PF              ← 翻页
    
    正确算法: 对每个对话FUNC,往后跨任意节点找最近的STR,
             仅当遇到下一个**语义对话FUNC**(StrOut/StrOutNWC/PF/Select/ScriptCall)
             时停止——它们会接管自己的STR或表示对话流转。
    
    StrOutNWC/StrOutNW 设角色名,紧随其后的 StrOut 输出对话。
    PF (PageFeed) 翻页清除 pending name → 之后 StrOut 为旁白。
    """
    DIALOG_FUNCS = {'StrOut', 'StrOutNW', 'StrOutNWC', 'PF',
                    'Select.Text', 'Select.Text1', 'Select.Text2',
                    'ScriptCall'}
    SEARCH_WINDOW = 15
    PATH_MARKERS = ('.ogg', '.wav', '.mp3', '.png', '.jpg', '.bmp', '.ykg', '\\')

    def is_path_like(s):
        return s and any(m in s for m in PATH_MARKERS)
    
    def find_arg_str(func_idx):
        """从 func_idx 往后找第一个**非路径状**的STR,跨越无参FUNC,
        遇到下一个语义对话FUNC则停止。
        
        Yuka StrOut/StrOutNWC可带可选voice/资源路径前缀:
          StrOutNWC + STR voice_path + INT + STR name  ← name是"第一个非路径STR"
          StrOutNWC + INT + STR name                   ← 同上(无voice)
          StrOut    + STR message                      ← message同样
        """
        for j in range(func_idx + 1, min(len(yks.s1), func_idx + 1 + SEARCH_WINDOW)):
            sj = yks.s1[j]
            if sj >= len(yks.s2): continue
            t = yks.s2[sj][0]
            if t == TYPE_STR:
                s = yks.s4_str(yks.s2[sj][2], encoding)
                if s and not is_path_like(s):
                    return sj, s
                # 路径STR → 跳过继续找
            elif t == TYPE_FUNC:
                fn = yks.s4_str(yks.s2[sj][1], encoding)
                if fn in DIALOG_FUNCS:
                    return None, None
        return None, None

    results = []
    pending_name = None
    pending_name_id = None
    name_consumed = True

    for i, si in enumerate(yks.s1):
        if si >= len(yks.s2): continue
        t, f1, f2, f3 = yks.s2[si]
        if t != TYPE_FUNC: continue
        fn = yks.s4_str(f1, encoding)

        if fn == 'StrOutNWC':
            # 设置角色名 (NWC = Name With Character?)
            sid, name = find_arg_str(i)
            if sid is not None and name:
                pending_name = name
                pending_name_id = sid
                name_consumed = False
        elif fn in ('StrOut', 'StrOutNW'):
            # 输出对话 (StrOutNW = StrOut No-Wait 变体)
            sid, msg = find_arg_str(i)
            if sid is not None and msg is not None:
                if not name_consumed:
                    results.append({
                        "name": pending_name,
                        "message": msg,
                        "message_id": sid,
                        "name_id": pending_name_id,
                    })
                    name_consumed = True
                else:
                    results.append({"name": None, "message": msg, "message_id": sid})
        elif fn == 'PF':
            name_consumed = True
        elif fn in ('Select.Text', 'Select.Text1', 'Select.Text2'):
            sid, txt = find_arg_str(i)
            if sid is not None and txt:
                results.append({"name": "__select__", "message": txt, "message_id": sid})
    return results


# ============================================================
#  导入
# ============================================================
def rebuild_s4(yks, trans, out_enc='cp932'):
    """S4重建：append策略
    
    将翻译后的字符串追加到S4末尾，只修改对应STR的f2指向新位置。
    原始S4内容完全不变，其他引用的二进制数据不受任何影响。
    """
    all_refs = yks.get_all_s4_refs()
    new_s4 = bytearray(yks.s4)  # 保持原始S4不变
    replaced = 0

    for s2i, new_text in trans.items():
        if s2i >= len(yks.s2): continue
        t, f1, f2, f3 = yks.s2[s2i]
        if t != TYPE_STR: continue
        try:
            new_raw = new_text.encode(out_enc) + b'\x00'
        except UnicodeEncodeError as e:
            print(f"[warn] S2[{s2i}] encode fail: {e}"); continue

        # 检查是否和原文相同(避免无谓追加)
        old_end = yks.s4.find(b'\x00', f2)
        if old_end < 0: old_end = len(yks.s4) - 1
        old_raw = yks.s4[f2:old_end + 1]
        if new_raw == old_raw:
            continue  # 内容相同,不需要修改

        # 追加新字符串到S4末尾
        new_off = len(new_s4)
        new_s4.extend(new_raw)

        # 更新S2中所有指向同一S4偏移的STR引用
        for ref_i, ref_fi, ref_off in all_refs:
            if ref_off == f2 and yks.s2[ref_i][0] == TYPE_STR and ref_fi == 2:
                yks.s2[ref_i][2] = new_off

        replaced += 1

    updated = 0
    if replaced > 0:
        # 统计偏移变化
        for ref_i, ref_fi, ref_off in all_refs:
            orig_val = ref_off
            cur_val = yks.s2[ref_i][1] if ref_fi == 1 else yks.s2[ref_i][2]
            if cur_val != orig_val:
                updated += 1

    yks.s4 = bytes(new_s4)
    return updated, replaced


# ============================================================
#  CLI
# ============================================================
def do_extract(args):
    yks = YKS001.load(args.input)
    entries = extract_dialogue(yks, args.encoding)
    out = args.output or os.path.splitext(args.input)[0] + '.json'
    with open(out, 'w', encoding='utf-8') as f:
        json.dump(entries, f, ensure_ascii=False, indent=2)
    nn = sum(1 for e in entries if e['name'] is None)
    nd = sum(1 for e in entries if e['name'] not in (None, '__select__'))
    ns = sum(1 for e in entries if e.get('name') == '__select__')
    print(f"[extract] {os.path.basename(args.input)} → {len(entries)} 条 (旁白{nn} 对话{nd} 选择{ns})")

def do_inject(args):
    yks = YKS001.load(args.input)
    with open(args.trans, 'r', encoding='utf-8') as f:
        entries = json.load(f)
    trans = {}
    for e in entries:
        mid = e.get('message_id'); msg = e.get('message')
        if mid is not None and msg is not None: trans[mid] = msg
        nid = e.get('name_id'); nm = e.get('name')
        if nid is not None and nm is not None: trans[nid] = nm
    if not trans: print("[inject] 无条目"); return
    upd, rep = rebuild_s4(yks, trans, args.encoding)
    out = args.output or os.path.splitext(args.input)[0] + '_cn.yks'
    yks.save(out, encrypt=args.encrypt)
    print(f"[inject] 替换{rep}条 更新{upd}偏移 → {os.path.basename(out)}")

def do_batch_e(args):
    files = sorted(glob.glob(os.path.join(args.yks_dir, '*.yks')))
    os.makedirs(args.out_dir, exist_ok=True)
    total = 0
    for fp in files:
        yks = YKS001.load(fp)
        ents = extract_dialogue(yks, args.encoding)
        if not ents: continue
        out = os.path.join(args.out_dir, os.path.splitext(os.path.basename(fp))[0] + '.json')
        with open(out, 'w', encoding='utf-8') as f:
            json.dump(ents, f, ensure_ascii=False, indent=2)
        total += len(ents)
        print(f"  {os.path.basename(fp)}: {len(ents)}条")
    print(f"[batch_e] {len(files)}文件 {total}条")

def do_batch_r(args):
    jsons = sorted(glob.glob(os.path.join(args.json_dir, '*.json')))
    os.makedirs(args.out_dir, exist_ok=True)
    for jf in jsons:
        base = os.path.splitext(os.path.basename(jf))[0]
        yp = os.path.join(args.yks_dir, base + '.yks')
        if not os.path.exists(yp): continue
        yks = YKS001.load(yp)
        with open(jf, 'r', encoding='utf-8') as f: ents = json.load(f)
        tr = {}
        for e in ents:
            mid = e.get('message_id'); msg = e.get('message')
            if mid is not None and msg is not None: tr[mid] = msg
            nid = e.get('name_id'); nm = e.get('name')
            if nid is not None and nm is not None: tr[nid] = nm
        if not tr: continue
        rebuild_s4(yks, tr, args.encoding)
        yks.save(os.path.join(args.out_dir, base + '.yks'), encrypt=args.encrypt)
        print(f"  {base}: {len(tr)}条")
    print("[batch_r] 完成")

def main():
    p = argparse.ArgumentParser(
        description='YKS001文本工具 (Yuka Engine)',
        usage='''yks_text.py <command> [args]

命令:
  extract   <input.yks> [output.json]              单文件提取
  inject    <orig.yks> <trans.json> [output.yks]    单文件导入
  batch_e   <yks_dir> <out_dir>                     批量提取
  batch_r   <yks_dir> <json_dir> <out_dir>          批量导入

选项:
  --encoding  读写编码 (默认cp932, 中文用gbk)
  --encrypt   输出XOR 0xAA加密 (封回YKC需要)
''')
    p.add_argument('command', choices=['extract', 'inject', 'batch_e', 'batch_r'])
    p.add_argument('args', nargs='*')
    p.add_argument('--encoding', default='cp932')
    p.add_argument('--encrypt', action='store_true')
    a = p.parse_args()

    class A: pass
    args = A()
    args.encoding = a.encoding
    args.encrypt = a.encrypt

    if a.command == 'extract':
        if len(a.args) < 1: p.error('extract需要: <input.yks> [output.json]')
        args.input = a.args[0]
        args.output = a.args[1] if len(a.args) > 1 else None
        do_extract(args)
    elif a.command == 'inject':
        if len(a.args) < 2: p.error('inject需要: <orig.yks> <trans.json> [output.yks]')
        args.input = a.args[0]
        args.trans = a.args[1]
        args.output = a.args[2] if len(a.args) > 2 else None
        do_inject(args)
    elif a.command == 'batch_e':
        if len(a.args) < 2: p.error('batch_e需要: <yks_dir> <out_dir>')
        args.yks_dir = a.args[0]
        args.out_dir = a.args[1]
        do_batch_e(args)
    elif a.command == 'batch_r':
        if len(a.args) < 3: p.error('batch_r需要: <yks_dir> <json_dir> <out_dir>')
        args.yks_dir = a.args[0]
        args.json_dir = a.args[1]
        args.out_dir = a.args[2]
        do_batch_r(args)

if __name__ == '__main__':
    main()
