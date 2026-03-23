#!/usr/bin/env python3
"""
lponpon_obj_text.py - Overflow/らーじPonPon OBJ脚本 文本提取/导入工具

OBJ字节码VM文本块结构:
  [0x80] [varlen_byte_length] [encrypted_uint16_array] [0x81] [0xf5]

文本加密方式 (FUN_004094f0):
  - 以 uint16 (LE) 为单位 XOR
  - 初始密钥: 0x5A5A
  - 密钥变化: 每处理一个 uint16 后 key += 1
  - 每个 uint16 解密后即为 cp932 字符码:
    - 高字节 0x00: ASCII 单字节字符 (低字节)
    - 高字节 0x81-0x9F/0xE0-0xFC: cp932 双字节字符 (高字节=lead, 低字节=trail)

注: 这与 FUN_00409540 (文件名解密: byte XOR, key=0x5A递减) 完全不同

控制码:
  [0x81][0xf5] = 翻页等待 (文本块终止符)
  uint16 值中 高字节非0且非cp932 lead: 内联控制码
  已知: [1081] = 主角名变量, [028f]/[0280] = 文本特效标记

提取格式: GalTransl JSON (UTF-8)

用法:
  python lponpon_obj_text.py extract  input.obj  [output.json]
  python lponpon_obj_text.py insert   input.obj  input.json  [output.obj]
  python lponpon_obj_text.py batch_e  obj_dir    [json_dir]
  python lponpon_obj_text.py batch_i  obj_dir    json_dir    [out_dir]
"""

import struct, json, sys, os, glob

# ============================================================
# 变长整数编码 (FUN_00412700)
# ============================================================

def decode_varlen(data, pos):
    """读取变长整数, 返回 (value, new_pos)"""
    b = data[pos]; pos += 1
    if (b & 0x80) == 0:
        return b & 0x7F, pos
    val = b & 0x0F
    sb = b & 0x30
    if sb == 0x10:
        val = val * 256 + data[pos]; pos += 1
    elif sb == 0x20:
        val = val * 256 + data[pos]; pos += 1
        val = val * 256 + data[pos]; pos += 1
    elif sb == 0x30:
        val = val * 256 + data[pos]; pos += 1
        val = val * 256 + data[pos]; pos += 1
        val = val * 256 + data[pos]; pos += 1
    if b & 0x40:
        val = (-val) & 0xFFFFFFFF
    return val, pos


def encode_varlen(val):
    """编码变长整数, 返回 bytes (与FUN_00412700解码格式完全对应)"""
    if val < 0:
        val = (-val) & 0xFFFFFFFF
        neg = True
    else:
        neg = False
    
    # 值 < 0x80: 直接单字节 (bit7=0), 不支持负数
    if not neg and val < 0x80:
        return bytes([val])
    
    # 值需要 bit7 编码
    if val <= 0x0F:
        b = 0x80 | (val & 0x0F)
        if neg: b |= 0x40
        return bytes([b])
    elif val <= 0x0FFF:
        hi = (val >> 8) & 0x0F
        lo = val & 0xFF
        b = 0x80 | 0x10 | hi
        if neg: b |= 0x40
        return bytes([b, lo])
    elif val <= 0x0FFFFF:
        b0 = (val >> 16) & 0x0F
        b1 = (val >> 8) & 0xFF
        b2 = val & 0xFF
        b = 0x80 | 0x20 | b0
        if neg: b |= 0x40
        return bytes([b, b1, b2])
    else:
        b0 = (val >> 24) & 0x0F
        b1 = (val >> 16) & 0xFF
        b2 = (val >> 8) & 0xFF
        b3 = val & 0xFF
        b = 0x80 | 0x30 | b0
        if neg: b |= 0x40
        return bytes([b, b1, b2, b3])


# ============================================================
# 文本加解密 (FUN_004094f0)
# ============================================================

def decrypt_text_words(raw_bytes):
    """uint16 XOR解密, key=0x5A5A递增, 返回解密后的uint16列表"""
    words = []
    key = 0x5A5A
    for i in range(0, len(raw_bytes) - 1, 2):
        w = struct.unpack_from('<H', raw_bytes, i)[0]
        words.append(w ^ key)
        key = (key + 1) & 0xFFFF
    return words


def encrypt_text_words(words):
    """uint16 XOR加密, key=0x5A5A递增, 返回加密后的bytes"""
    result = bytearray()
    key = 0x5A5A
    for w in words:
        enc = w ^ key
        result.extend(struct.pack('<H', enc))
        key = (key + 1) & 0xFFFF
    return bytes(result)


