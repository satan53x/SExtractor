#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
简化的DAT文件重新封包工具
使用原始压缩索引，只修改文件偏移和大小信息
实现真正的伪压缩：文件数据不压缩，但保持索引区压缩
"""

import struct
import os
import sys
from pathlib import Path

def lz_decompress(data):
    """LZSS解压缩算法"""
    output = bytearray()
    frame = bytearray(0x1000)
    frame_pos = 0xFEE
    
    pos = 0
    bits = 0
    mask = 0
    
    while pos < len(data):
        mask >>= 1
        if mask == 0:
            if pos >= len(data):
                break
            bits = data[pos]
            pos += 1
            mask = 0x80
        
        if (bits & mask) == 0:
            # 直接字节
            if pos >= len(data):
                break
            b = data[pos]
            pos += 1
            output.append(b)
            frame[frame_pos & 0xFFF] = b
            frame_pos += 1
        else:
            # LZ引用
            if pos + 1 >= len(data):
                break
            offset_data = struct.unpack('<H', data[pos:pos+2])[0]
            pos += 2
            count = (offset_data & 0xF) + 3
            offset = offset_data >> 4
            
            for _ in range(count):
                v = frame[offset & 0xFFF]
                frame[frame_pos & 0xFFF] = v
                frame_pos += 1
                output.append(v)
                offset += 1
    
    return bytes(output)

def lz_compress_simple(data):
    """
    简单的LZSS压缩 - 不进行实际压缩，只是按格式包装
    这样可以确保兼容性，虽然压缩率不高
    """
    if not data:
        return b''
    
    output = bytearray()
    pos = 0
    
    while pos < len(data):
        # 每8个字节为一组，全部标记为直接字节
        flag_byte = 0x00  # 所有位都是0，表示都是直接字节
        output.append(flag_byte)
        
        # 添加最多8个直接字节
        for _ in range(8):
            if pos >= len(data):
                break
            output.append(data[pos])
            pos += 1
    
    return bytes(output)

def simple_repack_dat(original_dat, source_dir, output_dat):
    """
    简化的重新封包方法
    读取原始压缩索引，修改其中的偏移和大小信息，然后重新压缩
    """
    print("="*60)
    print("简化DAT文件重新封包")
    print("="*60)
    print(f"原始DAT文件: {original_dat}")
    print(f"源文件目录: {source_dir}")
    print(f"输出DAT文件: {output_dat}")
    print()
    
    # 读取原始DAT文件
    with open(original_dat, 'rb') as f:
        f.seek(0, 2)
        file_size = f.tell()
        
        # 读取尾部信息（-8情况：只有压缩大小和解压大小）
        f.seek(file_size - 8)
        packed_size = struct.unpack('<I', f.read(4))[0] ^ 0xFFFFFFFF
        unpacked_size = struct.unpack('<I', f.read(4))[0] ^ 0xFFFFFFFF
        
        print(f"原始文件大小: {file_size:,} 字节")
        print(f"索引区压缩大小: {packed_size:,} 字节")
        print(f"索引区解压后大小: {unpacked_size:,} 字节")
        
        # 读取并解压原始索引
        index_start = file_size - 8 - packed_size
        f.seek(index_start)
        original_packed_index = f.read(packed_size)
        original_unpacked_index = lz_decompress(original_packed_index)
        
        print(f"文件条目数: {unpacked_size // 0x20}")
    
    # 检查源文件目录
    source_path = Path(source_dir)
    if not source_path.exists():
        raise FileNotFoundError(f"源文件目录不存在: {source_dir}")
    
    print()
    print("开始重新封包...")
    
    # 构建新的数据区
    new_data = bytearray()
    current_offset = 0
    
    # 修改索引区
    new_index = bytearray(original_unpacked_index)
    entry_count = len(original_unpacked_index) // 0x20
    
    processed_files = 0
    missing_files = 0
    
    for i in range(entry_count):
        entry_offset = i * 0x20
        entry_data = new_index[entry_offset:entry_offset + 0x20]
        
        # 解析条目
        flags = struct.unpack('<I', entry_data[0:4])[0]
        name_bytes = entry_data[4:0x14]
        name_end = name_bytes.find(b'\x00')
        name = name_bytes[:name_end].decode('shift-jis', errors='ignore') if name_end != -1 else ""
        
        source_file = source_path / name
        
        if source_file.exists():
            # 读取文件数据
            with open(source_file, 'rb') as f:
                file_data = f.read()
            
            # 写入数据区（不压缩）
            file_offset = current_offset
            file_size = len(file_data)
            new_data.extend(file_data)
            current_offset += file_size
            
            # 修改索引条目中的标志、偏移和大小
            new_flags = flags & ~0xFF0000  # 清除压缩标志
            new_flags = new_flags & ~0x2000000  # 清除StoredSize标志
            
            # 更新索引条目
            struct.pack_into('<I', new_index, entry_offset, new_flags)  # flags
            struct.pack_into('<I', new_index, entry_offset + 0x14, file_offset)  # offset
            struct.pack_into('<I', new_index, entry_offset + 0x18, file_size)  # size
            struct.pack_into('<I', new_index, entry_offset + 0x1C, file_size)  # unpacked_size
            
            print(f"  [{i:3d}] {name:30s} - {file_size:8,} 字节")
            processed_files += 1
            
        else:
            print(f"  [{i:3d}] {name:30s} - 文件缺失!")
            missing_files += 1
            # 创建空文件条目
            new_flags = flags & ~0xFF0000 & ~0x2000000
            struct.pack_into('<I', new_index, entry_offset, new_flags)
            struct.pack_into('<I', new_index, entry_offset + 0x14, current_offset)  # offset
            struct.pack_into('<I', new_index, entry_offset + 0x18, 0)  # size = 0
            struct.pack_into('<I', new_index, entry_offset + 0x1C, 0)  # unpacked_size = 0
    
    print()
    print(f"处理完成: {processed_files} 个文件成功, {missing_files} 个文件缺失")
    
    # 使用简单压缩重新压缩索引
    print("正在重新压缩索引区...")
    compressed_index = lz_compress_simple(new_index)
    
    print(f"  索引区原始大小: {len(new_index):,} 字节")
    print(f"  索引区压缩后大小: {len(compressed_index):,} 字节")
    print(f"  压缩率: {len(compressed_index)/len(new_index):.2%}")
    
    # 验证压缩结果
    decompressed_test = lz_decompress(compressed_index)
    if decompressed_test == new_index:
        print("  索引压缩验证成功")
    else:
        print("  警告: 索引压缩验证失败!")
    
    # 写入新的DAT文件
    print()
    print("正在写入DAT文件...")
    
    with open(output_dat, 'wb') as f:
        # 写入数据区（未压缩）
        f.write(new_data)
        
        # 写入压缩的索引区
        f.write(compressed_index)
        
        # 写入尾部信息（-8情况：只写入压缩大小和解压大小）
        packed_size = len(compressed_index)
        unpacked_size = len(new_index)
        f.write(struct.pack('<I', packed_size ^ 0xFFFFFFFF))
        f.write(struct.pack('<I', unpacked_size ^ 0xFFFFFFFF))
    
    output_size = len(new_data) + len(compressed_index) + 8
    
    print()
    print("="*60)
    print("重新封包完成!")
    print("="*60)
    print(f"数据区大小: {len(new_data):,} 字节")
    print(f"索引区大小: {len(new_index):,} 字节 (压缩后: {len(compressed_index):,} 字节)")
    print(f"总文件大小: {output_size:,} 字节")
    print(f"处理文件数: {processed_files}/{entry_count}")
    if missing_files > 0:
        print(f"缺失文件数: {missing_files}")
    print()
    print(f"新DAT文件已保存: {output_dat}")

def main():
    """主函数"""
    if len(sys.argv) < 3:
        print("简化DAT文件重新封包工具")
        print()
        print("用法:")
        print(f"  python {sys.argv[0]} <原始.dat> <源文件目录> [输出.dat]")
        print()
        print("参数:")
        print("  原始.dat     - 原始DAT文件，用于读取文件索引信息")
        print("  源文件目录   - 包含要封包的文件的目录")
        print("  输出.dat     - 输出的新DAT文件（可选，默认为 simple_repacked.dat）")
        print()
        print("示例:")
        print(f"  python {sys.argv[0]} script.dat script_extracted script_simple.dat")
        print()
        print("说明:")
        print("  - 使用简单的压缩算法确保兼容性")
        print("  - 文件数据不压缩，索引区使用简单压缩")
        print("  - 保持原始的文件顺序和名称")
        return
    
    original_dat = sys.argv[1]
    source_dir = sys.argv[2]
    output_dat = sys.argv[3] if len(sys.argv) > 3 else 'simple_repacked.dat'
    
    try:
        simple_repack_dat(original_dat, source_dir, output_dat)
    except FileNotFoundError as e:
        print(f"错误: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == '__main__':
    main()
