# -*- coding: utf-8 -*-
"""
nexas_common.py - NeXAS / 真剣演舞 引擎脚本通用解析模块

文件格式（融合开源工具的语义理解 + 自家结构分析）:
    [u32  magic]                     = 0x11D3 (剧本) / 0x11E7 (system.bin)
                                       同时也作为 extras_count
    [extras  magic × (u32 op, u32 arg)]
                                       开源工具叫 EXTRA，含 reserved 8B + 变量声明区
                                       第 0 项是 (0, 0) 占位
    [u32  commands_count]            (= 我之前称的 n2)
    [commands_raw  count × (u32 op, u32 arg)]
                                       op=0 不是独立指令，而是参数前缀，arg
                                       累积到下一个非 0 op 的 prefix 数组
    [u32  strings_count]
    [strings  count × cp932 NUL-terminated]
                                       第 1 个通常是空字符串
    [trailer  bytes]                 字符串区之后到文件末尾，含变量名表等
                                       注入时原样保留 (= 开源工具的 .dat0)

每条 entry 都是固定 8B = (op_u32, arg_u32)。
跳转目标用原始 entry index (含 op=0)，不是 byte offset。
"""

import struct
import re


# ============================================================
# Opcode 助记符表（融合开源工具）
# ============================================================
OP_MNEMONIC = {
    # 注: op=0 不出现在折叠后流中，是 prefix 累积器
    0x04: 'CMD.04',          # 复合指令的一部分（CASE4 / LOAD_CUSTOM_TEXT / SET_EFFECT）
    0x05: 'CMD.05',          # LOAD_STRING (data=1) / PUSH (其他)
    0x06: 'CMD.06',          # LOAD_CUSTOM_TEXT / SET_EFFECT 触发的一部分
    0x07: 'FUNC',            # 函数调用 (data 是函数 ID)
    0x09: 'CMD.09',          # PUSH_CUSTOM_TEXT (data=1 时)
    0x0E: 'CMD.0E',          # SPECIAL_TEXT (data 末字节=0x80 时)
    0x10: 'CMPR0',
    0x15: 'CMPR5',
    0x17: 'CMPR7',
    0x18: 'CMPR8',           # 也叫 CMPR
    0x1A: 'CMPRA',
    0x1B: 'INIT',
    0x1C: 'DEINIT',
    0x1D: 'INF1',
    0x2C: 'INF2',
    0x3F: 'LABEL',           # 我自己识别的（开源工具未命名，但实测是跳转目标）
    0x40: 'JMP',             # 我自己识别的（开源工具未命名）
    0x41: 'JNGE',            # jump if not greater-equal
    0x42: 'JNLE',            # jump if not less-equal
}

# FUNC 命名表（来自开源工具）
FUNC_NAMES = {
    0x8035:   'GOTO_NEXT_SCENE',
    0x18036:  'REGISTER_SCENE',
    0x20005:  'WAIT',
    0x4006F:  'PUSH_MESSAGE',
    0x2009A:  'BG_FADE',
    0x8803E:  'BG_PUSH',
    0x301C2:  'VOICE_FADE',
    0x2014F:  'TEX_CLEAR',
    0x60165:  'TEX_FADE',
    0x90143:  'TEX_PUSH',
    0x501B2:  'BGM_PLAY',
    0x501BF:  'SE_PLAY',
    0x601C0:  'SYSTEM_VOICE_PLAY',
}


# ============================================================
# 解析
# ============================================================

class ParseError(Exception):
    pass


