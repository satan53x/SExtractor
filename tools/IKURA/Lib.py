import json, os, re, io
import subprocess

def open_file_b(path)->bytes:
    return open(path,'rb').read()

def from_bytes(b:bytes)->int:
    return int.from_bytes(b, byteorder='little', signed=False)

def listdir(path):
    res = os.listdir(path)
    res = [".".join(i.split(".")[:-1]) for i in res]
    return res


def save_file_b(path, data, enc = None)->None:
    if enc:
        data = bytearray(data)
        for i in range(len(data)):
            data[i] ^= enc[i % len(enc)]
        data = bytes(data)
    with open(path,'wb') as f:
        f.write(data)

def save_json(path:str,data)->None:
    with open(path,'w',encoding='utf8') as f:
        json.dump(data,f,ensure_ascii=False,indent=4)

def open_json(path:str):
    f = open(path,'r',encoding='utf8')
    return json.load(f)

def to_bytes(num:int,length:int)->bytes:
    return num.to_bytes(length,byteorder='little')

def replace_symbol_for_gbk(text):
    text = text.replace("〜","～")
    text = text.replace("♪", "")
    text = text.replace("♡", "")
    text = text.replace("......", "……").replace(".....", "……").replace("....", "……").replace("...", "…").replace("..", "…").replace(".", "。")

    text = text.replace("・", "·").replace("･･･", "…").replace("⋯", "…")
    text = text.replace("「「", "「")
    text = text.replace("」」", "」")
    text = text.replace("「「", "「")
    text = text.replace("」」", "」")
    return text

def replace_halfwidth_with_fullwidth(string):
    # 将半角符号替换为全角符号
    string = string.replace("......", "……").replace(".....", "……").replace("....", "……").replace("......", "……").replace("...", "…").replace("..", "…")
    halfwidth_chars = ",?!~0123456789qwertyuiopasdfghjklzxcvbnmQWERTYUIOPASDFGHJKLZXCVBNM _:()-―+%."
    fullwidth_chars = "，？！～０１２３４５６７８９ｑｗｅｒｔｙｕｉｏｐａｓｄｆｇｈｊｋｌｚｘｃｖｂｎｍＱＷＥＲＴＹＵＩＯＰＡＳＤＦＧＨＪＫＬＺＸＣＶＢＮＭ\u3000＿：（）ーー＋％．"
    mapping = str.maketrans(halfwidth_chars, fullwidth_chars)
    return string.translate(mapping)

def processQuote(text):
    singleFlag = False
    doubleFlag = False
    newText = ""
    for i in text:
        if i == "'":
            if singleFlag:
                newText += "」"
                singleFlag = False
            else:
                newText += "「"
                singleFlag = True
        elif i == "\"":
            if doubleFlag:
                newText += "」"
                doubleFlag = False
            else:
                newText += "「"
                doubleFlag = True
        else:
            newText += i
    if doubleFlag or singleFlag:
        print(text)
        raise RuntimeError
    return newText
        


def copyfontinfo(ori_font,info_provider,outpath):
    ori = subprocess.check_output(('otfccdump.exe', '-n', '0', '--hex-cmap', '--no-bom', ori_font)).decode('utf8',errors='ignore')
    ori = json.loads(ori)
    infoprov = subprocess.check_output(('otfccdump.exe', '-n', '0', '--hex-cmap', '--no-bom', info_provider)).decode('utf8',errors='ignore')
    infoprov = json.loads(infoprov)

    ori['name'] = infoprov['name']
    for i in ori['OS_2']:
        if type(ori['OS_2'][i]) !=type(1):
            ori['OS_2'][i] = infoprov['OS_2'][i]

    subprocess.run(['otfccbuild.exe', '-O3', '-o', outpath], input=json.dumps(ori), encoding='utf-8')
    
