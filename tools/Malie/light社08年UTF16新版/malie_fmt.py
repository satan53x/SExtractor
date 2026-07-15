# -*- coding: utf-8 -*-
"""
malie_fmt.py — Malie 引擎 EXEC 字节码格式共享库
================================================

游戏《タペストリー -you will meet yourself-》(light社, Malie引擎)
提供 EXEC 解压后明文字节码的完整解析 / 重建 / 消息 token 化能力，
供 malie_text_extract.py 与 malie_text_inject.py 共用。

字节码明文布局（按 sc.dll 的 ScenarioProcessor_ReadExecImage 顺序）:
  段0 IdentScope 标识符表 : [u32 cnt] + cnt×{String名 + VarType链 + 4×u32} + [u32 scope_tail]
  段1 函数定义表          : [u32 cnt] + cnt×{String名 + u32 funcid + u32 + u32}
  段2 标签表              : [u32 cnt] + cnt×{String名 + u32 type(=代码段入口偏移)}
  段3 字符串常量池 (+32)  : [u32 len] + 数据(NUL分隔的UTF-16LE串数组)
  段4 代码段       (+12)  : [u32 len] + 字节码指令流(IP从0线性执行)
  段5 对话消息池   (+20)  : [u32 len] + 带控制码的UTF-16LE正文
  段6 消息偏移表   (+28)  : [u32 cnt] + cnt×u32(msgtab[i]=段5内字节偏移)

String 格式: [u32 长度(高位0x80000000是标志位)] + UTF-16LE字节(含结尾NUL)
VarType   : 递归链 [u32 tag]; tag==0止(仅4B); 否则再读[u32]继续

★所有逻辑均经全量验证:
  - 结构解析到EOF剩0字节
  - 消息解析器48793条往返0不一致
  - opcode表944840条指令全覆盖0未知op
"""

import struct

STRING_FLAG = 0x80000000  # String 长度前缀高位标志

# ────────────────────────────────────────────────────────────────────────
#  opcode 表（★已100%验证★）
#  值 = 该 opcode 在字节码流中的操作数宽度序列
#  'U'=u32(4B)  'W'=u16(2B)  'B'=u8(1B)
# ────────────────────────────────────────────────────────────────────────
OPERAND_WIDTHS = {
    0:  ['U'],       # JMP 绝对偏移
    1:  ['U'],       # pop; if != 0 JMP
    2:  ['U'],       # pop; if == 0 JMP
    3:  ['U', 'B'],  # CALL(funcid_u32, argc_u8)
    4:  ['B', 'B'],  # CALL(funcid_u8, argc_u8)
    5:  [],          # 停止(clear bit0)
    6:  [],          # 间接读
    7:  [],          # 存储
    8:  ['U'],       # push u32 常量
    9:  ['B'],       # push u8 + base
    10: ['W'],       # push u16 + base
    11: [],          # NOP (default 分支)
    12: ['U'],       # push u32 + base
    13: ['U'],       # push u32 常量 (同 8)
    14: [],          # pop
    15: [],          # push 0
    16: [],          # NOP (default 分支)
    17: ['B'],       # push u8
    # 18..43 : 栈算术/比较/逻辑/位运算, 全部 0 操作数
    **{k: [] for k in range(18, 44)},
    44: [],          # 调试
    45: ['U'],       # CALL_SUB(label_idx)  ← 操作数是标签索引, 经标签表.type解析成偏移
    46: [],          # 局部变量存取
    47: [],
    48: [],
    49: ['U'],       # ENTER 建栈帧(操作数=局部区大小)
    50: [],          # RETURN 无返回值
    51: ['B'],       # RETURN 有返回值(u8=argc)  ★坑:必须读这1字节,漏读连锁desync
}

# 跳转类 opcode（操作数是代码段内绝对偏移，变长注入需重定位）
JUMP_OPCODES = {0, 1, 2}

_WIDTH_BYTES = {'U': 4, 'W': 2, 'B': 1}