def parse_script(data):
    """
    解析 NeXAS 脚本 bytes，返回完整结构。
    返回 dict:
      magic        : u32
      extras       : [(u32 op, u32 arg), ...]    长度 = magic
      commands     : [(orig_idx, op, arg, [prefix...]), ...]
                       折叠后非 op=0 指令列表
                       orig_idx 是该指令在原始 entry 数组中的位置
      raw_commands : [(op, arg), ...]            原始未折叠
      strings      : [str, ...]                  cp932 解码
      strings_raw  : [bytes, ...]                原始字节（注入时直接用）
      trailer      : bytes                       字符串区之后到末尾
      commands_offset : int                      commands 原始 entry 起始 byte offset
    """
    if len(data) < 4:
        raise ParseError(f"文件太小 ({len(data)} bytes)")

    magic = struct.unpack_from('<I', data, 0)[0]
    if magic < 0x100 or magic > 0xFFFF:
        raise ParseError(f"magic=0x{magic:X} 不像有效的 NeXAS 脚本")

    pos = 4
    # extras
    extras_byte_size = magic * 8
    if pos + extras_byte_size + 4 > len(data):
        raise ParseError(f"extras 越界 (magic={magic}, len={len(data)})")
    extras = []
    for _ in range(magic):
        op, arg = struct.unpack_from('<2I', data, pos)
        extras.append((op, arg))
        pos += 8

    # commands_count
    cmd_count = struct.unpack_from('<I', data, pos)[0]
    pos += 4
    cmd_start = pos
    if pos + cmd_count * 8 + 4 > len(data):
        raise ParseError(f"commands 越界 (cmd_count={cmd_count})")

    # 读 commands raw + 折叠
    raw_commands = []
    folded = []
    pending_prefix = []
    for orig_idx in range(cmd_count):
        op, arg = struct.unpack_from('<2I', data, pos)
        pos += 8
        raw_commands.append((op, arg))
        if op == 0:
            pending_prefix.append(arg)
        else:
            folded.append((orig_idx, op, arg, pending_prefix))
            pending_prefix = []
    if pending_prefix:
        # 末尾遗留的前缀（少见但合理保留）
        folded.append((cmd_count, 0, 0, pending_prefix))

    # strings
    str_count = struct.unpack_from('<I', data, pos)[0]
    pos += 4
    strings = []
    strings_raw = []
    for _ in range(str_count):
        nul = data.find(b'\x00', pos)
        if nul == -1:
            # 末尾若无终止 NUL，把剩余当一个字符串
            raw = data[pos:]
            strings_raw.append(raw)
            try:
                strings.append(raw.decode('cp932'))
            except UnicodeDecodeError:
                strings.append('?')
            pos = len(data)
            break
        raw = data[pos:nul]
        strings_raw.append(raw)
        try:
            strings.append(raw.decode('cp932'))
        except UnicodeDecodeError:
            strings.append('?')
        pos = nul + 1

    # trailer
    trailer = data[pos:]

    return {
        'magic': magic,
        'extras': extras,
        'commands': folded,
        'raw_commands': raw_commands,
        'strings': strings,
        'strings_raw': strings_raw,
        'trailer': trailer,
        'commands_offset': cmd_start,
    }


# ============================================================
# 复合指令识别（融合开源工具的 ProcessDump 逻辑）
# ============================================================

