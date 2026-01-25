#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
obj文件批量提取和写回脚本
支持从cp932编码的obj文件提取字符串到utf-8编码的txt文件
以及从修改后的txt文件重新生成obj文件
"""

import os
import struct
import argparse
from pathlib import Path


class ObjProcessor:
    def __init__(self):
        self.script_dir = Path(__file__).parent
        self.obj_dir = self.script_dir / "obj"
        self.out_dir = self.script_dir / "out"
    
    def extract_strings_from_obj(self, obj_path):
        """从obj文件提取字符串"""
        try:
            with open(obj_path, 'rb') as f:
                data = f.read()
            
            if len(data) < 8:
                print(f"警告: {obj_path} 文件太小，跳过")
                return None
            
            # 读取第一个索引条目（其他字节区，不提取）- 4字节地址+2字节长度
            first_addr = struct.unpack('<I', data[0:4])[0]
            first_length = struct.unpack('<H', data[4:6])[0]
            
            # 读取第二个索引条目来确定索引区结束位置
            string_start = struct.unpack('<I', data[6:10])[0]
            
            # 计算索引条目数量（每个条目6字节：4字节地址+2字节长度）
            index_count = string_start // 6
            
            strings = []
            
            # 从第二个索引条目开始解析（跳过第一个其他字节区）
            for i in range(1, index_count):  # 从索引1开始，跳过索引0
                offset = i * 6  # 每个索引条目6字节：4字节地址+2字节长度
                if offset + 6 > len(data):
                    break
                
                # 读取绝对地址和长度（4字节地址+2字节长度）
                addr = struct.unpack('<I', data[offset:offset+4])[0]
                length = struct.unpack('<H', data[offset+4:offset+6])[0]
                
                # 提取字符串
                if addr < len(data) and addr + length <= len(data):
                    string_bytes = data[addr:addr+length]
                    try:
                        # 尝试用cp932解码
                        string_text = string_bytes.decode('cp932', errors='ignore')
                        # 将\x00字节转义为可见字符串，避免在UTF-8文本中丢失
                        string_text = string_text.replace('\x00', '\\x00')
                        # 添加地址和长度标记
                        marked_string = f"【{addr:08x}{length:08x}】{string_text}"
                        strings.append(marked_string)
                    except UnicodeDecodeError:
                        print(f"警告: 无法解码字符串 at {addr:08x}")
                        strings.append(f"【{addr:08x}{length:08x}】<解码失败>")
            
            return strings
            
        except Exception as e:
            print(f"错误: 处理文件 {obj_path} 时出错: {e}")
            return None
    
    def write_strings_to_txt(self, strings, txt_path):
        """将字符串写入txt文件"""
        try:
            with open(txt_path, 'w', encoding='utf-8') as f:
                for string in strings:
                    f.write(string + '\n')
            return True
        except Exception as e:
            print(f"错误: 写入文件 {txt_path} 时出错: {e}")
            return False
    
    def read_strings_from_txt(self, txt_path):
        """从txt文件读取字符串"""
        try:
            with open(txt_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            strings = []
            for line in lines:
                line = line.rstrip('\n\r')
                if line:
                    strings.append(line)
            
            return strings
        except Exception as e:
            print(f"错误: 读取文件 {txt_path} 时出错: {e}")
            return None
    
    def parse_marked_string(self, marked_string):
        """解析带标记的字符串，提取地址、长度和文本"""
        if not marked_string.startswith('【') or '】' not in marked_string:
            return None, None, marked_string
        
        try:
            end_bracket = marked_string.find('】')
            marker = marked_string[1:end_bracket]
            text = marked_string[end_bracket+1:]
            
            if len(marker) == 16:  # 8位地址 + 8位长度
                addr = int(marker[:8], 16)
                length = int(marker[8:], 16)
                return addr, length, text
            else:
                return None, None, text
        except ValueError:
            return None, None, marked_string
    
    def rebuild_obj_file(self, txt_path, original_obj_path, output_obj_path):
        """从txt文件重建obj文件"""
        try:
            # 读取修改后的字符串
            strings = self.read_strings_from_txt(txt_path)
            if not strings:
                return False
            
            # 读取原始obj文件
            with open(original_obj_path, 'rb') as f:
                original_data = f.read()
            
            # 读取原始文件的第一个索引条目（字符串区结尾地址信息）- 4字节地址+2字节长度
            first_addr = struct.unpack('<I', original_data[0:4])[0]
            first_length = struct.unpack('<H', original_data[4:6])[0]
            
            # 提取原始的其他字节区数据（从第一个地址之后开始到文件结尾）
            other_bytes = original_data[first_addr:]
            
            # 解析字符串并计算新的布局
            parsed_strings = []
            for string in strings:
                old_addr, old_length, text = self.parse_marked_string(string)
                parsed_strings.append((old_addr, old_length, text))
            
            # 计算新的字符串区数据
            string_data = b''
            new_indices = []
            
            # 计算索引区大小（包括第一个其他字节区索引）- 每个索引6字节
            total_indices = len(parsed_strings) + 1  # +1 for other bytes section
            string_start_pos = total_indices * 6
            
            # 计算字符串数据
            for old_addr, old_length, text in parsed_strings:
                # 将\\x00转换回\x00字节
                text = text.replace('\\x00', '\x00')
                
                # 将文本编码为cp932，保留\x00字节
                try:
                    # 直接编码，保留所有字符包括\x00
                    encoded_text = text.encode('cp932')
                except UnicodeEncodeError:
                    print(f"警告: 无法编码文本 '{text}' 为cp932，使用忽略模式")
                    encoded_text = text.encode('cp932', errors='ignore')
                
                # 记录新的绝对地址和实际长度
                new_addr = string_start_pos + len(string_data)
                actual_length = len(encoded_text)
                new_indices.append((new_addr, actual_length))  # 使用实际长度
                
                string_data += encoded_text
            
            # 其他字节区放在字符串数据之后
            other_bytes_start = string_start_pos + len(string_data)
            
            # 构建新的索引区
            index_data = b''
            
            # 第一个索引：其他字节区（地址指向字符串区结尾，即其他字节区开始位置）- 4字节地址+2字节长度
            other_bytes_entry = struct.pack('<IH', other_bytes_start, first_length)
            index_data += other_bytes_entry
            
            # 其他索引：字符串区 - 4字节地址+2字节长度
            for i, (addr, length) in enumerate(new_indices):
                index_entry = struct.pack('<IH', addr, length)
                index_data += index_entry
            
            # 构建新的obj文件：索引区 + 字符串区 + 其他字节区
            new_obj_data = index_data + string_data + other_bytes
            
            # 写入新的obj文件
            with open(output_obj_path, 'wb') as f:
                f.write(new_obj_data)
            
            return True
            
        except Exception as e:
            print(f"错误: 重建obj文件时出错: {e}")
            return False
    
    def extract_all(self, input_dir="script"):
        """批量提取所有obj文件"""
        input_path = Path(input_dir)
        if not input_path.exists():
            print(f"错误: 输入目录 {input_dir} 不存在")
            return False
        
        # 创建输出目录
        self.obj_dir.mkdir(exist_ok=True)
        
        obj_files = list(input_path.glob("*.obj"))
        if not obj_files:
            print(f"在目录 {input_dir} 中没有找到obj文件")
            return False
        
        success_count = 0
        for obj_file in obj_files:
            print(f"处理文件: {obj_file.name}")
            
            # 提取字符串
            strings = self.extract_strings_from_obj(obj_file)
            if strings is None:
                continue
            
            # 生成txt文件路径
            txt_file = self.obj_dir / f"{obj_file.stem}.txt"
            
            # 写入txt文件
            if self.write_strings_to_txt(strings, txt_file):
                print(f"  -> 提取完成: {txt_file}")
                success_count += 1
            else:
                print(f"  -> 提取失败: {obj_file.name}")
        
        print(f"\n提取完成! 成功处理 {success_count}/{len(obj_files)} 个文件")
        return True
    
    def rebuild_all(self, input_dir="script"):
        """批量重建所有obj文件"""
        input_path = Path(input_dir)
        if not input_path.exists():
            print(f"错误: 输入目录 {input_dir} 不存在")
            return False
        
        if not self.obj_dir.exists():
            print(f"错误: obj目录 {self.obj_dir} 不存在，请先执行提取操作")
            return False
        
        # 创建输出目录
        self.out_dir.mkdir(exist_ok=True)
        
        txt_files = list(self.obj_dir.glob("*.txt"))
        if not txt_files:
            print(f"在目录 {self.obj_dir} 中没有找到txt文件")
            return False
        
        success_count = 0
        for txt_file in txt_files:
            print(f"处理文件: {txt_file.name}")
            
            # 找到对应的原始obj文件
            original_obj = input_path / f"{txt_file.stem}.obj"
            if not original_obj.exists():
                print(f"  -> 警告: 找不到原始obj文件 {original_obj}")
                continue
            
            # 生成输出obj文件路径
            output_obj = self.out_dir / f"{txt_file.stem}.obj"
            
            # 重建obj文件
            if self.rebuild_obj_file(txt_file, original_obj, output_obj):
                print(f"  -> 重建完成: {output_obj}")
                success_count += 1
            else:
                print(f"  -> 重建失败: {txt_file.name}")
        
        print(f"\n重建完成! 成功处理 {success_count}/{len(txt_files)} 个文件")
        return True


def main():
    parser = argparse.ArgumentParser(description='obj文件批量提取和写回工具')
    parser.add_argument('action', choices=['extract', 'rebuild'], 
                       help='操作类型: extract=提取字符串, rebuild=重建obj文件')
    parser.add_argument('--input', '-i', default='script', 
                       help='输入目录路径 (默认: script)')
    
    args = parser.parse_args()
    
    processor = ObjProcessor()
    
    if args.action == 'extract':
        print("开始提取obj文件中的字符串...")
        processor.extract_all(args.input)
    elif args.action == 'rebuild':
        print("开始重建obj文件...")
        processor.rebuild_all(args.input)


if __name__ == "__main__":
    main()
