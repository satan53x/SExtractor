#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CAPYBARA DAT 001 格式封包工具
用法1: python 1.py <文件夹路径> <输出文件.dat>
用法2: python 1.py <原文.dat> <文件夹路径> <输出文件.dat>
"""

import os
import sys
import struct

def extract_names_format(original_dat):
    """
    从原始 DAT 文件中提取文件名区域的格式
    
    返回:
        (names_offset, names_data_template) 或 None
    """
    try:
        with open(original_dat, 'rb') as f:
            # 检查文件头
            header = f.read(16)
            if header != b'CAPYBARA DAT 001':
                return None
            
            # 读取文件名区域信息
            f.seek(0x10)
            names_offset = struct.unpack('<I', f.read(4))[0]
            names_length = struct.unpack('<I', f.read(4))[0]
            
            # 读取文件名区域
            f.seek(names_offset)
            names_data = f.read(names_length)
            
            return (names_offset, names_data)
    except Exception as e:
        print(f"警告: 无法读取原始 DAT 文件格式 - {e}")
        return None

def pack_dat(folder_path, output_file, original_dat=None):
    """
    将文件夹中的文件打包成 CAPYBARA DAT 001 格式
    
    参数:
        folder_path: 要打包的文件夹路径
        output_file: 输出的 DAT 文件路径
        original_dat: 原始 DAT 文件路径（可选，用于提取格式）
    """
    # 检查文件夹是否存在
    if not os.path.isdir(folder_path):
        print(f"错误: 文件夹 '{folder_path}' 不存在")
        return False
    
    # 收集所有文件
    files = []
    for root, dirs, filenames in os.walk(folder_path):
        for filename in filenames:
            file_path = os.path.join(root, filename)
            # 获取相对路径作为存档中的文件名
            rel_path = os.path.relpath(file_path, folder_path)
            # 将路径分隔符统一为反斜杠（Windows风格）
            rel_path = rel_path.replace('/', '\\')
            files.append((rel_path, file_path))
    
    if not files:
        print(f"错误: 文件夹 '{folder_path}' 中没有文件")
        return False
    
    print(f"找到 {len(files)} 个文件")
    
    # 尝试从原始 DAT 文件提取格式
    names_offset = 0x00080010  # 默认固定偏移
    names_data = b''
    
    if original_dat and os.path.exists(original_dat):
        print(f"从原始 DAT 文件提取格式: {original_dat}")
        format_info = extract_names_format(original_dat)
        if format_info:
            orig_names_offset, orig_names_data = format_info
            names_offset = orig_names_offset
            
            # 解析原始文件名格式
            orig_names_text = orig_names_data.decode('cp932', errors='ignore')
            orig_lines = orig_names_text.split('\r\n')
            
            # 找出每个文件名后的 \r\n 数量
            print("  原始文件名格式:")
            name_paddings = []
            i = 0
            while i < len(orig_lines):
                line = orig_lines[i].strip()
                if line and line != ':END':
                    # 计算这个文件名后面有多少个空行（\r\n）
                    padding_count = 0
                    j = i + 1
                    while j < len(orig_lines) and not orig_lines[j].strip():
                        padding_count += 1
                        j += 1
                    name_paddings.append(padding_count)
                    print(f"    {line}: {padding_count} 个 \\r\\n")
                    i = j
                else:
                    i += 1
            
            # 使用提取的格式构建新的文件名区域
            for idx, (name, _) in enumerate(files):
                try:
                    name_bytes = name.encode('cp932')
                except UnicodeEncodeError:
                    name_bytes = name.encode('shift_jis', errors='replace')
                
                names_data += name_bytes + b'\r\n'
                
                # 使用对应的填充数量，如果超出则使用最后一个的填充数量
                if idx < len(name_paddings):
                    padding_count = name_paddings[idx]
                else:
                    padding_count = name_paddings[-1] if name_paddings else 0
                
                # 添加额外的 \r\n 填充
                names_data += b'\r\n' * padding_count
            
            # 在 :END 前添加额外的 \r\n\r\n
            names_data += b'\r\n\r\n:END\r\n'
        else:
            print("  无法提取格式，使用默认格式")
            original_dat = None
    
    # 如果没有原始文件或提取失败，使用默认格式
    if not original_dat or not names_data:
        print("使用默认格式: 第一个文件名后超长 \\r\\n，其他文件名后 1 个 \\r\\n")
        for idx, (name, _) in enumerate(files):
            try:
                name_bytes = name.encode('cp932')
            except UnicodeEncodeError:
                name_bytes = name.encode('shift_jis', errors='replace')
            
            names_data += name_bytes + b'\r\n'
            
            # 第一个文件名后面添加超长的 \r\n（总共约 100 个，已经加了 1 个，再加 99 个）
            if idx == 0:
                names_data += b'\r\n' * 99
        
        # 在 :END 前添加额外的 \r\n\r\n
        names_data += b'\r\n\r\n:END\r\n'
    
    names_length = len(names_data)
    
    # 数据区域紧跟在文件名区域后面
    data_offset = names_offset + names_length
    
    # 读取所有文件数据并计算偏移
    file_entries = []
    current_offset = data_offset
    
    for name, file_path in files:
        with open(file_path, 'rb') as f:
            file_data = f.read()
        file_size = len(file_data)
        file_entries.append({
            'name': name,
            'offset': current_offset,
            'size': file_size,
            'data': file_data
        })
        current_offset += file_size
        print(f"  添加: {name} (大小: {file_size} 字节, 偏移: {file_entries[-1]['offset']})")
    
    # 写入 DAT 文件
    try:
        with open(output_file, 'wb') as f:
            # 写入文件头 "CAPYBARA DAT 001" (16字节)
            header = b'CAPYBARA DAT 001'
            f.write(header)
            
            # 写入文件名区域偏移和长度 (偏移 0x10 和 0x14)
            f.write(struct.pack('<I', names_offset))  # 0x10: 文件名区域偏移
            f.write(struct.pack('<I', names_length))  # 0x14: 文件名区域长度
            
            # 写入第一个文件的索引条目 (0x18-0x1F)
            if file_entries:
                f.write(struct.pack('<I', file_entries[0]['offset']))  # 文件偏移
                f.write(struct.pack('<I', file_entries[0]['size']))    # 文件大小
            else:
                f.write(b'\x00' * 8)
            
            # 填充 0x20 到 0x338 之间的空间（用 0x00 填充）
            # 0x338 - 0x20 = 0x318 = 792 字节
            f.write(b'\x00' * 0x318)
            print(f"  填充: 0x318 (792) 字节 (0x00) 从 0x20 到 0x338")
            
            # 写入其他文件的索引条目 (从 0x338 开始)
            for entry in file_entries[1:]:
                f.write(struct.pack('<I', entry['offset']))  # 文件偏移
                f.write(struct.pack('<I', entry['size']))    # 文件大小
            
            # 填充到文件名区域之间的空间（用 0x00 填充）
            current_pos = f.tell()
            padding_size = names_offset - current_pos
            if padding_size > 0:
                f.write(b'\x00' * padding_size)
                print(f"  填充: {padding_size} 字节 (0x00) 从 0x{current_pos:X} 到 0x{names_offset:X}")
            
            # 写入文件名区域
            f.write(names_data)
            
            # 写入实际文件数据
            for entry in file_entries:
                f.write(entry['data'])
        
        print(f"\n成功创建: {output_file}")
        print(f"总大小: {os.path.getsize(output_file)} 字节")
        return True
        
    except Exception as e:
        print(f"错误: 写入文件时出错 - {e}")
        return False

def main():
    """主函数"""
    if len(sys.argv) not in [3, 4]:
        print("用法1: python 1.py <文件夹路径> <输出文件.dat>")
        print("用法2: python 1.py <原文.dat> <文件夹路径> <输出文件.dat>")
        print("\n示例1: python 1.py ./my_folder output.dat")
        print("示例2: python 1.py original.dat ./my_folder output.dat")
        sys.exit(1)
    
    if len(sys.argv) == 3:
        # 不使用原始文件
        original_dat = None
        folder_path = sys.argv[1]
        output_file = sys.argv[2]
    else:
        # 使用原始文件提取格式
        original_dat = sys.argv[1]
        folder_path = sys.argv[2]
        output_file = sys.argv[3]
    
    print(f"CAPYBARA DAT 001 封包工具")
    if original_dat:
        print(f"原始文件: {original_dat}")
    print(f"输入文件夹: {folder_path}")
    print(f"输出文件: {output_file}")
    print("-" * 50)
    
    success = pack_dat(folder_path, output_file, original_dat)
    
    if success:
        sys.exit(0)
    else:
        sys.exit(1)

if __name__ == '__main__':
    main()