def detect_complex_ops(commands, strings):
    """
    扫描 commands，识别复合模式并标注助记符 + 关联字符串。
    返回 list of dict:
      idx, orig_idx, op, data, prefix, mnem, string (可选), func_name (可选)
    """
    result = []
    n_str = len(strings)
    for i, (orig_idx, op, data, prefix) in enumerate(commands):
        entry = {
            'idx': i, 'orig_idx': orig_idx, 'op': op, 'data': data,
            'prefix': list(prefix), 'mnem': OP_MNEMONIC.get(op, f'CMD.{op:02X}'),
        }
        result.append(entry)

    # 第二轮: 模式识别（必须先有完整 entry 才能回头识别）
    consumed_str_ids = set()
    i = 0
    while i < len(result):
        e = result[i]
        op, data, prefix = e['op'], e['data'], e['prefix']

        # op=5: LOAD_STRING (data=1) / PUSH (其他)
        if op == 0x05:
            if data == 1 and len(prefix) >= 1:
                sid = prefix[-1]
                # signed: 负数视为不引用
                if sid < 0x80000000 and sid < n_str:
                    e['mnem'] = 'LOAD_STRING'
                    e['string'] = strings[sid]
                    e['string_id'] = sid
                    consumed_str_ids.add(sid)
                    e['prefix'] = prefix[:-1]   # 字符串 id 已被消费，不显示
                else:
                    e['mnem'] = 'PUSH'
            else:
                e['mnem'] = 'PUSH'

        # op=4: 复合指令 (CASE4 / LOAD_CUSTOM_TEXT / SET_EFFECT 的一部分)
        elif op == 0x04:
            # CASE4: data=0 + prefix=[0x80000000] + prev op=4 with single prefix string_id
            if data == 0 and len(prefix) == 1 and prefix[0] == 0x80000000 and i > 0:
                prev = result[i-1]
                if prev['op'] == 0x04 and len(prev['prefix']) == 1:
                    sid = prev['prefix'][0]
                    if 0 <= sid < n_str:
                        prev['mnem'] = 'CASE4'
                        prev['string'] = strings[sid]
                        prev['string_id'] = sid
                        prev['prefix'] = []
                        consumed_str_ids.add(sid)
                        e['mnem'] = 'CASE4_END'   # 标记后半部分

            # SET_EFFECT: data=任意 + prefix=[string_id]
            # （这种情况其实在 op=9 + prev op=6 的链中识别）

        # op=6: LOAD_CUSTOM_TEXT 的一部分
        elif op == 0x06:
            # 等待 op=9 来回头识别
            pass

        # op=9: PUSH_CUSTOM_TEXT (data=1 + prev op=6 with prefix=string_id)
        elif op == 0x09 and data == 1 and i > 0:
            prev = result[i-1]
            if prev['op'] == 0x06 and len(prev['prefix']) == 1:
                sid_signed = struct.unpack('<i', struct.pack('<I', prev['prefix'][0]))[0]
                if sid_signed >= 0 and sid_signed < n_str:
                    sid = sid_signed
                    e['mnem'] = 'PUSH_CUSTOM_TEXT'
                    prev['mnem'] = 'LOAD_CUSTOM_TEXT'
                    prev['string'] = strings[sid]
                    prev['string_id'] = sid
                    prev['prefix'] = []
                    consumed_str_ids.add(sid)
                    # 进一步: prev-1 op=4 with prefix string_id → SET_EFFECT
                    if i >= 2:
                        pp = result[i-2]
                        if pp['op'] == 0x04 and len(pp['prefix']) == 1:
                            sid2_signed = struct.unpack('<i', struct.pack('<I', pp['prefix'][0]))[0]
                            if sid2_signed >= 0 and sid2_signed < n_str:
                                pp['mnem'] = 'SET_EFFECT'
                                pp['string'] = strings[sid2_signed]
                                pp['string_id'] = sid2_signed
                                pp['prefix'] = []
                                consumed_str_ids.add(sid2_signed)
                elif sid_signed == -2147483644:  # 0x80000004
                    e['mnem'] = 'PUSH_CUSTOM_TEXT'
                    # prev-1 op=4 同样可能是 SET_EFFECT
                    if i >= 2:
                        pp = result[i-2]
                        if pp['op'] == 0x04 and len(pp['prefix']) == 1:
                            sid2_signed = struct.unpack('<i', struct.pack('<I', pp['prefix'][0]))[0]
                            if sid2_signed >= 0 and sid2_signed < n_str:
                                pp['mnem'] = 'SET_EFFECT'
                                pp['string'] = strings[sid2_signed]
                                pp['string_id'] = sid2_signed
                                pp['prefix'] = []
                                consumed_str_ids.add(sid2_signed)

        # op=0xE: SPECIAL_TEXT (data 末字节=0x80, prefix=[string_id])
        elif op == 0x0E:
            if (data >> 24) == 0x80 and len(prefix) >= 1:
                sid = prefix[-1]
                if 0 <= sid < n_str:
                    e['mnem'] = 'SPECIAL_TEXT'
                    e['string'] = strings[sid]
                    e['string_id'] = sid
                    e['prefix'] = prefix[:-1]
                    consumed_str_ids.add(sid)

        # op=7: FUNC（命名表）
        elif op == 0x07:
            e['mnem'] = 'FUNC'
            if data in FUNC_NAMES:
                e['func_name'] = FUNC_NAMES[data]

        # op=0x41 / 0x42: JNGE / JNLE
        # 已经在 OP_MNEMONIC 里处理
        i += 1

    return result, consumed_str_ids


