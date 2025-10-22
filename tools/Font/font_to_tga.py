# ------------------------------------------------------------
# https://github.com/satan53x/SExtractor/tree/main/tools/Font
# 生成字库tga图片，引擎名不清楚，游戏名为：ビフレストの魔物娼館
# ------------------------------------------------------------
import math
import os
import struct
from PIL import Image, ImageDraw, ImageFont

#chars = "中文测试"
work_dir = '.'
ttf_path = "./WenQuanYi_CNJP.ttf"
img_format = 'tga' #图片类型
dat_name = 'text'

font_size = 22 #字体大小
img_w, img_h = 1024, 4096 #图片长宽
init_x, init_y = 0, 0 #初始位置
char_w, char_h = 24, 24 #字符长宽
interval_w, interval_h = 1, 0 #字符间距

folder = f'{img_format}'
fill_color = (255, 255, 255)

FontName = "M+ 1c".encode('cp932') #字库名称
FontFilePath = "IMG/text.tga".encode('cp932') #字库路径

#--------------------------------------------
img:Image = None
img_font:ImageFont = None
img_draw:ImageDraw = None
ascent = 0
descent = 0
info_map = {}

#--------------------------------------------
def draw_text(text, file_seq):
	#print('\033[32m绘制：\033[0m', text)
	start = 0
	pos_x = init_x
	pos_y = init_y
	while start < len(text):
		char, jis_code = text[start]
		#绘制
		left, top, right, bottom = img_font.getbbox(char)
		if pos_x + right > img_w:
			#换行
			pos_x = init_x
			pos_y += char_h + interval_h
			if pos_y + char_h > img_h:
				#换页
				text = text[start:]
				return text
		#draw
		img_draw.text((pos_x, pos_y), char, font=img_font, fill=fill_color)
		x0 = pos_x
		y0 = pos_y
		x1 = pos_x + right
		y1 = pos_y + bottom
		box = [x0, y0, x1, y1]
		#添加信息
		info = {
			'code': jis_code,
			'char': char,
			'box': box,
			'attr': [interval_w, interval_h], #也许是间距？
			'file_seq': file_seq,
		}
		info_map[jis_code] = info
		pos_x += right + interval_w
		start += 1
	return []
	
def init(height=img_h):
	global img, img_font, img_draw, ascent, descent
	img = Image.new(mode='RGBA', size=(img_w, height))
	img_font = ImageFont.truetype(ttf_path, font_size)
	img_draw = ImageDraw.Draw(img)
	ascent, descent = img_font.getmetrics()
	print('metrics:', ascent, descent)

#--------------------------------------------
class DatManager:
	def __init__(self):
		self.FontName = FontName
		self.FontFilePath = FontFilePath

	def generate(self, info_map, file_count):
		#head
		data = bytearray()
		length = len(self.FontName)
		data.extend(struct.pack(f'<I{length}s', length, self.FontName)) #字体名
		data.extend(struct.pack('<II', char_w, char_h)) #字符宽高
		length = len(self.FontFilePath)
		data.extend(struct.pack(f'<I{length}s', length, self.FontFilePath)) #字体文件名
		data.extend(struct.pack('<I', len(info_map)))
		#data
		for jis_code, info in info_map.items():
			bs = self.create_char_index(info)
			data.extend(bs)
		#修正
		return data

	def create_char_index(self, info):
		x0, y0, x1, y1 = info['box']
		bs = struct.pack('<HBBIIIIII', 
			info['code'], 
			x1 - x0, 0x1E, 
			x0, y0, x1, y1, 
			0xFFFFFFFF, 0
		)
		return bs

#--------------------------------------------
def main():
	manager = DatManager()
	#填充文本：cp932有效字符
	count = 0
	text = []
	add_char = '　' #无效字符占位
	seq = 0
	#ASCII
	for jis_code in range(0x20, 0x7F):
		text.append([chr(jis_code), jis_code])
	#JIS
	first_list = list(range(0x81, 0xA0)) + list(range(0xE0, 0xEB)) + list(range(0xFA, 0xFD)) #第一字节
	second_list = list(range(0x40, 0x80)) + list(range(0x80, 0x100)) #第二字节
	for i in first_list:
		#累计
		for j in second_list:
			jis_code = i*0x100 + j
			bs = jis_code.to_bytes(2, 'big')
			try:
				char = bs.decode('cp932')
				text.append([char, jis_code])
				count += 1
			except:
				continue #不占位
				#text += add_char #占位
	#绘制
	init()
	print('total count:', len(text))
	text = draw_text(text, seq)
	#img.show()
	#break
	#输出
	name = f'{dat_name}.{img_format}' #输出的图片名字
	print('\033[32m输出：\033[0m', name)
	os.makedirs(os.path.join(work_dir, 'new'), exist_ok=True)
	path = os.path.join(work_dir, 'new', name)
	img.save(path, img_format)
	seq += 1
	print('remain count:', len(text))
	#输出dat
	data = manager.generate(info_map, seq)
	path = os.path.join(work_dir, 'new', dat_name + '.txt')
	with open(path, 'wb') as fp:
		fp.write(data)

if __name__ == '__main__':
	main()