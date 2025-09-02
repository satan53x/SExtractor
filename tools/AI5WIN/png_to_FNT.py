# ------------------------------------------------------------
# https://github.com/satan53x/SExtractor/tree/main/tools/AI5WIN
# ------------------------------------------------------------
from PIL import Image, ImageDraw, ImageFont
import numpy as np
from tqdm import trange

char_width = 24
char_height = 34
txt_file = 'char_list.txt'
img_file = 'char_list.png' #需要16个索引的调色板图片
font_file = 'FONT.FNT'
pal_file = 'FONT.PAL'
tbl_file = 'FONT.TBL'
start_x = 12
start_y = 12
margin_x = 4
margin_y = 0


#--------------------------------------------
text = []
img = None
dump_font = True

#--------------------------------------------
def read_char_list():
    with open(txt_file, encoding='utf-8') as f:
        for line in f:
            text.append(line.strip())

def read_img():
    global img
    img = Image.open(img_file)
    if img.mode != 'P':
        print('不是索引图像')
        exit()

def write_pal():
    #调色板
    pal_buffer = bytearray()
    pal = img.getpalette()
    pal_buffer.extend(pal)

    with open(pal_file, 'wb') as f:
        f.write(pal_buffer)
        print('\033[32m输出：\033[0m', pal_file)

#--------------------------------------------
def main():
    read_img()
    read_char_list()
    write_pal()
    font_buffer = bytearray()
    tbl_buffer = bytearray()
    pixel_data = np.array(img)
    width = char_width + margin_x
    height = char_height + margin_y
    for i, line in enumerate(text):
        x = start_x
        y = start_y + i * height
        for j, c in enumerate(line):
            #字符
            bs = c.encode('cp932')
            tbl_buffer.append(bs[1])
            tbl_buffer.append(bs[0])
            #像素
            if dump_font:
                region = pixel_data[y:y+char_height, x:x+char_width]
                data = region.flatten()
                for i in range(0, len(data), 2):
                    #组合高低位
                    b = data[i] << 4 | data[i+1]
                    font_buffer.append(b)
            x += width
    tbl_buffer.extend(b'\x00\x00')
    #输出
    with open(tbl_file, 'wb') as f:
        f.write(tbl_buffer)
        print('\033[32m输出：\033[0m', tbl_file)
    with open(font_file, 'wb') as f:
        f.write(font_buffer)
        print('\033[32m输出：\033[0m', font_file)

if __name__ == '__main__':
    main()