def words_to_text(words):
    """将uint16列表转为文本字符串"""
    chars = []
    for w in words:
        hi = (w >> 8) & 0xFF
        lo = w & 0xFF
        if hi == 0x00:
            if lo >= 0x20:
                chars.append(chr(lo))
            elif lo == 0x0A:
                chars.append('\n')
            elif lo == 0x0D:
                chars.append('\r')
            else:
                chars.append(f'\\x{lo:02x}')
        elif (0x81 <= hi <= 0x9F) or (0xE0 <= hi <= 0xFC):
            try:
                chars.append(bytes([hi, lo]).decode('cp932'))
            except:
                chars.append(f'[{w:04x}]')
        else:
            chars.append(f'[{w:04x}]')
    return ''.join(chars)


def text_to_words(text):
    """将文本字符串转回uint16列表"""
    words = []
    i = 0
    while i < len(text):
        ch = text[i]
        
        # 转义序列 \xNN
        if ch == '\\' and i + 3 < len(text) and text[i+1] == 'x':
            try:
                val = int(text[i+2:i+4], 16)
                words.append(val)
                i += 4
                continue
            except:
                pass
        
        # 控制码 [NNNN]
        if ch == '[' and i + 5 < len(text) and text[i+5] == ']':
            try:
                val = int(text[i+1:i+5], 16)
                words.append(val)
                i += 6
                continue
            except:
                pass
        
        # 换行
        if ch == '\n':
            words.append(0x000A)
            i += 1
            continue
        if ch == '\r':
            words.append(0x000D)
            i += 1
            continue
        
        # ASCII
        if ord(ch) < 0x80:
            words.append(ord(ch))
            i += 1
            continue
        
        # cp932 双字节字符
        try:
            encoded = ch.encode('cp932')
            if len(encoded) == 2:
                words.append((encoded[0] << 8) | encoded[1])
            elif len(encoded) == 1:
                words.append(encoded[0])
            else:
                # 无法编码为cp932, 尝试保留原始
                words.append(ord(ch))
        except:
            words.append(ord(ch))
        i += 1
    
    return words


# ============================================================
# 文本块查找
# ============================================================

def find_text_blocks(data):
    """
    在OBJ字节码中找出所有文本块
    模式: 0x80 [varlen_length] [length bytes] 0x81
    
    终止符 0x81 后跟1字节参数:
      0x00 = 段落/场景结束
      0x01 = 翻页继续  
      0xf5 = 等待点击
      其他 = 各种控制模式
    
    返回: [(block_start, data_start, data_length, term_pos, term_byte), ...]
    """
    blocks = []
    pos = 0
    while pos < len(data) - 2:
        if data[pos] == 0x80:
            try:
                length, data_start = decode_varlen(data, pos + 1)
                if 2 <= length <= 50000 and data_start + length < len(data):
                    end = data_start + length
                    if data[end] == 0x81:
                        term_byte = data[end + 1] if end + 1 < len(data) else 0
                        blocks.append((pos, data_start, length, end, term_byte))
                        pos = end + 2
                        continue
            except:
                pass
        pos += 1
    
    return blocks


# ============================================================
# 角色/voice 信息提取
# ============================================================

def decrypt_name_bytes(enc_bytes, length):
    """FUN_00409540: 文件名解密 (byte XOR, key=0x5A递减)"""
    key = 0x5A
    dec = bytearray()
    for i in range(length):
        dec.append((enc_bytes[i] ^ key) & 0xFF)
        key = (key - 1) & 0xFF
    return bytes(dec)


def find_voice_blocks(data):
    """
    找出所有 handler 0x89 (voice/角色标识) 的位置、voice文件名和角色ID
    格式: ... 04 44 [char_id] 00 15 10 53 04 89 [varlen_length] [encrypted_name]
    返回: { voice_end_pos: (voice_name, char_id), ... }
    """
    voices = {}
    pos = 0
    while pos < len(data) - 2:
        if data[pos] == 0x89:
            try:
                length, name_start = decode_varlen(data, pos + 1)
                if 1 <= length <= 32 and name_start + length <= len(data):
                    enc = data[name_start:name_start + length]
                    dec = decrypt_name_bytes(enc, length)
                    name = dec.decode('cp932').rstrip('\x00')
                    if name.isprintable() and len(name) > 0:
                        voice_end = name_start + length
                        
                        # 向前找 char_id: 04 44 XX 00 15 10
                        char_id = -1
                        for j in range(max(0, pos - 20), pos):
                            if (j + 5 < len(data) and
                                data[j] == 0x04 and data[j+1] == 0x44 and
                                data[j+3] == 0x00 and data[j+4] == 0x15 and
                                data[j+5] == 0x10):
                                char_id = data[j+2]
                                break
                        
                        voices[voice_end] = (name, char_id)
            except:
                pass
        pos += 1
    return voices


