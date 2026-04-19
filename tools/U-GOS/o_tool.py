import struct
import sys
import json
import os
import re

line_start_skip = re.compile(r"^(●|//|'|!|◎|○|sys_|[a-z]+\\)")

class uGOSPatcher:
    def __init__(self, filepath):
        with open(filepath, 'rb') as f:
            self.bytecode = bytearray(f.read())
        self.length = len(self.bytecode)

    def is_translatable(self, text):
        if not text:
            return False
            
        #ignore_prefixes = ('●', '//', "'", '!', '◎', '○', 'sys_')
        if line_start_skip.match(text):
            return False
            
        path_indicators = ['.dat', '.bmp', '.png', '.ogg', '.wav', '.txt'] # need '/' ?
        if any(indicator in text for indicator in path_indicators):
            return False
            
        if not any(ord(c) > 0x7E for c in text):
            return False
            
        return True

    def read_string_block(self, target_offset):
        if target_offset >= self.length - 2:
            return 0, b"", "", b""
            
        block_len = struct.unpack_from('<H', self.bytecode, target_offset)[0]
        if block_len == 0 or target_offset + 2 + block_len > self.length:
            return 0, b"", "", b""
            
        raw_data = self.bytecode[target_offset+2 : target_offset+2+block_len]
        clean_bytes = bytearray(b for b in raw_data if b not in (7, 8, 9, 10, 0))
        
        try:
            text = clean_bytes.decode('cp932')
            return block_len, raw_data, text, clean_bytes
        except UnicodeDecodeError:
            return block_len, raw_data, "", b""

    def sweep_bytecode(self, mode="export", json_data=None):
        offset = 0
        extracted_data = []
        json_idx = 0
        
        while offset < self.length:
            opcode = self.bytecode[offset]
            offset += 1
            
            pointer_offset = None
            target_offset = None
            ptr_type = None
            
            if opcode in [0, 1, 3, 7, 8, 192, 193, 194, 195, 208, 209, 210, 211, 212]:
                pass 
            elif opcode == 2:
                pointer_offset = offset
                target_offset = struct.unpack_from('<I', self.bytecode, offset)[0]
                ptr_type = 'DWORD'
                offset += 4
            elif opcode in [5, 6]:
                offset += 4
            elif opcode in [16, 19, 23]:
                offset += 2
            elif opcode == 18:
                pointer_offset = offset
                target_offset = struct.unpack_from('<H', self.bytecode, offset)[0]
                ptr_type = 'WORD'
                offset += 2
            elif opcode in [21, 22]:
                offset += 2
            elif opcode in [32, 35, 39]:
                offset += 1
            elif opcode == 34:
                pointer_offset = offset
                target_offset = self.bytecode[offset]
                ptr_type = 'BYTE'
                offset += 1
            elif opcode in [37, 38]:
                offset += 1

            if target_offset is not None:
                block_len, raw_data, text, orig_bytes = self.read_string_block(target_offset)
                
                if self.is_translatable(text):
                    if mode == "export":
                        entry = {}
                        if '「' in text:
                            name_part, msg_part = text.split('「', 1)
                            entry["name"] = name_part.replace('　', '').strip()
                            entry["message"] = '「' + msg_part
                        else:
                            entry["message"] = text
                        extracted_data.append(entry)
                        
                    elif mode == "import" and json_data and json_idx < len(json_data):
                        trans_entry = json_data[json_idx]
                        json_idx += 1
                        # Reconstruct text without forcing brackets (they are already in trans_entry['message'])
                        if "name" in trans_entry and trans_entry["name"]:
                            new_text = f"{trans_entry['name']}　{trans_entry['message']}"
                        else:
                            new_text = trans_entry['message']
                        try:
                            new_bytes = new_text.encode('cp932')
                        except UnicodeEncodeError as e:
                            print(f"[!] Encoding error on '{new_text}'. Ensure characters are Shift-JIS compatible.")
                            continue
                        idx = raw_data.find(orig_bytes)
                        if idx != -1:
                            prefix = raw_data[:idx]
                            suffix = raw_data[idx+len(orig_bytes):]
                            new_raw_data = prefix + new_bytes + suffix
                            
                            new_block = struct.pack('<H', len(new_raw_data)) + new_raw_data
                            
                            if len(new_block) <= block_len + 2:
                                # Overwrite in-place
                                self.bytecode[target_offset : target_offset+len(new_block)] = new_block
                            else:
                                # Append to EOF
                                new_target_offset = len(self.bytecode)
                                self.bytecode.extend(new_block)
                                
                                # Update pointer
                                if ptr_type == 'DWORD':
                                    struct.pack_into('<I', self.bytecode, pointer_offset, new_target_offset)
                                elif ptr_type == 'WORD':
                                    if new_target_offset > 0xFFFF:
                                        print(f"[!] Error: File too large to patch WORD pointer at {hex(pointer_offset)}")
                                    else:
                                        struct.pack_into('<H', self.bytecode, pointer_offset, new_target_offset)
                                elif ptr_type == 'BYTE':
                                    if new_target_offset > 0xFF:
                                        print(f"[!] Error: File too large to patch BYTE pointer at {hex(pointer_offset)}")
                                    else:
                                        self.bytecode[pointer_offset] = new_target_offset

        return extracted_data

    def export_json(self, output_path):
        data = self.sweep_bytecode(mode="export")
        if data:
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return len(data)
        return 0

    def import_json(self, json_path, output_o_path):
        with open(json_path, 'r', encoding='utf-8') as f:
            json_data = json.load(f)
        self.sweep_bytecode(mode="import", json_data=json_data)
        with open(output_o_path, 'wb') as f:
            f.write(self.bytecode)

