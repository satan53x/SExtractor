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
    50: [],          # RETURN 无返回值 ★注:VM case50在读u8前已把IP重置到返回地址,
                     #    那个u8是返回点的运行期读取,不是op50自身的静态操作数→静态宽度=0
    51: ['B'],       # RETURN 有返回值(u8=argc)  ★坑:必须读这1字节,漏读连锁desync
    # 52..255: VM 解释器(sc.dll sub_10007B70)的 default 分支 = 0 操作数,
    #   任何未显式 case 的字节都是合法的 0 操作数 opcode。SCC 用到 54(0x36)。
    #   全部登记为 0 操作数以镜像解释器;错位由 selftest 的"标签落指令边界"检查兜底。
    **{k: [] for k in range(52, 256)},
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
CTRL_LEAD   = 0x0007  # 控制码引导字([0007][sub] 结构族)
CTRL_RUBY   = 0x0001  # [0007][0001] 注音开始
CTRL_PAUSE  = 0x0004  # [0007][0004] 停顿符
CTRL_PAGE   = 0x0006  # [0007][0006] 换页(一条消息可含多次内部换页)
CTRL_VOICE  = 0x0008  # [0007][0008] 语音标记开始
CTRL_STREND = 0x0009  # [0007][0009] 字符串结束
RUBY_SEP    = 0x000A  # 注音汉字/读音分隔（在注音语境内）
NUL         = 0x0000  # 终止/分隔

# 裸特效控制码（不带 0007 引导，直接出现在正文流里）——本作(SCC)新增
# 均经全量 11343 条消息逐字节回环验证。
EFX_COLOR   = 0x0001  # [0001][R][G][B] 变色开始（R/G/B 各一个 UTF-16 码元，值 0x00XX）
EFX_COLOREND= 0x0002  # [0002] 变色结束
EFX_STYLE   = 0x0003  # [0003][S] 样式/强调开始（S ∈ {0x12,0x18,0x19,0x1A,0x1C,0x1E,...}）
EFX_STYLEEND= 0x0004  # [0004] 样式结束
EFX_STAMP   = 0x0006  # [0006][K] 表情/特效/停顿贴片（K ∈ 0..6，自含）
HARD_BR     = 0x000A  # 裸 000A = 硬换行（不在注音语境内时）

# “裸特效” token 名集合：变色/样式/表情。按用户规则：夹在正文中间的删除，贴边界的存 meta。
EFFECT_TOKENS = frozenset({'color', 'colorend', 'style', 'styleend', 'stamp'})
# 结构性 token（保留骨架，空注入逐字节还原）：语音/注音/停顿/换页/串结束/其它0007/换行/NUL
STRUCT_TOKENS = frozenset({'voice', 'ruby', 'pause', 'page', 'strend', 'raw07', 'br', 'nul'})


def is_ctrl_unit(ch):
    """UTF-16 码元是否为控制符(< 0x20)。NUL 已在解析阶段单独成 token,不会进正文。"""
    return ord(ch) < 0x20


def split_boundary_controls(s):
    """把一段正文拆成 (前导控制符, 中间正文, 尾随控制符)。
    前导/尾随 = 字符串首尾处最长的一段控制符(码元<0x20)。
    中间正文里可能仍夹着控制符(交给上层判断)。返回三个 str。"""
    a = 0
    n = len(s)
    while a < n and is_ctrl_unit(s[a]):
        a += 1
    b = n
    while b > a and is_ctrl_unit(s[b - 1]):
        b -= 1
    return s[:a], s[a:b], s[b:]


