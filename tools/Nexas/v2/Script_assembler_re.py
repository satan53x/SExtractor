import glob
import json
import sys
from pathlib import Path
import os

# -1  don't auto split
#  0  auto split by ttf image width 
half_width = -1
max_width = 958
UnpackedDir = ".\\ASM"
CompiledDir = ".\\ScriptNew"

if half_width == 0:
	os.environ['PATH'] = 'vips-dev/bin' + ';' + os.environ['PATH']
	import pyvips

STRINGS = []

def getStringLength(string: str, postprocess = False) -> int:
	if (postprocess == False):
		i = 1
		sep = 1
	else:
		i = 0
		sep = 0
	parsed_string = ""
	while(i < len(string) - sep):
		if i+sep == len(string):
			c = string[i:]
		else:
			c = string[i:i+1]
		if (c != "@"):
			parsed_string += c
			i += 1
			continue
		i += 1
		c = string[i:i+1]
		match(c):
			case "n": # Break line
				parsed_string += "&#10;"
				i += 1
			case "v": # Voice file, always 8 characters
				i += 1
				i += 8
			case "r": # Text over text
				while(True):
					i += 1
					c = string[i:i+1]
					if (c == "@"):
						break
					parsed_string += c
				while(True):
					i += 1
					c = string[i:i+1]
					if (c == "@"):
						i += 1
						break
			case "b": #Bold(?) If it is, it seems Bold doesn't change width of text
				i += 1
			case "t": # Timed pause
				i += 1
				i += 4
			case "h": #Sprite change
				while(i < len(string)):
					i += 1
					c = string[i:i+1]
					if ("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_".find(c) == -1):
						break
			case "k": # activate preloaded effect
				i += 1
			case "s": #Unknown
				i += 1
				i += 4
			case "e": #Unknown
				i += 1
			case "m": #Unknown
				i += 1
				i += 2
			case "d": #Unknown
				i += 1
			case "o":
				i += 1
				i += 3
			case _:
				print(f"Unknown case! Tag: {c}")
				print(f"String: {string}")
				print("Aborting...")
				sys.exit()
	parsed_string = parsed_string.replace("&", "&amp;")
	if (len(parsed_string) == 0):
		return 0
	try:
		img = pyvips.Image.text(parsed_string, dpi=159,fontfile=sys.argv[2])
	except Exception as exc:
		print("Something went wrong with text processing!")
		print("Original string:")
		print(string)
		print("Parsed string len: %d" % len(parsed_string))
		print(parsed_string)
		print(exc)
		print("Aborting...")
		sys.exit()
	return img.width

def splitToList(string: str):
	return string[1:-1].split(",")

def AddToStrings(string: str):
	text = string[1:-1].replace("\\n", "\n")
	if (text not in STRINGS):
		index = 0
		for s in STRINGS:
			if s == None:
				break
			index += 1
		if index < len(STRINGS):
			STRINGS[index] = text
		else:
			STRINGS.append(text)
	else:
		index = STRINGS.index(text)
	return index

def initStrings(path):
	STRINGS.clear()
	filepath = os.path.splitext(path)[0] + ".json"
	if os.path.isfile(filepath):
		f = open(filepath, "r", encoding="UTF-8")
		content = json.load(f)
		f.close()
		for data in content:
			if data == False or data == True:
				STRINGS.append(None)
			else:
				STRINGS.append(data)
		if STRINGS[0] == None:
			STRINGS[0] = ""
	else:
		STRINGS.append("")

if (len(sys.argv) < 2):
	print("Usage:")
	print("Script_assembler_re.py [*.asm folder] [font filepath]")

if len(sys.argv) >= 2:
	scriptDir = sys.argv[1]
else:
	scriptDir = f'{UnpackedDir}'
files = glob.glob(f"{scriptDir}/*.asm")
os.makedirs(CompiledDir, exist_ok=True)

