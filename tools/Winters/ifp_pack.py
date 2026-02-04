#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
IFP格式封包工具
基于Winters游戏引擎的资源归档格式
使用方法: python 1.py 文件夹 封包.ifp
"""

import os
import sys
import struct
from pathlib import Path


def get_file_type(file_path):
    """根据文件扩展名判断文件类型"""
    ext = file_path.suffix.lower()
    type_map = {
        '.bmp': 0x0B,
        '.png': 0x0C,
        '.jpg': 0x0D,
        '.jpeg': 0x0D,
        '.txt': 0x15,  # script类型
    }
    return type_map.get(ext, 0x15)  # 默认为script类型


def pack_ifp(input_folder, output_file):
    """
    将文件夹中的文件打包成IFP格式
    
    Args:
        input_folder: 输入文件夹路径
        output_file: 输出IFP文件路径
    """
    input_path = Path(input_folder)
    
    if not input_path.exists() or not input_path.is_dir():
        print(f"错误: 文件夹 '{input_folder}' 不存在")
        return False
    
    # 收集所有文件，按文件名中的数字排序
    files = []
    for file_path in input_path.iterdir():
        if file_path.is_file():
            files.append(file_path)
    
    # 提取文件名中的数字进行排序
    def get_file_number(path):
        import re
        match = re.search(r'#(\d+)', path.name)
        return int(match.group(1)) if match else 0
    
    files.sort(key=get_file_number)
    
    if not files:
        print(f"错误: 文件夹 '{input_folder}' 中没有文件")
        return False
    
    print(f"找到 {len(files)} 个文件")
    
    # 计算索引和数据位置
    file_count = len(files)
    index_start = 0x660  # 索引固定位置
    data_start = 0x8010  # 数据固定起始位置
    
    # 准备文件数据和索引
    file_data_list = []
    index_entries = []
    current_offset = data_start
    
    for file_path in files:
        # 读取文件数据
        with open(file_path, 'rb') as f:
            file_data = f.read()
        
        file_size = len(file_data)
        file_type = get_file_type(file_path)
        
        # 创建索引条目（每个0x10字节）
        index_entry = struct.pack('<HHIII',
            file_type,      # type (2字节)
            0x00,           # mask_type (2字节) - 暂不支持遮罩
            current_offset, # offset (4字节)
            file_size,      # size (4字节)
            0x00            # mask_size (4字节) - 暂不支持遮罩
        )
        
        index_entries.append(index_entry)
        file_data_list.append(file_data)
        
        current_offset += file_size
        print(f"  添加: {file_path.name} (类型: 0x{file_type:02X}, 大小: {file_size} 字节)")
    
    # 计算总文件大小
    total_size = current_offset
    
    # 计算索引区大小（包含结束标记）
    index_size = (file_count + 1) * 0x10
    
    # 写入IFP文件
    with open(output_file, 'wb') as f:
        # 写入文件头（0x00-0x1F，共32字节）
        # 0x00: "IAGS" 签名
        f.write(b'IAGS')
        
        # 0x04: "_IFP_01     " (12字节)
        f.write(b'_IFP_01     ')
        
        # 0x10: 固定值 1 (4字节)
        f.write(struct.pack('<I', 1))
        
        # 0x14: 固定值 0x10 (4字节)
        f.write(struct.pack('<I', 0x10))
        
        # 0x18: 固定值 0x8000 (4字节)
        f.write(struct.pack('<I', 0x8000))
        
        # 0x1C: 未知/保留 (4字节)
        f.write(struct.pack('<I', 0))
        
        # 0x20: 写入第一个索引条目（特殊处理）
        if index_entries:
            f.write(index_entries[0])
        
        # 0x30到0x660: 全部填充00
        padding_size = index_start - 0x30
        f.write(b'\x00' * padding_size)
        
        # 0x660: 写入剩余的索引条目（从第二个开始）
        for entry in index_entries[1:]:
            f.write(entry)
        
        # 写入最后一个空索引条目（结束标记）
        f.write(b'\x00' * 0x10)
        
        # 从索引结束到0x8010: 填充00
        current_pos = f.tell()
        if current_pos < data_start:
            f.write(b'\x00' * (data_start - current_pos))
        
        # 0x8010: 写入实际文件数据
        for file_data in file_data_list:
            f.write(file_data)
    
    print(f"\n封包完成: {output_file}")
    print(f"总大小: {total_size} 字节")
    print(f"文件数: {file_count}")
    print(f"索引位置: 0x{index_start:08X}")
    print(f"数据起始: 0x{data_start:08X}")
    
    return True


def main():
    """主函数"""
    if len(sys.argv) != 3:
        print("使用方法: python 1.py 文件夹 封包.ifp")
        print("示例: python 1.py ./scr output.ifp")
        sys.exit(1)
    
    input_folder = sys.argv[1]
    output_file = sys.argv[2]
    
    print(f"IFP格式封包工具")
    print(f"输入文件夹: {input_folder}")
    print(f"输出文件: {output_file}")
    print("-" * 50)
    
    success = pack_ifp(input_folder, output_file)
    
    if success:
        print("\n封包成功!")
        sys.exit(0)
    else:
        print("\n封包失败!")
        sys.exit(1)


if __name__ == "__main__":
    main()