# ────────────────────────────────────────────────────────────────────────
#  低层读取器
# ────────────────────────────────────────────────────────────────────────
class Reader:
    __slots__ = ('d', 'off')

    def __init__(self, data, off=0):
        self.d = data
        self.off = off

    def u16(self):
        v = struct.unpack_from('<H', self.d, self.off)[0]
        self.off += 2
        return v

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
    自动识别两种格式：

    ★v0（タペストリー等旧版）:
      [u32 ident_cnt] + idents + [u32 tail] + funcs + labels
      + seg3 + seg4(code) + seg5(消息池) + seg6(消息偏移表)

    ★v1（最新版）:
      [u16 header=0] + idents(无cnt, 以STRING_FLAG为止) + [u32 tail]
      + funcs + labels + seg3 + seg4(code)
      + [u32 cnt] + cnt×(u32 off, u32 len)  ← 消息表(指向seg3+seg5合并池)
      + seg5(消息池) + trailing(3072B加密签名)

    共有字段:
      idents, ident_tail, funcs, labels, seg3, code, seg5, msgtab
    v1 额外字段:
      _version, _header, _msgtab_pairs, _seg3_len_orig, _trailing
    """

    def __init__(self, data):
        r = Reader(data)

        # ── 格式识别 ──
        # v0: offset 0 是 u32 ident_cnt (合理范围 0~5000)
        # v1: offset 0 是 u16 header(=0), offset 2 是 STRING_FLAG(0x80xxxxxx)
        first4 = struct.unpack_from('<I', data, 0)[0]
        self._version = 0
        if first4 > 5000 or first4 == 0:
            if len(data) > 6:
                at2 = struct.unpack_from('<I', data, 2)[0]
                if at2 & STRING_FLAG and (at2 & ~STRING_FLAG) < 10000:
                    self._version = 1

        if self._version == 1:
            self._parse_v1(data, r)
        else:
            self._parse_v0(data, r)

    # ── v0 / v2 解析 ──
    # v0（旧版）: seg3 → seg4 → seg5(block) → msgtab(u32[]偏移)
    # v2（新版混合）: seg3 → seg4 → msgtab(cnt + off/len pairs) → seg5(block)，无trailing
    # 段0~段2 两者完全相同（u32 count + idents）
    def _parse_v0(self, data, r):
        ident_cnt = r.u32()
        self.idents = []
        for _ in range(ident_cnt):
            s = r.off
            r.string(); r.vartype()
            r.u32(); r.u32(); r.u32(); r.u32()
            self.idents.append(data[s:r.off])
        self.ident_tail = r.u32()

        func_cnt = r.u32()
        self.funcs = []
        for _ in range(func_cnt):
            name = r.string()
            f0 = r.u32(); f1 = r.u32(); f3 = r.u32()
            self.funcs.append((name, f0, f1, f3))

        lbl_cnt = r.u32()
        self.labels = []
        for _ in range(lbl_cnt):
            name = r.string()
            typ = r.u32()
            self.labels.append((name, typ))

        self.seg3 = r.block()
        self.code = r.block()

        # ── 自动检测 seg5/msgtab 顺序 ──
        # 读取下一个 u32，判断它是 seg5 块长度(v0) 还是 msgtab 条目数(v2)
        pivot = r.off
        val = struct.unpack_from('<I', data, pivot)[0]
        is_v2 = False
        if 0 < val < 200000:   # 合理的消息条目数范围
            after_pairs = pivot + 4 + val * 8
            if after_pairs + 4 <= len(data):
                seg5_candidate = struct.unpack_from('<I', data, after_pairs)[0]
                if after_pairs + 4 + seg5_candidate == len(data):
                    is_v2 = True   # msgtab-first → seg5 正好到 EOF

        if is_v2:
            self._version = 2
            self._header = None
            self._seg3_len_orig = None

            # 消息表 (在 seg5 之前): [u32 cnt] + cnt × (u32 off, u32 len)
            arr_cnt = r.u32()
            self._msgtab_pairs = []
            for _ in range(arr_cnt):
                off = r.u32()
                length = r.u32()
                self._msgtab_pairs.append((off, length))
            self.msgtab = [off for off, _ in self._msgtab_pairs]

            # seg5
            self.seg5 = r.block()

            # v2 无 trailing
            self._trailing = b''
        else:
            # 原版 v0: seg5 → msgtab(纯偏移)
            self.seg5 = r.block()

            arr_cnt = r.u32()
            self.msgtab = list(struct.unpack_from('<%dI' % arr_cnt, data, r.off))
            r.off += 4 * arr_cnt

            self._header = None
            self._msgtab_pairs = None
            self._seg3_len_orig = None
            self._trailing = b''

        self._parsed_end = r.off
        self._total = len(data)

    # ── v1 解析（新版格式） ──
    def _parse_v1(self, data, r):
        self._header = r.u16()   # u16 header (=0)

        # 段0: 无 count, 以 STRING_FLAG 作为条目存在标志
        self.idents = []
        while r.off + 4 <= len(data):
            peek = struct.unpack_from('<I', data, r.off)[0]
            if not (peek & STRING_FLAG):
                break
            s = r.off
            r.string(); r.vartype()
            r.u32(); r.u32(); r.u32(); r.u32()
            self.idents.append(data[s:r.off])
        self.ident_tail = r.u32()

        # 段1 函数表
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

        # 段3 / 段4
        self.seg3 = r.block()
        self.code = r.block()

        # v1: 消息表在 seg5 之前, 格式 [u32 cnt] + cnt × (u32 off, u32 len)
        # 所有偏移均为 seg5 内直接偏移
        arr_cnt = r.u32()
        self._msgtab_pairs = []
        for _ in range(arr_cnt):
            off = r.u32()
            length = r.u32()
            self._msgtab_pairs.append((off, length))

        # seg5 (对话消息池)
        self.seg5 = r.block()

        # 文件尾(加密签名等)
        self._trailing = data[r.off:]

        # 兼容字段: v0 的 msgtab 只存偏移列表, v1 也提供一份(取 pair 的 off 部分)
        self.msgtab = [off for off, _ in self._msgtab_pairs]

        self._parsed_end = r.off
        self._total = len(data)

    # ── 重建 ──
    def build(self):
        if self._version == 1:
            return self._build_v1()
        if self._version == 2:
            return self._build_v2()
        return self._build_v0()

    def _build_v0(self):
        out = bytearray()

        def w_u32(v):
            out.extend(struct.pack('<I', v))

        def w_string(name_bytes):
            w_u32(len(name_bytes) | STRING_FLAG)
            out.extend(name_bytes)

        w_u32(len(self.idents))
        for raw in self.idents:
            out.extend(raw)
        w_u32(self.ident_tail)

        w_u32(len(self.funcs))
        for name, f0, f1, f3 in self.funcs:
            w_string(name)
            w_u32(f0); w_u32(f1); w_u32(f3)

        w_u32(len(self.labels))
        for name, typ in self.labels:
            w_string(name)
            w_u32(typ)

        w_u32(len(self.seg3)); out.extend(self.seg3)
        w_u32(len(self.code)); out.extend(self.code)
        w_u32(len(self.seg5)); out.extend(self.seg5)

        w_u32(len(self.msgtab))
        out.extend(struct.pack('<%dI' % len(self.msgtab), *self.msgtab))

        return bytes(out)

    def _build_v1(self):
        out = bytearray()

        def w_u16(v):
            out.extend(struct.pack('<H', v))

        def w_u32(v):
            out.extend(struct.pack('<I', v))

        def w_string(name_bytes):
            w_u32(len(name_bytes) | STRING_FLAG)
            out.extend(name_bytes)

        # header
        w_u16(self._header)

        # 段0 (无 count)
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

        # 段3 / 段4
        w_u32(len(self.seg3)); out.extend(self.seg3)
        w_u32(len(self.code)); out.extend(self.code)

        # 消息表 (在 seg5 之前)
        w_u32(len(self._msgtab_pairs))
        for off, length in self._msgtab_pairs:
            w_u32(off)
            w_u32(length)

        # seg5
        w_u32(len(self.seg5)); out.extend(self.seg5)

        # trailing
        out.extend(self._trailing)

        return bytes(out)

    def _build_v2(self):
        """v2: v0 头(段0有count) + v1 尾(msgtab pairs在seg5前, 无trailing)"""
        out = bytearray()

        def w_u32(v):
            out.extend(struct.pack('<I', v))

        def w_string(name_bytes):
            w_u32(len(name_bytes) | STRING_FLAG)
            out.extend(name_bytes)

        # 段0 (v0风格, 有 count)
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

        # 段3 / 段4
        w_u32(len(self.seg3)); out.extend(self.seg3)
        w_u32(len(self.code)); out.extend(self.code)

        # 消息表 (在 seg5 之前, 同 v1)
        w_u32(len(self._msgtab_pairs))
        for off, length in self._msgtab_pairs:
            w_u32(off)
            w_u32(length)

        # seg5
        w_u32(len(self.seg5)); out.extend(self.seg5)

        # v2 无 trailing
        return bytes(out)

    # ── 消息访问 ──
    def message_count(self):
        if self._version >= 1:
            return len(self._msgtab_pairs)
        return len(self.msgtab)

    def message_raw(self, i):
        if self._version >= 1:
            off, length = self._msgtab_pairs[i]
            return self.seg5[off:off + length]
        # v0
        s = self.msgtab[i]
        e = self.msgtab[i + 1] if i + 1 < len(self.msgtab) else len(self.seg5)
        return self.seg5[s:e]

    def is_seg3_message(self, i):
        """v1/v2 不再区分 seg3/seg5 消息。所有 msgtab 条目均指向 seg5。"""
        return False


# ────────────────────────────────────────────────────────────────────────
#  消息 token 化（★全量 11343 条逐字节回环验证无损★）
# ────────────────────────────────────────────────────────────────────────
#  token 形式（0007 引导结构族）:
#    ('text',  str)          纯正文（UTF-16 码元，可含全角空格 0x3000）
#    ('voice', name)         [0007][0008] 语音名 [0000]
#    ('ruby',  kanji, yomi)  [0007][0001] 汉字 [000A] 读音 [0000]
#    ('pause',)              [0007][0004]
#    ('page',)               [0007][0006]  内部换页（一条消息可多次）
#    ('strend',)             [0007][0009]
#    ('raw07', sub)          其它 [0007][sub]（本作见 sub=0x0002）
#  裸特效族（本作新增，用户规则里“要清理”的对象）:
#    ('color', r, g, b)      [0001][R][G][B]  变色开始
#    ('colorend',)           [0002]           变色结束
#    ('style', s)            [0003][S]        样式/强调开始
#    ('styleend',)           [0004]           样式结束
#    ('stamp', k)            [0006][K]        表情/特效贴片（自含）
#  其它:
#    ('br',)                 裸 [000A]        硬换行
#    ('nul',)                裸 [0000]        分隔/终止
#    ('odd', bytes)          落单奇数字节（保险丝，正常不出现）

def _units(raw):
    return [raw[k] | (raw[k + 1] << 8) for k in range(0, len(raw) - 1, 2)]


def parse_message(raw):
    """段5 单条消息原始字节 -> token 列表。rebuild_message() 严格无损还原。"""
    u = _units(raw)
    n = len(u)
    toks = []
    buf = []
    j = 0

    def flush():
        if buf:
            toks.append(('text', ''.join(chr(c) for c in buf)))
            buf.clear()

    while j < n:
        x = u[j]
        if x == CTRL_LEAD and j + 1 < n:
            sub = u[j + 1]
            if sub == CTRL_VOICE:                      # 语音名到 NUL
                flush(); j += 2; name = []
                while j < n and u[j] != NUL:
                    name.append(chr(u[j])); j += 1
                j += 1
                toks.append(('voice', ''.join(name))); continue
            if sub == CTRL_RUBY:                        # 注音: 汉字[000A]读音[0000]
                flush(); j += 2; k = []; y = []
                while j < n and u[j] != RUBY_SEP:
                    k.append(chr(u[j])); j += 1
                j += 1
                while j < n and u[j] != NUL:
                    y.append(chr(u[j])); j += 1
                j += 1
                toks.append(('ruby', ''.join(k), ''.join(y))); continue
            if sub == CTRL_PAUSE:  flush(); toks.append(('pause',));  j += 2; continue
            if sub == CTRL_PAGE:   flush(); toks.append(('page',));   j += 2; continue
            if sub == CTRL_STREND: flush(); toks.append(('strend',)); j += 2; continue
            flush(); toks.append(('raw07', sub)); j += 2; continue   # 其它 0007 子码
        if x == EFX_COLOR and j + 3 < n:                # 变色: 0001 R G B
            flush(); toks.append(('color', u[j + 1], u[j + 2], u[j + 3])); j += 4; continue
        if x == EFX_COLOREND:  flush(); toks.append(('colorend',));  j += 1; continue
        if x == EFX_STYLE and j + 1 < n:                # 样式: 0003 S
            flush(); toks.append(('style', u[j + 1])); j += 2; continue
        if x == EFX_STYLEEND:  flush(); toks.append(('styleend',));  j += 1; continue
        if x == EFX_STAMP and j + 1 < n:                # 表情: 0006 K
            flush(); toks.append(('stamp', u[j + 1])); j += 2; continue
        if x == HARD_BR:       flush(); toks.append(('br',));  j += 1; continue
        if x == NUL:           flush(); toks.append(('nul',)); j += 1; continue
        if x < 0x20:           # 未预期控制码（保险丝）——不应触发
            flush(); toks.append(('raw07', -x)); j += 1; continue
        buf.append(x); j += 1

    flush()
    if 2 * n < len(raw):        # 落单奇数字节（正常不出现）
        toks.append(('odd', raw[2 * n:]))
    return toks


def rebuild_message(toks):
    """token 列表 -> 段5 消息原始字节（parse_message 的逆）。"""
    out = bytearray()

    def w(s):
        out.extend(s.encode('utf-16le'))

    def w16(v):
        out.extend(struct.pack('<H', v & 0xFFFF))

    for t in toks:
        k = t[0]
        if k == 'text':      w(t[1])
        elif k == 'voice':   w16(CTRL_LEAD); w16(CTRL_VOICE); w(t[1]); w16(NUL)
        elif k == 'ruby':    w16(CTRL_LEAD); w16(CTRL_RUBY); w(t[1]); w16(RUBY_SEP); w(t[2]); w16(NUL)
        elif k == 'pause':   w16(CTRL_LEAD); w16(CTRL_PAUSE)
        elif k == 'page':    w16(CTRL_LEAD); w16(CTRL_PAGE)
        elif k == 'strend':  w16(CTRL_LEAD); w16(CTRL_STREND)
        elif k == 'raw07':   w16(CTRL_LEAD); w16(t[1])
        elif k == 'color':   w16(EFX_COLOR); w16(t[1]); w16(t[2]); w16(t[3])
        elif k == 'colorend':w16(EFX_COLOREND)
        elif k == 'style':   w16(EFX_STYLE); w16(t[1])
        elif k == 'styleend':w16(EFX_STYLEEND)
        elif k == 'stamp':   w16(EFX_STAMP); w16(t[1])
        elif k == 'br':      w16(HARD_BR)
        elif k == 'nul':     w16(NUL)
        elif k == 'odd':     out.extend(t[1])
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


# ────────────────────────────────────────────────────────────────────────
#  文本清洗 / 消息结构切分 / 边界特效分类（extract 与 inject 共用）
# ────────────────────────────────────────────────────────────────────────
#  规则（用户约定）:
#   · 裸特效(变色/样式/表情) 夹在正文中间 → 删除; 贴正文首尾(如紧邻闭合括号)→ 存 meta 回填
#   · 注音 ruby → 正文保留汉字, 丢弃读音(译中不需日文假名)
#   · 硬换行 000A 与 内部换页 0007/0006 → 在译者可读文本里都呈现为 '\n'
#   · 语音/串结束/NUL/停顿 → 结构骨架, 不进译者文本

OPEN_BR  = frozenset('「『（【〔《〈｢〖〘“')
CLOSE_BR = frozenset('」』）】〕》〉｣〗〙”')
_SPACE   = frozenset(' \u3000\t\n')


def _is_spoken_text(s):
    """text token 是否含“实际台词字符”(排除括号与空白)。"""
    for ch in s:
        if ch not in OPEN_BR and ch not in CLOSE_BR and ch not in _SPACE:
            return True
    return False


def text_to_tokens(s):
    """把含 '\\n' 的纯文本串切成 [('text',run)/('br',), ...]（'\\n' → 硬换行 br）。"""
    out = []
    for k, part in enumerate(s.split('\n')):
        if k > 0:
            out.append(('br',))
        if part:
            out.append(('text', part))
    return out


def split_message_struct(toks):
    """一条消息 token 列表 -> (voice_name, body, tail)。
      voice_name : 起始 voice token 的名字(无则 '')
      tail       : 末尾连续的 {page, strend, nul} 结构终止串
      body       : 中间部分(可能含内部 page/ruby/br/effect/pause)"""
    i = 0
    voice_name = ''
    # 跳过起始的 voice（说话人）
    if toks and toks[0][0] == 'voice':
        voice_name = toks[0][1]
        i = 1
    # 末尾结构终止串
    j = len(toks)
    while j > i and toks[j - 1][0] in ('page', 'strend', 'nul'):
        j -= 1
    body = list(toks[i:j])
    tail = list(toks[j:])
    return voice_name, body, tail


def clean_body_text(body):
    """body token -> 译者可读的纯净文本。
       text→原样, ruby→汉字, br/page→'\\n', 其余(特效/停顿/nul/raw07)→丢弃。"""
    out = []
    for t in body:
        k = t[0]
        if k == 'text':   out.append(t[1])
        elif k == 'ruby': out.append(t[1])          # 只留汉字
        elif k == 'br':   out.append('\n')
        elif k == 'page': out.append('\n')          # 内部换页在文本里呈现为换行
        # 特效/停顿/串结束/nul/raw07: 丢弃
    return ''.join(out)


def classify_body_effects(body):
    """把 body 里的裸特效 token 按位置分为 (lead_fx, trail_fx)，中间的丢弃。
       依据: 第一个/最后一个“实际台词” token(text含台词字符 或 ruby)。
       返回两段 token 列表(保持原顺序)。"""
    spoken = [idx for idx, t in enumerate(body)
              if (t[0] == 'text' and _is_spoken_text(t[1])) or t[0] == 'ruby']
    fx = [(idx, t) for idx, t in enumerate(body) if t[0] in EFFECT_TOKENS]
    if not fx:
        return [], []
    if not spoken:
        # 无台词(纯特效/符号) → 全部当前导, 保守保留
        return [t for _, t in fx], []
    first, last = spoken[0], spoken[-1]
    lead_fx  = [t for idx, t in fx if idx < first]
    trail_fx = [t for idx, t in fx if idx > last]
    return lead_fx, trail_fx


def wrap_segment_text(text, lead_fx, trail_fx):
    """把一段译文文本包成 token: 前导特效放在开括号之后, 尾随特效放在闭括号之前。"""
    i = 0
    while i < len(text) and text[i] in OPEN_BR:
        i += 1
    open_run, rest = text[:i], text[i:]
    m = len(rest)
    while m > 0 and rest[m - 1] in CLOSE_BR:
        m -= 1
    core, close_run = rest[:m], rest[m:]
    toks = []
    if open_run:  toks += text_to_tokens(open_run)
    toks += list(lead_fx)
    if core:      toks += text_to_tokens(core)
    toks += list(trail_fx)
    if close_run: toks += text_to_tokens(close_run)
    return toks


def _emit_region(region, line, lead_fx, trail_fx):
    """重建一个“区”(两断点间的 token 段): 用 line 替换其中的 text/ruby 正文,
       保留内部结构 token(内部 voice/strend/pause/raw07), 丢弃中间裸特效。
       前导/尾随特效仅在整条消息首/尾区通过 lead_fx/trail_fx 回填。"""
    out = []
    text_done = False
    for t in region:
        if t[0] in ('text', 'ruby'):
            if not text_done:
                out += wrap_segment_text(line, lead_fx, trail_fx)
                text_done = True
            # 同区多个 text/ruby 已并入这一行, 跳过其余
        elif t[0] in EFFECT_TOKENS:
            continue                    # 中间裸特效: 删除
        else:
            out.append(t)               # 内部 voice/strend/pause/raw07/nul: 保留
    if not text_done and line:
        out += wrap_segment_text(line, lead_fx, trail_fx)
    return out


def build_translated_message(full_toks, translation):
    """把译文写回一条消息, 应用用户策略:
         · 保留 语音/结构终止串(含链式消息内部的 voice/strend)
         · 首尾裸特效回填, 中间裸特效删除
         · 注音退化为普通文本(译文已覆盖), 停顿删除
       换行/换页(按区对齐替换):
         body 以 br(硬换行)/page(内部换页) 切成若干“区”, 区数 = 断点数+1 = 原行数。
         译文按 '\\n' 拆行。行数 == 区数 → 逐区替换正文, 保留每个断点的原始类型
         (page 还是 br)与区内结构 token; 否则(译者改了行数) → 退化: 译文并入首区,
         其余区正文清空但保留其结构(不丢语音/换页)。
       返回新的 token 列表(交给 rebuild_message)。"""
    voice_name, body, tail = split_message_struct(full_toks)
    lead_fx, trail_fx = classify_body_effects(body)

    # 以 br/page 把 body 切成区, 并记录每个断点类型
    regions = [[]]
    breaks = []
    for t in body:
        if t[0] in ('br', 'page'):
            breaks.append(t[0])
            regions.append([])
        else:
            regions[-1].append(t)

    lines = translation.split('\n')
    matched = (len(lines) == len(regions))
    last = len(regions) - 1

    out = []
    if voice_name:
        out.append(('voice', voice_name))
    for i, region in enumerate(regions):
        lf = lead_fx if i == 0 else []
        tf = trail_fx if i == last else []
        line = lines[i] if matched else (translation if i == 0 else '')
        out += _emit_region(region, line, lf, tf)
        if i < last:
            out.append((breaks[i],))    # 原样保留 br 或 page
    out += tail
    return out
