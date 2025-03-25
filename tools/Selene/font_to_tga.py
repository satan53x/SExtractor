# ------------------------------------------------------------
# https://github.com/satan53x/SExtractor/tree/main/tools/Font
# 生成selene引擎的字库tga图片
# ------------------------------------------------------------
import math
import os
from PIL import Image, ImageDraw, ImageFont

#chars = "中文测试"
work_dir = '.'
ttf_path = "../Font/WenQuanYi_CNJP.ttf"
img_format = 'tga' #图片类型
dat_name = 'FONT_01'
jis_map_path = "Selene_dll_1E4330h_20000h.dat"

font_size = 23 #字体大小
img_w, img_h = 1024, 1024 #图片长宽
init_x, init_y = 0, 0 #初始位置
char_w, char_h = 27, 27 #字符长宽
interval_w, interval_h = 2, 3 #字符间距

folder = f'{img_format}'
fill_color = (255, 255, 255)

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
	#最后一页
	factor = math.ceil((pos_y+char_h) / 128)
	if factor < img_h // 128:
		global img
		img = img.crop((0, 0, img_w, factor * 128))
	return []

def closest_power_of_two(n):
	if n <= 0:
		return 1
	lower = 1
	while lower * 2 <= n:
		lower *= 2
	return lower
	
def init(height=img_h):
	global img, img_font, img_draw, ascent, descent
	img = Image.new(mode='RGBA', size=(img_w, height))
	img_font = ImageFont.truetype(ttf_path, font_size)
	img_draw = ImageDraw.Draw(img)
	ascent, descent = img_font.getmetrics()
	print('metrics:', ascent, descent)

#--------------------------------------------
data_item_size = 8
file_item_size = 0x20

class DatManager:
	def read_jis_map(self):
		self.jis_map = []
		self.table = []
		fp = open(jis_map_path, 'rb')
		data = fp.read()
		fp.close()
		for jis_code in range(len(data)//2):
			bs = data[jis_code*2:(jis_code+1)*2]
			v = int.from_bytes(bs, 'little')
			self.jis_map.append(v)
			if v != 0xFFFF:
				self.table.append(jis_code)

	def generate(self, info_map, file_count):
		#head
		data = bytearray(b'FFS\x00')
		data.extend((0x16).to_bytes(1)) #未知
		data.extend(file_count.to_bytes(1))
		data.extend(b'\x00\x00')
		#table
		self.table_count = len(self.table)
		if self.table_count != 0x2492:
			print('Table count not match 0x2492', self.table_count)
		char_list = []
		for i in range(self.table_count):
			jis_code = self.table[i]
			if jis_code in info_map:
				char_index = len(char_list)
				info = info_map[jis_code]
				char_list.append(info)
			else:
				char_index = 0xFFFF
			bs = char_index.to_bytes(2, 'little')
			data.extend(bs)
		#file
		for seq in range(file_count):
			name = f'{dat_name}_{seq:02}'
			bs = name.encode('cp932').ljust(file_item_size, b'\x00')
			data.extend(bs)
		#data
		for info in char_list:
			N = self.create_char_index(info)
			bs = N.to_bytes(data_item_size, 'little')
			data.extend(bs)
		#修正
		self.char_count = len(char_list)
		print("Char count:", hex(self.char_count))
		data[6:8] = self.char_count.to_bytes(2, 'little')
		return data

	def create_char_index(self, info):
		return encode_to_N(*info['box'], *info['attr'], info['file_seq'])
	
def encode_to_N(x0, y0, x1, y1, a0, a1, b):
	N = 0
	N |= (y1 & 0x7FF) << 53  # y1 (11 bits)
	N |= (x1 & 0x7FF) << 42  # x1 (11 bits)
	N |= (y0 & 0x7FF) << 31  # y0 (11 bits)
	N |= (x0 & 0x7FF) << 20  # x0 (11 bits)
	N |= (a0 & 0x3F)  << 14  # a0 (6 bits)
	N |= (a1 & 0x3F)  << 8   # a1 (6 bits)
	N |= (b & 0xFF)          # b (8 bits)
	return N

#--------------------------------------------
def main():
	manager = DatManager()
	manager.read_jis_map()
	#填充文本：cp932有效字符
	count = 0
	text = []
	add_char = '　' #无效字符占位
	seq = 0
	#ASCII
	for jis_code in range(0x20, 0x7F):
		if manager.jis_map[jis_code] == 0xFFFF:
			print('Jis map not support:', chr(jis_code), hex(jis_code))
			continue
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
				if manager.jis_map[jis_code] == 0xFFFF:
					print('Jis map not support:', char, hex(jis_code))
					continue
				text.append([char, jis_code])
				count += 1
			except:
				continue #不占位
				#text += add_char #占位
	#绘制
	while (len(text) > 0):
		init()
		print('remain count:', len(text))
		text = draw_text(text, seq)
		#img.show()
		#break
		#输出
		name = f'{dat_name}_{seq:02}.{img_format}' #输出的图片名字
		print('\033[32m输出：\033[0m', name)
		os.makedirs(os.path.join(work_dir, 'new'), exist_ok=True)
		path = os.path.join(work_dir, 'new', name)
		img.save(path, img_format)
		seq += 1
	#输出dat
	data = manager.generate(info_map, seq)
	path = os.path.join(work_dir, 'new', dat_name + '.SFF')
	with open(path, 'wb') as fp:
		fp.write(data)

if __name__ == '__main__':
	main()