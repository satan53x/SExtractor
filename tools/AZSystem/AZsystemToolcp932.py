import os
import sys
import struct

def is_valid_cp932(buffer: bytes) -> bool:
    """验证是否为合法的日文编码"""
    if not buffer: return False
    try:
        buffer.decode('cp932')
        return True
    except:
        return False

def dump_text(input_path: str, output_path: str):
    """提取脚本中的文本"""
    try:
        with open(input_path, 'rb') as f:
            buffer = bytearray(f.read())
    except: return
        
    extracted_texts = []
    i, size = 0, len(buffer)
    
    while i < size:
        # 对话和人名 (2A, 29, 28, 27)
        if i + 24 <= size and (buffer[i] in [0x2a, 0x29, 0x28, 0x27]) and buffer[i+1:i+4] == b'\x00\x00\x00':
            block_length = struct.unpack('<I', buffer[i+4:i+8])[0]
            if 24 <= block_length < 100000 and i + block_length <= size:
                text_bytes = buffer[i+24 : i+block_length-1]
                if is_valid_cp932(text_bytes):
                    try:
                        text_str = text_bytes.decode('cp932')
                        prefix = "[NAME]" if buffer[i] == 0x27 else ""
                        extracted_texts.append(f"{prefix}{text_str}")
                    except: pass
                i += block_length
                continue
        
        # 选项 (0D)
        elif i + 24 < size and buffer[i] == 0x0d and buffer[i+1:i+4] == b'\x00\x00\x00':
            block_length = struct.unpack('<I', buffer[i+4:i+8])[0]
            if 24 <= block_length < 100000 and i + block_length <= size:
                curr = i + 24
                end = i + block_length
                while curr < end:
                    null_pos = buffer.find(b'\x00', curr, end)
                    if null_pos == -1: break
                    t_bytes = buffer[curr:null_pos]
                    if is_valid_cp932(t_bytes):
                        try: extracted_texts.append(f"[CHOICE]{t_bytes.decode('cp932')}")
                        except: pass
                    curr = null_pos + 1
                i += block_length
                continue
        i += 1

    if extracted_texts:
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            for text in extracted_texts: f.write(text + '\n')

def inject_text(input_bin_path: str, input_txt_path: str, output_bin_path: str):
    """将翻译后的文本注入脚本"""
    file_name = os.path.basename(input_bin_path)
    print(f"正在处理: {file_name} ...", end='\r')
    
    try:
        with open(input_bin_path, 'rb') as f:
            buffer = bytearray(f.read())
        with open(input_txt_path, 'r', encoding='utf-8') as f:
            translations = [line.strip('\n') for line in f.readlines()]
    except: return
        
    new_buffer = bytearray()
    idx, dvi, i, size = 0, 0, 0, len(buffer)
    
    while i < size:
        # 对话/名字注入
        if i + 24 <= size and (buffer[i] in [0x2a, 0x29, 0x28, 0x27]) and buffer[i+1:i+4] == b'\x00\x00\x00':
            op = buffer[i]
            length = struct.unpack('<I', buffer[i+4:i+8])[0]
            if 24 <= length < 100000 and i + length <= size:
                t_bytes = buffer[i+24 : i+length-1]
                if is_valid_cp932(t_bytes):
                    if idx < len(translations) and not translations[idx].startswith("[CHOICE]"):
                        text = translations[idx]
                        idx += 1
                        if op == 0x27 and text.startswith("[NAME]"): text = text[6:]
                        
                        # 核心转换：此处可改为 'gbk' 如果你做了汇编补丁
                        new_text = text.encode('cp932', errors='ignore')
                        new_len = 24 + len(new_text) + 1
                        dvi += (new_len - length)
                        
                        new_buffer.extend(struct.pack('<II', op, new_len))
                        new_buffer.extend(buffer[i+8 : i+24])
                        new_buffer.extend(new_text + b'\x00')
                        i += length
                        continue
                new_buffer.extend(buffer[i : i + length])
                i += length
                continue

        # 选项注入 (0D)
        elif i + 24 < size and buffer[i] == 0x0d and buffer[i+1:i+4] == b'\x00\x00\x00':
            length = struct.unpack('<I', buffer[i+4:i+8])[0]
            if 24 <= length < 100000 and i + length <= size:
                choices = []
                while idx < len(translations) and translations[idx].startswith("[CHOICE]"):
                    choices.append(translations[idx][8:])
                    idx += 1
                
                if choices:
                    new_texts = bytearray()
                    for c in choices:
                        new_texts.extend(c.encode('cp932', errors='ignore') + b'\x00')
                    
                    new_len = 24 + len(new_texts)
                    dvi += (new_len - length)
                    
                    header = bytearray(buffer[i+8 : i+24])
                    struct.pack_into('<I', header, 4, len(choices)) # 更新选项数量
                    
                    new_buffer.extend(b'\x0d\x00\x00\x00')
                    new_buffer.extend(struct.pack('<I', new_len))
                    new_buffer.extend(header)
                    new_buffer.extend(new_texts)
                    i += length
                    continue
                new_buffer.extend(buffer[i : i + length])
                i += length
                continue

        # 修正跳转指针 (0B/0C 指令)
        elif i + 12 <= size and buffer[i] in [0x0b, 0x0c] and buffer[i+1:i+4] == b'\x00\x00\x00':
            # 这是一个跳转指令，后面通常跟着 18 00 00 00 和 目标地址
            if buffer[i+4:i+8] == b'\x18\x00\x00\x00':
                orgi_jump = struct.unpack('<I', buffer[i+8:i+12])[0]
                new_buffer.extend(buffer[i:i+8])
                new_buffer.extend(struct.pack('<I', orgi_jump + dvi))
                i += 12
                continue
        
        new_buffer.append(buffer[i])
        i += 1

    os.makedirs(os.path.dirname(output_bin_path), exist_ok=True)
    with open(output_bin_path, 'wb') as f: f.write(new_buffer)
    print(f"封包完成 -> {file_name}      ")

def main():
    if len(sys.argv) < 2:
        print("AZSystem Tool - 增强版")
        return

    mode = sys.argv[1].lower()
    if mode == "dump":
        in_f, out_f = sys.argv[2], sys.argv[3]
        for root, _, files in os.walk(in_f):
            for file in files:
                dump_text(os.path.join(root, file), os.path.join(out_f, file + ".txt"))
    elif mode == "inject":
        in_bin, in_txt, out_f = sys.argv[2], sys.argv[3], sys.argv[4]
        for root, _, files in os.walk(in_bin):
            for file in files:
                bin_p = os.path.join(root, file)
                txt_p = os.path.join(in_txt, file + ".txt")
                out_p = os.path.join(out_f, file)
                if os.path.exists(txt_p):
                    inject_text(bin_p, txt_p, out_p)
                else:
                    os.makedirs(os.path.dirname(out_p), exist_ok=True)
                    with open(bin_p, 'rb') as f1, open(out_p, 'wb') as f2: f2.write(f1.read())

if __name__ == "__main__":
    main()