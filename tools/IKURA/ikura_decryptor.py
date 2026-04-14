import os
import struct

# ========================================================
# 基础算法库
# ========================================================
HEX_ENCODE_MAP = b"G5FXIL094MPRKWCJ3OEBVA7HQ2SU8Y6TZ1ND"
HEX_TABLE = [
    0x06, 0x21, 0x19, 0x10, 0x08, 0x01, 0x1E, 0x16, 0x1C, 0x07, 0x15, 0x13, 0x0E, 0x23, 0x12, 0x02,
    0x00, 0x17, 0x04, 0x0F, 0x0C, 0x05, 0x09, 0x22, 0x11, 0x0A, 0x18, 0x0B, 0x1A, 0x1F, 0x1B, 0x14,
    0x0D, 0x03, 0x1D, 0x20,
]

def chr2hex(c):
    if 48 <= c <= 57: return c - 48
    if 97 <= c <= 122: return c - 97 + 10
    if 65 <= c <= 90: return c - 65 + 10
    return 0

def chr2hexcode(c): return HEX_TABLE[chr2hex(c)]

def encode_hex(symbol):
    if symbol > 127: symbol -= 256
    return HEX_ENCODE_MAP[symbol % 36]

def str2hex(s):
    hex_val = 0
    for i in range(len(s)):
        hex_val |= chr2hex(s[i]) << ((len(s) - i - 1) << 2)
    return hex_val

def create_key(secret):
    length = bytearray(2)
    for i in range(2):
        length[i] = encode_hex((chr2hexcode(secret[0x0500 + i]) - chr2hexcode(secret[0x0100 + i])) & 0xFF)
    key_len = str2hex(length)
    key = bytearray(key_len)
    for i in range(key_len):
        key[i] = encode_hex((chr2hexcode(secret[0x0510 + i]) - chr2hexcode(secret[0x0110 + i])) & 0xFF)
    return key

def update_key(secret, key, index):
    p = (index & 0x3F) * 0x10
    for i in range(len(key)):
        key[i] = encode_hex((chr2hexcode(key[i]) + chr2hexcode(secret[p + i])) & 0xFF)

def handle_isf_xor(data, secret):
    """ 执行 ISF 外层异或解密 """
    key = bytearray(create_key(secret))
    key_len = len(key)
    data = bytearray(data)
    for i in range(len(data)):
        if i % key_len == 0:
            update_key(secret, key, i // key_len)
        data[i] ^= key[i % key_len]
    return data

# ========================================================
# 引擎解析库
# ========================================================
def unpack_drs(f):
    """ 早期 DRS 格式 """
    f.seek(0)
    dir_size = struct.unpack("<H", f.read(2))[0]
    count = (dir_size // 16) - 1
    
    f.seek(14)
    first_offset = struct.unpack("<I", f.read(4))[0]
    
    f.seek(2)
    entries = []
    current_dir_pos = 2
    
    for i in range(count):
        name = f.read(12).split(b'\0')[0].decode('ascii', 'ignore')
        f.seek(current_dir_pos + 12)
        offset = struct.unpack("<I", f.read(4))[0]
        
        next_entry_pos = current_dir_pos + 16
        f.seek(next_entry_pos + 12)
        next_offset = struct.unpack("<I", f.read(4))[0]
        
        size = next_offset - offset
        entries.append((name, offset, size))
        
        current_dir_pos = next_entry_pos
        f.seek(current_dir_pos)
        
    return entries

def unpack_mpx(f):
    """ 新版 MPX(IKURA) 格式 """
    f.seek(8)
    count = struct.unpack("<I", f.read(4))[0]
    f.seek(32) 
    entries = []
    for _ in range(count):
        entry_data = f.read(20)
        name = entry_data[0:12].split(b'\0')[0].decode('ascii', 'ignore')
        offset = struct.unpack("<I", entry_data[12:16])[0]
        size = struct.unpack("<I", entry_data[16:20])[0]
        entries.append((name, offset, size))
    return entries

# ========================================================
# 供 GUI 调用的接口
# ========================================================
def auto_extract_secret(exe_path):
    """供 GUI 调用的 Secret 提取接口"""
    if not os.path.exists(exe_path): return None
    print(f"[*] 扫描 EXE: {exe_path}")
    with open(exe_path, "rb") as f:
        data = f.read()
    offset = 0
    while True:
        offset = data.find(b'UOB0', offset)
        if offset == -1: break
        potential = data[offset : offset + 2048]
        if len(potential) == 2048 and all(0x30 <= b <= 0x5A for b in potential):
            print(f"[+] 提取到 2048 字节 Secret (偏移: {hex(offset)})")
            return potential
        offset += 4
    return None

def unpack_and_decrypt(file_path, secret, output_root):
    """供 GUI 调用的核心解包接口，自动识别引擎并写入配置"""
    with open(file_path, "rb") as f:
        sig = f.read(4)
        f.seek(0)
        
        engine_type = "DRS"
        if sig == b'SM2M':
            print(f"[*] 引擎判定: 新版 MPX / IKURA (SM2MPX10)")
            entries = unpack_mpx(f)
            engine_type = "MPX"
        else:
            print(f"[*] 引擎判定: 早期经典版 DRS")
            entries = unpack_drs(f)
            engine_type = "DRS"
            
        # 【新增】：统一生成 file_order.json，记录包名、引擎和文件顺序
        import json
        order_data = {
            "original_name": os.path.basename(file_path),
            "engine": engine_type,
            "file_order": [e[0] for e in entries]
        }
        with open("file_order.json", "w", encoding="utf-8") as jf:
            json.dump(order_data, jf, indent=4)
            
        for name, offset, size in entries:
            f.seek(offset)
            data = f.read(size)
            
            if name.lower().endswith((".isf", ".snr")) and secret:
                if data[-16:] == b"SECRETFILTER100a":
                    print(f"  [>] 解密 XOR 壳: {name}")
                    data = handle_isf_xor(data[:-16], secret)
                else:
                    print(f"  [>] 提取(无壳): {name}")
            else:
                pass # print(f"  [>] 提取资源: {name}") # 防止刷屏
            
            save_path = os.path.join(output_root, name)
            os.makedirs(os.path.dirname(save_path), exist_ok=True)
            with open(save_path, "wb") as out_f:
                out_f.write(data)