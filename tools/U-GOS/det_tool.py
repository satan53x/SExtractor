import os
import struct
import sys

def decompress_rle(data: bytes) -> bytearray:
    out = bytearray()
    ring_buffer = bytearray(256)
    frame_pos = 0
    i = 0
    length = len(data)
    
    while i < length:
        ctl = data[i]
        i += 1
        
        if ctl != 0xFF:
            out.append(ctl)
            ring_buffer[frame_pos & 0xFF] = ctl
            frame_pos += 1
        else:
            if i >= length: 
                break
            ctl2 = data[i]
            i += 1
            
            if ctl2 == 0xFF:
                out.append(0xFF)
                ring_buffer[frame_pos & 0xFF] = 0xFF
                frame_pos += 1
            else:
                offset = frame_pos - ((ctl2 >> 2) + 1)
                count = (ctl2 & 3) + 3
                
                for _ in range(count):
                    v = ring_buffer[offset & 0xFF]
                    offset += 1
                    out.append(v)
                    ring_buffer[frame_pos & 0xFF] = v
                    frame_pos += 1
                    
    return out

def compress_rle(data: bytes) -> bytearray:
    out = bytearray()
    i = 0
    length = len(data)
    
    while i < length:
        max_len = min(6, length - i)
        best_len = 0
        best_dist = 0
        
        if max_len >= 3:
            search_start = max(0, i - 64)
            window = data[search_start:i]
            
            for l in range(max_len, 2, -1):
                target = data[i : i+l]
                idx = window.rfind(target)
                if idx != -1:
                    best_len = l
                    best_dist = len(window) - idx
                    break
                    
        if best_dist == 64 and best_len == 6:
            best_len = 5
            
        if best_len >= 3:
            out.append(0xFF)
            ctl2 = ((best_dist - 1) << 2) | (best_len - 3)
            out.append(ctl2)
            i += best_len
        else:
            val = data[i]
            out.append(val)
            if val == 0xFF:
                out.append(0xFF)
            i += 1
            
    return out

def unpack_det(base_name: str, out_dir: str):
    det_path = f"{base_name}.det"
    nme_path = f"{base_name}.nme"
    atm_path = f"{base_name}.atm"
    ext = ".atm"
    
    if not os.path.exists(atm_path):
        atm_path = f"{base_name}.at2"
        ext = ".at2"
        if not os.path.exists(atm_path):
            print(f"Error: Index file (.atm or .at2) not found for {base_name}")
            return

    with open(nme_path, 'rb') as f: nme_data = f.read()
    with open(atm_path, 'rb') as f: atm_data = f.read()
    with open(det_path, 'rb') as f: det_data = f.read()

    true_atm_len = len(atm_data) - 4
    true_nme_len = len(nme_data) - 4

    if true_atm_len % 20 == 0 and true_atm_len % 16 != 0:
        entry_size = 20
    elif true_atm_len % 16 == 0 and true_atm_len % 20 != 0:
        entry_size = 16
    else:
        if true_atm_len >= 32:
            test_offset = struct.unpack('<I', atm_data[16:20])[0]
            entry_size = 20 if test_offset >= true_nme_len else 16
        else:
            entry_size = 16

    file_count = true_atm_len // entry_size
    print(f"Detected {entry_size}-byte index format ({ext}). Found {file_count} actual files.")
    os.makedirs(out_dir, exist_ok=True)
    
    extracted_files = []
    
    for i in range(file_count):
        idx = i * entry_size
        name_offset, data_offset, comp_size = struct.unpack('<III', atm_data[idx:idx+12])

        if name_offset >= true_nme_len:
            continue

        name_end = nme_data.find(b'\x00', name_offset)
        if name_end == -1 or name_end > true_nme_len: 
            name_end = true_nme_len
            
        raw_name = nme_data[name_offset:name_end]
        
        if not raw_name:
            continue
            
        try:
            file_name = raw_name.decode('cp932').replace('\\', '/')
        except UnicodeDecodeError:
            file_name = f"unknown_subfolder/file_{i}.bin"
            
        file_name = file_name.strip().lstrip('/')
        
        if not file_name or file_name in ['.', '..'] or file_name.endswith('/'):
            continue
            
        extracted_files.append(file_name.replace('/', '\\'))
            
        if comp_size == 0 and '.' not in os.path.basename(file_name):
            continue
            
        out_path = os.path.join(out_dir, file_name)
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        
        compressed_chunk = det_data[data_offset : data_offset + comp_size]
        
        try:
            decompressed_chunk = decompress_rle(compressed_chunk)
            with open(out_path, 'wb') as f:
                f.write(decompressed_chunk)
            print(f" [OK] {file_name}")
        except Exception as e:
            print(f" [Error] Failed to extract {file_name}: {e}")
            
    order_path = os.path.join(out_dir, "order.txt")
    with open(order_path, "w", encoding="utf-8") as f:
        # Write the metadata to the top of the file
        f.write(f"EXT={ext}\n")
        f.write(f"MODE={entry_size}\n")
        # Write the filenames
        for fname in extracted_files:
            f.write(fname + "\n")
    print(f"[!] Metadata and file order saved to {order_path}")

