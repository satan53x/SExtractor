import os
import sys
import struct
import random

class ByteStringEncryptor:
    """模拟C#中的ByteStringEncryptedStream加密"""
    def __init__(self, key_bytes):
        self.key = key_bytes
        self.key_len = len(key_bytes)
    
    def encrypt(self, data, offset=0):
        """对数据进行异或加密"""
        result = bytearray(data)
        for i in range(len(result)):
            result[i] ^= self.key[(offset + i) % self.key_len]
        return bytes(result)

def create_pkg_archive(folder_path, output_path):
    """创建PKG归档文件"""
    # 获取文件夹中的所有文件
    files = []
    for root, dirs, filenames in os.walk(folder_path):
        for filename in filenames:
            file_path = os.path.join(root, filename)
            rel_path = os.path.relpath(file_path, folder_path)
            # 将路径分隔符统一为反斜杠（Windows风格）
            rel_path = rel_path.replace('/', '\\')
            files.append((rel_path, file_path))
    
    if not files:
        print("文件夹中没有找到文件")
        return
    
    # 按文件名排序
    files.sort(key=lambda x: x[0])
    
    # 使用固定的密钥（从原始PKG文件分析得出）
    key_value = 0x8AEEF101
    key_bytes = struct.pack('<I', key_value)
    print(f"使用密钥: 0x{key_value:08X}")
    
    # 创建加密器
    encryptor = ByteStringEncryptor(key_bytes)
    
    # 计算整个PKG文件的大小
    # 头部8字节 + 索引表大小 + 所有文件大小
    total_file_size = 0
    for rel_path, file_path in files:
        total_file_size += os.path.getsize(file_path)
    pkg_size = 8 + len(files) * 136 + total_file_size
    
    # 生成签名（文件大小与密钥异或）
    signature = pkg_size ^ key_value
    print(f"PKG文件大小: {pkg_size} 字节")
    print(f"生成签名: 0x{signature:08X}")
    
    # 构建文件头
    header = bytearray()
    # 0x00-0x03: 签名（文件大小与密钥异或）
    header.extend(struct.pack('<I', signature))
    # 0x04-0x07: 文件数量（加密）
    encrypted_count = encryptor.encrypt(struct.pack('<I', len(files)))
    header.extend(encrypted_count)
    
    # 构建文件索引表
    index_data = bytearray()
    current_offset = 8 + len(files) * 136  # 头部8字节 + 索引表大小
    
    for i, (rel_path, file_path) in enumerate(files):
        # 获取文件大小
        file_size = os.path.getsize(file_path)
        
        # 文件名（128字节，用0填充）
        name_bytes = rel_path.encode('utf-8')[:127]  # 留一个字节给结束符
        name_bytes = name_bytes.ljust(128, b'\x00')
        index_data.extend(name_bytes)
        
        # 文件大小（4字节）
        index_data.extend(struct.pack('<I', file_size))
        
        # 文件偏移（4字节）
        index_data.extend(struct.pack('<I', current_offset))
        
        current_offset += file_size
    
    # 加密索引表
    encrypted_index = bytearray(encryptor.encrypt(index_data))
    
    # 恢复密钥位置（不被加密）
    # 第一个文件条目的0x7C-0x7F位置（相对于索引表开始）
    encrypted_index[0x7C:0x80] = key_bytes
    
    # 如果有第二个文件，也在相应位置放置密钥
    if len(files) > 1:
        # 第二个文件条目的0x7C-0x7F位置
        encrypted_index[0x88 + 0x7C:0x88 + 0x80] = key_bytes
    
    # 写入PKG文件
    with open(output_path, 'wb') as pkg_file:
        # 写入头部
        pkg_file.write(header)
        
        # 写入加密的索引表
        pkg_file.write(encrypted_index)
        
        # 写入加密的文件数据
        for rel_path, file_path in files:
            print(f"添加文件: {rel_path}")
            with open(file_path, 'rb') as f:
                file_data = f.read()
                # 加密文件数据
                encrypted_data = encryptor.encrypt(file_data)
                pkg_file.write(encrypted_data)
    
    print(f"\nPKG文件已创建: {output_path}")
    print(f"包含 {len(files)} 个文件")
    print(f"总大小: {os.path.getsize(output_path)} 字节")

def main():
    if len(sys.argv) != 3:
        print("使用方法: python pkg_pack_v1.py 需要封包的文件夹 封包名.PKG")
        sys.exit(1)
    
    folder_path = sys.argv[1]
    output_path = sys.argv[2]
    
    if not os.path.exists(folder_path):
        print(f"错误: 文件夹 '{folder_path}' 不存在")
        sys.exit(1)
    
    if not os.path.isdir(folder_path):
        print(f"错误: '{folder_path}' 不是一个文件夹")
        sys.exit(1)
    
    # 确保输出文件有.pkg扩展名
    if not output_path.lower().endswith('.pkg'):
        output_path += '.pkg'
    
    create_pkg_archive(folder_path, output_path)

if __name__ == "__main__":
    main()
