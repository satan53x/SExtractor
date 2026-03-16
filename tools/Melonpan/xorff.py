import os
import sys
import shutil

def xor_file(input_path, output_path):
    """对单个文件进行XOR 0xFF操作"""
    try:
        with open(input_path, 'rb') as infile:
            data = infile.read()
        
        # 对每个字节进行XOR 0xFF操作
        xor_data = bytes(b ^ 0xFF for b in data)
        
        with open(output_path, 'wb') as outfile:
            outfile.write(xor_data)
        
        return True
    except Exception as e:
        print(f"处理文件 {input_path} 时出错: {e}")
        return False

def process_folder(input_folder, output_folder):
    """处理整个文件夹"""
    # 检查输入文件夹是否存在
    if not os.path.exists(input_folder):
        print(f"错误：输入文件夹 '{input_folder}' 不存在")
        return False
    
    # 创建输出文件夹（如果不存在）
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)
        print(f"已创建输出文件夹: {output_folder}")
    
    # 统计信息
    total_files = 0
    processed_files = 0
    failed_files = 0
    
    # 遍历输入文件夹中的所有文件
    for root, dirs, files in os.walk(input_folder):
        # 计算相对路径，用于在输出文件夹中保持目录结构
        rel_path = os.path.relpath(root, input_folder)
        if rel_path == '.':
            rel_path = ''
        
        # 创建对应的输出子文件夹
        output_subdir = os.path.join(output_folder, rel_path)
        if not os.path.exists(output_subdir):
            os.makedirs(output_subdir)
        
        # 处理当前文件夹中的所有文件
        for file in files:
            input_file = os.path.join(root, file)
            output_file = os.path.join(output_subdir, file)
            
            print(f"处理: {input_file} -> {output_file}")
            total_files += 1
            
            if xor_file(input_file, output_file):
                processed_files += 1
            else:
                failed_files += 1
    
    # 打印统计信息
    print("\n" + "="*50)
    print(f"处理完成！")
    print(f"总文件数: {total_files}")
    print(f"成功处理: {processed_files}")
    print(f"处理失败: {failed_files}")
    print(f"输出文件夹: {output_folder}")
    print("="*50)
    
    return True

def main():
    # 检查命令行参数
    if len(sys.argv) != 3:
        print("使用方法: python 1.py 输入文件夹 输出文件夹")
        print("示例: python 1.py ./input ./output")
        sys.exit(1)
    
    input_folder = sys.argv[1]
    output_folder = sys.argv[2]
    
    # 确认操作
    print(f"输入文件夹: {input_folder}")
    print(f"输出文件夹: {output_folder}")
    print("此操作将对所有文件进行 XOR 0xFF 处理")
    
    # 如果输入和输出文件夹相同，给出警告
    if os.path.abspath(input_folder) == os.path.abspath(output_folder):
        print("\n警告：输入和输出文件夹相同！这将覆盖原始文件！")
        response = input("是否继续？(y/N): ")
        if response.lower() != 'y':
            print("操作已取消")
            sys.exit(0)
    else:
        response = input("是否继续？(Y/n): ")
        if response.lower() == 'n':
            print("操作已取消")
            sys.exit(0)
    
    # 执行处理
    process_folder(input_folder, output_folder)

if __name__ == "__main__":
    main()