# ============================================================
# LABEL / CHOICE BLOCK 检测
# ============================================================

def detect_labels(complex_cmds, raw_commands):
    """
    收集所有跳转目标。返回 set of orig_idx (跳转目标在原始 entry 数组中的位置)。
    """
    labels = set()
    for e in complex_cmds:
        if e['op'] in (0x40, 0x41, 0x42):
            tgt = e['data']
            if 0 <= tgt < len(raw_commands):
                labels.add(tgt)
        elif e['op'] == 0x3F:
            labels.add(e['orig_idx'])
    return labels


def detect_choice_blocks(complex_cmds):
    """
    识别选项块模式。
    选项块（CASE4 序列）: 多个连续的 CASE4 + 终结
    或者老的 CHOICE 模式（op=0x04 0 + op=0x06 1 + N×(CONST i, OP_19, JNGE Ti) + LABEL）

    返回 list of dict: {'start': cmd_idx, 'end': cmd_idx, 'choices': [(i, target_orig_idx, string)]}
    """
    blocks = []
    n = len(complex_cmds)
    i = 0
    while i < n:
        e = complex_cmds[i]
        # 模式A: 连续 CASE4 (新引擎风格)
        if e['mnem'] == 'CASE4':
            j = i
            choices = []
            while j < n and complex_cmds[j].get('mnem') == 'CASE4':
                ce = complex_cmds[j]
                choices.append({
                    'string': ce.get('string', ''),
                    'string_id': ce.get('string_id', -1),
                    'cmd_idx': j,
                })
                j += 1   # 跳过 CASE4
                if j < n and complex_cmds[j].get('mnem') == 'CASE4_END':
                    j += 1   # 跳过配对的 CASE4_END (op=4 data=0)
            if len(choices) >= 1:
                blocks.append({
                    'start_cmd': i,
                    'end_cmd': j - 1,
                    'choices': choices,
                    'kind': 'CASE4',
                })
                i = j
                continue
        i += 1
    return blocks


def strip_control_tags(s):
    """
    剥离 NeXAS 引擎的固定位置控制符 (开头 prefix + 句末 suffix),
    保留文中的 @n / @s / @m 等布局 tag 给 translator。

    全游戏 (259文件 70767字符串) 实测各 @x tag 位置分布:

        Tag   总数   开头    中间   句末
        @v    32708  32708    0      0    ← 100%开头: 语音ID (12字符 arg)
        @h        8      8    0      0    ← 100%开头: 立绘ID (12字符 arg)
        @s      141     37   104     0    ← 26%开头/74%中间: 文字大小 (4字符 arg)
        @n     9012      2  9009     1    ← 99%中间: 换行 (无 arg)
        @t       42      0    0     42    ← 100%句末: 定时暂停 (4字符 arg)
        @k       45      0    0     45    ← 100%句末: 触发效果 (无 arg)
        @w        2      0    0      2    ← 100%句末: 等待 (4字符 arg)
        @m        4      0    4      0    ← 100%中间: 字间距 (2字符 arg)

    剥离策略 (开头/句末分开处理, 同一字符串可能多种共存):
      - 开头 prefix: 循环吃掉所有 @v / @h / @s
      - 句末 suffix: 循环吃掉所有 @t/@k/@w/@n (在末尾位置时)
      - 中间 tag (@n/@s/@m): 保留, 让 translator 看到布局信息

    注意: @s 在开头和中间都出现, 只剥开头那个 (中间的保留)。

    返回: (cleaned_text, tags_dict)
        tags_dict 例: {'voice':'@vS050_A1_0005', 'size':'@s4040', 'suffix':'@w0000@k'}
    """
    if not s or '@' not in s:
        return s, {}

    out = s
    tags = {}

    # 1. 剥开头 prefix: @v / @h / @s
    while True:
        prefix_kind = None
        if out.startswith('@v'):
            prefix_kind = 'voice'
        elif out.startswith('@h'):
            prefix_kind = 'sprite'
        elif out.startswith('@s'):
            prefix_kind = 'size'

        if prefix_kind:
            i = 2
            while i < len(out) and (out[i].isalnum() or out[i] == '_'):
                i += 1
            # 累加 (允许同一种 prefix 多个,但用 list 储存)
            existing = tags.get(prefix_kind)
            if existing is None:
                tags[prefix_kind] = out[:i]
            else:
                tags[prefix_kind] = existing + out[:i]
            out = out[i:]
        else:
            break

    # 2. 剥句末 suffix: @t/@k/@w/@n[arg] 序列
    suffix_chars = ''
    suffix_pattern = re.compile(r'@([tkwn])([A-Za-z0-9_]*)$')
    while True:
        m = suffix_pattern.search(out)
        if not m:
            break
        suffix_chars = m.group(0) + suffix_chars
        out = out[:m.start()]

    if suffix_chars:
        tags['suffix'] = suffix_chars

    return out, tags


