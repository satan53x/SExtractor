import os
import struct
import sys

def extract_skm_strings(input_file):
    # 创建输出目录
    os.makedirs('out', exist_ok=True)
    
    # 读取二进制文件
    with open(input_file, 'rb') as f:
        data = f.read()
    
    # 验证文件头 (0x0-0x5)
    header = data[0:6]
    if header != b'\x53\x4B\x4D\x53\x64\x00':
        print("错误：无效的文件头")
        sys.exit(1)
    
    # 获取字符串总数 (0x6-0x9 小端序)
    str_count = struct.unpack('<I', data[6:10])[0]
    
    # 索引数据流 (0x0A - 0x17329)
    index_start = 0x0A
    index_end = 0x17329 + 1  # 包含结束位置
    index_data = data[index_start:index_end]
    
    # 字符串数据流 (0x1732A - 文件结尾)
    str_data_start = 0x1732A
    str_data = data[str_data_start:]
    
    # XOR 0xFF 解密字符串数据
    decrypted_data = bytes(b ^ 0xFF for b in str_data)
    
    # 解析索引并提取字符串
    strings = []
    for i in range(str_count):
        # 每8字节为一个索引项
        start = i * 8
        end = start + 8
        
        if end > len(index_data):
            break
            
        # 解析偏移量和长度 (小端序)
        offset = struct.unpack('<I', index_data[start:start+4])[0]
        length = struct.unpack('<I', index_data[start+4:end])[0]
        
        # 检查偏移是否有效
        if offset + length > len(decrypted_data):
            print(f"警告：索引{i}超出范围 (offset:{offset}, length:{length})")
            continue
            
        # 提取字符串并解码 (CP932)
        try:
            raw_str = decrypted_data[offset:offset+length]
            decoded_str = raw_str.decode('cp932')
            strings.append(decoded_str)
        except UnicodeDecodeError:
            print(f"解码错误：索引{i} offset:{offset} length:{length}")
            strings.append(f"[解码失败]")

    # 写入输出文件
    output_file = os.path.join('out', os.path.basename(input_file) + '.txt')
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write('\n'.join(strings))
    
    print(f"成功提取 {len(strings)}/{str_count} 个字符串到 {output_file}")

if __name__ == "__main__":
    extract_skm_strings('msg.skm')
