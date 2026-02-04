#!/usr/bin/env python3

import sys
import os

def pad_shorter_file(file1, file2):
    # 获取文件大小
    with open(file1, 'rb') as f1, open(file2, 'rb') as f2:
        data1 = f1.read()
        data2 = f2.read()
    
    len1, len2 = len(data1), len(data2)
    
    # 如果文件大小相同，直接返回
    if len1 == len2:
        print(f"两个文件大小相同 ({len1} 字节)，无需填充")
        return
    
    # 确定哪个文件需要填充
    if len1 > len2:
        larger, smaller = data1, data2
        larger_name, smaller_name = file1, file2
    else:
        larger, smaller = data2, data1
        larger_name, smaller_name = file2, file1
    
    # 创建填充内容
    padding_size = len(larger) - len(smaller)
    padded = smaller + b'\x00' * padding_size
    
    # 保存填充后的文件
    output_name = f"{smaller_name}_padded"
    with open(output_name, 'wb') as f:
        f.write(padded)
    
    print(f"原文件: {smaller_name} ({len(smaller)} 字节)")
    print(f"填充后: {output_name} ({len(padded)} 字节)")
    print(f"参考文件: {larger_name} ({len(larger)} 字节)")
    print(f"填充字节数: {padding_size}")

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("用法: python script.py <文件1> <文件2>")
        sys.exit(1)
    
    pad_shorter_file(sys.argv[1], sys.argv[2])