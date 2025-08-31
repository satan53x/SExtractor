#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import struct
from pathlib import Path

ARC_HEAD_SIZE = 0x20

class ARCGReplacer:
    def __init__(self):
        self.signature = b'ARCG'
        self.version = 0x10000
        
    def read_archive(self, arc_path):
        """读取ARCG封包的结构"""
        with open(arc_path, 'rb') as f:
            # 读取文件头
            signature = f.read(4)
            if signature != self.signature:
                raise ValueError(f"不是有效的ARCG文件: {arc_path}")
            
            version = struct.unpack('<I', f.read(4))[0]
            if version != self.version:
                raise ValueError(f"不支持的版本: {hex(version)}")
            
            index_offset = struct.unpack('<I', f.read(4))[0]
            index_size = struct.unpack('<I', f.read(4))[0]
            dir_count = struct.unpack('<H', f.read(2))[0]
            file_count = struct.unpack('<I', f.read(4))[0]
            
            # 读取索引
            f.seek(index_offset)
            index_data = f.read(index_size)
            
            # 解析索引
            entries = []
            index_pos = 0
            
            # 读取目录信息
            dir_infos = []
            for i in range(dir_count):
                name_len = index_data[index_pos]
                index_pos += 1
                dir_name = index_data[index_pos:index_pos+name_len-1].decode('cp932', errors='replace')
                index_pos += name_len - 1
                
                file_list_offset = struct.unpack('<I', index_data[index_pos:index_pos+4])[0]
                index_pos += 4
                file_count_in_dir = struct.unpack('<I', index_data[index_pos:index_pos+4])[0]
                index_pos += 4
                
                dir_infos.append({
                    'name': dir_name,
                    'file_list_offset': file_list_offset - index_offset,
                    'file_count': file_count_in_dir
                })
            
            # 读取文件信息
            for dir_info in dir_infos:
                dir_name = dir_info['name']
                file_pos = dir_info['file_list_offset']
                
                for j in range(dir_info['file_count']):
                    name_len = index_data[file_pos]
                    file_pos += 1
                    file_name = index_data[file_pos:file_pos+name_len-1].decode('cp932', errors='replace')
                    file_pos += name_len - 1
                    
                    file_offset = struct.unpack('<I', index_data[file_pos:file_pos+4])[0]
                    file_pos += 4
                    file_size = struct.unpack('<I', index_data[file_pos:file_pos+4])[0]
                    file_pos += 4
                    
                    # 构建完整路径
                    if dir_name.rstrip('\x00'):
                        full_path = f"{dir_name}/{file_name}"
                    else:
                        full_path = file_name
                    
                    entries.append({
                        'path': full_path,
                        'dir': dir_name,
                        'name': file_name,
                        'offset': file_offset,
                        'size': file_size,
                        'data': None
                    })
            
            # 读取文件数据
            for entry in entries:
                f.seek(entry['offset'])
                entry['data'] = f.read(entry['size'])
            
            return entries
    
    def replace_files_only(self, original_arc, replace_dir, output_arc):
        """只替换封包中的同名文件，不添加新文件"""
        print(f"读取原始封包: {original_arc}")
        
        try:
            entries = self.read_archive(original_arc)
        except Exception as e:
            print(f"读取封包失败: {e}")
            return False
        
        print(f"原始封包包含 {len(entries)} 个文件")
        
        # 创建文件名映射（处理编码问题）
        file_map = {}
        for i, entry in enumerate(entries):
            file_name = entry['name'].rstrip('\x00')
            
            # 存储原始文件名
            file_map[file_name] = i
            
            # 尝试不同的编码转换
            try:
                # 尝试将cp932编码的文件名转为UTF-8再转回来，看是否匹配
                file_name_bytes = file_name.encode('cp932', errors='ignore')
                file_name_utf8 = file_name_bytes.decode('utf-8', errors='ignore')
                if file_name_utf8 != file_name:
                    file_map[file_name_utf8] = i
            except:
                pass
            
            try:
                # 尝试直接UTF-8编码
                file_name_utf8 = file_name.encode('utf-8', errors='ignore').decode('utf-8', errors='ignore')
                if file_name_utf8 != file_name:
                    file_map[file_name_utf8] = i
            except:
                pass
        
        # 扫描替换文件夹
        replace_path = Path(replace_dir)
        if not replace_path.exists() or not replace_path.is_dir():
            print(f"错误: 替换文件夹 '{replace_dir}' 不存在或不是文件夹")
            return False
        
        replaced_count = 0
        
        print(f"\n扫描替换文件夹: {replace_dir}")
        
        # 遍历替换文件夹中的所有文件
        for root, dirs, files in os.walk(replace_path):
            for file_name in files:
                file_path = Path(root) / file_name
                
                # 读取文件数据
                with open(file_path, 'rb') as f:
                    file_data = f.read()
                
                # 尝试多种编码匹配
                matched = False
                matched_index = -1
                
                # 直接匹配文件名
                if file_name in file_map:
                    matched_index = file_map[file_name]
                    matched = True
                
                # 如果没匹配上，尝试编码转换
                if not matched:
                    # 尝试将文件系统的文件名转换为cp932
                    try:
                        file_name_cp932 = file_name.encode('utf-8').decode('cp932', errors='ignore')
                        if file_name_cp932 in file_map:
                            matched_index = file_map[file_name_cp932]
                            matched = True
                    except:
                        pass
                
                if not matched:
                    # 尝试反向转换
                    try:
                        file_name_utf8 = file_name.encode('cp932', errors='ignore').decode('utf-8', errors='ignore')
                        if file_name_utf8 in file_map:
                            matched_index = file_map[file_name_utf8]
                            matched = True
                    except:
                        pass
                
                if not matched:
                    # 遍历所有文件名，尝试字节级别的比较
                    for orig_name, idx in file_map.items():
                        try:
                            # 比较原始字节
                            orig_bytes = orig_name.encode('cp932', errors='ignore')
                            file_bytes = file_name.encode('utf-8', errors='ignore')
                            
                            # 尝试解码后比较
                            if orig_bytes == file_bytes:
                                matched_index = idx
                                matched = True
                                break
                            
                            # 尝试规范化后比较
                            orig_normalized = orig_name.replace('　', ' ').replace('・', '·')
                            file_normalized = file_name.replace('　', ' ').replace('・', '·')
                            if orig_normalized == file_normalized:
                                matched_index = idx
                                matched = True
                                break
                                
                        except:
                            continue
                
                if matched and matched_index >= 0:
                    # 替换文件
                    old_size = entries[matched_index]['size']
                    entries[matched_index]['data'] = file_data
                    entries[matched_index]['size'] = len(file_data)
                    
                    print(f"替换: {entries[matched_index]['name']} ({old_size} -> {len(file_data)} 字节)")
                    replaced_count += 1
                else:
                    print(f"跳过(未找到匹配): {file_name}")
        
        print(f"\n统计: 替换 {replaced_count} 个文件")
        print(f"输出封包包含 {len(entries)} 个文件（与原始封包相同）")
        
        # 重新构建封包
        print(f"\n创建新封包: {output_arc}")
        return self.write_archive(entries, output_arc)
    
    def list_files(self, arc_path, output_txt=None):
        """列出封包中的所有文件"""
        print(f"读取封包: {arc_path}")
        
        try:
            entries = self.read_archive(arc_path)
        except Exception as e:
            print(f"读取封包失败: {e}")
            return
        
        print(f"\n封包包含 {len(entries)} 个文件:")
        print("-" * 60)
        
        output_lines = []
        
        # 按目录分组显示
        current_dir = None
        for entry in sorted(entries, key=lambda x: (x['dir'], x['name'])):
            if entry['dir'] != current_dir:
                current_dir = entry['dir']
                if current_dir:
                    line = f"\n[目录: {current_dir}]"
                else:
                    line = f"\n[根目录]"
                print(line)
                output_lines.append(line)
            
            line = f"  {entry['name']:<40} {entry['size']:>10} 字节"
            print(line)
            output_lines.append(line)
        
        print("-" * 60)
        print(f"总计: {len(entries)} 个文件")
        
        # 如果指定了输出文件，保存到文本文件
        if output_txt:
            with open(output_txt, 'w', encoding='utf-8') as f:
                f.write('\n'.join(output_lines))
            print(f"\n文件列表已保存到: {output_txt}")
    
    def write_archive(self, entries, output_file):
        """写入ARCG封包"""
        # 按目录组织文件
        dir_entries = {}
        for entry in entries:
            dir_name = entry['dir']
            if dir_name not in dir_entries:
                dir_entries[dir_name] = []
            dir_entries[dir_name].append(entry)
        
        # 确保目录名排序一致
        sorted_dirs = sorted(dir_entries.keys())
        
        # 构建索引
        index_data = bytearray()
        
        # 计算目录部分的大小
        dir_section_size = 0
        for dir_name in sorted_dirs:
            dir_name_bytes = dir_name.encode('cp932', errors='replace')
            dir_section_size += 1 + len(dir_name_bytes) + 8 
            dir_section_size += 4 #单目录-未知4字节
        
        # 写入目录条目
        file_list_start = ARC_HEAD_SIZE + dir_section_size
        
        for dir_name in sorted_dirs:
            files = dir_entries[dir_name]
            dir_name_bytes = dir_name.encode('cp932', errors='replace')
            
            # 写入目录名
            index_data.append(len(dir_name_bytes) + 1)
            index_data.extend(dir_name_bytes)
            
            # 写入文件列表偏移和文件数
            index_data.extend(struct.pack('<I', file_list_start))
            index_data.extend(struct.pack('<I', len(files)))
            index_data.extend(struct.pack('<I', 0)) #单目录-未知4字节
            
            # 计算下一个目录的文件列表偏移
            for file_entry in files:
                file_name_bytes = file_entry['name'].encode('cp932', errors='replace')
                file_list_start += 1 + len(file_name_bytes) + 8
        
        # 计算文件数据开始位置
        data_start = ARC_HEAD_SIZE + len(index_data)
        for dir_name in sorted_dirs:
            for file_entry in dir_entries[dir_name]:
                file_name_bytes = file_entry['name'].encode('cp932', errors='replace')
                data_start += 1 + len(file_name_bytes) + 8
        data_start += 4 #索引区-未知4字节
        
        # 写入文件列表
        current_data_offset = data_start
        
        for dir_name in sorted_dirs:
            #sorted_files = sorted(dir_entries[dir_name], key=lambda x: x['name'])
            sorted_files = dir_entries[dir_name]
            for file_entry in sorted_files:
                file_name_bytes = file_entry['name'].encode('cp932', errors='replace')
                
                # 写入文件名
                index_data.append(len(file_name_bytes) + 1)
                index_data.extend(file_name_bytes)
                
                # 写入文件偏移和大小
                index_data.extend(struct.pack('<I', current_data_offset))
                index_data.extend(struct.pack('<I', file_entry['size']))
                
                file_entry['new_offset'] = current_data_offset
                current_data_offset += file_entry['size']

        index_data.extend(struct.pack('<I', 0)) #索引区-未知4字节
        
        # 写入文件
        try:
            with open(output_file, 'wb') as f:
                # 写入文件头
                f.write(self.signature)
                f.write(struct.pack('<I', self.version))
                f.write(struct.pack('<I', ARC_HEAD_SIZE))
                f.write(struct.pack('<I', len(index_data)))
                f.write(struct.pack('<H', len(dir_entries)))
                f.write(struct.pack('<I', len(entries)))
                f.write(b'\x00' * (ARC_HEAD_SIZE - 0x16))
                
                # 写入索引
                f.write(index_data)
                
                # 写入文件数据
                for dir_name in sorted_dirs:
                    #sorted_files = sorted(dir_entries[dir_name], key=lambda x: x['name'])
                    sorted_files = dir_entries[dir_name]
                    for file_entry in sorted_files:
                        if file_entry['data'] is None:
                            print(f"警告: 文件 {file_entry['path']} 没有数据")
                            f.write(b'\x00' * file_entry['size'])
                        else:
                            f.write(file_entry['data'])
                
                print(f"成功创建: {output_file}")
                print(f"文件大小: {f.tell()} 字节")
                return True
                
        except Exception as e:
            print(f"写入文件时出错: {e}")
            import traceback
            traceback.print_exc()
            return False

