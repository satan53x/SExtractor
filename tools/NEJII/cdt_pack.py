import os
import sys
import struct
from pathlib import Path

try:
    import lzss
except ImportError:
    print("错误: 需要安装 lzss 库")
    print("请运行: pip install lzss")
    sys.exit(1)


def compress_lzss(data):
    """
    使用标准LZSS库压缩数据
    """
    try:
        compressed = lzss.compress(data)
        
        # 只有在压缩后更小时才使用压缩
        if len(compressed) < len(data):
            return compressed, True
        else:
            return data, False
    except Exception as e:
        print(f"警告: 压缩失败 - {e}")
        return data, False


def pack_cdt(input_folder, output_file, use_compression=True):
    """
    将文件夹打包成CDT格式
    """
    input_path = Path(input_folder)
    
    if not input_path.exists() or not input_path.is_dir():
        print(f"错误: 文件夹 '{input_folder}' 不存在")
        return False
    
    # 收集所有文件
    files = []
    for file_path in input_path.rglob('*'):
        if file_path.is_file():
            files.append(file_path)
    
    if not files:
        print("错误: 文件夹中没有文件")
        return False
    
    print(f"找到 {len(files)} 个文件")
    print(f"压缩模式: {'启用' if use_compression else '禁用'}")
    
    # 准备数据
    entries = []
    file_data = []
    current_offset = 0
    total_original_size = 0
    total_packed_size = 0
    
    for file_path in files:
        # 读取文件数据
        with open(file_path, 'rb') as f:
            data = f.read()
        
        # 获取相对文件名（最多16字节，包含null终止符）
        relative_name = file_path.relative_to(input_path).as_posix()
        if len(relative_name) > 15:
            relative_name = relative_name[:15]
        name_bytes = relative_name.encode('ascii', errors='ignore').ljust(16, b'\0')
        
        unpacked_size = len(data)
        total_original_size += unpacked_size
        
        # 尝试压缩
        if use_compression:
            packed_data, is_packed = compress_lzss(data)
            is_packed_flag = 1 if is_packed else 0
        else:
            packed_data = data
            is_packed_flag = 0
        
        packed_size = len(packed_data)
        total_packed_size += packed_size
        
        entry = {
            'name': name_bytes,
            'size': packed_size,
            'unpacked_size': unpacked_size,
            'is_packed': is_packed_flag,
            'offset': current_offset,
            'data': packed_data
        }
        
        entries.append(entry)
        file_data.append(packed_data)
        current_offset += packed_size
        
        compression_info = ""
        if is_packed_flag:
            ratio = (1 - packed_size / unpacked_size) * 100 if unpacked_size > 0 else 0
            compression_info = f" [压缩: {unpacked_size} -> {packed_size} 字节, {ratio:.1f}%]"
        
        print(f"添加: {relative_name} (大小: {unpacked_size} 字节){compression_info}")
    
    # 写入CDT文件
    with open(output_file, 'wb') as f:
        # 写入所有文件数据
        for data in file_data:
            f.write(data)
        
        # 记录索引开始位置
        index_offset = f.tell()
        
        # 写入索引
        for entry in entries:
            # 文件名 (16字节)
            f.write(entry['name'])
            # 压缩后大小 (4字节)
            f.write(struct.pack('<I', entry['size']))
            # 原始大小 (4字节)
            f.write(struct.pack('<I', entry['unpacked_size']))
            # 是否压缩 (4字节)
            f.write(struct.pack('<I', entry['is_packed']))
            # 文件偏移 (4字节)
            f.write(struct.pack('<I', entry['offset']))
        
        # 写入尾部签名和信息
        f.write(b'RK1\0')  # 签名 (4字节)
        f.write(struct.pack('<I', len(entries)))  # 文件数量 (4字节)
        f.write(struct.pack('<I', index_offset))  # 索引偏移 (4字节)
    
    # 输出统计信息
    print(f"\n成功创建: {output_file}")
    print(f"文件数量: {len(entries)}")
    print(f"索引偏移: 0x{index_offset:X}")
    print(f"原始总大小: {total_original_size:,} 字节")
    print(f"打包后大小: {total_packed_size:,} 字节")
    if use_compression and total_original_size > 0:
        ratio = (1 - total_packed_size / total_original_size) * 100
        print(f"总压缩率: {ratio:.2f}%")
    
    return True


def main():
    if len(sys.argv) < 3:
        print("使用方法: python 1.py <被封包的文件夹> <封包名.CDT> [--no-compress]")
        print("例如: python 1.py ./my_folder output.CDT")
        print("不压缩: python 1.py ./my_folder output.CDT --no-compress")
        sys.exit(1)
    
    input_folder = sys.argv[1]
    output_file = sys.argv[2]
    use_compression = '--no-compress' not in sys.argv
    
    # 确保输出文件有正确的扩展名
    if not output_file.lower().endswith(('.cdt', '.pdt', '.vdt', '.ovd')):
        print("警告: 输出文件扩展名不是 .CDT/.PDT/.VDT/.OVD")
    
    pack_cdt(input_folder, output_file, use_compression)


if __name__ == '__main__':
    main()
