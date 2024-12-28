import os
from PIL import Image, ImageDraw, ImageFont

#chars = "中文测试"
ttf_path = "WenQuanYi_CNJP.ttf"
img_format = 'bmp' #图片类型

font_size = 60 #字体大小
img_w, img_h = 1024, 11520 #图片长宽
init_x, init_y = 0, 0 #初始位置
char_w, char_h = 64, 64 #字符长宽
interval_w, interval_h = 0, 0  #字符间距
# font_size = 30 #字体大小
# img_w, img_h = 512, 5760 #图片长宽
# init_x, init_y = 0, 0 #初始位置
# char_w, char_h = 32, 32 #字符长宽
# interval_w, interval_h = 0, 0  #字符间距

folder = f'{img_format}'
page_h = 12 * char_h #每页高度
char_count = 16 #每行字符数
fill_color = (255, 255, 255)
output_scale = 1 #输出缩放

#--------------------------------------------
bit_depth = 32 #位深
if bit_depth <= 8:
    grad = 256 // 2**bit_depth
    palette = []
    t = 0
    for i in range(2**bit_depth):
        palette.extend([t, t, t])
        t += grad

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

def init(height=img_h):
    global img, img_font, img_draw
    if bit_depth <= 8:
        img = Image.new(mode='P', size=(img_w, height))
        img.putpalette(palette)
    else:
        img = Image.new(mode='RGBA', size=(img_w, height))
    img_font = ImageFont.truetype(ttf_path, font_size)
    img_draw = ImageDraw.Draw(img)

#--------------------------------------------
def main():
    #填充文本：cp932有效字符
    count = 0
    draw_page_count = [15, 16] #多少页输出一次
    text = ''
    add_char = '　' #无效字符占位
    seq = 0
    first_list = list(range(0x81, 0xA0)) + list(range(0xE0, 0xF0)) + list(range(0xFA, 0xFD)) #第一字节
    second_list = list(range(0x40, 0x80)) + list(range(0x80, 0x100)) #第二字节
    for i in first_list:
        #累计
        valid = 0
        for j in second_list:
            bs = (i*0x100 + j).to_bytes(2, 'big')
            try:
                text += bs.decode('cp932')
                valid += 1
            except:
                #continue #不占位
                text += add_char #占位
        count += 1
        #绘制
        if count == draw_page_count[0] or i == len(first_list)-1:
            print(f'最后编码：{i:02X}{j:02X}')
            if len(draw_page_count) > 1:
                draw_page_count.pop(0)
            init((count) * page_h)
            draw_text(text)
            #降采样
            if output_scale != 1:
                global img
                target_size = (int(img.width * output_scale), int(img.height * output_scale))
                img = img.resize(target_size, Image.Resampling.BICUBIC)
            #img.show()
            #输出
            seq += 1
            name = f'ff_0{seq-1}l.{img_format}' #输出的图片名字
            print('\033[32m输出：\033[0m', name)
            if not os.path.exists(folder): os.makedirs(folder)
            img.save(os.path.join(folder, name), img_format)
            #累计清空
            text = ''
            count = 0

if __name__ == '__main__':
    main()