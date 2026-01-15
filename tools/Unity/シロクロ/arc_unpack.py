import struct
import os
from pathlib import Path

def read_string(file):
    """读取一个长度前缀的字符串"""
    length = struct.unpack('B', file.read(1))[0]  # 1字节长度
    if length == 0:
        return ""
    # 读取字符串数据并解码
    data = file.read(length)
    return data.decode('utf-8')

def unpack_arc(arc_file_path, output_dir=None):
    """
    解包ARC文件
    
    参数:
        arc_file_path: ARC文件路径
        output_dir: 输出目录，默认为ARC文件同目录下的"unpacked"文件夹
    """
    
    # 设置输出目录
    if output_dir is None:
        arc_dir = os.path.dirname(arc_file_path)
        arc_name = os.path.splitext(os.path.basename(arc_file_path))[0]
        output_dir = os.path.join(arc_dir, f"{arc_name}")
    
    # 创建输出目录
    os.makedirs(output_dir, exist_ok=True)
    
    with open(arc_file_path, 'rb') as f:
        # 获取文件大小
        f.seek(0, 2)
        file_size = f.tell()
        
        # 读取最后8字节作为索引表起始地址
        f.seek(-8, 2)
        index_start = struct.unpack('<Q', f.read(8))[0]  # 小端序8字节
        
        print(f"文件大小: {file_size} 字节")
        print(f"索引表起始地址: 0x{index_start:08X}")
        
        # 跳转到索引表位置
        f.seek(index_start)
        
        # 读取索引数量
        index_count = struct.unpack('<I', f.read(4))[0]  # 小端序4字节
        print(f"索引数量: {index_count}")
        
        # 解析所有索引
        for i in range(index_count):
            print(f"\n解析索引 {i+1}/{index_count}:")
            
            # 读取文件名
            filename = read_string(f)
            print(f"  文件名: {filename}")
            
            # 读取文件地址和长度（都是8字节）
            file_offset = struct.unpack('<Q', f.read(8))[0]
            file_length = struct.unpack('<Q', f.read(8))[0]
            print(f"  文件偏移: 0x{file_offset:08X}")
            print(f"  文件长度: {file_length} 字节")
            
            # 读取固定字节0x4E
            fixed_byte = struct.unpack('B', f.read(1))[0]
            if fixed_byte != 0x4E:
                print(f"  警告: 预期固定字节0x4E，但找到0x{fixed_byte:02X}")
            
            # 读取路径字符串
            path_str = read_string(f)
            print(f"  路径: {path_str}")
            
            # 保存文件
            if file_length > 0:
                # 记录当前位置以便返回
                current_pos = f.tell()
                
                # 跳转到文件数据位置
                f.seek(file_offset)
                
                # 创建完整的输出路径
                if path_str:
                    # 如果路径字符串以/开头，去掉它
                    if path_str.startswith('/'):
                        path_str = path_str[1:]
                    full_path = os.path.join(output_dir, path_str)
                    os.makedirs(os.path.dirname(full_path), exist_ok=True)
                    output_file = os.path.join(full_path, filename)
                else:
                    output_file = os.path.join(output_dir, filename)
                
                # 确保目录存在
                os.makedirs(os.path.dirname(output_file), exist_ok=True)
                
                # 读取并保存文件数据
                file_data = f.read(file_length)
                with open(output_file, 'wb') as out_f:
                    out_f.write(file_data)
                
                print(f"  已保存: {output_file}")
                
                # 返回索引表位置
                f.seek(current_pos)
            else:
                print(f"  空文件，跳过保存")
    
    print(f"\n解包完成！文件保存在: {output_dir}")

def main():
    # 使用示例
    import sys
    
    if len(sys.argv) < 2:
        print("用法: python unpack_arc.py <ARC文件路径> [输出目录]")
        print("示例: python unpack_arc.py game.arc")
        return
    
    arc_file = sys.argv[1]
    output_dir = sys.argv[2] if len(sys.argv) > 2 else None
    
    if not os.path.exists(arc_file):
        print(f"错误: 文件 '{arc_file}' 不存在")
        return
    
    try:
        unpack_arc(arc_file, output_dir)
    except Exception as e:
        print(f"解包过程中出现错误: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()