for i in range(0, len(files)):
	BASE = {}
	DUMP = []
	Extra = []
	print(Path(files[i]).stem)
	initStrings(files[i])
	file = open(files[i], "r", encoding="UTF-8")
	itr = 0
	for line in file:
		Args = line.strip().split("\t")
		if (Args[0][0] == ";"):
			continue
		if(Args[0][0:1] == "{"):
			value = int(Args[0][1:-1], base=16)
			if (("0x%04x" % value) in BASE):
				print("DETECTED IDENTICAL LABELS! CEASING OPERATION")
				print(Args[0])
				sys.exit()
			match(Args[1]):
				case "LOAD_STRING" | "LOAD_CUSTOM_TEXT" | "SET_EFFECT" | "SPECIAL_TEXT" | "CASE4":
					BASE["0x%04x" % (value + 1)] = itr + 1
					BASE["0x%04x" % value] = itr
					itr += 2

				case _:
					if (len(Args) == 4):
						values = splitToList(Args[3])
						for z in range(1, len(values)+1):
							BASE["0x%04x" % (value + z)] = itr + z
						BASE["0x%04x" % value] = itr
						itr = itr + 1 + len(values)
					else:
						BASE["0x%04x" % value] = itr
						itr += 1
		else:
			match(Args[1]):
				case "LOAD_STRING" | "LOAD_CUSTOM_TEXT" | "SET_EFFECT" | "SPECIAL_TEXT":
					itr += 2
				case "EXTRA":
					continue
				case _:
					if (len(Args) == 4):
						values = splitToList(Args[3])
						itr = itr + 1 + len(values)
					else:
						itr += 1
	file.seek(0)
	line = file.readlines()
	for iter in range(len(line)):
		Args = line[iter].strip().split("\t")
		if (len(Args) == 0 or Args[0][0] == ";"):
			continue
		elif (Args[1][0:3] == "CMD"):
			if (len(Args) == 4):
				values = splitToList(Args[3])
				for x in range(len(values)):
					DUMP.append(0x0.to_bytes(4, "little"))
					DUMP.append(int(values[x], base=16).to_bytes(4, "little"))
			DUMP.append(int(Args[1][4:], base=16).to_bytes(4, "little"))
			DUMP.append(int(Args[2], base=16).to_bytes(4, "little"))
		else: 
			match(Args[1]):
				case "INIT":
					if (len(Args) == 4):
						values = splitToList(Args[3])
						for x in range(len(values)):
							DUMP.append(0x0.to_bytes(4, "little"))
							DUMP.append(int(values[x], base=16).to_bytes(4, "little"))
					DUMP.append(0x1B.to_bytes(4, "little"))
					DUMP.append(int(Args[2], base=16).to_bytes(4, "little"))
				case "DEINIT":
					DUMP.append(0x1C.to_bytes(4, "little"))
					DUMP.append(int(Args[2], base=16).to_bytes(4, "little"))
				case "CMPR0":
					DUMP.append(0x10.to_bytes(4, "little"))
					DUMP.append(int(Args[2], base=16).to_bytes(4, "little"))
				case "CMPR5":
					DUMP.append(0x15.to_bytes(4, "little"))
					DUMP.append(int(Args[2], base=16).to_bytes(4, "little"))
				case "CMPR7":
					DUMP.append(0x17.to_bytes(4, "little"))
					DUMP.append(int(Args[2], base=16).to_bytes(4, "little"))
				case "CMPR8":
					DUMP.append(0x18.to_bytes(4, "little"))
					DUMP.append(int(Args[2], base=16).to_bytes(4, "little"))
				case "CMPRA":
					DUMP.append(0x1A.to_bytes(4, "little"))
					DUMP.append(int(Args[2], base=16).to_bytes(4, "little"))
				case "JNGE":
					DUMP.append(0x41.to_bytes(4, "little"))
					DUMP.append(BASE[Args[2]].to_bytes(4, "little"))
				case "JNLE":
					DUMP.append(0x42.to_bytes(4, "little"))
					DUMP.append(BASE[Args[2]].to_bytes(4, "little"))
				case "INF1":
					if (len(Args) == 4):
						values = splitToList(Args[3])
						for x in range(len(values)):
							DUMP.append(0x0.to_bytes(4, "little"))
							DUMP.append(int(values[x], base=16).to_bytes(4, "little"))
					DUMP.append(0x1D.to_bytes(4, "little"))
					DUMP.append(int(Args[2], base=16).to_bytes(4, "little"))
				case "INF2":
					DUMP.append(0x2C.to_bytes(4, "little"))
					DUMP.append(int(Args[2], base=16).to_bytes(4, "little"))
				case "PUSH":
					if (len(Args) == 4):
						values = splitToList(Args[3])
						for x in range(len(values)):
							DUMP.append(0x0.to_bytes(4, "little"))
							DUMP.append(int(values[x], base=16).to_bytes(4, "little"))
					DUMP.append(0x5.to_bytes(4, "little"))
					DUMP.append(int(Args[2], base=16).to_bytes(4, "little"))
				case "CMPR":
					DUMP.append(0x18.to_bytes(4, "little"))
					DUMP.append(int(Args[2], base=16).to_bytes(4, "little"))
				case "CASE4":
					DUMP.append(0x0.to_bytes(4, "little"))
					DUMP.append(AddToStrings(Args[2]).to_bytes(4, "little"))
					DUMP.append(0x4.to_bytes(4, "little"))
					DUMP.append(0x0.to_bytes(4, "little"))
				case "LOAD_STRING":
					DUMP.append(0x0.to_bytes(4, "little"))
					string = Args[2]
					Args_temp = line[iter+1].strip().split("\t")
					if (Args_temp[0][0] != ";") and half_width > 0:
						if (Args_temp[1] == "FUNC" and Args_temp[2] == "'PUSH_MESSAGE'") or (Args_temp[1] == "PUSH_MESSAGE"):						
							width = getStringLength(Args[2], False)
							if (width > max_width):
								new_string = []
								entry = []
								old_string = Args[2][1:-1].split(" ")
								for x in range(len(old_string)):
									entry.append(old_string[x])
									width = getStringLength(" ".join(entry), True)
									if (width > max_width):
										entry.pop()
										new_string.append(" ".join(entry))
										entry = []
										entry.append(old_string[x])
								new_string.append(" ".join(entry))
								if (len(new_string) > 4):
									print("Detected more than 4 lines for string:")
									print(Args[2])
									print("Aborting...")
									sys.exit()
								Args[2] = "@n".join(new_string)
								Args[2] = f"'{Args[2]}'"
					DUMP.append(AddToStrings(Args[2]).to_bytes(4, "little"))
					DUMP.append(0x5.to_bytes(4, "little"))
					DUMP.append(0x1.to_bytes(4, "little"))
				case "PUSH_MESSAGE":
					DUMP.append(0x7.to_bytes(4, "little"))
					DUMP.append(0x4006f.to_bytes(4, "little"))
				case "FUNC":
					DUMP.append(0x7.to_bytes(4, "little"))
					match(Args[2]):
						case "'GOTO_NEXT_SCENE'":
							DUMP.append(0x8035.to_bytes(4, "little"))
						case "'REGISTER_SCENE'":
							DUMP.append(0x18036.to_bytes(4, "little"))
						case "'WAIT'":
							DUMP.append(0x20005.to_bytes(4, "little"))
						case "'PUSH_MESSAGE'":
							DUMP.append(0x4006f.to_bytes(4, "little"))
						case "'BG_FADE'":
							DUMP.append(0x2009A.to_bytes(4, "little"))
						case "'BG_PUSH'":
							DUMP.append(0x8803E.to_bytes(4, "little"))
						case "'VOICE_FADE'":
							DUMP.append(0x301C2.to_bytes(4, "little"))
						case "'TEX_CLEAR'":
							DUMP.append(0x2014f.to_bytes(4, "little"))
						case "'TEX_FADE'":
							DUMP.append(0x60165.to_bytes(4, "little"))
						case "'TEX_PUSH'":
							DUMP.append(0x90143.to_bytes(4, "little"))
						case "'BGM_PLAY'":
							DUMP.append(0x501b2.to_bytes(4, "little"))
						case "'SE_PLAY'":
							DUMP.append(0x501bf.to_bytes(4, "little"))
						case "'SYSTEM_VOICE_PLAY'":
							DUMP.append(0x601c0.to_bytes(4, "little"))
						case _:
							DUMP.append(int(Args[2], base=16).to_bytes(4, "little"))
				case "LOAD_CUSTOM_TEXT":
					DUMP.append(0x0.to_bytes(4, "little"))
					DUMP.append(AddToStrings(Args[3]).to_bytes(4, "little"))
					DUMP.append(0x6.to_bytes(4, "little"))
					DUMP.append(int(Args[2], base=16).to_bytes(4, "little"))
				case "PUSH_CUSTOM_TEXT":
					DUMP.append(0x9.to_bytes(4, "little"))
					DUMP.append(0x1.to_bytes(4, "little"))
				case "SET_EFFECT":
					DUMP.append(0x0.to_bytes(4, "little"))
					DUMP.append(AddToStrings(Args[3]).to_bytes(4, "little"))
					DUMP.append(0x4.to_bytes(4, "little"))
					DUMP.append(int(Args[2], base=16).to_bytes(4, "little"))
				case "SPECIAL_TEXT":
					DUMP.append(0x0.to_bytes(4, "little"))
					DUMP.append(AddToStrings(Args[3].replace("~", "～")).to_bytes(4, "little"))
					DUMP.append(0xE.to_bytes(4, "little"))
					value = int(Args[2], base=16) + 0x80000000
					DUMP.append(value.to_bytes(4, "little"))
				case "EXTRA":
					Extra = splitToList(Args[2])
				case _:
					print("Undetected command!")
					print(Args[1])
					print(Args[0])
					sys.exit()

	new_file = open(f"{CompiledDir}/{Path(files[i]).stem}.bin", "wb")
	# new_file.write(int(len(Extra)/2).to_bytes(4, "little"))
	# for x in range(len(Extra)):
	# 	new_file.write(int(Extra[x], base=16).to_bytes(4, "little"))
	new_file.write(int(len(DUMP)/2).to_bytes(4, "little"))
	new_file.write(b"".join(DUMP))
	new_file.write(len(STRINGS).to_bytes(4, "little"))
	for x in range(len(STRINGS)):
		text = STRINGS[x]
		if text == None:
			text = ""
		string = text.encode("cp932") + b"\x00"
		new_file.write(string)
	# end data
	filepath = os.path.splitext(files[i])[0] + ".dat0"
	end_file = open(filepath , "rb")
	end_data = end_file.read()
	end_file.close()
	new_file.write(end_data)
	new_file.close()