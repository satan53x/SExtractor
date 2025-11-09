import os
import struct
import sys

def rebuild_skm_file(txt_file, output_dir):
    # 读取提取的字符串
    with open(txt_file, 'r', encoding='utf-8') as f:
        strings = [line.rstrip('\n') for line in f.readlines()]
    
    str_count = len(strings)
    
    # 创建输出目录
    os.makedirs(output_dir, exist_ok=True)
    
    # 构建文件头
    header = b'\x53\x4B\x4D\x53\x64\x00'  # SKMSd\x00
    str_count_bytes = struct.pack('<I', str_count)  # 小端序字符串总数
    
    # 构建索引数据流和字符串数据流
    index_data = bytearray()
    str_data = bytearray()
    current_offset = 0
    
    for s in strings:
        # 编码为CP932并XOR加密
        try:
            encoded = s.encode('cp932')
            encrypted = bytes(b ^ 0xFF for b in encoded)
        except UnicodeEncodeError:
            print(f"编码错误: 跳过字符串 '{s[:20]}...'")
            encrypted = b''
        
        # 添加索引项 (偏移 + 长度)
        index_data.extend(struct.pack('<I', current_offset))  # 小端序偏移
        index_data.extend(struct.pack('<I', len(encrypted)))  # 小端序长度
        
        # 添加加密后的字符串数据
        str_data.extend(encrypted)
        current_offset += len(encrypted)
    
    # 构建完整文件内容
    file_content = (
        header +
        str_count_bytes +
        index_data +
        str_data
    )
    
    # 写入输出文件
    skm_filename = os.path.basename(txt_file).replace('.txt', '')
    output_path = os.path.join(output_dir, skm_filename)
    
    with open(output_path, 'wb') as f:
        f.write(file_content)
    
    print(f"成功重建 {str_count} 个字符串到 {output_path}")
    print(f"文件大小: {len(file_content)} 字节")
    print(f"索引数据流: {len(index_data)} 字节")
    print(f"字符串数据流: {len(str_data)} 字节")

if __name__ == "__main__":
    # 设置输入输出路径
    input_txt = os.path.join('out', 'msg.skm.txt')
    output_dir = 'out1'
    
    if not os.path.exists(input_txt):
        print(f"错误: 输入文件不存在 {input_txt}")
        sys.exit(1)
    
    rebuild_skm_file(input_txt, output_dir)