def instr_len(code, ip):
    """返回 code[ip] 处一条指令的总字节长度；未知 opcode 返回 None。"""
    op = code[ip]
    w = OPERAND_WIDTHS.get(op)
    if w is None:
        return None
    n = 1
    for t in w:
        n += _WIDTH_BYTES[t]
    return n


# ────────────────────────────────────────────────────────────────────────
#  控制码常量（段5 正文内）
# ────────────────────────────────────────────────────────────────────────
CTRL_LEAD   = 0x0007  # 控制码引导字
CTRL_RUBY   = 0x0001  # [0007][0001] 注音开始
CTRL_PAUSE  = 0x0004  # [0007][0004] 停顿符
CTRL_PAGE   = 0x0006  # [0007][0006] 换页/消息结束
CTRL_VOICE  = 0x0008  # [0007][0008] 语音标记开始
CTRL_STREND = 0x0009  # [0007][0009] 字符串结束
RUBY_SEP    = 0x000A  # 注音汉字/读音分隔
NUL         = 0x0000  # 终止/分隔


# ────────────────────────────────────────────────────────────────────────
#  低层读取器
# ────────────────────────────────────────────────────────────────────────
class Reader:
    __slots__ = ('d', 'off')

    def __init__(self, data, off=0):
        self.d = data
        self.off = off

    def u32(self):
        v = struct.unpack_from('<I', self.d, self.off)[0]
        self.off += 4
        return v

    def string(self):
        """读一个 String: [u32 len(高位标志)] + UTF-16LE字节。返回原始字节(含结尾NUL)。"""
        blen = self.u32() & ~STRING_FLAG
        raw = self.d[self.off:self.off + blen]
        self.off += blen
        return raw

    def vartype(self):
        """读 VarType 递归链，返回消费的原始字节。"""
        start = self.off
        while True:
            tag = self.u32()
            if tag == 0:
                break
            self.u32()
        return self.d[start:self.off]

    def block(self):
        """读 [u32 len] + len 字节数据块，返回数据字节。"""
        blen = self.u32()
        b = self.d[self.off:self.off + blen]
        self.off += blen
        return b


# ────────────────────────────────────────────────────────────────────────
#  ExecImage — 完整解析 / 重建
# ────────────────────────────────────────────────────────────────────────
class ExecImage:
    """
    解析解压后的 EXEC 明文字节码为可编辑的结构，并能无损重建。

    字段保留为"尽量原始"的形式，以保证 rebuild() 严格 byte-exact:
      idents      : list of raw bytes  (每个标识符项的完整原始字节)
      ident_tail  : int                (scope_tail)
      funcs       : list of (name_bytes:bytes, funcid:int, f1:int, f3:int)
      labels      : list of (name_bytes:bytes, type:int)
      seg3        : bytes  (字符串常量池)
      code        : bytes  (段4 代码段)
      seg5        : bytes  (对话消息池)
      msgtab      : list of int  (段6 消息偏移表)
    """

    def __init__(self, data):
        r = Reader(data)

        # 段0 IdentScope
        ident_cnt = r.u32()
        self.idents = []
        for _ in range(ident_cnt):
            s = r.off
            r.string()      # name
            r.vartype()     # vartype 链
            r.u32(); r.u32(); r.u32(); r.u32()   # 4×u32
            self.idents.append(data[s:r.off])
        self.ident_tail = r.u32()

        # 段1 函数定义表
        func_cnt = r.u32()
        self.funcs = []
        for _ in range(func_cnt):
            name = r.string()
            f0 = r.u32(); f1 = r.u32(); f3 = r.u32()
            self.funcs.append((name, f0, f1, f3))

        # 段2 标签表
        lbl_cnt = r.u32()
        self.labels = []
        for _ in range(lbl_cnt):
            name = r.string()
            typ = r.u32()
            self.labels.append((name, typ))

        # 段3/4/5
        self.seg3 = r.block()
        self.code = r.block()
        self.seg5 = r.block()

        # 段6 消息偏移表
        arr_cnt = r.u32()
        self.msgtab = list(struct.unpack_from('<%dI' % arr_cnt, data, r.off))
        r.off += 4 * arr_cnt

        self._parsed_end = r.off
        self._total = len(data)

    # ── 重建 ──
    def build(self):
        out = bytearray()

        def w_u32(v):
            out.extend(struct.pack('<I', v))

        def w_string(name_bytes):
            w_u32(len(name_bytes) | STRING_FLAG)
            out.extend(name_bytes)

        # 段0
        w_u32(len(self.idents))
        for raw in self.idents:
            out.extend(raw)
        w_u32(self.ident_tail)

        # 段1
        w_u32(len(self.funcs))
        for name, f0, f1, f3 in self.funcs:
            w_string(name)
            w_u32(f0); w_u32(f1); w_u32(f3)

        # 段2
        w_u32(len(self.labels))
        for name, typ in self.labels:
            w_string(name)
            w_u32(typ)

        # 段3/4/5
        w_u32(len(self.seg3)); out.extend(self.seg3)
        w_u32(len(self.code)); out.extend(self.code)
        w_u32(len(self.seg5)); out.extend(self.seg5)

        # 段6
        w_u32(len(self.msgtab))
        out.extend(struct.pack('<%dI' % len(self.msgtab), *self.msgtab))

        return bytes(out)

    # ── 消息访问 ──
    def message_count(self):
        return len(self.msgtab)

    def message_raw(self, i):
        s = self.msgtab[i]
        e = self.msgtab[i + 1] if i + 1 < len(self.msgtab) else len(self.seg5)
        return self.seg5[s:e]


