# ------------------------------------------------------------
# https://github.com/satan53x/SExtractor/tree/main/tools/AI5WIN
# ------------------------------------------------------------
import sys
from PIL import Image

PAL_filename = 'FONT.PAL'
FNT_filename = 'FONT.FNT'
char_width = 24
char_height = 34

char_size = char_height * char_width // 2

#-------------------------------
palette = []
fnt_data = None

def read_pal():
	palette.clear()
	with open(PAL_filename, 'rb') as f:
		data = f.read()
	for i in range(len(data) // 3):
		r, g, b = data[i * 3], data[i * 3 + 1], data[i * 3 + 2]
		color = (int(r), int(g), int(b))
		palette.append(color)

def read_fnt():
	global fnt_data
	with open(FNT_filename, 'rb') as f:
		fnt_data = f.read()
	
def get_char(seq):
	pos = seq * char_size
	data = fnt_data[pos:pos + char_size]
	# 每字节拆分为2像素
	pixels = []
	for byte in data:
		for shift in (4, 0):
			index = (byte >> shift) & 0x0F
			if index == 0:
				pixel = (0, 0, 0, 0)
			else:
				pixel = (palette[index][0], palette[index][1], palette[index][2], 255)
			pixels.append(pixel)
	return pixels

def show(seq_list):
	count = len(seq_list)
	all_pixels = []
	for seq in seq_list:
		char_pixels = get_char(seq)
		all_pixels.extend(char_pixels)
	#显示
	img = Image.new("RGBA", (char_width, char_height * count))
	img.putdata(all_pixels)
	img.show()

def main():
	pass

if __name__ == "__main__":
	read_pal()
	read_fnt()
	count = len(fnt_data) // char_size
	print('Count:', count)
	if len(sys.argv) > 2:
		start = int(sys.argv[1])
		end = int(sys.argv[2])
		show(range(start, end))
	else:
		show(0, 16)