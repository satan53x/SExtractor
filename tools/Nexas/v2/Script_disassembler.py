import glob
import io
import sys
from pathlib import Path
import os
import json

UnpackedDir = ".\\ASM"
ClearStrings = False

def swap32(x: str):
	string = x[6:8] + x[4:6] + x[2:4] + x[0:2]

	while(string[0] == "0"):
		if len(string) < 2:
			break
		string = string[1:]
	return string

if len(sys.argv) >= 2:
	scriptDir = sys.argv[1]
else:
	scriptDir = '.\\Script'
files = glob.glob(f"{scriptDir}/*.bin")

def Sort(key: int):
	return key

def ProcessDump(BLOB: list):
	pops = []
	for i in range(len(BLOB["COMMANDS"])):
		match(BLOB["COMMANDS"][i]["CMD"]):
			case 4:
				if (BLOB["COMMANDS"][i]["DATA"] != "00000000"):
					continue
				if "U32" not in BLOB["COMMANDS"][i].keys():
					continue
				elif len(BLOB["COMMANDS"][i]["U32"]) > 1:
					#print("ERROR")
					continue
				if (BLOB["COMMANDS"][i]["U32"][0] != "00000080"):
					continue
				if (BLOB["COMMANDS"][i-1]["CMD"] != 4):
					continue
				if "U32" not in BLOB["COMMANDS"][i-1].keys():
					string_id = -1
				elif len(BLOB["COMMANDS"][i-1]["U32"]) > 1:
					#print("ERROR")
					continue
				else: 
					string_id = int.from_bytes(bytes.fromhex(BLOB["COMMANDS"][i-1]["U32"][0]), "little", signed=True)
				if (string_id < 0):
					continue
				BLOB["COMMANDS"][i-1]["CMD"] = "CASE4"
				BLOB["COMMANDS"][i-1]["STRING"] = BLOB["STRINGS"][string_id]
				BLOB["COMMANDS"][i-1].pop("DATA")
				if string_id not in pops:
					pops.append(string_id)
			case 5:
				if (BLOB["COMMANDS"][i]["DATA"] != "01000000"):
					BLOB["COMMANDS"][i]["CMD"] = "PUSH"
					continue
				if "U32" not in BLOB["COMMANDS"][i].keys():
					string_id = -1
				elif len(BLOB["COMMANDS"][i]["U32"]) > 1:
					print("ERROR")
				else: 
					string_id = int.from_bytes(bytes.fromhex(BLOB["COMMANDS"][i]["U32"][0]), "little", signed=True)
				if (string_id < 0):
					continue
				BLOB["COMMANDS"][i].pop("U32")
				BLOB["COMMANDS"][i]["CMD"] = "LOAD_STRING"
				BLOB["COMMANDS"][i]["STRING"] = BLOB["STRINGS"][string_id]
				BLOB["COMMANDS"][i].pop("DATA")
				if string_id not in pops:
					pops.append(string_id)
			case 7:
					BLOB["COMMANDS"][i]["CMD"] = "FUNC"
			case 9:
				if (BLOB["COMMANDS"][i]["DATA"] != "01000000"):
					continue
				if BLOB["COMMANDS"][i-1]["CMD"] != 6:
					continue
				string_id = int.from_bytes(bytes.fromhex(BLOB["COMMANDS"][i-1]["U32"][0]), "little", signed=True)
				if (string_id < 0 and string_id != -2147483644):
					continue
				if (string_id != -2147483644):
					BLOB["COMMANDS"][i]["CMD"] = "PUSH_CUSTOM_TEXT"
					BLOB["COMMANDS"][i].pop("DATA")
					BLOB["COMMANDS"][i-1]["STRING"] = BLOB["STRINGS"][string_id]
					BLOB["COMMANDS"][i-1].pop("U32")
					BLOB["COMMANDS"][i-1]["CMD"] = "LOAD_CUSTOM_TEXT"
					if string_id not in pops:
						pops.append(string_id)
					if BLOB["COMMANDS"][i-2]["CMD"] != 4:
						continue
					if "U32" not in BLOB["COMMANDS"][i-2].keys():
						continue
					string_id = int.from_bytes(bytes.fromhex(BLOB["COMMANDS"][i-2]["U32"][0]), "little", signed=True)
					if (string_id < 0):
						continue
					BLOB["COMMANDS"][i-2]["CMD"] = "SET_EFFECT"
					BLOB["COMMANDS"][i-2]["STRING"] = BLOB["STRINGS"][string_id]
					BLOB["COMMANDS"][i-2].pop("U32")
					if string_id not in pops:
						pops.append(string_id)
				else:
					BLOB["COMMANDS"][i]["CMD"] = "PUSH_CUSTOM_TEXT"
					BLOB["COMMANDS"][i].pop("DATA")
					if BLOB["COMMANDS"][i-2]["CMD"] != 4:
						continue
					if "U32" not in BLOB["COMMANDS"][i-2].keys():
						continue
					string_id = int.from_bytes(bytes.fromhex(BLOB["COMMANDS"][i-2]["U32"][0]), "little", signed=True)
					if (string_id < 0):
						continue
					BLOB["COMMANDS"][i-2]["CMD"] = "SET_EFFECT"
					BLOB["COMMANDS"][i-2]["STRING"] = BLOB["STRINGS"][string_id]
					BLOB["COMMANDS"][i-2].pop("U32")
					if string_id not in pops:
						pops.append(string_id)
					
			case 0xE:
				if (BLOB["COMMANDS"][i]["DATA"][6:] != "80"):
					continue
				string_id = int.from_bytes(bytes.fromhex(BLOB["COMMANDS"][i]["U32"][0]), "little", signed=True)
				if (string_id < 0):
					continue
				BLOB["COMMANDS"][i]["CMD"] = "SPECIAL_TEXT"
				BLOB["COMMANDS"][i].pop("U32")
				BLOB["COMMANDS"][i]["DATA"] = BLOB["COMMANDS"][i]["DATA"][:6] + "00"
				BLOB["COMMANDS"][i]["STRING"] = BLOB["STRINGS"][string_id]
				if string_id not in pops:
					pops.append(string_id)
			case 0x10:
				BLOB["COMMANDS"][i]["CMD"] = "CMPR0"
			case 0x15:
				BLOB["COMMANDS"][i]["CMD"] = "CMPR5"
			case 0x17:
				BLOB["COMMANDS"][i]["CMD"] = "CMPR7"
			case 0x18:
				BLOB["COMMANDS"][i]["CMD"] = "CMPR8"
			case 0x1A:
				BLOB["COMMANDS"][i]["CMD"] = "CMPRA"
			case 0x1B:
				BLOB["COMMANDS"][i]["CMD"] = "INIT"
			case 0x1C:
				BLOB["COMMANDS"][i]["CMD"] = "DEINIT"
			case 0x1D:
				BLOB["COMMANDS"][i]["CMD"] = "INF1"
			case 0x2C:
				BLOB["COMMANDS"][i]["CMD"] = "INF2"
			case 0x41:
				BLOB["COMMANDS"][i]["CMD"] = "JNGE"
			case 0x42:
				BLOB["COMMANDS"][i]["CMD"] = "JNLE"
			case _:
				continue
	pops = list(set(pops))
	for i in range(len(pops)):
		BLOB["STRINGS"][pops[i]] = True #means it was pulled
	if len(BLOB["STRINGS"]) != len(pops):
		if len(BLOB["STRINGS"]) == len(pops)+1 and BLOB["STRINGS"][0] == "":
			BLOB["STRINGS"] = []
		else:			
			print("Some string were not pulled!")
			print(BLOB["STRINGS"])
			#sys.exit()
	else:
		BLOB["STRINGS"] = []
	
	other_strings = BLOB["STRINGS"] #remain strings
	BLOB.pop("STRINGS")
	BLOB = BLOB["COMMANDS"]
	return BLOB, other_strings


