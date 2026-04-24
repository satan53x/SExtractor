import sys
import hashlib
import hmac
import struct

class NScripterCrypt:
    BLOCK_LENGTH = 1024
    
    def __init__(self, key):
        self.key = key
        self.md5 = hashlib.md5()
        self.sha1 = hashlib.sha1()
    
    def process_file(self, input_path, output_path):
        with open(input_path, 'rb') as infile, open(output_path, 'wb') as outfile:
            file_size = infile.seek(0, 2)
            infile.seek(0)
            
            block_num = 0
            while True:
                block = infile.read(self.BLOCK_LENGTH)
                if not block:
                    break
                
                decrypted_block = self._process_block(block, block_num)
                outfile.write(decrypted_block)
                block_num += 1
    
    def _process_block(self, block, block_num):
        # 生成块号的小端字节
        bn = struct.pack('<q', block_num)
        
        # 计算MD5和SHA1哈希
        md5_hash = hashlib.md5(bn).digest()
        sha1_hash = hashlib.sha1(bn).digest()
        
        # 生成HMAC密钥
        hmac_key = bytes(md5_hash[i] ^ sha1_hash[i] for i in range(16))
        
        # 计算HMAC-SHA512
        hmac_hash = hmac.new(hmac_key, self.key, hashlib.sha512).digest()
        
        # 初始化映射表
        map_table = list(range(256))
        
        index = 0
        h = 0
        for i in range(256):
            if h == len(hmac_hash):
                h = 0
            tmp = map_table[i]
            index = (tmp + hmac_hash[h] + index) & 0xFF
            map_table[i] = map_table[index]
            map_table[index] = tmp
            h += 1
        
        # 洗牌300次
        i0 = 0
        i1 = 0
        for i in range(300):
            i0 = (i0 + 1) & 0xFF
            tmp = map_table[i0]
            i1 = (i1 + tmp) & 0xFF
            map_table[i0] = map_table[i1]
            map_table[i1] = tmp
        
        # 解密/加密块
        result = bytearray(block)
        for i in range(len(result)):
            i0 = (i0 + 1) & 0xFF
            tmp = map_table[i0]
            i1 = (i1 + tmp) & 0xFF
            map_table[i0] = map_table[i1]
            map_table[i1] = tmp
            result[i] ^= map_table[(map_table[i0] + tmp) & 0xFF]
        
        return bytes(result)

def main():
    if len(sys.argv) != 3:
        print("Usage: python 1.py <input_file> <output_file>")
        sys.exit(1)
    
    input_file = sys.argv[1]
    output_file = sys.argv[2]
    
    # 这里需要提供密钥，请根据实际情况修改
    # 常见的NScripter密钥示例
    key = b"dfklmdsgkmlkmljklgfnlsdfnklsdfjkl;sdfmkldfskfsdmklsdfjklfdsjklsdfsdfl;"  # 请替换为实际的密钥
    
    crypt = NScripterCrypt(key)
    crypt.process_file(input_file, output_file)
    print(f"Processed: {input_file} -> {output_file}")

if __name__ == "__main__":
    main()