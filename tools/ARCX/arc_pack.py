import os
import struct
from pathlib import Path
import lzss_s

def pack_arc(out_dir, new_arc_dir, original_arc_path):
    """封包out文件夹到新的ARC文件"""
    # 创建输出目录
    new_arc_dir = Path(new_arc_dir)
    new_arc_dir.mkdir(exist_ok=True, parents=True)

    # 获取原始ARC文件名
    arc_name = Path(original_arc_path).name

    # 初始化压缩器
    #lzss = LzssEncoder()

    # 获取out文件夹中所有文件（按名称排序）
    out_files = sorted(Path(out_dir).glob('*.*'))
    if not out_files:
        print("错误: out文件夹中没有找到任何文件")
        return

    # 读取原始ARC文件结构
    original_entries = []
    with open(original_arc_path, 'rb') as f_orig:
        # 读取文件头 (16字节)
        file_header = f_orig.read(0x10)
        
        # 读取所有索引条目
        while True:
            entry_pos = f_orig.tell()
            index_data = f_orig.read(0x1C)
            if len(index_data) < 0x1C:
                break
            
            # 解析索引数据
            total_size = struct.unpack('<I', index_data[0:4])[0]
            header_size = struct.unpack('<I', index_data[0x08:0x0C])[0]
            compressed_size = struct.unpack('<I', index_data[0x0C:0x10])[0]
            uncompressed_size = struct.unpack('<I', index_data[0x10:0x14])[0]
            compressed = index_data[0x1B] #01压缩 00不压缩

            # 读取资源块
            resource_block_size = total_size - 0x1C
            resource_block = f_orig.read(resource_block_size)
            index_data += resource_block[0:header_size - 0x1C]
            
            original_entries.append({
                'position': entry_pos,
                'index_data': index_data,
                'total_size': total_size,
                'compressed_size': compressed_size,
                'uncompressed_size': uncompressed_size,
                'header_size': header_size,
                'compressed': compressed,
            })

    # 检查文件数量是否匹配
    if len(out_files) != len(original_entries):
        print(f"错误: 文件数量不匹配 (out: {len(out_files)}, 原始ARC: {len(original_entries)})")
        return

    # 创建新ARC文件
    new_arc_path = new_arc_dir / arc_name
    with open(new_arc_path, 'wb') as f_new:
        # 写入原始文件头
        f_new.write(file_header)
        
        # 处理每个文件
        for i, (file_path, orig_entry) in enumerate(zip(out_files, original_entries)):
            # 读取文件内容
            with open(file_path, 'rb') as f_in:
                file_data = f_in.read()
            
            # 更新索引数据
            index_data = bytearray(orig_entry['index_data'])
            
            # 检查是否有压缩标志
            if orig_entry['compressed']:
                # 有压缩标志：进行压缩
                uncompressed_size = len(file_data)
                compressed_data = bytearray(uncompressed_size)
                compressed_size = lzss_s.compress(compressed_data, file_data)
                #compressed_size = len(compressed_data)
                new_resource_block = compressed_data[0:compressed_size]
                
                # 更新资源块大小
                resource_block_size = len(new_resource_block)
                total_size = orig_entry['header_size'] + resource_block_size
                
                # 更新索引字段
                struct.pack_into('<I', index_data, 0, total_size)
                struct.pack_into('<I', index_data, 0x0C, compressed_size)
                struct.pack_into('<I', index_data, 0x10, uncompressed_size)
                
                flag_info = f"压缩"
                size_info = f"大小: {uncompressed_size}->{compressed_size}"
            
            else:
                # 没有压缩标志：原样封包
                new_resource_block = file_data
                file_size = len(file_data)
                
                # 更新资源块大小
                resource_block_size = len(new_resource_block)
                total_size = orig_entry['header_size'] + resource_block_size
                
                # 更新索引字段（压缩/解压大小相同）
                struct.pack_into('<I', index_data, 0, total_size)
                struct.pack_into('<I', index_data, 0x0C, file_size)  # 压缩大小
                struct.pack_into('<I', index_data, 0x10, file_size)  # 解压大小
                
                flag_info = "无压缩标志（原样封包）"
                size_info = f"大小: {file_size}"
            
            # 写入索引和数据
            f_new.write(index_data)
            f_new.write(new_resource_block)
            
            # 打印信息
            print(f"封包文件[{i:04d}]: {file_path.name} | {flag_info} | {size_info}")

    print(f"封包完成! 新文件保存在: {new_arc_path}")

if __name__ == '__main__':
    # 配置路径
    ORIGINAL_ARC = 'SCX.ARC'
    OUT_DIR = 'out'
    NEW_ARC_DIR = 'new'

    # 检查原始ARC文件
    if not os.path.exists(ORIGINAL_ARC):
        print(f"错误: 原始ARC文件 {ORIGINAL_ARC} 不存在")
    else:
        pack_arc(OUT_DIR, NEW_ARC_DIR, ORIGINAL_ARC)
