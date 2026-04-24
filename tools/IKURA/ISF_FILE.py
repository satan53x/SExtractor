from Lib import *
import re
import logging

logging.basicConfig(level=logging.INFO, filename="log_dump.txt", filemode="w")

# ==========================================
# 官方 ikuar 引擎全版本智能加解密模块
# ==========================================
def ikuar_decrypt(data):
    """根据文件头自动选择解密算法"""
    data = bytearray(data)
    version = int.from_bytes(data[4:6], 'little')
    key = data[6]
    
    if version == 0x9795:
        for i in range(8, len(data)):
            b = data[i]
            data[i] = (b >> 2) | ((b << 6) & 0xFF)
    elif version == 0xD197:
        for i in range(8, len(data)):
            data[i] = (~data[i]) & 0xFF
    elif version == 0xCE89:
        for i in range(8, len(data)):
            data[i] = data[i] ^ key
    return bytes(data)

def ikuar_encrypt(data):
    """根据文件头自动选择加密算法"""
    data = bytearray(data)
    version = int.from_bytes(data[4:6], 'little')
    key = data[6]
    
    if version == 0x9795:
        for i in range(8, len(data)):
            b = data[i]
            data[i] = ((b << 2) & 0xFF) | (b >> 6)
    elif version == 0xD197:
        for i in range(8, len(data)):
            data[i] = (~data[i]) & 0xFF
    elif version == 0xCE89:
        for i in range(8, len(data)):
            data[i] = data[i] ^ key
    return bytes(data)


# ==========================================
# 官方精准文本解析器
# ==========================================
def parse_pm_content(content, trans_func=None, engine="MPX"):
    if len(content) == 0:
        return [] if trans_func is None else content
        
    offset = 1 
    extracted = []
    new_content = bytearray(content[:1])
    
    while offset < len(content):
        cmd = content[offset]
        new_content.append(cmd)
        offset += 1
        
        if cmd == 0x01: 
            new_content.extend(content[offset:offset+4])
            offset += 4
        elif cmd == 0x04:
            new_content.extend(content[offset:offset+1])
            offset += 1
        elif cmd == 0x08:
            new_content.extend(content[offset:offset+4])
            offset += 4
        elif cmd == 0x09:
            new_content.extend(content[offset:offset+1])
            offset += 1
        elif cmd == 0x0A:
            new_content.extend(content[offset:offset+4])
            offset += 4
        elif cmd in (0x0B, 0x0C, 0x10):
            new_content.extend(content[offset:offset+2])
            offset += 2
        elif cmd == 0x11:
            new_content.extend(content[offset:offset+4])
            offset += 4
        elif cmd == 0xFF:
            if engine == "DRS":
                start = offset
                while offset < len(content) and content[offset] != 0x00:
                    offset += 1
                text_bytes = content[start:offset]
                if len(text_bytes) > 0:
                    if trans_func is None:
                        extracted.append(decode_DRS_text(text_bytes))
                    else:
                        new_content.extend(trans_func(text_bytes))
                if offset < len(content):
                    if trans_func is not None:
                        new_content.append(content[offset])
                    offset += 1
            else: # 修复后的 MPX 逻辑：终极融合版（前瞻识别 + 换行过滤）
                start = offset
                text_end = offset
                
                while text_end < len(content):
                    # 1. 第一优先级：遇到句中换行符 00 06 FF，当作文本整体跳过（保留给后面的 replace 删掉）
                    if text_end + 2 < len(content) and content[text_end:text_end+3] == b'\x00\x06\xFF':
                        text_end += 3
                        continue
                        
                    # 2. 遇到独立的 00，向后“偷看”一眼
                    if content[text_end] == 0x00:
                        if text_end + 1 < len(content):
                            next_byte = content[text_end + 1]
                            # 如果下一个字节是 00, 05, 06, FF 等引擎专属控制符
                            # 证明这不是假空格，而是文本彻底说完了，后面全是底层代码！
                            if next_byte in (0x00, 0x01, 0x04, 0x05, 0x06, 0x08, 0x09, 0x0A, 0x0B, 0x0C, 0x10, 0x11, 0xFF):
                                break
                        else:
                            break # 句子刚好以单个 00 结尾
                            
                    # 3. 兼容 MPX 偶尔用作块尾的 03 结束符
                    elif content[text_end] == 0x03 and text_end + 1 == len(content):
                        break
                        
                    text_end += 1

                # ================= 完美切割 =================
                text_bytes = content[start:text_end]
                tail_bytes = content[text_end:]
                
                # 遵循原作者的初衷，清洗掉由于上面放行进来的句中换行符
                text_bytes = text_bytes.replace(b'\x00\x06\xFF', b'')
                text_bytes = text_bytes.rstrip(b'\x00') # 保险去个尾巴
                
                if len(text_bytes) > 0:
                    if trans_func is None:
                        extracted.append(decode_ikuar_text(text_bytes))
                    else:
                        new_content.extend(trans_func(text_bytes))
                        
                # 【极其重要】打包时，把后面诸如 00 00 05 04 5F 等控制代码原封不动接回去！
                if trans_func is not None:
                    new_content.extend(tail_bytes)
                    
                offset = len(content)
                
    if trans_func is None:
        return extracted
    else:
        return bytes(new_content)


