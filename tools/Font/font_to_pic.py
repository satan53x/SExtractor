import os
from PIL import Image, ImageDraw, ImageFont

#chars = "中文测试"
ttf_path = "WenQuanYi_CNJP.ttf"
img_format = 'webp' #图片类型

folder = 'image38'
font_size = 38 #字体大小
img_w, img_h = 1024, 640 #图片长宽
init_x, init_y = 10, 12 #初始位置
char_w, char_h = 38, 38 #字符长宽
interval_w, interval_h = 10, 10  #字符间距
# folder = 'image31'
# font_size = 31 #字体大小
# img_w, img_h = 800, 440 #图片长宽
# init_x, init_y = 10, 10 #初始位置
# char_w, char_h = 31, 31 #字符长宽
# interval_w, interval_h = 10, 10  #字符间距

char_count = 19 #每行字符数
fill_color = (255, 255, 255)

#--------------------------------------------
img:Image = None
img_font:ImageFont = None
img_draw:ImageDraw = None

#--------------------------------------------
def draw_line(line, pos_y):
    # 遍历每个字符
    pos_x = init_x
    for i, char in enumerate(line):
        img_draw.text((pos_x, pos_y), char, font=img_font, fill=fill_color)
        pos_x += char_w + interval_w

def draw_text(text):
    #print('\033[32m绘制：\033[0m', text)
    start = 0
    pos_y = init_y
    while start < len(text):
        line = text[start:start + char_count]
        start += char_count
        #绘制
        draw_line(line, pos_y)
        pos_y += char_h + interval_h

def init():
    global img, img_font, img_draw
    img = Image.new(mode='RGBA', size=(img_w, img_h))
    img_font = ImageFont.truetype(ttf_path, font_size)
    img_draw = ImageDraw.Draw(img)

#--------------------------------------------
def main():
    #填充文本：cp932有效字符
    add_char = '･' #无效字符占位
    seq = 0
    first_list = list(range(0x81, 0xA0)) + list(range(0xE0, 0xF0)) + list(range(0xFA, 0xFD)) #第一字节
    second_list = list(range(0x40, 0x7F)) + list(range(0x80, 0xFD)) #第二字节
    for i in first_list:
        #每一页
        init()
        text = ''
        valid = 0
        for j in second_list:
            bs = (i*0x100 + j).to_bytes(2, 'big')
            try:
                text += bs.decode('cp932')
                valid += 1
            except:
                #continue #不占位
                text += add_char #占位
        #绘制
        if valid == 0: continue
        draw_text(text)
        #img.show()
        #输出
        seq += 1
        name = f'fnt_s{font_size}_n{seq}.{img_format}' #输出的图片名字
        print('\033[32m输出：\033[0m', name)
        if not os.path.exists(folder): os.makedirs(folder)
        img.save(os.path.join(folder, name), img_format)

if __name__ == '__main__':
    main()