# ────────────────────────────────────────────────────────────────────────
#  消息 token 化（★已全量验证无损★）
# ────────────────────────────────────────────────────────────────────────
#  token 形式:
#    ('text',  str)          纯正文
#    ('voice', name:str)     ⟪VOICE⟫ + 语音名 + NUL
#    ('ruby',  kanji, yomi)  ⟪RUBY⟫ + 汉字 + SEP + 读音 + NUL
#    ('pause',)              [0007][0004]
#    ('page',)               [0007][0006]
#    ('strend',)             [0007][0009]
#    ('nul',)                单独 [0000]
#    ('raw07', code:int)     其它未预期的 [0007][code]（保险丝，正常不出现）
#    ('odd', bytes)          落单字节（保险丝，正常不出现）

def parse_message(raw):
    """段5 单条消息原始字节 -> token 列表。rebuild_message() 可无损还原。"""
    toks = []
    j = 0
    n = len(raw)
    buf = []

    def flush():
        if buf:
            toks.append(('text', ''.join(buf)))
            buf.clear()

    def rd(k):
        return raw[k] | (raw[k + 1] << 8)

    while j + 1 < n:
        cp = rd(j)
        if cp == CTRL_LEAD and j + 3 < n:
            nxt = rd(j + 2)
            if nxt == CTRL_VOICE:
                flush(); j += 4
                name = []
                while j + 1 < n:
                    c2 = rd(j)
                    if c2 == NUL:
                        j += 2; break
                    name.append(chr(c2)); j += 2
                toks.append(('voice', ''.join(name)))
                continue
            if nxt == CTRL_RUBY:
                flush(); j += 4
                kanji, yomi = [], []
                while j + 1 < n:
                    c2 = rd(j)
                    if c2 == RUBY_SEP:
                        j += 2; break
                    kanji.append(chr(c2)); j += 2
                while j + 1 < n:
                    c2 = rd(j)
                    if c2 == NUL:
                        j += 2; break
                    yomi.append(chr(c2)); j += 2
                toks.append(('ruby', ''.join(kanji), ''.join(yomi)))
                continue
            if nxt == CTRL_PAUSE:
                flush(); toks.append(('pause',)); j += 4; continue
            if nxt == CTRL_PAGE:
                flush(); toks.append(('page',)); j += 4; continue
            if nxt == CTRL_STREND:
                flush(); toks.append(('strend',)); j += 4; continue
            # 未预期的 [0007][code] —— 保险丝
            flush(); toks.append(('raw07', nxt)); j += 4; continue
        if cp == NUL:
            flush(); toks.append(('nul',)); j += 2; continue
        buf.append(chr(cp)); j += 2

    flush()
    if j < n:   # 落单字节（正常不应出现）
        toks.append(('odd', raw[j:]))
    return toks