def main():
    sys.argv = ['python 2.py -r Salem.scb patch out.scb', '-r', 'Salem.scb', 'patch', 'out.scb']
    if len(sys.argv) < 2:
        print("ARCG封包替换工具 v1.1")
        print("=" * 60)
        print("\n使用方法:")
        print("  1. 列出封包内容:")
        print("     python script.py -l 封包文件 [输出文本文件]")
        print("")
        print("  2. 替换同名文件（不添加新文件）:")
        print("     python script.py -r 原始封包 替换文件夹 [输出封包]")
        print("")
        print("示例:")
        print("  python script.py -l game.arc")
        print("  python script.py -l game.arc filelist.txt")
        print("  python script.py -r game.arc translations game_cn.arc")
        sys.exit(1)
    
    mode = sys.argv[1]
    replacer = ARCGReplacer()
    
    if mode == '-l' or mode == '--list':
        # 列出文件模式
        if len(sys.argv) < 3:
            print("错误: 需要指定封包文件")
            sys.exit(1)
        
        arc_file = sys.argv[2]
        output_txt = sys.argv[3] if len(sys.argv) >= 4 else None
        replacer.list_files(arc_file, output_txt)
        
    elif mode == '-r' or mode == '--replace':
        # 替换模式（只替换，不添加）
        if len(sys.argv) < 4:
            print("错误: 需要指定原始封包和替换文件夹")
            sys.exit(1)
        
        original_arc = sys.argv[2]
        replace_dir = sys.argv[3]
        
        if len(sys.argv) >= 5:
            output_arc = sys.argv[4]
        else:
            base_name = Path(original_arc).stem
            ext = Path(original_arc).suffix
            output_arc = f"{base_name}_modified{ext}"
        
        if not replacer.replace_files_only(original_arc, replace_dir, output_arc):
            sys.exit(1)
    else:
        print(f"错误: 未知的模式 '{mode}'")
        print("使用 python script.py 查看帮助")
        sys.exit(1)

if __name__ == "__main__":
    main()
