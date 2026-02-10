#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FGA文件Huffman压缩封包工具
用法: python pack_fga_huffman.py <源文件夹> <输出.fga>
基于garbro的Huffman压缩算法实现
"""

import struct
import os
import sys
from collections import Counter
import heapq

class HuffmanNode:
    """Huffman树节点"""
    def __init__(self, char=None, freq=0, left=None, right=None):
        self.char = char
        self.freq = freq
        self.left = left
        self.right = right
    
    def __lt__(self, other):
        return self.freq < other.freq
    
    def is_leaf(self):
        return self.char is not None

class BitWriter:
    """位写入器（MSB优先）"""
    def __init__(self):
        self.bits = []
    
    def write_bit(self, bit):
        """写入一个位"""
        self.bits.append(1 if bit else 0)
    
    def write_bits(self, value, count):
        """写入多个位"""
        for i in range(count - 1, -1, -1):
            self.write_bit((value >> i) & 1)
    
    def to_bytes(self):
        """转换为字节数组"""
        # 补齐到8的倍数
        while len(self.bits) % 8 != 0:
            self.bits.append(0)
        
        result = bytearray()
        for i in range(0, len(self.bits), 8):
            byte = 0
            for j in range(8):
                byte = (byte << 1) | self.bits[i + j]
            result.append(byte)
        return bytes(result)

def build_huffman_tree(data):
    """构建Huffman树"""
    if not data:
        return None
    
    # 统计字节频率
    freq = Counter(data)
    
    # 创建优先队列
    heap = [HuffmanNode(char=byte, freq=count) for byte, count in freq.items()]
    heapq.heapify(heap)
    
    # 构建Huffman树
    while len(heap) > 1:
        left = heapq.heappop(heap)
        right = heapq.heappop(heap)
        parent = HuffmanNode(freq=left.freq + right.freq, left=left, right=right)
        heapq.heappush(heap, parent)
    
    return heap[0] if heap else None

def build_huffman_codes(root):
    """从Huffman树构建编码表"""
    if root is None:
        return {}
    
    codes = {}
    
    def traverse(node, code):
        if node.is_leaf():
            codes[node.char] = code if code else '0'
        else:
            if node.left:
                traverse(node.left, code + '0')
            if node.right:
                traverse(node.right, code + '1')
    
    traverse(root, '')
    return codes

def write_huffman_tree(node, writer):
    """
    写入Huffman树（递归）
    格式：1位标记 + 数据
    - 如果是分支节点：写入1，然后递归写入左右子树
    - 如果是叶子节点：写入0，然后写入8位字节值
    """
    if node.is_leaf():
        # 叶子节点：0 + 8位字节值
        writer.write_bit(0)
        writer.write_bits(node.char, 8)
    else:
        # 分支节点：1 + 左子树 + 右子树
        writer.write_bit(1)
        write_huffman_tree(node.left, writer)
        write_huffman_tree(node.right, writer)

def huffman_compress_garbro(data):
    """
    使用garbro兼容的Huffman压缩
    格式：[解压后大小:4字节] + [Huffman树] + [压缩数据]
    返回: (压缩后的数据, 原始大小, 压缩大小)
    """
    if not data:
        return b'', 0, 0
    
    original_size = len(data)
    
    # 构建Huffman树和编码表
    tree = build_huffman_tree(data)
    if tree is None:
        return b'', 0, 0
    
    codes = build_huffman_codes(tree)
    
    # 创建位写入器
    writer = BitWriter()
    
    # 写入Huffman树
    write_huffman_tree(tree, writer)
    
    # 编码数据
    for byte in data:
        code = codes[byte]
        for bit in code:
            writer.write_bit(bit == '1')
    
    # 转换为字节
    compressed_data = writer.to_bytes()
    
    # 构建最终格式：[解压后大小:4字节] + [压缩数据]
    result = bytearray()
    result.extend(struct.pack('<I', original_size))
    result.extend(compressed_data)
    
    return bytes(result), original_size, len(result)

def pack_fga_huffman(source_folder, output_fga):
    """
    将文件夹中的文件封包为FGA格式（使用garbro兼容的Huffman压缩）
    
    FGA文件结构:
    - 索引块大小: 0x318 (792字节)
    - 每个索引块最多32个条目
    - 每个条目: 24字节 (0x18)
      - 文件名: 12字节 (以null结尾)
      - 文件偏移: 4字节 (小端)
      - 文件大小: 4字节 (小端) - 原始未压缩的大小
      - 保留字段: 4字节 (通常为0)
    - 当索引块满时，使用12个0xFF标记跳转到下一个索引块
    """
    
    # 收集所有文件
    files = []
    for filename in sorted(os.listdir(source_folder)):
        filepath = os.path.join(source_folder, filename)
        if os.path.isfile(filepath):
            files.append(filename)
    
    if not files:
        print(f"错误: 文件夹 '{source_folder}' 中没有文件")
        return False
    
    print(f"找到 {len(files)} 个文件")
    
    # 计算需要的索引块数量
    max_entries_per_block = 32
    num_blocks = (len(files) + max_entries_per_block - 1) // max_entries_per_block
    
    print(f"需要 {num_blocks} 个索引块")
    
    index_block_size = 0x318
    
    with open(output_fga, 'wb') as f:
        file_data_list = []
        
        # 读取并压缩所有文件数据
        print("\n压缩文件...")
        total_original_size = 0
        total_compressed_size = 0
        
        for filename in files:
            filepath = os.path.join(source_folder, filename)
            with open(filepath, 'rb') as file_in:
                original_data = file_in.read()
                original_size = len(original_data)
                
                # 压缩数据
                compressed_data, orig_size, comp_size = huffman_compress_garbro(original_data)
                
                compression_ratio = (1 - comp_size / original_size) * 100 if original_size > 0 else 0
                print(f"  {filename}: {original_size} -> {comp_size} 字节 (压缩率: {compression_ratio:.1f}%)")
                
                file_data_list.append((filename, compressed_data, original_size))
                total_original_size += original_size
                total_compressed_size += comp_size
        
        overall_ratio = (1 - total_compressed_size / total_original_size) * 100 if total_original_size > 0 else 0
        print(f"\n总计: {total_original_size} -> {total_compressed_size} 字节 (总压缩率: {overall_ratio:.1f}%)")
        
        # 计算文件偏移
        current_offset = index_block_size
        file_entries = []
        
        for i, (filename, data, original_size) in enumerate(file_data_list):
            # 文件名最多12字节，超过才截断
            if len(filename) > 12:
                print(f"警告: 文件名 '{filename}' 过长，将被截断")
                filename = filename[:12]
            
            compressed_size = len(data)
            
            file_entries.append({
                'name': filename,
                'offset': current_offset,
                'size': compressed_size,  # 索引中存储：4字节头+压缩数据的总大小
                'original_size': original_size,  # 原始大小（用于显示）
                'data': data
            })
            
            current_offset += compressed_size
        
        # 重新计算偏移，考虑多个索引块
        if num_blocks > 1:
            file_entries = []
            current_offset = index_block_size
            
            for block_idx in range(num_blocks):
                start_idx = block_idx * max_entries_per_block
                end_idx = min(start_idx + max_entries_per_block, len(file_data_list))
                
                for i in range(start_idx, end_idx):
                    filename, data, original_size = file_data_list[i]
                    # 文件名最多12字节，超过才截断
                    if len(filename) > 12:
                        filename = filename[:12]
                    
                    compressed_size = len(data)
                    
                    file_entries.append({
                        'name': filename,
                        'offset': current_offset,
                        'size': compressed_size,  # 索引中存储：4字节头+压缩数据的总大小
                        'original_size': original_size,  # 原始大小（用于显示）
                        'data': data,
                        'block_index': block_idx
                    })
                    
                    current_offset += compressed_size
                
                if block_idx < num_blocks - 1:
                    next_index_offset = current_offset
                    file_entries[start_idx]['next_index_offset'] = next_index_offset
                    current_offset += index_block_size
        
        # 写入第一个索引块
        print(f"\n写入索引块 0 (偏移 0x0)")
        index_buffer = bytearray(index_block_size)
        
        entries_in_block = min(max_entries_per_block, len(file_entries))
        
        for i in range(entries_in_block):
            entry = file_entries[i]
            pos = i * 0x18
            
            name_bytes = entry['name'].encode('ascii')
            index_buffer[pos:pos+len(name_bytes)] = name_bytes
            
            struct.pack_into('<I', index_buffer, pos+0xC, entry['offset'])
            struct.pack_into('<I', index_buffer, pos+0x10, entry['size'])
            struct.pack_into('<I', index_buffer, pos+0x14, 0)
            
            print(f"  条目 {i:2d}: {entry['name']:12s} | 偏移: 0x{entry['offset']:08X} | 索引大小: {entry['size']:6d} | 原始: {entry['original_size']:6d}")
        
        if num_blocks > 1:
            pos = entries_in_block * 0x18
            for j in range(12):
                index_buffer[pos + j] = 0xFF
            
            next_index_offset = index_block_size
            for i in range(entries_in_block):
                next_index_offset += file_entries[i]['size']
            
            struct.pack_into('<I', index_buffer, pos+0xC, next_index_offset)
            print(f"  跳转标记: 下一个索引块在 0x{next_index_offset:08X}")
        
        f.write(index_buffer)
        
        print(f"\n写入第一个数据区")
        for i in range(entries_in_block):
            entry = file_entries[i]
            f.write(entry['data'])
            print(f"  写入文件: {entry['name']} ({entry['size']} 字节)")
        
        # 写入后续的索引块和数据区
        for block_idx in range(1, num_blocks):
            start_idx = block_idx * max_entries_per_block
            end_idx = min(start_idx + max_entries_per_block, len(file_entries))
            entries_in_block = end_idx - start_idx
            
            index_offset = f.tell()
            print(f"\n写入索引块 {block_idx} (偏移 0x{index_offset:X})")
            
            index_buffer = bytearray(index_block_size)
            
            for i in range(entries_in_block):
                entry = file_entries[start_idx + i]
                pos = i * 0x18
                
                name_bytes = entry['name'].encode('ascii')
                index_buffer[pos:pos+len(name_bytes)] = name_bytes
                
                struct.pack_into('<I', index_buffer, pos+0xC, entry['offset'])
                struct.pack_into('<I', index_buffer, pos+0x10, entry['size'])
                struct.pack_into('<I', index_buffer, pos+0x14, 0)
                
                print(f"  条目 {i:2d}: {entry['name']:12s} | 偏移: 0x{entry['offset']:08X} | 索引大小: {entry['size']:6d} | 原始: {entry['original_size']:6d}")
            
            if block_idx < num_blocks - 1:
                pos = entries_in_block * 0x18
                for j in range(12):
                    index_buffer[pos + j] = 0xFF
                
                next_index_offset = f.tell() + index_block_size
                for i in range(entries_in_block):
                    next_index_offset += file_entries[start_idx + i]['size']
                
                struct.pack_into('<I', index_buffer, pos+0xC, next_index_offset)
                print(f"  跳转标记: 下一个索引块在 0x{next_index_offset:08X}")
            
            f.write(index_buffer)
            
            print(f"\n写入数据区 {block_idx}")
            for i in range(entries_in_block):
                entry = file_entries[start_idx + i]
                f.write(entry['data'])
                print(f"  写入文件: {entry['name']} ({entry['size']} 字节)")
    
    print(f"\n封包完成！输出文件: {output_fga}")
    print(f"总文件数: {len(files)}")
    print(f"总大小: {os.path.getsize(output_fga)} 字节")
    print(f"原始数据大小: {total_original_size} 字节")
    print(f"压缩后大小: {total_compressed_size} 字节")
    print(f"总压缩率: {overall_ratio:.1f}%")
    return True

def main():
    if len(sys.argv) != 3:
        print("用法: python pack_fga_huffman.py <源文件夹> <输出.fga>")
        print("示例: python pack_fga_huffman.py scr output.fga")
        sys.exit(1)
    
    source_folder = sys.argv[1]
    output_fga = sys.argv[2]
    
    if not os.path.isdir(source_folder):
        print(f"错误: 文件夹 '{source_folder}' 不存在")
        sys.exit(1)
    
    if not pack_fga_huffman(source_folder, output_fga):
        sys.exit(1)

if __name__ == '__main__':
    main()
