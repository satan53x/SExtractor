import os
import struct
import json

def to_bytes(value, length):
    return value.to_bytes(length, byteorder='little')

def open_file_b(path):
    with open(path, "rb") as f:
        return f.read()

def pack_drs_engine(src_folder, output_path):
    """经典 DRS 引擎打包逻辑"""
    print("[*] 读取配置: 正在执行【早期 DRS 引擎】打包规范...")
    files = os.listdir(src_folder)
    files.sort() # DRS规范：字母排序
    num_files = len(files)
    dir_size = (num_files + 1) * 0x10
    current_offset = 2 + dir_size

    entries_data = bytearray()
    file_datas = bytearray()

    for file in files:
        name_bytes = file.upper().encode("932")
        if len(name_bytes) > 12:
            print(f"⚠️ 警告：文件名 {file} 超过12字节，将被截断！")
            name_bytes = name_bytes[:12]
        else:
            name_bytes += b'\x00' * (12 - len(name_bytes))
        
        entries_data.extend(name_bytes)
        entries_data.extend(to_bytes(current_offset, 4))
        
        data = open_file_b(os.path.join(src_folder, file))
        file_datas.extend(data)
        current_offset += len(data)

    entries_data.extend(b'\x00' * 12)
    entries_data.extend(to_bytes(current_offset, 4))

    with open(output_path, "wb") as f:
        f.write(to_bytes(dir_size, 2))
        f.write(entries_data)
        f.write(file_datas)
    print("[!] DRS 封包完成！")

def pack_mpx_engine(src_folder, output_path, file_order):
    """新版 MPX / IKURA 引擎打包逻辑"""
    print("[*] 读取配置: 正在执行【新版 MPX (IKURA) 引擎】严格对齐打包规范...")
    magic = b"SM2MPX10"
    num_files = len(file_order)
    headerlen = 0x20 + 0x14 * num_files
    filestart = (headerlen + 15) & ~15 
    unk1 = b"isf_r" + b"\x00" * 7 + b"\x20\x00\x00\x00"

    entrys = []
    datas = []

    for file_name in file_order:
        name_bytes = file_name.encode("932")
        file_path = os.path.join(src_folder, file_name)
        if not os.path.exists(file_path):
            continue

        entry = name_bytes + b"\x00" * (0x0c - len(name_bytes))
        entry += to_bytes(filestart, 4)
        data = open_file_b(file_path)
        entry += to_bytes(len(data), 4)
        
        entrys.append(entry)
        datas.append(data)
        filestart += (len(data) + 15) & ~15

    with open(output_path, "wb") as f:
        f.write(magic)
        f.write(to_bytes(num_files, 4))
        f.write(to_bytes(headerlen, 4))
        f.write(unk1)
        for entry in entrys: f.write(entry)
        f.write(b"\x00" * (((headerlen + 15) & ~15) - headerlen))
        for data in datas:
            f.write(data)
            f.write(b"\x00" * (((len(data) + 15) & ~15) - len(data)))
    print("[!] MPX (IKURA) 封包完成！")

def auto_pack_isf(src_folder, output_dir):
    """终极一键智能打包入口，完全依赖 JSON 配置文件"""
    if not os.path.exists("file_order.json"):
        raise FileNotFoundError("当前目录下找不到 file_order.json 工程配置，请先执行模块A解包！")
        
    with open("file_order.json", "r", encoding="utf-8") as f:
        config_data = json.load(f)
        
    orig_name = config_data.get("original_name", "Isf")
    engine = config_data.get("engine", "MPX") # 找不到默认当 MPX 处
    
    output_path = os.path.join(output_dir, orig_name)
    os.makedirs(output_dir, exist_ok=True)

    # 根据配置自动分流
    if engine == "MPX":
        pack_mpx_engine(src_folder, output_path, config_data.get("file_order", []))
    else:
        pack_drs_engine(src_folder, output_path)
    
    return output_path