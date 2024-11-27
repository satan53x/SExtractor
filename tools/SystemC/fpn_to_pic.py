# ------------------------------------------------------------
# https://github.com/satan53x/SExtractor/tree/main/tools/SystemC
# ------------------------------------------------------------
import os
import numpy as np
from PIL import Image
import matplotlib.pyplot as plt
from tqdm import trange

char_width = 24
char_height = char_width
font_file = f'mfont{char_width}.fpn'
pic_folder = f'font{char_width}'

def bytes_to_dot_matrix(byte_data, width=char_width, height=char_height):
    # 每个点占2位，所以总位数是width*height*2
    total_bits = width * height * 2
    if len(byte_data) * 8 < total_bits // 8:
        raise ValueError(f"字节数据不足，需要至少 {total_bits//8} 字节")
    # 创建点阵矩阵，用于存储2位值
    matrix = np.zeros((height, width), dtype=int)
    # 逐位填充矩阵
    for i in range(height):
        for j in range(width):
            # 计算当前点在所有字节中的位置（2位）
            bit_index = (i * width + j) * 2
            byte_pos = bit_index // 8
            bit_pos = bit_index % 8
            # 提取对应2位的值
            b = byte_data[byte_pos]
            bit_value = (b >> bit_pos) & 0b11
            matrix[i, j] = bit_value
    
    return matrix

def display_dot_matrix(matrix):
    # 定义4种状态的显示字符
    chars = ['□', '▫', '▪', '■']
    for row in matrix:
        print(''.join([chars[x] for x in row]))

def save_dot_matrix_image(matrix, filename='dot_matrix.png'):
    # 4种状态的灰度值
    grayscale_values = [0, 85, 170, 255] #0黑 255白
    img_array = np.zeros((matrix.shape[0], matrix.shape[1]), dtype=np.uint8)
    
    for i in range(matrix.shape[0]):
        for j in range(matrix.shape[1]):
            img_array[i, j] = grayscale_values[matrix[i, j]]
    
    img = Image.fromarray(img_array, mode='L')
    img.save(filename)
    #img.show()

def main():
    f = open(font_file, 'rb')
    data = f.read()
    f.close()
    if data[0:4] != b'FONT':
        print('Not a font file.')
        return
    if int.from_bytes(data[4:6], byteorder='little') != char_height:
        print('Wrong height.')
        return
    if not os.path.exists(pic_folder):
        os.makedirs(pic_folder)
    data = data[8:]
    char_bytes_len = char_width * 2 * char_height // 8
    for i in trange(len(data) // char_bytes_len):
        #if i == 100: break #test
        pos = char_bytes_len * i
        char_data = data[pos: pos+char_bytes_len]
        dot_matrix = bytes_to_dot_matrix(char_data)
        save_dot_matrix_image(dot_matrix, f'{pic_folder}/{i}.png')

def test():
    example_bytes = bytearray.fromhex("""
    00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
    00 00 00 00 00 00 00 00 00 00 00 19 00 00 00 00
    64 00 00 00 00 00 00 3F 00 00 00 00 FC 00 00 00
    00 00 00 3F 00 00 00 00 FC 00 00 00 00 00 00 3F
    00 00 00 00 FC 00 00 00 00 00 00 3F 00 00 00 00
    FC 00 00 00 80 AA AA BF AA AA AA AA FE AA AA 02
    E0 FF FF FF FF FF FF FF FF FF FF 0B D0 FF FF FF
    FF FF FF FF FF FF FF 0B 80 AA AA BF AA AA AA AA
    FE AA AA 02 00 00 00 3F 00 00 00 00 FC 00 00 00
    00 00 00 3F 00 00 00 00 FC 00 00 00 00 00 00 3F
    00 D0 07 00 FC 00 00 00 00 00 00 3F 00 F0 0B 00
    FC 00 00 00 00 00 00 19 00 F0 0B 00 00 00 00 00
    00 00 00 00 00 F0 0B 00 00 00 00 00 00 00 00 00
    00 F0 0B 00 00 00 00 00 00 00 00 00 00 F0 0B 00
    00 00 00 00 D0 FF FF FF FF FF FF FF FF FF FF 07
    E0 FF FF FF FF FF FF FF FF FF FF 0B D0 FF FF FF
    FF FF FF FF FF FF FF 07 00 00 00 00 00 F0 0B 00
    00 00 00 00 00 00 00 00 00 F0 0B 00 00 00 00 00
    00 00 00 00 00 F0 0B 00 00 00 00 00 00 00 00 00
    00 F0 0B 00 00 00 00 00 00 00 00 00 00 F0 0B 00
    00 00 00 00 00 00 00 00 00 F0 0B 00 00 00 00 00
    00 00 A9 AA AA FA AF AA AA 6A 00 00 00 C0 FF FF
    FF FF FF FF FF FF 03 00 00 D0 FF FF FF FF FF FF
    FF FF 07 00 00 E0 AF AA AA AA AA AA AA FA 0B 00
    00 E0 0F 00 00 00 00 00 00 F0 0B 00 00 E0 0F 00
    00 00 00 00 00 F0 0B 00 00 E0 0F 00 00 00 00 00
    00 F0 0B 00 00 E0 0F 00 00 00 00 00 00 F0 0B 00
    00 E0 0F 00 00 00 00 00 00 F0 0B 00 00 E0 0F 00
    00 00 00 00 00 F0 0B 00 00 E0 0F 00 00 00 00 00
    00 F0 0B 00 00 E0 0F 00 00 00 00 00 00 F0 0B 00
    00 E0 0F 00 00 00 00 00 00 F0 0B 00 00 E0 0F 00
    00 00 00 00 00 F0 0B 00 00 E0 AF AA AA AA AA AA
    AA FE 0B 00 00 D0 FF FF FF FF FF FF FF FF 07 00
    00 C0 FF FF FF FF FF FF FF FF 03 00 00 00 A9 AA
    AA AA AA AA AA 6A 00 00 00 00 00 00 00 00 00 00
    00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00

    """)
    dot_matrix = bytes_to_dot_matrix(example_bytes)

    print("控制台文本显示:")
    display_dot_matrix(dot_matrix)

    #print("\n保存图像:")
    save_dot_matrix_image(dot_matrix)

if __name__ == '__main__':
    main()