import sys
import os
import struct
import json

class Entry:
    def __init__(self):
        self.Name = ""
        self.Offset = 0
        self.Size = 0
        self.Type = ""
        self.Prefix = ""
        self.Counter = 0

class ArcFile:
    def __init__(self, file_path, dir_entries):
        self.FilePath = file_path
        self.DirEntries = dir_entries

def try_open_arc(file_name):
    if not file_name.endswith(".dat") or not os.path.basename(file_name).lower().startswith("arc"):
        return None
    
    with open(file_name, "rb") as f:
        file_data = f.read()
        current_offset = 0
        dir_entries = []

        while current_offset < len(file_data):
            size = struct.unpack_from("<I", file_data, current_offset)[0]
            if size == 0:
                break

            counter = struct.unpack_from("<I", file_data, current_offset + 4)[0]
            
            name_length = struct.unpack_from("<H", file_data, current_offset + 8)[0]
            if name_length == 0 or name_length > 0x100:
                return None
            
            name = file_data[current_offset + 10 : current_offset + 10 + name_length].decode("utf-8", errors="ignore")
            if len(name) == 0:
                return None
            
            current_offset += 10 + name_length
            if current_offset + size > len(file_data):
                return None
            
            entry = Entry()
            entry.Name = name
            entry.Offset = current_offset
            entry.Size = size
            entry.Counter = counter
            
            signature = struct.unpack_from("<I", file_data, current_offset)[0]
            if file_data[current_offset + 4 : current_offset + 7] == b'\x47\x57\x44':
                entry.Type = "image"
                entry.Name = os.path.splitext(entry.Name)[0] + ".gwd"
            elif file_data[current_offset + 8 : current_offset + 12] == b'\x57\x41\x56\x45':
                entry.Type = "audio"
                entry.Name = os.path.splitext(entry.Name)[0] + ".wav"
            elif file_data[current_offset + 1 : current_offset + 5] == b'\x73\x01\x01\x52':
                entry.Type = "image"
                entry.Name = os.path.splitext(entry.Name)[0] + ""
            else:
                entry.Type = "unknown"
            
            dir_entries.append(entry)
            current_offset += size
        
        if len(dir_entries) == 0:
            return None
        
        return ArcFile(file_name, dir_entries)

def extract_arc(arc_file, output_dir):
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    
    extracted_files = []

    for entry in arc_file.DirEntries:
        file_path = os.path.join(output_dir, entry.Name)
        
        with open(arc_file.FilePath, "rb") as f:
            f.seek(entry.Offset)
            data = f.read(entry.Size)
        
        with open(file_path, "wb") as f:
            f.write(data)
        
        print(f"Extracted: {entry.Name}")
        
        # Append the file details to the list
        extracted_files.append({
            "name": entry.Name,
            "counter": entry.Counter
            # Convert bytes to hexadecimal string
        })
    
    # Save the extracted file details to a JSON file
    json_output_path = os.path.join(output_dir, "arc.json")
    with open(json_output_path, "w") as json_file:
        json.dump(extracted_files, json_file, indent=4)
    
    print(f"Extraction details saved to: {json_output_path}")

def main():
    if len(sys.argv) != 3:
        print("Usage: python script.py <file_or_directory> <output_directory>")
        return
    
    target_path = sys.argv[1]
    output_dir = sys.argv[2]
    
    if os.path.isfile(target_path):
        result = try_open_arc(target_path)
        if result:
            print(f"Archive found: {result.FilePath}")
            extract_arc(result, output_dir)
            print(f"Files extracted to: {output_dir}")
        else:
            print("Not a valid ARC/ADVSYS3 archive.")
    elif os.path.isdir(target_path):
        for root, _, files in os.walk(target_path):
            for file_name in files:
                file_path = os.path.join(root, file_name)
                result = try_open_arc(file_path)
                if result:
                    print(f"Archive found: {result.FilePath}")
                    extract_arc(result, output_dir)
                    print(f"Files extracted to: {output_dir}")
    else:
        print(f"{target_path} is not a valid file or directory.")

if __name__ == "__main__":
    main()
