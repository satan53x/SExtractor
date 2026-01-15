import struct
import os
from pathlib import Path

def write_string(file, string):
    """写入一个长度前缀的字符串"""
    if not string:
        file.write(struct.pack('B', 0))
        return 1
    
    encoded = string.encode('utf-8')
    length = len(encoded)
    if length > 255:
        print(f"警告: 字符串 '{string}' 太长 ({length} 字节)，将被截断")
        encoded = encoded[:255]
        length = 255
    
    file.write(struct.pack('B', length))
    file.write(encoded)
    return 1 + length

def pack_arc(input_dir, output_file=None):
    """
    将目录打包为ARC文件
    
    参数:
        input_dir: 输入目录路径
        output_file: 输出ARC文件路径，默认为输入目录名加.arc后缀
    """
    
    if not os.path.exists(input_dir):
        print(f"错误: 目录 '{input_dir}' 不存在")
        return
    
    # 设置输出文件路径
    if output_file is None:
        output_file = os.path.join(os.path.dirname(input_dir), 
                                  f"{os.path.basename(input_dir)}.arc")
    
    # 收集所有文件
    file_list = []
    for root, dirs, files in os.walk(input_dir):
        for file in files:
            file_path = os.path.join(root, file)
            rel_path = os.path.relpath(file_path, input_dir)
            file_list.append((file_path, rel_path))
    
    print(f"找到 {len(file_list)} 个文件")
    
    # 创建输出文件
    with open(output_file, 'wb') as f:
        # 写入文件头
        f.write(b'@ARCH000')
        write_string(f, '20241122095209')
        
        # 第一步：收集索引信息并写入文件数据
        index_entries = []
        
        print("写入文件数据...")
        for i, (file_path, rel_path) in enumerate(file_list):
            print(f"  处理文件 {i+1}/{len(file_list)}: {rel_path}")
            
            # 记录当前文件偏移
            file_offset = f.tell()
            
            # 读取并写入文件内容
            with open(file_path, 'rb') as src_file:
                file_data = src_file.read()
                f.write(file_data)
            
            file_length = len(file_data)
            
            # 准备索引条目
            file_name = os.path.basename(file_path)
            # 路径：使用相对路径，如果只是文件名则使用空字符串
            path_str = os.path.dirname(rel_path) if os.path.dirname(rel_path) else ""
            
            index_entries.append({
                'filename': file_name,
                'offset': file_offset,
                'length': file_length,
                'path': path_str
            })
        
        # 记录索引表起始位置
        index_start = f.tell()
        print(f"\n索引表起始位置: 0x{index_start:08X}")
        
        # 第二步：写入索引数量
        index_count = len(index_entries)
        f.write(struct.pack('<I', index_count))
        
        # 第三步：写入每个索引条目
        print(f"写入 {index_count} 个索引条目...")
        index_size = 4  # 从索引数量开始计数
        
        for i, entry in enumerate(index_entries):
            if i % 100 == 0 and i > 0:
                print(f"  已写入 {i}/{index_count} 个索引...")
            
            # 写入文件名（长度前缀字符串）
            index_size += write_string(f, entry['filename'])
            
            # 写入文件偏移和长度（8字节）
            f.write(struct.pack('<Q', entry['offset']))
            f.write(struct.pack('<Q', entry['length']))
            index_size += 16
            
            # 写入固定字节 0x4E
            f.write(struct.pack('B', 0x4E))
            index_size += 1
            
            # 写入路径字符串（长度前缀字符串）
            index_size += write_string(f, entry['path'])
        
        # 第四步：写入索引表起始地址（最后8字节）
        f.write(struct.pack('<Q', index_start))
        index_size += 8
        
        # 获取文件总大小
        total_size = f.tell()
        
        print(f"\n打包完成！")
        print(f"输出文件: {output_file}")
        print(f"总大小: {total_size:,} 字节")
        print(f"数据部分: {index_start:,} 字节")
        print(f"索引表: {index_size:,} 字节")
        print(f"文件数量: {index_count}")

def main():
    """主函数，处理命令行参数"""
    import sys
    
    if len(sys.argv) < 2:
        print("用法: python pack_arc.py <输入目录> [输出文件]")
        print("示例: python pack_arc.py ./unpacked_data game.arc")
        print("示例: python pack_arc.py ./unpacked_data")
        return
    
    input_dir = sys.argv[1]
    output_file = sys.argv[2] if len(sys.argv) > 2 else None
    
    if not os.path.exists(input_dir):
        print(f"错误: 目录 '{input_dir}' 不存在")
        return
    
    if not os.path.isdir(input_dir):
        print(f"错误: '{input_dir}' 不是目录")
        return
    
    try:
        pack_arc(input_dir, output_file)
    except Exception as e:
        print(f"打包过程中出现错误: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