def restore_control_tags(translated, tags):
    """
    还原 tag 到译文: 开头按原顺序 voice/sprite/size, 句末 suffix。

    剥离时是循环吃 prefix, 但每种 prefix 只保留一个 key (累加).
    还原顺序应跟原始位置一致 - 不过同种 prefix 间顺序未保留,
    实测 99% 字符串只有一种 prefix, 罕见情况下顺序差异不影响显示。
    """
    if not tags:
        return translated
    out = translated
    # prefix: 顺序无所谓 (实测同种 prefix 单个为主)
    # 但为稳定: voice 在最前 (语音先于一切), sprite, size 在后
    if 'size' in tags:
        out = tags['size'] + out
    if 'sprite' in tags:
        out = tags['sprite'] + out
    if 'voice' in tags:
        out = tags['voice'] + out
    if 'suffix' in tags:
        out = out + tags['suffix']
    return out


def detect_dialogues(complex_cmds, strings):
    """
    从 complex_cmds 识别对话单元 (name + message)。

    引擎模式 (a1_0500 实测):
      引擎在显示一段对话时, LOAD_STRING msg 会出现多次 (preload + display)。
      只有**最后一次出现**才是真正显示位置, 此时前面紧邻 [name][@][name] 三连。
      
    算法:
      1. 收集所有 LOAD_STRING 出现序列
      2. 对每个 unique msg_sid, 取**最后一次出现位置**作为 _site
      3. 在该位置之前, 反向找最近的 [X][@][X] 三连 -> 该 X 即 name
      4. 如果找不到或 X 是空, 该 msg 无 name (旁白)

    跳过条件:
      - 字符串是 '@v' / '@' 等分隔符
      - 字符串是空字符串
      - 字符串是纯 ASCII (资源名 SE_xxx, .png, .ogg 等)
    """
    import re
    seq = []
    for e in complex_cmds:
        if e['mnem'] == 'LOAD_STRING':
            seq.append({
                'orig_idx': e['orig_idx'],
                'sid': e.get('string_id', -1),
                'string': e.get('string', '')
            })

    # 1. 收集每个 sid 的所有出现位置
    sid_positions = {}
    for i, x in enumerate(seq):
        sid_positions.setdefault(x['sid'], []).append(i)

    # 2. 找所有 name (跟踪 [X][@][X] 模式定位)
    # name_set: 哪些 sid 是 name
    name_set = set()
    for i in range(len(seq) - 2):
        if (seq[i+1]['string'] == '@'
            and seq[i+2]['sid'] == seq[i]['sid']
            and seq[i]['string'] != '@v'):
            name_set.add(seq[i]['sid'])

    # 3. 对每个 message sid 配对
    # 已知资源文件扩展名 (这些字符串是引擎读取的资源,不是对话)
    RES_EXT_RE = re.compile(r'\.(png|jpg|jpeg|bmp|gif|spm|ogg|wav|mp3|bin|txt|dat|csv)$', re.IGNORECASE)
    
    dialogues = []
    for sid, positions in sid_positions.items():
        if sid < 0 or sid >= len(strings):
            continue
        s = strings[sid]
        # 跳过空 / 分隔符 / name 本身 / 资源名
        if not s: continue
        if s in ('@v', '@'): continue
        if sid in name_set: continue
        if re.match(r'^[\x20-\x7E]+$', s): continue
        # 跳过资源文件名 (即使含日文字符,如 'タカヒロ.png')
        if RES_EXT_RE.search(s): continue

        # 用最后一次出现位置作为 _site
        last_pos = positions[-1]

        # 反向找最近的 [X][@][X] 三连 (X 可为空)
        # 跳过 @v / @ / 自己的 sid
        name_str = ''
        name_sid = -1
        j = last_pos - 1
        # 简化: 找连续的 [name_x][@][name_x] 三元组
        while j >= 2:
            cur = seq[j]
            if cur['string'] in ('@v', '@'):
                j -= 1
                continue
            if cur['sid'] == sid:
                j -= 1
                continue
            # 检查 j-2, j-1, j 是否是 [X][@][X]
            if (seq[j-1]['string'] == '@'
                and seq[j-2]['sid'] == cur['sid']):
                name_str = cur['string']
                name_sid = cur['sid'] if name_str else -1
                break
            j -= 1

        dialogues.append({
            'name': name_str,
            'message': s,
            '_name_sid': name_sid,
            '_msg_sid': sid,
            '_site': seq[last_pos]['orig_idx'],
            '_idx': 0,  # 后面排序后重分配
        })

    # 按 _site 排序 (=按剧本时间顺序)
    dialogues.sort(key=lambda d: d['_site'])
    for i, d in enumerate(dialogues):
        d['_idx'] = i

    return dialogues


