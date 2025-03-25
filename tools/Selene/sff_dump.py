import json
import os
from PIL import Image

work_dir = 'new'
dat_name= 'FONT_01.SFF'
pic_postfix = 'tga'

#------------------------------------------------------
char_item_size = 8
file_item_size = 0x20

pic_list = []

#------------------------------------------------------
def extract_bits(value, start, length):
	return (value >> start) & ((1 << length) - 1)

def extract_box_and_attributes(N):
	y1 = extract_bits(N, 53, 11)
	x1 = extract_bits(N, 42, 11)
	y0 = extract_bits(N, 31, 11)
	x0 = extract_bits(N, 20, 11)
	a0 = extract_bits(N, 14, 6)
	a1 = extract_bits(N, 8, 6)
	b = extract_bits(N, 0, 8)
	return (x0, y0, x1, y1), (a0, a1), b

class DatManager:
	def parse(self, data):
		#head
		start = 0
		end = 0x8
		self.head_section = data[start:end]
		self.file_count = self.head_section[5]
		self.char_count = int.from_bytes(self.head_section[6:8], 'little') #有效的元素个数
		#table
		self.table_count = 0x2492 #所有元素个数，固定
		start = end
		end += self.table_count * 2
		self.table_section = data[start:end]
		#file
		start = end
		end += self.file_count * file_item_size
		self.file_section = data[start:end]
		self.pic_names = []
		pos = 0
		for i in range(self.file_count):
			bs = self.file_section[pos:pos+file_item_size]
			pos += file_item_size
			bs = bs.rstrip(b'\x00')
			self.pic_names.append(bs.decode('utf-8'))
		#char
		start = end
		end += self.char_count * char_item_size
		self.char_section = data[start:end]
		if end != len(data):
			print("Dat length not match", end, len(data))

	def get_index(self, index):
		start = index*char_item_size
		bs = self.char_section[start:start+char_item_size]
		n = int.from_bytes(bs, 'little')
		box, attr, file_seq = extract_box_and_attributes(n)
		return box, attr, file_seq
	
manager = DatManager()
#------------------------------------------------------
def load_pic():
	#载入图片
	pic_list.clear()
	for i in range(len(manager.pic_names)):
		path = os.path.join(work_dir, manager.pic_names[i]+'.'+pic_postfix)
		image = Image.open(path)
		pic_list.append(image)

def dump():
	out = []
	for i in range(0, manager.char_count):
		box, attr, file_seq = manager.get_index(i)
		item = {
			"index": f'{i:04X}',
			"file_seq": file_seq,
			"box": box,
			"attr": attr,
		}
		out.append(item)
	path = os.path.join(work_dir, 'dump.json')
	s = json.dumps(out, indent=4, ensure_ascii=False)
	with open(path, 'w', encoding="utf-8") as fp:
		fp.write(s)
		print('Dump json.')

def test():
	#ち 82BF    485 56 20 27
	#dll 1E4330+82BF*2=1F48AE 018D
	#table 018D*2=0310 00A4
	#char 00A4*8=520 00C4301E 1ADCC709
	index = 0x00A4
	box, attr, file_seq = manager.get_index(index)
	print(f'{index:04X} {file_seq:04X}')
	print(f'{box[0]} {box[1]} {box[2]} {box[3]}')
	print(f'{attr[0]} {attr[1]}')
	image = pic_list[file_seq]
	sub = image.crop(box)
	sub.show()

def main():
	path = os.path.join(work_dir, dat_name)
	file = open(path, 'rb')
	if not file:
		print("Open file error:", path)
		return
	data = file.read()
	manager.parse(data)
	load_pic()
	#test()
	dump()
	print('Done.')

if __name__ == "__main__":
	main()