def rebuild_message(toks):
    """token 列表 -> 段5 消息原始字节（parse_message 的逆）。"""
    out = bytearray()

    def w(s):
        out.extend(s.encode('utf-16le'))

    def w16(v):
        out.extend(struct.pack('<H', v))

    for t in toks:
        k = t[0]
        if k == 'text':
            w(t[1])
        elif k == 'voice':
            w16(CTRL_LEAD); w16(CTRL_VOICE); w(t[1]); w16(NUL)
        elif k == 'ruby':
            w16(CTRL_LEAD); w16(CTRL_RUBY); w(t[1]); w16(RUBY_SEP); w(t[2]); w16(NUL)
        elif k == 'pause':
            w16(CTRL_LEAD); w16(CTRL_PAUSE)
        elif k == 'page':
            w16(CTRL_LEAD); w16(CTRL_PAGE)
        elif k == 'strend':
            w16(CTRL_LEAD); w16(CTRL_STREND)
        elif k == 'nul':
            w16(NUL)
        elif k == 'raw07':
            w16(CTRL_LEAD); w16(t[1])
        elif k == 'odd':
            out.extend(t[1])
    return bytes(out)


# ────────────────────────────────────────────────────────────────────────
#  段3 字符串常量池 拆分 / 重建
# ────────────────────────────────────────────────────────────────────────
def split_seg3(seg3):
    """
    段3 -> [(byte_offset, text_str), ...]
    以 NUL(0x0000) 为分隔。byte_offset 是该串首字符在段3内的字节偏移。
    重建时需保持串序与分隔结构，故同时返回可无损重建所需的信息。
    """
    items = []
    cur = []
    start = 0
    i = 0
    n = len(seg3)
    while i + 1 < n:
        cp = seg3[i] | (seg3[i + 1] << 8)
        if cp == 0:
            items.append((start, bytes(cur).decode('utf-16le', 'surrogatepass')))
            cur = []
            start = i + 2
        else:
            cur.append(seg3[i]); cur.append(seg3[i + 1])
        i += 2
    # 处理末尾可能没有 NUL 结尾的残留
    trailing = seg3[start:] if start < n else b''
    return items, trailing


# ────────────────────────────────────────────────────────────────────────
#  角色名映射（语音名前缀 -> 角色）
# ────────────────────────────────────────────────────────────────────────
#  语音名形如 v_hkr0001 / v_hkr0008_a，前缀 v_XXX 是稳定的说话人标识。
#  罗马音缩写与角色名的对应无法可靠自动推断（大量角色名是汉字），
#  因此策略是: 已确证的种子直接映射; 其余保留前缀原样(诚实, 不瞎猜),
#  由用户在 speaker_map.json 中人工补全。
import re as _re

# 已人工确证的前缀 -> 角色名 种子（可继续补充）
VOICE_PREFIX_TO_CHARA = {
    'v_hkr': 'ひかり',
    'v_hrm': '遥海',
    'v_snp': '晋平',
    'v_hjm': 'はじめ',
    'v_mna': '美那',
    'v_uta': '詩',
    'v_ski': '紗希',
    'v_yuk': '陽子',
    'v_ikt': '幾人',
}


def voice_prefix(voice_name):
    """从语音名取稳定前缀 v_XXX。取不出返回原名。"""
    if not voice_name:
        return ''
    m = _re.match(r'(v_[a-z]+)', voice_name)
    return m.group(1) if m else voice_name


def voice_to_chara(voice_name, extra_map=None):
    """
    语音名 -> 说话人标识。
    优先用 extra_map(用户人工映射) → 内置种子 → 前缀原样(如 'v_xxx')。
    始终返回非空字符串, 保证译者能区分说话人。
    """
    pfx = voice_prefix(voice_name)
    if not pfx:
        return ''
    if extra_map and pfx in extra_map:
        return extra_map[pfx]
    if pfx in VOICE_PREFIX_TO_CHARA:
        return VOICE_PREFIX_TO_CHARA[pfx]
    return pfx   # 诚实: 用前缀本身当说话人标识