def detect_choices(complex_cmds):
    """
    识别选项菜单。

    引擎模式 (b1_1008 实测):
      SET_EFFECT '【'
      LOAD_CUSTOM_TEXT '<选项内容>'   ← 真正的选项文字
      PUSH_CUSTOM_TEXT
      ... 几条 CMD ...
      LOAD_CUSTOM_TEXT '】'

    返回: [{message, _msg_sid, _site, _idx}, ...]
    每个选项作为独立项，注入时与 dialogues 共用 sid 索引。
    """
    choices = []
    seen_sid = set()
    for i in range(1, len(complex_cmds)):
        e = complex_cmds[i]
        prev = complex_cmds[i-1]
        if (e['mnem'] == 'LOAD_CUSTOM_TEXT'
            and prev['mnem'] == 'SET_EFFECT'
            and prev.get('string', '') == '【'):
            s = e.get('string', '')
            sid = e.get('string_id', -1)
            if s and s != '】' and sid not in seen_sid:
                seen_sid.add(sid)
                choices.append({
                    'message': s,
                    '_msg_sid': sid,
                    '_site': e['orig_idx'],
                    '_idx': len(choices),
                })
    return choices


# ============================================================
# 续接对话合并 (引擎层面把一句话拆成两段的情况)
# ============================================================

# 续接合并标记: 用 4 连全角空格,实测全游戏只在 4 处 staff roll 单字符串内出现,
# 不会跨对话冲突. 注入时按此标记拆回两段.
CONTINUATION_MARKER = '\u3000\u3000\u3000\u3000'