def classify_blocks(data, blocks):
    """
    对每个文本块分类: 旁白 / NPC台词 / 主角回复
    
    引擎规律 (通过反汇编验证):
    - 旁白: 前面紧接 67 10 53 04 (set word[0x10]=1, call sub[4])
    - NPC台词 (有voice): 前面有 89 [voice] 44 00, 然后直接 0x80 文本
    - 主角回复: 前面紧接 04 44 0a/0b 00 15 10 53 04
    
    返回: [(block_info, kind, voice_name), ...]
      kind: 'narration' | 'npc' | 'protagonist'
    """
    voices = find_voice_blocks(data)
    
    result = []
    for idx, (bstart, ds, blen, ep, term) in enumerate(blocks):
        # 检查前缀模式
        
        # 旁白: 67 10 53 04 紧接在 0x80 之前
        is_narr = (bstart >= 4 and 
                   data[bstart-4:bstart] == b'\x67\x10\x53\x04')
        
        # 主角回复: 04 44 XX 00 15 10 53 04 紧接在 0x80 之前
        is_protag = False
        if bstart >= 8:
            pre8 = data[bstart-8:bstart]
            if (pre8[0] == 0x04 and pre8[1] == 0x44 and pre8[3] == 0x00 and
                pre8[4] == 0x15 and pre8[5] == 0x10 and pre8[6] == 0x53):
                is_protag = True
        
        # NPC台词: 前面有 89 voice然后 44 00 直接到 0x80
        # 检查: bstart-2 应该是 44 00, 再往前是 voice block 结尾
        is_npc = False
        voice_name = ""
        char_id = -1
        if bstart >= 2 and data[bstart-2:bstart] == b'\x44\x00':
            # 44 00 之前应该是 voice 的结尾位置
            voice_end = bstart - 2
            if voice_end in voices:
                is_npc = True
                voice_name, char_id = voices[voice_end]
        
        if is_narr:
            kind = 'narration'
        elif is_npc:
            kind = 'npc'
        elif is_protag:
            kind = 'protagonist'
        else:
            # 未知前缀: 检查更宽范围是否有 89 (有些NPC台词前缀可能略有变化)
            wider = data[max(0,bstart-30):bstart]
            if b'\x89' in wider and not is_narr:
                kind = 'npc'
                # 尝试从wider范围提取voice name
                for vend, (vname, vid) in voices.items():
                    if bstart - 30 <= vend <= bstart:
                        voice_name = vname
                        char_id = vid
                        break
            else:
                kind = 'narration'
        
        result.append(((bstart, ds, blen, ep, term), kind, voice_name, char_id))
    
    return result


# ============================================================
# 提取 / 导入
# ============================================================

def extract(obj_path, json_path=None):
    """提取OBJ文本到GalTransl JSON"""
    if json_path is None:
        json_path = os.path.splitext(obj_path)[0] + '.JSON'
    
    data = open(obj_path, 'rb').read()
    blocks = find_text_blocks(data)
    
    entries = []
    msg_count = 0
    for i, (bstart, dstart, dlen, ep, term) in enumerate(blocks):
        raw = data[dstart:dstart + dlen]
        text = words_to_text(decrypt_text_words(raw))
        
        entry = {
            "message": text,
            "_idx": i,
            "_offset": f"0x{bstart:04x}",
        }
        entries.append(entry)
        if text.strip():
            msg_count += 1
    
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(entries, f, ensure_ascii=False, indent=2)
    
    basename = os.path.basename(obj_path)
    outname = os.path.basename(json_path)
    print(f"  {basename}: {len(entries)} entries, {msg_count} messages -> {outname}")
    return entries


def insert(obj_path, json_path, out_path=None):
    """将翻译后的JSON导入OBJ"""
    if out_path is None:
        out_path = obj_path
    
    data = bytearray(open(obj_path, 'rb').read())
    blocks = find_text_blocks(data)
    
    with open(json_path, 'r', encoding='utf-8') as f:
        entries = json.load(f)
    
    # 建立 block_idx → new_text 的映射
    block_texts = {}
    for e in entries:
        idx = e.get('_idx', -1)
        block_texts[idx] = e.get('message', '')
    
    # 从后往前替换, 避免偏移错位
    replaced = 0
    for idx in range(len(blocks) - 1, -1, -1):
        bstart, dstart, dlen, ep, term = blocks[idx]
        
        if idx not in block_texts:
            continue
        
        new_text = block_texts[idx]
        
        # 转为uint16列表并加密
        new_words = text_to_words(new_text)
        new_encrypted = encrypt_text_words(new_words)
        new_byte_len = len(new_encrypted)
        
        # 编码新的varlen长度
        new_varlen = encode_varlen(new_byte_len)
        
        # 构建新块: 0x80 + varlen + encrypted_data
        # 注意: 0x81 0xf5 终止符不变, 不需要重写
        new_block = bytes([0x80]) + new_varlen + new_encrypted
        
        # 替换: 从 bstart 到 ep (不含 0x81 + term_byte)
        old_block_len = ep - bstart  # 0x80 + varlen + data
        data[bstart:bstart + old_block_len] = new_block
        replaced += 1
    
    with open(out_path, 'wb') as f:
        f.write(data)
    
    basename = os.path.basename(obj_path)
    outname = os.path.basename(out_path)
    print(f"  {basename}: {replaced} blocks replaced -> {outname}")


