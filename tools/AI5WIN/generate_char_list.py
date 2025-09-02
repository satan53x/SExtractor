# ------------------------------------------------------------
# https://github.com/satan53x/SExtractor/tree/main/tools/AI5WIN
# ------------------------------------------------------------
import unicodedata

TBL_TXT = 'tbl.txt'
OUT_TXT = 'char_list.txt'

def main():
	text = []
	with open(TBL_TXT, 'r', encoding='utf-8') as f:
		string = f.read()
		for char in string:
			text.append(char)

	#JIS
	first_list = list(range(0x81, 0xA0)) + list(range(0xE0, 0xEB)) + list(range(0xFA, 0xFD)) #第一字节
	second_list = list(range(0x40, 0x80)) + list(range(0x80, 0x100)) #第二字节
	for i in first_list:
		#每一页
		valid = 0
		for j in second_list:
			bs = (i*0x100 + j).to_bytes(2, 'big')
			try:
				char = bs.decode('cp932')
				if unicodedata.east_asian_width(char) not in ('F', 'W'):
					continue
				if char not in text:
					text.append(char)
					valid += 1
			except:
				continue #不占位
				#page.append(add_char) #占位
		#页结束
		print(f'Page {i:02X}: append {valid}')
	#输出
	col_count = 80
	with open(OUT_TXT, 'w', encoding='utf-8') as f:
		for i in range(0, len(text), col_count):
			f.write(''.join(text[i:i+col_count]) + '\n')

main()