def merge_continuations(items):
    """
    合并被引擎拆成两段的同人物连续对话。

    检测条件 (基于 strip_control_tags 后的 cleaned message):
      1. 当前 item 含 「 但不含 」 (开括号未闭合)
      2. 下一个 item 同 name (或都为空 name)
      3. 下一个 item 含 」 但 「 数量 < 」 (闭合前句)
      4. 都不是 _choice (选项不参与合并)

    合并方式:
      cleaned 文本: cur + CONTINUATION_MARKER + next
      _msg_sid: 保留 cur 的 (主)
      _continuation_sid: 记录 next 的 sid (注入时按 marker 拆回)
      _continuation_tags: 记录 next 的 _tags (注入时分开还原)

    返回: 合并后的 items list
    """
    if not items:
        return items

    out = []
    i = 0
    while i < len(items):
        cur = items[i]
        # 选项不合并
        if cur.get('_choice'):
            out.append(cur)
            i += 1
            continue

        msg = cur['message']
        n_open = msg.count('「')
        n_close = msg.count('」')

        # 当前未闭合 + 有下一项
        if n_open > n_close and i + 1 < len(items):
            nxt = items[i + 1]
            if (not nxt.get('_choice')
                and nxt['name'] == cur['name']
                and nxt['message'].count('」') > nxt['message'].count('「')):
                # 合并
                merged = dict(cur)
                merged['message'] = cur['message'] + CONTINUATION_MARKER + nxt['message']
                merged['_continuation_sid'] = nxt['_msg_sid']
                if nxt.get('_tags'):
                    merged['_continuation_tags'] = nxt['_tags']
                out.append(merged)
                i += 2
                continue

        out.append(cur)
        i += 1

    return out


def split_continuation(merged_msg):
    """
    把合并的 message 按 CONTINUATION_MARKER 拆回原始两段。
    返回: (part1, part2) 或 (msg, None) 如果未含 marker。
    """
    if CONTINUATION_MARKER not in merged_msg:
        return merged_msg, None
    p1, _, p2 = merged_msg.partition(CONTINUATION_MARKER)
    return p1, p2


# ============================================================
# 写入（注入用）
# ============================================================

def encode_string(s, encoding='cp932'):
    """编码字符串。失败时按 GBK 重试，再失败抛出。"""
    if encoding == 'cp932':
        try:
            return s.encode('cp932')
        except UnicodeEncodeError:
            try:
                return s.encode('gbk')
            except UnicodeEncodeError as e:
                raise ValueError(f"无法编码字符串: {s!r} (cp932 和 GBK 都失败: {e})")
    elif encoding == 'gbk':
        return s.encode('gbk')
    else:
        return s.encode(encoding)


def rebuild_script(parsed, new_strings, encoding='cp932'):
    """
    用新的字符串列表重建 .bin。
    parsed: parse_script 返回的 dict
    new_strings: list[str]，长度必须等于 parsed['strings'] 长度
    返回: bytes

    关键: 对未修改的字符串使用原始字节，避免 cp932 双向映射非对称问题
    （某些字符如 '羽' 有 NEC 外字 FB92 / 标准 JIS EE75 两个编码点，
      Python cp932 解码两者都接受但编码只输出标准的，导致 round-trip 失败）
    """
    if len(new_strings) != len(parsed['strings']):
        raise ValueError(f"新字符串数 {len(new_strings)} 不等于原数 {len(parsed['strings'])}")

    out = bytearray()
    out += struct.pack('<I', parsed['magic'])
    for op, arg in parsed['extras']:
        out += struct.pack('<2I', op, arg)
    out += struct.pack('<I', len(parsed['raw_commands']))
    for op, arg in parsed['raw_commands']:
        out += struct.pack('<2I', op, arg)
    out += struct.pack('<I', len(new_strings))
    for i, s in enumerate(new_strings):
        if s == parsed['strings'][i] and i < len(parsed['strings_raw']):
            # 未修改：直接用原始字节 (bit-perfect)
            out += parsed['strings_raw'][i] + b'\x00'
        else:
            # 修改了的字符串才重新编码
            out += encode_string(s, encoding) + b'\x00'
    out += parsed['trailer']
    return bytes(out)
