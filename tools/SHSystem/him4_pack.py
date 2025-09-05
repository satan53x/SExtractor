import os
import sys
import struct

def pack_him4(input_dir, output_file):
    """
    Packs files from a directory into a Him4 (HXP) archive.

    Based on the structure found in GARbro's ArcHXP.cs for Him4Opener.
    """
    # 1. 检查输入目录是否存在
    if not os.path.isdir(input_dir):
        print(f"错误: 文件夹 '{input_dir}' 不存在。")
        return

    # 2. 获取并排序文件列表
    try:
        filenames = sorted([f for f in os.listdir(input_dir) if os.path.isfile(os.path.join(input_dir, f))])
    except FileNotFoundError:
        print(f"错误: 无法访问文件夹 '{input_dir}'。")
        return
        
    if not filenames:
        print(f"警告: 文件夹 '{input_dir}' 为空，已生成一个空的封包。")
        file_count = 0
    else:
        file_count = len(filenames)

    print(f"找到 {file_count} 个文件，准备封包...")

    # 3. 计算头部和索引大小，并预先计算所有文件数据的偏移量
    # 头部结构: 'Him4' (4) + file_count (4) + offsets (4 * file_count)
    header_size = 8 + 4 * file_count
    
    offsets = []
    current_offset = header_size

    file_sizes = []
    for filename in filenames:
        filepath = os.path.join(input_dir, filename)
        size = os.path.getsize(filepath)
        file_sizes.append(size)
        
        offsets.append(current_offset)
        
        # 每个文件数据块都有一个8字节的头部 (packed_size + unpacked_size)
        current_offset += 8 + size

    # 4. 写入封包文件
    try:
        with open(output_file, 'wb') as f:
            # --- 写入文件头和索引 ---
            print("正在写入文件头和索引...")
            
            # 签名 'Him4'
            f.write(b'Him4')
            
            # 文件数量 (小端4字节无符号整数)
            f.write(struct.pack('<I', file_count))
            
            # 索引表 (每个文件的偏移量)
            for offset in offsets:
                f.write(struct.pack('<I', offset))

            # --- 写入文件数据 ---
            print("正在写入文件数据...")
            for i, filename in enumerate(filenames):
                filepath = os.path.join(input_dir, filename)
                print(f"  ({i+1}/{file_count}) 正在打包: {filename}")
                
                with open(filepath, 'rb') as in_f:
                    content = in_f.read()
                
                unpacked_size = file_sizes[i]
                
                # 写入每个数据块的头部
                # packed_size = 0 (表示未压缩)
                f.write(struct.pack('<I', 0))
                # unpacked_size
                f.write(struct.pack('<I', unpacked_size))
                
                # 写入文件内容
                f.write(content)

        print(f"\n封包成功! 文件已保存至: {output_file}")
        print(f"总大小: {os.path.getsize(output_file)} 字节")

    except IOError as e:
        print(f"错误: 写入文件 '{output_file}' 时发生错误: {e}")
    except Exception as e:
        print(f"发生未知错误: {e}")


def main():
    if len(sys.argv) != 3:
        print("用法: python pack_hxp.py <需要封包的文件夹> <输出封包文件名>")
        print("示例: python pack_hxp.py my_files archive.hxp")
        sys.exit(1)
        
    input_folder = sys.argv[1]
    output_filename = sys.argv[2]
    
    pack_him4(input_folder, output_filename)

if __name__ == '__main__':
    main()