class OriJsonOutput():
    def __init__(self) -> None:
        self.savefilter = lambda x: True
        self.textcount = 0
        self.preProcess = lambda x: x
        self.messageset = set()
        self.outlist = []
        self.dic = {}
    
    def add_text(self, text):
        self.dic["linecount"] = self.dic.get("linecount", 0) + 1
        self.dic['ori'] = self.dic.get("ori", []) + [text]
        self.dic['message'] = self.dic.get("message", "") + text

    def add_idx(self, idx):
        if "idx" not in self.dic:
            self.dic['idx'] = [idx]
        else:
            self.dic['idx'].append(idx)
    
    def add_name_idx(self, idx):
        if "name_idx" not in self.dic:
            self.dic['name_idx'] = [idx]
        else:
            self.dic['name_idx'].append(idx)
    
    def add_name(self, name):
        self.dic['name'] = self.preProcess(name)
    
    def remove_name(self):
        try:
            del self.dic['name']
        except:
            pass
    
    def save_json(self, path, split = 0):
        if len(self.outlist) == 0:
            return
        if not split:
            save_json(path, self.outlist)
        else:
            l = len(self.outlist) // split
            for i in range(split):
                outlist = self.outlist[i*l : i*l + l] if i+1 != split else self.outlist[i*l : ]
                save_json(f'{path}_{i+1}.json', outlist)
    
    def append_dict(self, quchong = False, remove_name = True):
        if "message" not in self.dic or not self.savefilter(self.dic):
            self.dic = {}
            print("Empty message, skipping")
            return
        
        if self.dic['message'] == "":
            self.dic = {}
            print("Empty message, skipping")
            return
        if "name" in self.dic:
            if self.dic["name"] == "":
                del self.dic["name"]

        self.outlist.append(self.dic)
        self.textcount += len(self.dic['message'])
        if 'name' in self.dic:
            if not remove_name:
                self.dic = {'name':self.dic['name']}
            else:
                self.dic = {}
        else:
            self.dic = {}
    
    def get_names(self):
        namedict = {}
        for i in self.outlist:
            if 'name' in i:
                namedict[i['name']] = i['name']
        return namedict
    
    def save_double_line(self, path):
        out = open(path, 'w', encoding='utf8')
        self.outlist.sort(key=lambda x: x.get("idx", 0))
        for i in range(len(self.outlist)):
            ori = self.outlist[i]["ori"]
            new = self.outlist[i]["message"]
            try:
                idx = self.outlist[i]["idx"]
            except:
                idx = i + 1
            out.write(f"☆{idx:06d}☆{ori}\n")
            out.write(f"★{idx:06d}★{new}\n\n")
        out.close()
    
class BytesReader(io.BytesIO):
    def __init__(self, data):
        super().__init__(data)
        self.length = len(data)

    def try_read(self, length):
        i = self.tell()
        res = self.read(length)
        self.seek(i)
        return res

    def readU32(self):
        if self.tell() + 4 > self.length:
            raise EOFError
        res = self.read(4)
        res = from_bytes(res)
        return res
    
    def readU8(self):
        res = self.read(1)
        res = from_bytes(res)
        return res
    
    def readU16(self):
        res = self.read(2)
        res = from_bytes(res)
        return res
    
    def is_end(self):
        if self.tell() >= self.length:
            return True
    
    def read_utill_zero(self):
        out = b""
        while True:
            c = self.read(1)
            if c == b"\x00":
                break
            if self.is_end():
                break
            out += c
        return out
    
    def read_text_from_offset(self, offset):
        ori_p = self.tell()
        self.seek(offset)
        res = self.read_utill_zero()
        self.seek(ori_p)
        return res
    
class StatusInfo:
    def __init__(self):
        self.textCount = 0
        self.namedict = {}

    def update(self, data:OriJsonOutput):
        self.textCount += data.textcount
        self.namedict.update(data.get_names())
    
    def output(self, save_name = False):
        print(f"Text Count: {self.textCount}")
        if save_name:
            save_json("namedict.json", self.namedict)

def split_text(text, max_length):
    res = []
    for i in range(0, len(text), max_length):
        res.append(text[i:i + max_length])
    return res
    
ikuar_KANA = bytes([
    0x81, 0x40, 0x81, 0x40, 0x81, 0x41, 0x81, 0x42, 0x81, 0x45, 0x81, 0x48, 0x81, 0x49, 0x81, 0x69,
    0x81, 0x6a, 0x81, 0x75, 0x81, 0x76, 0x82, 0x4f, 0x82, 0x50, 0x82, 0x51, 0x82, 0x52, 0x82, 0x53,
    0x82, 0x54, 0x82, 0x55, 0x82, 0x56, 0x82, 0x57, 0x82, 0x58, 0x82, 0xa0, 0x82, 0xa2, 0x82, 0xa4,
    0x82, 0xa6, 0x82, 0xa8, 0x82, 0xa9, 0x82, 0xaa, 0x82, 0xab, 0x82, 0xac, 0x82, 0xad, 0x82, 0xae,
    0x81, 0x40, 0x82, 0xb0, 0x82, 0xb1, 0x82, 0xb2, 0x82, 0xb3, 0x82, 0xb4, 0x82, 0xb5, 0x82, 0xb6,
    0x82, 0xb7, 0x82, 0xb8, 0x82, 0xb9, 0x82, 0xba, 0x82, 0xbb, 0x82, 0xbc, 0x82, 0xbd, 0x82, 0xbe,
    0x82, 0xbf, 0x82, 0xc0, 0x82, 0xc1, 0x82, 0xc2, 0x82, 0xc3, 0x82, 0xc4, 0x82, 0xc5, 0x82, 0xc6,
    0x82, 0xc7, 0x82, 0xc8, 0x82, 0xc9, 0x82, 0xca, 0x82, 0xcb, 0x82, 0xcc, 0x82, 0xcd, 0x82, 0xce,
    0x82, 0xd0, 0x82, 0xd1, 0x82, 0xd3, 0x82, 0xd4, 0x82, 0xd6, 0x82, 0xd7, 0x82, 0xd9, 0x82, 0xda,
    0x82, 0xdc, 0x82, 0xdd, 0x82, 0xde, 0x82, 0xdf, 0x82, 0xe0, 0x82, 0xe1, 0x82, 0xe2, 0x82, 0xe3,
    0x82, 0xe4, 0x82, 0xe5, 0x82, 0xe6, 0x82, 0xe7, 0x82, 0xe8, 0x82, 0xe9, 0x82, 0xea, 0x82, 0xeb,
    0x82, 0xed, 0x82, 0xf0, 0x82, 0xf1, 0x83, 0x41, 0x83, 0x43, 0x83, 0x45, 0x83, 0x47, 0x83, 0x49,
    0x83, 0x4a, 0x83, 0x4c, 0x83, 0x4e, 0x83, 0x50, 0x83, 0x52, 0x83, 0x54, 0x83, 0x56, 0x83, 0x58,
    0x83, 0x5a, 0x83, 0x5c, 0x83, 0x5e, 0x83, 0x60, 0x83, 0x62, 0x83, 0x63, 0x83, 0x65, 0x83, 0x67,
    0x83, 0x69, 0x83, 0x6a, 0x82, 0xaf, 0x83, 0x6c, 0x83, 0x6d, 0x83, 0x6e, 0x83, 0x71, 0x83, 0x74,
    0x83, 0x77, 0x83, 0x7a, 0x83, 0x7d, 0x83, 0x7e, 0x83, 0x80, 0x83, 0x81, 0x83, 0x82, 0x83, 0x84
])

