import os
import struct
from pathlib import Path
import lzss_s

def unpack_arc_file(arc_path):
    """解包SCX.ARC文件"""
    out_dir = Path('out')
    out_dir.mkdir(exist_ok=True)
    
    #lzss = LzssDecoder()
    
    with open(arc_path, 'rb') as f:
        # 跳过前16字节
        f.seek(0x10)
        current_pos = 0x10
        file_count = 0
        
        while True:
            # 读取索引条目 (28字节)
            index_data = f.read(0x1C)
            if len(index_data) != 0x1C:
                break
                
            # 解析索引数据
            total_size = struct.unpack('<I', index_data[0:4])[0]
            name_len = struct.unpack('<I', index_data[0x04:0x08])[0]
            header_size = struct.unpack('<I', index_data[0x08:0x0C])[0]
            compressed_size = struct.unpack('<I', index_data[0x0C:0x10])[0]
            uncompressed_size = struct.unpack('<I', index_data[0x10:0x14])[0]
            compressed = index_data[0x1B] #01压缩 00不压缩

            # 计算下一个索引位置
            next_index_pos = current_pos + total_size
            resource_block_start = current_pos + header_size
            resource_block_size = total_size - header_size

            #文件名
            subfile_name = f.read(name_len).rstrip(b'\x00').decode('cp932')
            subfile_name = subfile_name.replace('\\', '__')
            
            # 读取资源数据块
            f.seek(resource_block_start)
            resource_block = f.read(resource_block_size)
            
            output_path = out_dir / f'{file_count:04d}.{subfile_name}'
            # 处理找到压缩标志的情况
            if compressed:
                # 提取压缩数据
                compressed_data = resource_block
                if len(compressed_data) != compressed_size:
                    print(f"文件 {file_count} 压缩数据大小不匹配")
                    current_pos = next_index_pos
                    f.seek(next_index_pos)
                    continue
                    
                try:
                    # 解压缩数据
                    decompressed_data = bytearray(len(compressed_data)*16)
                    decompressed_size = lzss_s.decompress(decompressed_data, compressed_data)
                    decompressed_data = decompressed_data[:decompressed_size]
                    if len(decompressed_data) != uncompressed_size:
                        print(f"文件 {file_count} 解压大小不匹配: 预期 {uncompressed_size}, 实际 {len(decompressed_data)}")
                    
                    # 保存解压文件
                    with open(output_path, 'wb') as out_file:
                        out_file.write(decompressed_data)
                    
                    print(f"解包文件: {output_path}")
                    file_count += 1
                    
                except Exception as e:
                    print(f"解压文件 {file_count} 时出错: {e}")
                    # 出错时也保存原始数据以便调试
                    with open(output_path, 'wb') as out_file:
                        out_file.write(resource_block)
                    print(f"保存原始文件(解压出错): {output_path}")
                    file_count += 1
            
            # 未找到压缩标志的情况
            else:
                # 原样输出文件（不解压缩）
                with open(output_path, 'wb') as out_file:
                    out_file.write(resource_block)
                print(f"原样输出文件(未找到压缩标志): {output_path}")
                file_count += 1
            
            # 移动到下一个索引
            current_pos = next_index_pos
            f.seek(next_index_pos)

if __name__ == '__main__':
    current_dir = os.path.dirname(__file__)
    arc_file = os.path.join(current_dir, 'SCX.ARC')  # 同目录下的ARC文件名
    if not os.path.exists(arc_file):
        print(f"错误: 文件 {arc_file} 不存在")
    else:
        unpack_arc_file(arc_file)
        print("解包完成!")
