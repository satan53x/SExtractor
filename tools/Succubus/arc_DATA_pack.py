import os
import struct
import argparse

# ARC1 文件头的格式：
# 4s   - 签名 'ARC1'
# I    - 文件数量 (32位无符号整数)
# I    - 索引表偏移 (32位无符号整数)
# 4x   - 4字节填充
HEADER_FORMAT = '<4sIII'
HEADER_SIZE = 16  # 0x10

# 每个索引条目的格式：
# 16s  - 文件名 (16字节，null填充)
# I    - 文件大小 (32位无符号整数)
# I    - 文件偏移 (32位无符号整数)
INDEX_ENTRY_FORMAT = '<16sII'
INDEX_ENTRY_SIZE = 24 # 0x18

def pack_arc(source_directory, output_arc_path):
    """
    将指定目录下的所有文件打包成 Succubus ARC1 格式的归档文件。

    :param source_directory: 包含要打包文件的源文件夹路径。
    :param output_arc_path: 输出的 .arc 文件路径。
    """
    # 1. 收集源目录下的所有文件信息
    if not os.path.isdir(source_directory):
        print(f"错误: 源目录 '{source_directory}' 不存在或不是一个目录。")
        return

    filepaths = [os.path.join(source_directory, f) for f in os.listdir(source_directory) 
                 if os.path.isfile(os.path.join(source_directory, f))]
    
    if not filepaths:
        print(f"警告: 源目录 '{source_directory}' 为空，不进行打包。")
        return

    print(f"找到 {len(filepaths)} 个文件准备打包...")

    file_infos = []
    current_offset = HEADER_SIZE  # 文件数据从头文件之后开始

    for path in filepaths:
        filename = os.path.basename(path)
        
        # 检查文件名长度
        try:
            # 游戏引擎通常使用 Shift-JIS 或 ASCII 编码
            # latin-1 是一种安全的编码，可以处理任何字节值而不会引发错误
            filename_bytes = filename.encode('cp932')
        except UnicodeEncodeError:
            print(f"错误: 文件名 '{filename}' 包含无法编码的字符。")
            return

        if len(filename_bytes) > 16:
            print(f"错误: 文件名 '{filename}' 太长 (超过16字节)。请重命名。")
            return

        file_size = os.path.getsize(path)
        
        file_infos.append({
            'path': path,
            'name_bytes': filename_bytes,
            'size': file_size,
            'offset': current_offset
        })
        
        current_offset += file_size

    # 2. 计算索引表的偏移量
    # 索引表紧跟在所有文件数据之后
    index_table_offset = current_offset
    file_count = len(file_infos)

    # 3. 开始写入 .arc 文件
    try:
        with open(output_arc_path, 'wb') as arc_file:
            # 3.1 写入文件头
            print("正在写入文件头...")
            header = struct.pack(HEADER_FORMAT, 
                                 b'ARC1', 
                                 file_count, 
                                 index_table_offset,
                                 0) # 4字节填充
            arc_file.write(header)

            # 3.2 写入所有文件数据
            print("正在写入文件数据...")
            for info in file_infos:
                print(f"  - 正在打包: {os.path.basename(info['path'])}")
                with open(info['path'], 'rb') as source_file:
                    arc_file.write(source_file.read())

            # 3.3 写入索引表
            print("正在写入索引表...")
            for info in file_infos:
                # 将文件名填充到16字节
                padded_name = info['name_bytes'].ljust(16, b'\x00')
                
                index_entry = struct.pack(INDEX_ENTRY_FORMAT,
                                          padded_name,
                                          info['size'],
                                          info['offset'])
                arc_file.write(index_entry)
        
        print(f"\n打包成功！文件已保存至: {output_arc_path}")

    except IOError as e:
        print(f"写入文件时发生错误: {e}")

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="将一个文件夹打包成 Succubus ARC1 格式的归档文件。")
    parser.add_argument("source_dir", help="包含要打包文件的源文件夹。")
    parser.add_argument("output_file", help="输出的 .arc 文件名。")
    
    args = parser.parse_args()
    
    pack_arc(args.source_dir, args.output_file)
