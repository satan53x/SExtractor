#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import os
import struct
import zlib
from pathlib import Path

def pack_files_to_bin(input_folder, output_file, compress=True):
    """
    将文件夹封包为BIN/OZ格式的归档文件
    
    Args:
        input_folder: 输入文件夹路径
        output_file: 输出bin文件路径
        compress: 是否压缩文件数据（默认True）
    """
    # 获取文件夹中的所有文件
    input_path = Path(input_folder)
    if not input_path.exists() or not input_path.is_dir():
        print(f"错误: 文件夹 '{input_folder}' 不存在")
        return False
    
    # 获取所有文件（按名称排序）
    files = sorted([f for f in input_path.iterdir() if f.is_file()])
    file_count = len(files)
    
    if file_count == 0:
        print(f"错误: 文件夹 '{input_folder}' 中没有文件")
        return False
    
    print(f"找到 {file_count} 个文件")
    
    # 准备文件数据
    file_data_list = []
    for file_path in files:
        print(f"处理文件: {file_path.name}")
        with open(file_path, 'rb') as f:
            raw_data = f.read()
        
        if compress and len(raw_data) > 0:
            # 使用DFLT格式（zlib压缩）
            compressed_data = zlib.compress(raw_data)
            # 如果压缩后反而更大，就不压缩
            if len(compressed_data) < len(raw_data):
                header = b'DFLT'
                header += struct.pack('<I', len(compressed_data))  # 压缩后大小
                header += struct.pack('<I', len(raw_data))        # 原始大小
                file_data = header + compressed_data
            else:
                # 使用DATA格式（未压缩）
                header = b'DATA'
                header += struct.pack('<I', len(raw_data))  # 数据大小
                file_data = header + raw_data
        else:
            # 使用DATA格式（未压缩）
            header = b'DATA'
            header += struct.pack('<I', len(raw_data))  # 数据大小
            file_data = header + raw_data
        
        file_data_list.append(file_data)
    
    # 计算文件偏移
    header_size = 0x0C + (file_count * 4)  # 头部 + 偏移表
    offsets = []
    current_offset = header_size
    
    for file_data in file_data_list:
        offsets.append(current_offset)
        current_offset += len(file_data)
    
    # 写入输出文件
    print(f"写入归档文件: {output_file}")
    with open(output_file, 'wb') as f:
        # 写入文件头
        f.write(b'OZ\x00\x01')  # 签名 0x01005A4F (little-endian)
        f.write(b'OFST')         # 偏移表标记
        f.write(struct.pack('<I', file_count * 4))  # 索引大小
        
        # 写入偏移表
        for offset in offsets:
            f.write(struct.pack('<I', offset))
        
        # 写入文件数据
        for file_data in file_data_list:
            f.write(file_data)
    
    # 可选：生成文件列表
    lst_file = Path(output_file).with_suffix('.lst')
    print(f"生成文件列表: {lst_file}")
    with open(lst_file, 'w', encoding='shift-jis') as f:
        for file_path in files:
            f.write(file_path.name + '\n')
    
    print(f"封包完成！")
    print(f"  归档文件: {output_file}")
    print(f"  文件列表: {lst_file}")
    print(f"  文件数量: {file_count}")
    print(f"  文件大小: {os.path.getsize(output_file)} 字节")
    
    return True

def main():
    """主函数"""
    if len(sys.argv) != 3:
        print("用法: python bin_pack.py 需要封包文件夹 封包文件名.bin")
        print("示例: python bin_pack.py ./images output.bin")
        sys.exit(1)
    
    input_folder = sys.argv[1]
    output_file = sys.argv[2]
    
    # 确保输出文件扩展名是.bin
    if not output_file.lower().endswith('.bin'):
        print("警告: 输出文件应该使用.bin扩展名")
    
    # 执行封包
    success = pack_files_to_bin(input_folder, output_file)
    
    if not success:
        sys.exit(1)

if __name__ == "__main__":
    main()