class ISF_FILE():
    def __init__(self, engine="MPX", pack_profile="eng") -> None:
        self.engine = engine # 存储引擎模式
        self.pack_profile = pack_profile # "original" or "eng"
        self.head_len = 0
        self.version_info = b""
        self.offsetlist = []
        self.ops = []
        self.old_offset_to_op_idx = {}
        self.unmapped_ids = set() # <--- 新增：用于记录未匹配到的 ID

    def load_from_path(self, path):
        data = open_file_b(path)
        self.load_from_bytes(data)
    
    def load_from_bytes(self, data):
        # === [终极修复] MINYAN 魔改头极简剥离法 ===
        self.is_minyan = False
        if data.startswith(b'MINYAN'):
            self.is_minyan = True
            data = data[6:]  # 直接一刀切掉前 6 个字节的伪装签名！
            
        # === 原有的解密逻辑保持不变 ===
        # 1. 第一步：先对全文件进行智能解密！
        data = ikuar_decrypt(data)
        
        self.head_len = from_bytes(data[:4])
        self.version_info = data[4:8] 
        
        # 2. 读取跳转表 (修复原作者跳过第一个指针的Bug，严格从 0x08 开始)
        self.offsetlist = []
        offsetcounts = (self.head_len - 8) // 4
        for i in range(offsetcounts):
            offset = from_bytes(data[8 + i*4 : 12 + i*4])
            self.offsetlist.append(offset)

        # 3. 顺序解析真实字节码
        body_data = data[self.head_len:]
        reader = BytesReader(body_data)
        self.ops = []
        self.old_offset_to_op_idx = {}
        
        idx = 0
        while not reader.is_end():
            start_offset = reader.tell()
            self.old_offset_to_op_idx[start_offset] = idx
            
            op_code = reader.readU8()
            l = reader.readU8()
            raw_len_bytes = bytes([l])
            if l < 0x80:
                length = l
                head_bytes = 2
            elif l == 0x80:
                extra = reader.readU8()
                raw_len_bytes += bytes([extra])
                length = extra
                head_bytes = 3
            elif l == 0x81:
                extra = reader.readU8()
                raw_len_bytes += bytes([extra])
                length = extra + 0x100
                head_bytes = 3
            else:
                raise ValueError(f"Invalid length byte {l}")
                
            content = reader.read(length - head_bytes)
            self.ops.append({
                "op": op_code,
                "content": content,
                "_raw_len_bytes": raw_len_bytes,
                "_orig_content_len": len(content),
            })
            idx += 1
            
        self.old_offset_to_op_idx[reader.tell()] = idx



    def dumptext(self, nameidx_dict, split_embedded=False, convert_original_names=True):
        outlist = []
        savetitles = {}
        current_name_id = 0  
        NAME_RE = re.compile(r'^【(.*?)】(.*)')
        
        for idx, op in enumerate(self.ops):
            # === 1. 提取存档标题文本与 UI 文本 ===
            try:
                if self.engine == "DRS":
                    if op["op"] in [0xf7] and len(op["content"]) > 1:
                        dec = op["content"][:-1].decode("932", errors="ignore")
                        savetitles[dec] = dec
                    elif op["op"] in [0xe0] and len(op["content"]) > 2:
                        dec = op["content"][1:-1].decode("932", errors="ignore")
                        savetitles[dec] = dec
                    elif op["op"] in [0xe1] and len(op["content"]) > 3:
                        dec = op["content"][2:-1].decode("932", errors="ignore")
                        savetitles[dec] = dec
                    elif op["op"] in [0xe2, 0xe3] and len(op["content"]) > 6:
                        dec = op["content"][5:-1].decode("932", errors="ignore")
                        savetitles[dec] = dec
                    elif op["op"] in [0xe4] and len(op["content"]) >= 4:
                        i1 = op["content"][0]
                        i2 = op["content"][1]
                        c = BytesReader(op["content"][4:])
                        for _ in range(i1 + i2):
                            dec = c.read_utill_zero().decode("932", errors="ignore")
                            savetitles[dec] = dec
                    elif op["op"] == 0x5b and len(op["content"]) >= 17:
                        content = op["content"]
                        if content[0:4] == b'\x0A\x00\x00\x00' and content[12] == 0x01:
                            start = 17
                            end = start
                            while end < len(content) and content[end] != 0x00:
                                end += 1
                            text_bytes = content[start:end]
                            if len(text_bytes) > 0:
                                dec = decode_DRS_text(text_bytes)
                                savetitles[dec] = dec        
                else: # MPX 逻辑
                    if op["op"] in [0xf7]:
                        dec = decode_ikuar_text(op["content"][:-1])
                        savetitles[dec] = dec
                    elif op["op"] in [0xe0]:
                        dec = decode_ikuar_text(op["content"][1:-1])
                        savetitles[dec] = dec
                    elif op["op"] in [0xe1]:
                        dec = decode_ikuar_text(op["content"][2:-1])
                        savetitles[dec] = dec
                    elif op["op"] in [0xe2, 0xe3]:
                        dec = decode_ikuar_text(op["content"][5:-1])
                        savetitles[dec] = dec
                    elif op["op"] in [0xe4]:
                        i1 = op["content"][0]
                        i2 = op["content"][1]
                        c = BytesReader(op["content"][4:])
                        for _ in range(i1 + i2):
                            dec = decode_ikuar_text(c.read_utill_zero())
                            savetitles[dec] = dec
                            
                    # 👇 新增：MPX 引擎下的 0x5b 提取支持 👇
                    elif op["op"] == 0x5b and len(op["content"]) >= 17:
                        content = op["content"]
                        # 彻底放宽：只要索引 16 是 FF 就视为文本
                        if content[16] == 0xFF:
                            start = 17
                            end = start
                            while end < len(content) and content[end] != 0x00:
                                end += 1
                            text_bytes = content[start:end]
                            if len(text_bytes) > 0:
                                dec = decode_ikuar_text(text_bytes)
                                savetitles[dec] = dec
            except Exception:
                pass

            # === 2. 深入 0x2b/0x2c 内部提取 Name ID 和 文本 ===
            if op["op"] in (0x2b, 0x2c):
                if self.engine == "DRS":
                    current_name_id = 0 # DRS 每行重置
                content = op["content"]
                if len(content) == 0:
                    continue
                
                offset = 1
                while offset < len(content):
                    cmd = content[offset]
                    offset += 1
                    
                    if cmd == 0x01: offset += 4
                    elif cmd == 0x04: 
                        if self.engine == "DRS" and offset < len(content):
                            if offset + 2 < len(content) and content[offset+1] == 0x00 and content[offset+2] == 0x06:
                                current_name_id = content[offset]
                        offset += 1
                    elif cmd == 0x08: offset += 4
                    elif cmd == 0x09: offset += 1
                    elif cmd == 0x0A: offset += 4
                    elif cmd in (0x0B, 0x0C, 0x10): offset += 2
                    elif cmd == 0x11:
                        if offset + 4 <= len(content):
                            name_id_bytes = content[offset:offset+4]
                            current_name_id = int.from_bytes(name_id_bytes, 'little')
                            offset += 4
                    elif cmd == 0xFF:
                        if self.engine == "DRS":
                            start = offset
                            while offset < len(content) and content[offset] != 0x00:
                                offset += 1
                            text_bytes = content[start:offset]
                            if len(text_bytes) > 0:
                                # ====== 补回这里的容错安全网 ======
                                try:
                                    text_str = decode_DRS_text(text_bytes)
                                    name_str = nameidx_dict.get(str(current_name_id), "")
                                    
                                    # --- 新增：记录未知 ID ---
                                    if str(current_name_id) not in nameidx_dict:
                                        self.unmapped_ids.add(current_name_id)
                                    # --------------------------
                                    
                                    outlist.append({"name": name_str, "ori": text_str, "message": text_str})
                                except IndexError:
                                    print(f"      [警告] 指令越界 (OpCode: 0x{op['op']:02X})，跳过该行 (Hex: {text_bytes.hex()})")
                                except Exception as e:
                                    print(f"      [警告] 解码异常: {e}，跳过该行。")
                                # ===================================
                            if offset < len(content):
                                offset += 1
                        else: # 修复后的 MPX 逻辑 (这里是 dumptext 里的专属提取代码)
                            start = offset
                            text_end = offset
                            
                            while text_end < len(content):
                                # ================= 新增：字符边界跨越逻辑 =================
                                # 0. 处理特殊的转义字符，防止将附带的数据字节误判为控制码
                                if content[text_end] == 0x5C:
                                    text_end += 1
                                    if text_end < len(content) and content[text_end] != 0x00:
                                        text_end += 2
                                    else:
                                        text_end += 1
                                    continue
                                    
                                if content[text_end] == 0x7F:
                                    text_end += 2
                                    continue
                                    
                                if content[text_end] > 0x7F: # Shift-JIS 双字节
                                    text_end += 2
                                    continue
                                # ========================================================

                                # 1. 遇到句中换行符 00 06 FF，当作文本整体跳过
                                if text_end + 2 < len(content) and content[text_end:text_end+3] == b'\x00\x06\xFF':
                                    text_end += 3
                                    continue
                                    
                                # 2. 遇到独立的 00，向后“偷看”一眼
                                if content[text_end] == 0x00:
                                    if text_end + 1 < len(content):
                                        next_byte = content[text_end + 1]
                                        # 如果下一个字节是 00, 05, 06, FF 等引擎专属控制符，直接切断！
                                        if next_byte in (0x00, 0x01,0x02, 0x04, 0x05, 0x06, 0x08, 0x09, 0x0A, 0x0B, 0x0C, 0x10, 0x11, 0xFF):
                                            break
                                    else:
                                        break
                                        
                                # 3. 兼容 MPX 偶尔用作块尾的 03 结束符
                                elif content[text_end] == 0x03 and text_end + 1 == len(content):
                                    break
                                    
                                text_end += 1

                            # ================= 完美切割文本 =================
                            text_bytes = content[start:text_end]
                            
                            # === [修正] 放宽检测条件：只要检测到 】(81 7A) 紧跟 00 06 FF 即可 ===
                            # 不再强制要求后面必须是 「，彻底避开引擎对正文首字符的字典压缩或暗格干扰
                            has_name_br = b'\x81\x7A\x00\x06\xFF' in text_bytes
                            
                            # 清洗掉由于上面放行进来的句中换行符，以及末尾多余的 00 (无论它在哪)
                            text_bytes = text_bytes.replace(b'\x00\x06\xFF', b'')
                            text_bytes = text_bytes.rstrip(b'\x00')

                            # ================= 写入 JSON =================
                            if len(text_bytes) > 0:
                                text_str = decode_ikuar_text(text_bytes)
                                name_str = nameidx_dict.get(str(current_name_id), "")
                                message_str = text_str
                                
                                # --- 新增：记录未知 ID ---
                                if str(current_name_id) not in nameidx_dict:
                                    self.unmapped_ids.add(current_name_id)
                                # --------------------------
                            
                                if split_embedded:
                                    match = NAME_RE.match(text_str)
                                    if match:
                                        name_str = match.group(1)
                                        message_str = match.group(2)
                                
                                # --- [修改] 构建字典并动态追加标记 ---
                                out_dict = {"name": name_str, "ori": text_str, "message": message_str}
                                if has_name_br:
                                    out_dict["has_name_br"] = True
                                
                                outlist.append(out_dict)
                            
                            # 直接跳出这个模块，继续找下一句
                            offset = len(content)
                    else:
                        pass 

            # === 3. 提取系统 ===
            elif op["op"] == 0x15:
                name_bytes = op["content"][0x12:].rstrip(b'\x00')
                if len(name_bytes) > 0:
                    dec = name_bytes.decode("932", errors="ignore") if self.engine == "DRS" else decode_ikuar_text(name_bytes)
                    outlist.append({"name": "System", "ori": dec, "message": dec})
            elif op["op"] == 0x25: 
                name_bytes = op["content"][0x02:].rstrip(b'\x00')
                if len(name_bytes) > 0:
                    if convert_original_names:
                        dec = name_bytes.decode("932", errors="ignore") if self.engine == "DRS" else decode_ikuar_text(name_bytes)
                    else:
                        dec = name_bytes.decode("cp932", errors="replace")
                    outlist.append({"name": "System_CNS", "ori": dec, "message": dec})        

        return outlist, savetitles

    def trans(self, trans_iter, stdict):
        def encode_text(text: str) -> bytes:
            if self.pack_profile == "original":
                return text.encode("932", errors="ignore")
            return encode_ikuar_text(text)

        for op in self.ops:
            if op["op"] in (0x2b, 0x2c):
                def get_new_text(old_bytes):
                    nxt = trans_iter.__next__()
                    # 解包元组：如果 GUI 传来的是元组就拆解，纯文本就默认 False 增强容错
                    text_str, has_br = nxt if isinstance(nxt, tuple) else (nxt, False)
                    
                    new_bytes = encode_text(text_str)
                    
                    if has_br:
                        # === 恢复排版！在第一个 】(81 7A) 后面插入 00 06 FF ===
                        # 使用 replace(..., 1) 确保只替换名字框的 】
                        new_bytes = new_bytes.replace(b'\x81\x7A', b'\x81\x7A\x00\x06\xFF', 1)
                        
                    return new_bytes
                op["content"] = parse_pm_content(op["content"], trans_func=get_new_text, engine=self.engine)
                
            elif op["op"] == 0x15:
                name_bytes = op["content"][0x12:].rstrip(b'\x00')
                if len(name_bytes) > 0:
                    nxt = trans_iter.__next__()
                    text_str = nxt[0] if isinstance(nxt, tuple) else nxt
                    new_name = encode_text(text_str)
                    op["content"] = op["content"][:0x12] + new_name + b'\x00'
            elif op["op"] == 0x25 and self.engine == "DRS":
                name_bytes = op["content"][0x02:].rstrip(b'\x00')
                if len(name_bytes) > 0:
                    nxt = trans_iter.__next__()
                    text_str = nxt[0] if isinstance(nxt, tuple) else nxt
                    new_name = encode_text(text_str)
                    op["content"] = op["content"][:0x02] + new_name + b'\x00'        
                    
            elif op["op"] in [0xf7]:
                ori = op["content"][:-1].decode("932", errors="ignore") if self.engine == "DRS" else decode_ikuar_text(op["content"][:-1])
                if (ori in stdict and self.pack_profile != "original" and stdict[ori] != ori) or (self.pack_profile == "original" and ori in stdict):
                    new = encode_text(stdict[ori])
                    op["content"] = new + b'\x00'
            elif op["op"] in [0xe0]:
                ori = op["content"][1:-1].decode("932", errors="ignore") if self.engine == "DRS" else decode_ikuar_text(op["content"][1:-1])
                if (ori in stdict and self.pack_profile != "original" and stdict[ori] != ori) or (self.pack_profile == "original" and ori in stdict):
                    new = encode_text(stdict[ori])
                    op["content"] = op["content"][:1] + new + b'\x00'
            elif op["op"] in [0xe1]:
                ori = op["content"][2:-1].decode("932", errors="ignore") if self.engine == "DRS" else decode_ikuar_text(op["content"][2:-1])
                if (ori in stdict and self.pack_profile != "original" and stdict[ori] != ori) or (self.pack_profile == "original" and ori in stdict):
                    new = encode_text(stdict[ori])
                    op["content"] = op["content"][:2] + new + b'\x00'
            elif op["op"] in [0xe2, 0xe3]:
                ori = op["content"][5:-1].decode("932", errors="ignore") if self.engine == "DRS" else decode_ikuar_text(op["content"][5:-1])
                if (ori in stdict and self.pack_profile != "original" and stdict[ori] != ori) or (self.pack_profile == "original" and ori in stdict):
                    new = encode_text(stdict[ori])
                    op["content"] = op["content"][:5] + new + b'\x00'
            elif op["op"] in [0xe4]:
                i1 = op["content"][0]
                i2 = op["content"][1]
                c = BytesReader(op["content"][4:])
                for _ in range(i1 + i2):
                    ori_bytes = c.read_utill_zero()
                    res = ori_bytes.decode("932", errors="ignore") if self.engine == "DRS" else decode_ikuar_text(ori_bytes)
                    if (res in stdict and self.pack_profile != "original" and stdict[res] != res) or (self.pack_profile == "original" and res in stdict):
                        new = encode_text(stdict[res])
                        op["content"] = op["content"].replace(ori_bytes + b'\x00', new + b'\x00')
                        
            elif op["op"] == 0x5b and len(op["content"]) >= 17:
                content = op["content"]
                if content[16] == 0xFF:
                    start = 17
                    end = start
                    while end < len(content) and content[end] != 0x00:
                        end += 1
                    ori_bytes = content[start:end]
                    if len(ori_bytes) > 0:
                        # 动态解码：根据当前引擎选择合适的解码方式
                        ori = decode_DRS_text(ori_bytes) if self.engine == "DRS" else decode_ikuar_text(ori_bytes)
                        if (ori in stdict and self.pack_profile != "original" and stdict[ori] != ori) or (self.pack_profile == "original" and ori in stdict):
                            new_bytes = encode_text(stdict[ori])
                            op["content"] = content[:start] + new_bytes + b'\x00' + content[end+1:]

    def get_op_bytes(self, op) -> bytes:
        res = [to_bytes(op["op"], 1)]
        content = op["content"]
        orig_len_bytes = op.get("_raw_len_bytes")
        orig_content_len = op.get("_orig_content_len")

        # 内容长度没有变化时，尽量复用原始长度字节，确保零长度块、0x80/0x81 编码等完全回写
        if self.pack_profile == "eng" and orig_len_bytes is not None and orig_content_len == len(content):
            res.append(orig_len_bytes)
            res.append(content)
            return b''.join(res)

        l = len(content) + 2
        if l < 0x80:
            res.append(to_bytes(l, 1))
        else:
            l += 1
            if l < 0x100:
                res.append(to_bytes(0x80, 1))
                res.append(to_bytes(l, 1))
            elif l < 0x200:
                res.append(to_bytes(0x81, 1))
                res.append(to_bytes(l - 0x100, 1))
            elif l < 0x300:
                res.append(to_bytes(0x82, 1))
                res.append(to_bytes(l - 0x200, 1))
            else:
                raise ValueError(f"Invalid length {l}")
        res.append(content)
        return b''.join(res)

    def savefile(self, outpath, isEnc=True):
        op_new_offsets = {}
        body_bytes = bytearray()
        
        for idx, op in enumerate(self.ops):
            op_new_offsets[idx] = len(body_bytes)
            body_bytes.extend(self.get_op_bytes(op))
        
        op_new_offsets[len(self.ops)] = len(body_bytes)
        
        new_offsetlist = bytearray()
        for old_off in self.offsetlist:
            op_idx = self.old_offset_to_op_idx.get(old_off)
            if op_idx is None:
                new_off = old_off 
            else:
                new_off = op_new_offsets[op_idx]
            new_offsetlist.extend(to_bytes(new_off, 4))
        
        out = bytearray()
        out.extend(to_bytes(self.head_len, 4))
        out.extend(self.version_info)
        out.extend(new_offsetlist)
        
        pad_len = self.head_len - len(out)
        if pad_len > 0:
            out.extend(b'\x00' * pad_len)
            
        out.extend(body_bytes)
        
        if isEnc:
            final_bytes = ikuar_encrypt(out)
            # --- [修改] 如果是魔改版，把 MINYAN 贴回最开头 ---
            if getattr(self, 'is_minyan', False):
                final_bytes = b'MINYAN' + final_bytes
            save_file_b(outpath, final_bytes)
        else:
            if getattr(self, 'is_minyan', False):
                out = b'MINYAN' + out
            save_file_b(outpath, out)