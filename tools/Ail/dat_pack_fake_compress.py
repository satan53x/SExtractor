import os
import struct
from pathlib import Path
import array

class AilArchivePacker:
    def pack_archive(self, input_dir, output_dir):
        """打包整个档案"""
        # 准备目录
        sall_dir = Path(input_dir)
        if not sall_dir.is_dir():
            print(f"输入文件夹不存在: {input_dir}")
            return
        out_dir = Path(output_dir)
        out_dir.mkdir(exist_ok=True)

        # 收集并排序文件
        files = []
        max_index = -1
        for file_path in sall_dir.glob("sall#*"):
            try:
                index = int(file_path.stem.split('#')[1])
                files.append((index, file_path))
                max_index = max(max_index, index)
            except:
                continue

        if max_index < 0:
            raise Exception("No valid files found")

        # 准备文件表
        file_count = max_index + 1
        header_size = 4 + file_count * 4  # 文件数 + 大小表
        current_offset = header_size

        # 处理每个文件
        entries = []
        file_dict = dict(files)

        # 首先计算所有偏移
        for i in range(file_count):
            if i in file_dict:
                with open(file_dict[i], 'rb') as f:
                    data = f.read()
                
                # 检查是否需要压缩
                needs_compression = True
                if len(data) >= 4:
                    if data[4:8] == b"OggS":
                        needs_compression = False
                
                if needs_compression:
                    print('Compressing:', file_dict[i])
                    compressed = self.lzss_compress(data)
                    size = len(compressed)
                else:
                    header = struct.pack('<I', 0)  # 未压缩标记
                    # header = struct.pack('<HI', 0, len(data))  # 未压缩标记
                    compressed = header + data
                    size = len(compressed)

                entries.append({
                    'index': i,
                    'offset': current_offset,
                    'size': size,
                    'data': compressed,
                    'compressed': needs_compression
                })
                current_offset += size
            else:
                entries.append({
                    'index': i,
                    'offset': 0,
                    'size': 0,
                    'data': None
                })

        # 写入文件
        output_path = out_dir / "sall.snl"
        with open(output_path, 'wb') as f:
            # 写入文件数量
            f.write(struct.pack('<I', file_count))

            # 写入大小表
            for entry in entries:
                f.write(struct.pack('<I', entry['size']))

            # 写入文件数据
            for entry in entries:
                if entry['data'] is not None:
                    f.write(entry['data'])

    def lzss_compress(self, data):
        output = bytearray()
        # 写入压缩标记和原始大小
        output.extend(struct.pack('<H', 1))  # 0x0001
        output.extend(struct.pack('<I', len(data)))

        compressed = bytearray()
        pos = 0
        control_byte = 0

        while pos < len(data):
            compressed.extend(struct.pack('<B', control_byte))
            end = pos + 8
            if end > len(data):
                end = len(data)
            compressed.extend(data[pos:end])
            pos = end

        output.extend(compressed)
        return output

def main():
    packer = AilArchivePacker()
    packer.pack_archive("sall", "out")
    print("完成")

if __name__ == "__main__":
    main()