# ==========================================
# Batch（adapt .json）
# ==========================================

def batch_export(input_dir, output_dir):
    os.makedirs(output_dir, exist_ok=True)
    files = [f for f in os.listdir(input_dir) if f.endswith(".o")]
    print(f"[*] Found {len(files)} .o files. Starting export...")
    
    for filename in files:
        input_path = os.path.join(input_dir, filename)
        json_filename = filename[0:-2] + ".json"  # 1_pro01.json
        output_path = os.path.join(output_dir, json_filename)
        
        patcher = uGOSPatcher(input_path)
        count = patcher.export_json(output_path)
        print(f"[+] {filename} -> {json_filename} ({count} lines)")

def batch_import(input_o_dir, json_dir, output_dir):
    os.makedirs(output_dir, exist_ok=True)
    files = [f for f in os.listdir(input_o_dir) if f.endswith(".o")]
    print(f"[*] Found {len(files)} .o files. Starting import...")
    
    for filename in files:
        input_o_path = os.path.join(input_o_dir, filename)
        json_filename = filename[0:-2] + ".json" # 1_pro01.json
        json_path = os.path.join(json_dir, json_filename)
        output_o_path = os.path.join(output_dir, filename)
        
        if os.path.exists(json_path):
            patcher = uGOSPatcher(input_o_path)
            patcher.import_json(json_path, output_o_path)
            print(f"[+] Patched: {filename}")
        else:
            print(f"[!] Skip: {filename} (Missing {json_filename})")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage:")
        print("  Batch Export: python o_tool.py export-dir <in_folder> <out_json_folder>")
        print("  Batch Import: python o_tool.py import-dir <in_folder> <trans_json_folder> <out_folder>")
        sys.exit(1)
        
    mode = sys.argv[1].lower()
    
    if mode in ('export', '-e'):
        uGOSPatcher(sys.argv[2]).export_json(sys.argv[3])
    elif mode in ('import', '-i'):
        uGOSPatcher(sys.argv[2]).import_json(sys.argv[3], sys.argv[4])
    elif mode in ('export-dir', '-ed'):
        batch_export(sys.argv[2], sys.argv[3])
    elif mode in ('import-dir', '-id'):
        batch_import(sys.argv[2], sys.argv[3], sys.argv[4])
    else:
        print("Unknown mode.")