def readString(myfile):
	chars = []
	while True:
		c = myfile.read(1)
		if c == b'\x00':
			text = str(b"".join(chars).decode("cp932"))
			text = text.replace("\n", "\\n")
			return text
		chars.append(c)

os.makedirs(UnpackedDir, exist_ok=True)

for i in range(len(files)):
	BLOB = {}
	print(f"{Path(files[i]).stem}")
	script = open(files[i], "rb")
	#伪造头部
	content = script.read()
	script = io.BytesIO()
	script.write(b'\x00\x00\x00\x00')
	script.write(content)
	script.seek(0)
	extra = None
	extra_data_count = int.from_bytes(script.read(4), "little")
	if (extra_data_count != 0):
		extra = []
		for x in range(extra_data_count):
			entry = []
			entry.append(int.from_bytes(script.read(4), "little"))
			entry.append(int.from_bytes(script.read(4), "little"))
			extra.append(entry)
	commands_count = int.from_bytes(script.read(4), "little")
	COMMANDS = []
	u32_value = []
	label = 0
	for x in range(commands_count):
		entry = {}
		if (label == 0):
			label = script.tell()
		cmd = int.from_bytes(script.read(4), "little")
		if (cmd == 0):
			u32_value.append(script.read(4).hex())
			continue
		else:
			entry["LABEL"] = label
			label = 0
			if (len(u32_value) > 0):
				entry["U32"] = u32_value
				u32_value = []
			entry["CMD"] = cmd
		entry["DATA"] = script.read(4).hex()
		COMMANDS.append(entry)
	strings_count = int.from_bytes(script.read(4), "little")
	print(strings_count)
	BLOB["STRINGS"] = []
	for x in range(strings_count):
		string = readString(script)
		BLOB["STRINGS"].append(string)
	BLOB["COMMANDS"] = COMMANDS
	# all strings
	# new_file = open(f"All/{Path(files[i]).stem}.json", "w", encoding="UTF-8")
	# json.dump(BLOB["STRINGS"], new_file, indent="\t", ensure_ascii=False)
	# new_file.close()
	# end data
	end_file = open(f"{UnpackedDir}/{Path(files[i]).stem}.dat0", "wb")
	end_data = script.read()
	end_file.write(end_data)
	end_file.close()
	BLOB, other_strings = ProcessDump(BLOB)
	# other string
	if other_strings:
		new_file = open(f"{UnpackedDir}/{Path(files[i]).stem}.json", "w", encoding="UTF-8")
		json.dump(other_strings, new_file, indent="\t", ensure_ascii=False)
		new_file.close()

	new_file = open(f"{UnpackedDir}/{Path(files[i]).stem}.asm", "w", encoding="UTF-8")
	label_offset = 1
	if extra == None:
		pass
	else:
		label_offset += len(extra)
		new_file.write("#\tEXTRA\t[")
		for x in range(len(extra) - 1):
			new_file.write("0x%x, 0x%x, " % (extra[x][0], extra[x][1]))
		new_file.write("0x%x, 0x%x]\n" % (extra[len(extra) - 1][0], extra[len(extra) - 1][1]))
	for x in range(len(BLOB)):
		if isinstance(BLOB[x]["CMD"], int) == True:
			new_file.write("{0x%04X}" % (int(BLOB[x]["LABEL"]/8) - label_offset))
			new_file.write("\tCMD.%X\t" % BLOB[x]["CMD"])
			new_file.write("0x%s" % swap32(BLOB[x]["DATA"]))
			if "U32" in BLOB[x].keys():
				new_file.write("\t[")
				iters = len(BLOB[x]["U32"])
				for y in range(iters):
					new_file.write("0x%s" % swap32(BLOB[x]["U32"][y]))
					if (y+1 < iters):
						new_file.write(",")
				new_file.write("]")
			new_file.write("\n")
		else:
			new_file.write("{0x%04X}" % (int(BLOB[x]["LABEL"]/8) - label_offset))
			new_file.write("\t%s" % BLOB[x]["CMD"])
			match(BLOB[x]["CMD"]):
				case "PUSH_MESSAGE" | "PUSH_CUSTOM_TEXT":
					pass
				case "JNGE" | "JNLE":
					new_file.write("\t0x%04x" % int(swap32(BLOB[x]["DATA"]), base=16))
				case "LOAD_STRING" | "CASE4":
					new_file.write("\t'%s'" % BLOB[x]["STRING"])
				case "LOAD_CUSTOM_TEXT" | "SET_EFFECT" | "SPECIAL_TEXT":
					new_file.write("\t0x%s" % swap32(BLOB[x]["DATA"]))
					new_file.write("\t'%s'" % BLOB[x]["STRING"])
				case "PUSH":
					new_file.write("\t0x%x" % int(swap32(BLOB[x]["DATA"]), base=16))
					if "U32" in BLOB[x].keys():
						new_file.write("\t[")
						iters = len(BLOB[x]["U32"])
						for y in range(iters):
							new_file.write("0x%s" % swap32(BLOB[x]["U32"][y]))
							if (y+1 < iters):
								new_file.write(",")
						new_file.write("]")
				case "FUNC":
					FUNC_ID = int.from_bytes(bytes.fromhex(BLOB[x]["DATA"]), "little", signed=True)
					match(FUNC_ID):
						case 0x8035:
							new_file.write("\t'GOTO_NEXT_SCENE'")
						case 0x18036:
							new_file.write("\t'REGISTER_SCENE'")
						case 0x20005:
							new_file.write("\t'WAIT'")
						case 0x2009A:
							new_file.write("\t'BG_FADE'")
						case 0x2014f:
							new_file.write("\t'TEX_CLEAR'")
						case 0x301C2:
							new_file.write("\t'VOICE_FADE'")
						case 0x4006f:
							new_file.write("\t'PUSH_MESSAGE'")
						case 0x501b2:
							new_file.write("\t'BGM_PLAY'")
						case 0x501bf:
							new_file.write("\t'SE_PLAY'")
						case 0x60165:
							new_file.write("\t'TEX_FADE'")
						case 0x601C0:
							new_file.write("\t'SYSTEM_VOICE_PLAY'")
						case 0x8803E:
							new_file.write("\t'BG_PUSH'")
						case 0x90143:
							new_file.write("\t'TEX_PUSH'")
						case _:
							new_file.write("\t0x%X" % FUNC_ID)
				case _:
					new_file.write("\t0x%x" % int(swap32(BLOB[x]["DATA"]), base=16))
					if "U32" in BLOB[x].keys():
						new_file.write("\t[")
						iters = len(BLOB[x]["U32"])
						for y in range(iters):
							new_file.write("0x%s" % swap32(BLOB[x]["U32"][y]))
							if (y+1 < iters):
								new_file.write(",")
						new_file.write("]")
			new_file.write("\n")
	new_file.close()