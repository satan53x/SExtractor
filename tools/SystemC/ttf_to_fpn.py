# ------------------------------------------------------------
# https://github.com/satan53x/SExtractor/tree/main/tools/SystemC
# ------------------------------------------------------------
from PIL import Image, ImageDraw, ImageFont
import numpy as np
from tqdm import trange

char_width = 24
char_height = char_width
ttf_path = "../Font/WenQuanYi_CNJP.ttf"
font_file = f'mfont{char_width}.fpn'

divide_array = [180, 120, 80] #灰度分界，对应3,2,1
bg_color = 0
fill_color = 255
#推荐根据ttf文件调整居中代码
x_fix = 0 #x轴偏移修正
y_fix = 0 #y轴偏移修正

#--------------------------------------------
img_font:ImageFont = None
buffer:bytearray = None

#--------------------------------------------
def char_to_bitmap(font_path, char):
    img = Image.new('L', (char_width, char_height), color=bg_color)
    draw = ImageDraw.Draw(img)
    
    #居中算法
    left, top, right, bottom = img_font.getbbox(char) #从上向下
    t_center = ((left + right) / 2, (bottom + top) / 2)
    x = int(char_width/2 - t_center[0]) + x_fix
    y = int(char_height - bottom) + y_fix

    # Draw the character
    draw.text((x, y), char, font=img_font, fill=fill_color)
    #img.show()
    
    # Convert to numpy array
    bitmap = np.array(img)
    # Quantize
    # [0, 85, 170, 255] -> [0, 1, 2, 3]
    conditions = [bitmap > divide_array[0], bitmap > divide_array[1], bitmap > divide_array[2]]
    choices = [3, 2, 1]
    bitmap_2bit = np.select(conditions, choices, default=0)

    return bitmap_2bit

def draw_text(text):
    #print('\033[32m绘制：\033[0m', text)
    pos = 0
    
    for progress in trange(len(text)):
        c = text[progress]
        bitmap_2bit = char_to_bitmap(ttf_path, c)
        #buffer写入单个字
        for i in range(char_height):
            saved_width = char_width // 4 * 4
            if char_width % 4 != 0:
                saved_width += 4
            for j in range(0, saved_width, 4):
                #单点2bit, 4个点合并为一个字节，不足4个则补0
                n = 0 #单字节数值
                for offset in range(0, 4):
                    pos = j + offset
                    if pos >= char_width:
                        value = 0
                    else:
                        value = bitmap_2bit[i][pos]
                    n += value << (offset * 2)
                buffer.append(n)
                #print(i, j, hex(n))
        #print('Write：', c)
                    
def init():
    global buffer, img_font
    img_font = ImageFont.truetype(ttf_path, char_width)
    buffer = bytearray()
    buffer.extend(b'FONT')
    buffer.extend(int.to_bytes(char_width, byteorder='little', length=2))
    buffer.extend(b'\x00\x00')

#--------------------------------------------
def main():
    init()
    #填充文本：cp932有效字符
    add_char = '･' #无效字符占位
    seq = 0
    first_list = list(range(0x81, 0xA0)) + list(range(0xE0, 0xF0)) #第一字节
    second_list = list(range(0x40, 0x7F)) + list(range(0x80, 0xFD)) #第二字节
    text = []
    for i in first_list:
        #每一页
        page = []
        valid = 0
        for j in second_list:
            bs = (i*0x100 + j).to_bytes(2, 'big')
            try:
                page.append(bs.decode('shift-jis'))
                valid += 1
            except:
                #continue #不占位
                page.append(add_char) #占位
        #绘制
        #if valid == 0: continue
        print(f'Page {i:02X}: count {len(page)}')
        text.extend(page)
    draw_text(text)

    #输出
    print('\033[32m输出：\033[0m', font_file)
    f = open(font_file, 'wb')
    f.write(buffer)
    f.close()

if __name__ == '__main__':
    main()