def batch_extract(obj_dir, json_dir=None):
    """批量提取目录下所有OBJ"""
    if json_dir is None:
        json_dir = obj_dir
    os.makedirs(json_dir, exist_ok=True)
    
    files = sorted(glob.glob(os.path.join(obj_dir, '*.OBJ')) + 
                   glob.glob(os.path.join(obj_dir, '*.obj')))
    total_entries = 0
    total_msgs = 0
    for fpath in files:
        basename = os.path.splitext(os.path.basename(fpath))[0]
        json_path = os.path.join(json_dir, basename + '.JSON')
        entries = extract(fpath, json_path)
        total_entries += len(entries)
        total_msgs += sum(1 for e in entries if e.get('message', '').strip())
    
    print(f"\nTotal: {len(files)} files, {total_entries} entries, {total_msgs} messages")


def batch_insert(obj_dir, json_dir, out_dir=None):
    """批量导入"""
    if out_dir is None:
        out_dir = obj_dir
    os.makedirs(out_dir, exist_ok=True)
    
    json_files = sorted(glob.glob(os.path.join(json_dir, '*.JSON')) +
                        glob.glob(os.path.join(json_dir, '*.json')))
    for jpath in json_files:
        basename = os.path.splitext(os.path.basename(jpath))[0]
        obj_path = os.path.join(obj_dir, basename + '.OBJ')
        if not os.path.exists(obj_path):
            obj_path = os.path.join(obj_dir, basename + '.obj')
        if not os.path.exists(obj_path):
            print(f"  WARNING: {basename}.OBJ not found, skipped")
            continue
        out_path = os.path.join(out_dir, basename + '.OBJ')
        insert(obj_path, jpath, out_path)


# ============================================================
# 主入口
# ============================================================

def print_usage():
    print("lponpon_obj_text.py - Overflow/らーじPonPon OBJ脚本 文本提取/导入工具")
    print()
    print("OBJ文本块结构:")
    print("  [0x80] [varlen_length] [uint16_XOR_encrypted_text] [0x81] [0xf5]")
    print()
    print("加密方式 (FUN_004094f0):")
    print("  uint16 LE XOR, 初始key=0x5A5A, 每字 +1")
    print("  解密后每个 uint16 = cp932 字符码 (高字节00=ASCII, 81-9F/E0-FC=双字节)")
    print()
    print("提取格式: GalTransl JSON (UTF-8)")
    print("  [")
    print('    { "message": "台词", "_idx": 0, "_offset": "0x0054" },')
    print("    ...")
    print("  ]")
    print()
    print("用法:")
    print("  python lponpon_obj_text.py extract  input.obj  [output.json]")
    print("  python lponpon_obj_text.py insert   input.obj  input.json  [output.obj]")
    print("  python lponpon_obj_text.py batch_e  obj_dir    [json_dir]")
    print("  python lponpon_obj_text.py batch_i  obj_dir    json_dir    [out_dir]")


if __name__ == '__main__':
    if len(sys.argv) < 3:
        print_usage()
        sys.exit(0)
    
    cmd = sys.argv[1].lower()
    
    if cmd == 'extract':
        extract(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else None)
    elif cmd == 'insert':
        if len(sys.argv) < 4:
            print("Error: insert requires input.obj and input.json")
            sys.exit(1)
        insert(sys.argv[2], sys.argv[3], sys.argv[4] if len(sys.argv) > 4 else None)
    elif cmd in ('batch_e', 'batch_extract'):
        batch_extract(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else None)
    elif cmd in ('batch_i', 'batch_insert'):
        if len(sys.argv) < 4:
            print("Error: batch_i requires obj_dir and json_dir")
            sys.exit(1)
        batch_insert(sys.argv[2], sys.argv[3], sys.argv[4] if len(sys.argv) > 4 else None)
    else:
        print(f"Unknown command: {cmd}")
        print_usage()
        sys.exit(1)
