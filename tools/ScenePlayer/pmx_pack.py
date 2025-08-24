import os
import sys
import struct
import zlib
from io import BytesIO

class PMXPackager:
    def __init__(self):
        self.xor_key = 0x21
    
    def create_pmx_archive(self, input_dir, output_path):
        # 收集所有文件
        files = []
        for root, _, filenames in os.walk(input_dir):
            for filename in filenames:
                file_path = os.path.join(root, filename)
                # 计算相对路径
                rel_path = os.path.relpath(file_path, input_dir)
                # 替换路径分隔符为Unix风格（确保跨平台兼容性）
                rel_path = rel_path.replace('\\', '/')
                
                with open(file_path, 'rb') as f:
                    file_data = f.read()
                
                files.append((rel_path, file_data))
        
        if not files:
            print("错误: 输入文件夹中没有文件")
            return False
        
        # 构建索引和数据
        index_data = bytearray()
        file_data = bytearray()
        offset = 4 + len(files) * 0x24  # 文件头 + 索引条目
        
        for filename, data in files:
            # 确保文件名不超过31字符（保留1字节给空终止符）
            if len(filename) > 31:
                print(f"警告: 文件名 '{filename}' 超过31字符，将被截断")
                filename = filename[:31]
            
            # 写入文件名（C字符串格式，32字节）
            name_bytes = filename.encode('utf-8')[:31]
            index_data.extend(name_bytes)
            index_data.extend(b'\x00' * (32 - len(name_bytes)))
            
            # 写入文件大小
            index_data.extend(struct.pack('<I', len(data)))
            
            # 收集文件数据
            file_data.extend(data)
            
            # 更新偏移量
            offset += len(data)
        
        # 构建完整的数据（文件数量 + 索引 + 文件数据）
        full_data = struct.pack('<I', len(files)) + index_data + file_data
        
        # 压缩数据
        compressed_data = zlib.compress(full_data)
        
        # 异或处理
        xored_data = bytearray()
        for byte in compressed_data:
            xored_data.append(byte ^ self.xor_key)
        
        # 写入输出文件
        with open(output_path, 'wb') as f:
            f.write(xored_data)
        
        return True

def main():
    if len(sys.argv) != 3:
        print(">> Pack Command:")
        print("python pmx_pack.py input_folder output_file")
        sys.exit(1)
    
    input_dir = sys.argv[1]
    output_path = sys.argv[2]
    
    if not os.path.isdir(input_dir):
        print(f"错误: '{input_dir}' 不是一个有效的文件夹")
        sys.exit(1)
    
    packager = PMXPackager()
    if packager.create_pmx_archive(input_dir, output_path):
        print(f"成功创建PMX封包: {output_path}")
    else:
        print("创建PMX封包失败")
        sys.exit(1)

if __name__ == "__main__":
    main()