def pack_det(in_dir: str, base_name: str):
    entry_size = 20
    ext = ".atm"
    original_order = []
    
    order_path = os.path.join(in_dir, "order.txt")
    if not os.path.exists(order_path):
        order_path = os.path.join(in_dir, "oder.txt") 
        
    if os.path.exists(order_path):
        with open(order_path, "r", encoding="utf-8") as f:
            lines = [line.strip() for line in f if line.strip()]
            
        for line in lines:
            if line.startswith("EXT="):
                ext = line.split("=")[1]
            elif line.startswith("MODE="):
                entry_size = int(line.split("=")[1])
            else:
                original_order.append(line)
    else:
        print("[!] order.txt not found! Falling back to 20-byte .atm defaults.")

    print(f"Packing '{in_dir}/' into {base_name}.det/.nme/{ext} ({entry_size}-byte mode)...")
    
    nme_data = bytearray()
    atm_data = bytearray()
    det_data = bytearray()
    
    all_files = []
    for root, _, files in os.walk(in_dir):
        for file in files:
            if file in ["order.txt"]:
                continue
            file_path = os.path.join(root, file)
            rel_path = os.path.relpath(file_path, in_dir)
            all_files.append(rel_path.replace('/', '\\'))
            
    if original_order:
        order_dict = {fname: i for i, fname in enumerate(original_order)}
        all_files.sort(key=lambda x: order_dict.get(x, 999999))
        print("[!] Applied original binary search sort order.")
    else:
        all_files.sort()
    
    for archive_name in all_files:
        file_path = os.path.join(in_dir, archive_name.replace('\\', '/'))
        
        with open(file_path, 'rb') as f:
            raw_data = f.read()
            
        comp_data = compress_rle(raw_data)
        
        name_offset = len(nme_data)
        nme_data.extend(archive_name.encode('cp932') + b'\x00')
        
        data_offset = len(det_data)
        comp_size = len(comp_data)
        unpacked_size = len(raw_data)
        det_data.extend(comp_data)
        
        if entry_size == 20:
            atm_data.extend(struct.pack('<IIIII', name_offset, data_offset, comp_size, 0, unpacked_size))
        else:
            atm_data.extend(struct.pack('<IIII', name_offset, data_offset, comp_size, unpacked_size))
        
        print(f" [Packed] {archive_name} ({comp_size} bytes)")
            
    dummy_eof = b'\x00\x00\x00\x00' # Dummy, don't bother
    
    with open(f"{base_name}.nme", 'wb') as f: f.write(nme_data + dummy_eof)
    with open(f"{base_name}{ext}", 'wb') as f: f.write(atm_data + dummy_eof)
    with open(f"{base_name}.det", 'wb') as f: f.write(det_data + dummy_eof)
    print("Packing complete!")

if __name__ == "__main__":
    if len(sys.argv) < 4:
        print("Usage:")
        print("  Unpack: python DetTool.py -u <archive_base_name> <output_folder>")
        print("  Pack:   python DetTool.py -p <input_folder> <archive_base_name>")
        sys.exit(1)
        
    mode = sys.argv[1].lower()
    target1 = sys.argv[2]
    target2 = sys.argv[3]
    
    if mode in ('unpack', '-u'):
        unpack_det(target1, target2)
    elif mode in ('pack', '-p'):
        pack_det(target1, target2)
    else:
        print("Invalid mode.")