def _build_ikuar_reverse_map():
    rev = {}
    for b in range(0x80):
        pair = bytes(ikuar_KANA[b * 2:b * 2 + 2])
        ch = pair.decode('932', errors='ignore')
        if ch:
            # 只保留第一个命中的字节，避免出现同字符多编码歧义时覆盖
            rev.setdefault(ch, b)
    return rev

_IKUAR_REVERSE_MAP = None


def encode_ikuar_text(text: str) -> bytes:
    """将已解码的文本尽量按 ikura 引擎原始规则重新编码。"""
    global _IKUAR_REVERSE_MAP
    if _IKUAR_REVERSE_MAP is None:
        _IKUAR_REVERSE_MAP = _build_ikuar_reverse_map()

    out = bytearray()
    for ch in text:
        # 优先恢复引擎自己的单字节字典压缩
        mapped = _IKUAR_REVERSE_MAP.get(ch)
        if mapped is not None:
            out.append(mapped)
            continue

        enc = ch.encode('932', errors='ignore')
        if len(enc) == 1 and (enc[0] < 0x80 or 0xA1 <= enc[0] <= 0xDF or enc[0] == 0x7F):
            # 单字节字符按引擎惯用的 0x7F 逃逸方式保存，避免把原本的转义字节丢掉
            out.extend((0x7F, enc[0]))
        else:
            out.extend(enc)

    return bytes(out)


def decode_ikuar_text(byte_data):
    """完全匹配官方 C# 引擎逻辑的终极解码函数"""
    decoded_bytes = bytearray()
    i = 0
    while i < len(byte_data):
        b = byte_data[i]
        
        # === 1. 0x7F 转义符：单字节半角/ASCII原样输出 ===
        if b == 0x7F:
            if i + 1 < len(byte_data):
                decoded_bytes.append(byte_data[i+1])
            i += 2
            continue
            
        # === 2. 0x5C 转义符：引擎特殊控制符映射 ===
        if b == 0x5C:
            decoded_bytes.append(ikuar_KANA[0xB8])
            i += 1
            if i < len(byte_data) and byte_data[i] != 0x00:
                i += 1
            if i - 1 < len(byte_data):
                decoded_bytes.append(ikuar_KANA[byte_data[i - 1] * 2 + 1])
            i += 1
            continue

        # === 3. 大于 0x7F：标准的双字节 Shift-JIS ===
        if b > 0x7F:
            decoded_bytes.append(b)
            if i + 1 < len(byte_data):
                decoded_bytes.append(byte_data[i+1])
            i += 2
            
        # === 4. 小于 0x7F：官方特有的单字节字典压缩映射 ===
        else:
            decoded_bytes.append(ikuar_KANA[b * 2])
            decoded_bytes.append(ikuar_KANA[b * 2 + 1])
            i += 1
            
    return decoded_bytes.decode('932', errors='ignore')

def decode_DRS_text(byte_data):
    """バグを修正した真の完全版デコード関数"""
    decoded_bytes = bytearray()
    i = 0
    while i < len(byte_data):
        b = byte_data[i]
        
        # === 1. 0x7F 转义符：单字节半角/ASCII原样输出 ===
        if b == 0x7F:
            if i + 1 < len(byte_data):
                decoded_bytes.append(byte_data[i+1])
            i += 2
            continue

        # === 2. 大于 0x7F：标准的双字节 Shift-JIS ===
        if b > 0x7F:
            decoded_bytes.append(b)
            if i + 1 < len(byte_data):
                decoded_bytes.append(byte_data[i+1])
            i += 2
            
        # === 3. 小于 0x7F：包含 0x5C(イ) にも対応した完全な辞書マッピング ===
        else:
            decoded_bytes.append(ikuar_KANA[b * 2])
            decoded_bytes.append(ikuar_KANA[b * 2 + 1])
            i += 1
            
    return decoded_bytes.decode('932', errors='ignore')