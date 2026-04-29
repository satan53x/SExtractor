"""silky_op.py — Silky engine MES script <-> opcode txt 双向转换。

负责字节级双向转换：
  disassemble:  *.MES (二进制脚本)  ->  *.op.txt (人类可读 opcode 流)
  assemble:     *.op.txt           ->  *.MES

OP 表、STR_CRYPT 压缩/解压、跳转偏移修复、消息编号重建都在这里。

CLI:
  python silky_op.py disasm <in.MES> <out.op.txt> [--encoding cp932]
  python silky_op.py asm    <in.op.txt> <out.MES> [--encoding cp932]
"""

import struct
import os
import json


class SilkyMesScript:
    default_encoding = "cp932"
    technical_instances = (">", "<")

    # [Opcode, struct, name].
    command_library = (
        (0x00, '', 'RETURN'),
        (0x01, 'I', ''),  # Found only in LIBLARY.LIB
        (0x02, '', ''),
        (0x03, '', ''),  # Found only in LIBLARY.LIB
        (0x04, '', ''),
        (0x05, '', ''),
        (0x06, '', ''),  # Found only in LIBLARY.LIB

        (0x0A, 'S', 'STR_CRYPT'),
        (0x0B, 'S', 'STR_UNCRYPT'),
        (0x0C, '', ''),
        (0x0D, '', ''),
        (0x0E, '', ''),
        (0x0F, '', ''),

        (0x10, 'B', ''),
        (0x11, '', ''),
        (0x14, '>I', 'JUMP'),
        (0x15, '>I', 'MSG_OFSETTER'),
        (0x16, '>I', 'SPEC_OFSETTER'),  # Found only in LIBLARY.LIB
        (0x17, '', ''),
        (0x18, '', ''),
        (0x19, '>I', 'MESSAGE'),
        (0x1A, '>I', ''),
        (0x1B, '>I', ''),
        (0x1C, 'B', 'TO_NEW_STRING'),

        (0x32, 'i', 'PUSH'),
        (0x33, 'S', 'PUSH_STR'),
        (0x34, '', ''),
        (0x35, '', ''),
        (0x36, 'B', 'JUMP_2'),
        (0x37, '', ''),
        (0x38, '', ''),
        (0x3A, '', ''),
        (0x3B, '', ''),
        (0x3C, '', ''),
        (0x3D, '', ''),
        (0x3E, '', ''),
        (0x3F, '', ''),

        (0x40, '', ''),
        (0x41, '', ''),
        (0x42, '', ''),
        (0x43, '', ''),

        (0xFA, '', ''),
        (0xFB, '', ''),
        (0xFC, '', ''),
        (0xFD, '', ''),
        (0xFE, '', ''),
        (0xFF, '', ''),
    )
    offsets_library = (
        (0x14, 0),
        (0x15, 0),
        (0x16, 0),
        (0x1b, 0),
    )

    # Pre-built lookup tables (class-level, built once)
    _cmd_by_opcode = {entry[0]: (i, entry) for i, entry in enumerate(command_library)}
    _cmd_by_name = {}
    for _i, _entry in enumerate(command_library):
        if _entry[2]:
            _cmd_by_name[_entry[2]] = (_i, _entry)
    _offset_by_opcode = {entry[0]: entry for entry in offsets_library}

    def __init__(self, mes_name: str, txt_name: str, encoding: str = "", debug: bool = False, verbose: bool = False,
                 hackerman_mode: bool = False):
        self._verbose = verbose
        if encoding == "":
            self.encoding = self.default_encoding
        else:
            self.encoding = encoding
        self._hackerman_mode = hackerman_mode
        self._debug = debug
        self._mes_name = mes_name
        self._txt_name = txt_name
        self._prm = [0, 0]
        self._offsets = []
        self._first_offsets = []
        self._second_offsets = []

        self.get_I.instances = ("I", "i")
        self.get_H.instances = ("H", "h")
        self.get_B.instances = ("B", "b")
        self.get_S.instances = ("S",)
        self.set_I.instances = self.get_I.instances
        self.set_H.instances = self.get_H.instances
        self.set_B.instances = self.get_B.instances
        self.set_S.instances = self.get_S.instances

    # User methods.

    def disassemble(self) -> None:
        """Disassemble Silky Engine mes script."""
        self._offsets = []
        self._prm, self._first_offsets, self._second_offsets = self._diss_header()
        self._diss_other_offsets()
        if self._verbose:
            print("Parameters:", self._prm)
            print("First offsets:", len(self._first_offsets), self._first_offsets)
            print("Second offsets:", len(self._second_offsets), self._second_offsets)
            print("True offsets:", len(self._offsets), self._offsets)
        self._disassemble_commands()

    def assemble(self) -> None:
        """Assemble Silky Engine mes script."""
        self._prm, self._first_offsets, self._second_offsets, self._offsets = self._assemble_offsets_and_parameters()
        if self._verbose:
            print("Parameters:", self._prm)
            print("First offsets:", self._first_offsets)
            print("True offsets:", self._offsets)
        self._assemble_script_file()

    # Technical methods for assembling.

    def _resolve_command(self, command_string: str):
        """Resolve a command string (name or hex) to (index, entry). Uses lookup dicts."""
        lookup = self._cmd_by_name.get(command_string)
        if lookup:
            return lookup
        # Try by hex
        try:
            opcode = int(command_string, 16)
        except ValueError:
            raise SilkyMesArchiveError("Error! There is no such command.\n{}".format(command_string))
        lookup = self._cmd_by_opcode.get(opcode)
        if lookup:
            return lookup
        raise SilkyMesArchiveError("Error! There is no such command.\n{}".format(command_string))

    def _assemble_script_file(self) -> None:
        with open(self._txt_name, 'r', encoding='utf-8-sig') as in_file:
            all_lines = in_file.readlines()

        try:
            os.rename(self._mes_name, self._mes_name + '.bak')
        except OSError:
            pass

        buf = bytearray()
        message_count = 0
        search_offset = [i[0] for i in self._offsets]

        for parameter in self._prm:
            buf += struct.pack('I', parameter)
        for first_offset in self._first_offsets:
            buf += struct.pack('I', first_offset)
        for second_offset in self._second_offsets:
            buf += struct.pack('I', second_offset)

        i = 0
        total = len(all_lines)
        while i < total:
            line = all_lines[i]
            i += 1
            if line == '' or len(line) <= 1 or line == '\n' or line[0] == '$':
                continue
            if line[1] == '0':
                buf += bytes.fromhex(line[3:].rstrip('\n'))
            elif line[1] == '1':
                command_string = line[3:].rstrip('\n')
                command_index, entry = self._resolve_command(command_string)
                buf += struct.pack('B', entry[0])

                if i >= total:
                    break
                arg_line = all_lines[i]
                i += 1
                argument_list = json.loads(arg_line)

                this_command = entry[0]
                if this_command == 0x19:
                    argument_list[0] = message_count
                    message_count += 1
                else:
                    offset_entry = self._offset_by_opcode.get(this_command)
                    if offset_entry:
                        offset_set = offset_entry[1]
                        indexer = search_offset.index(argument_list[offset_set])
                        argument_list[offset_set] = self._offsets[indexer][1]

                buf += self.set_args(argument_list, entry[1], self.encoding, entry[0])

        with open(self._mes_name, 'wb') as out_file:
            out_file.write(buf)

    def _assemble_offsets_and_parameters(self) -> tuple:
        """Assemble offsets and parameters of Silky Engine's mes archive."""
        with open(self._txt_name, 'r', encoding='utf-8-sig') as in_file:
            all_lines = in_file.readlines()

        first_offsets = []
        second_offsets = []
        offsets = []
        prm = [0, 0]

        pointer = 0
        message_count = 0

        i = 0
        total = len(all_lines)
        while i < total:
            line = all_lines[i]
            i += 1
            if line == '' or len(line) <= 1 or line == '\n' or line[0] == '$':
                continue

            if line[1] == '0':  # "Free bytes".
                pointer += len(line[3:].rstrip('\n').split(' '))
            elif line[1] == '1':  # Command.
                command_string = line[3:].rstrip('\n')
                command_index, entry = self._resolve_command(command_string)

                if entry[0] == 0x19:
                    message_count += 1
                    first_offsets.append(pointer)

                pointer += 1

                if i >= total:
                    break
                arg_line = all_lines[i]
                i += 1
                argument_list = json.loads(arg_line)
                if entry[0] == 0x19:
                    argument_list[0] = 0
                argument_bytes = self.set_args(argument_list, entry[1], self.encoding, entry[0])
                pointer += len(argument_bytes)

            elif line[1] == '2':  # If label (of true offset).
                offset_number = int(line[3:].rstrip('\n'))
                offsets.append([offset_number, pointer])

            elif line[1] == '3':  # If special header's label.
                second_offsets.append(pointer)

        prm[0] = message_count
        prm[1] = len(second_offsets)

        return prm, first_offsets, second_offsets, offsets

    # Technical methods for disassembling.

    def _disassemble_commands(self) -> None:
        """Disassemble Silky Engine mes script commands."""
        pointer = self.get_true_offset(0)
        out_parts = []  # Collect output as list, join at end

        with open(self._mes_name, 'rb') as in_file:
            data = in_file.read()

        sorted_offset = sorted(list(enumerate(self._offsets)), key=lambda x: x[1])
        search_offset = [i[1] for i in sorted_offset]
        initial_sorted_offset = sorted_offset.copy()
        initial_search_offset = search_offset.copy()

        second_offsets_set = set(self.get_true_offset(i) for i in self._second_offsets)

        stringer = ''
        data_len = len(data)
        pos = pointer  # current position in data

        # Pre-build a dict for fast offset lookup
        # offset_at_pos: {position -> list of (original_index, offset_value)}
        offset_at_pos = {}
        for orig_idx, offset_val in sorted_offset:
            offset_at_pos.setdefault(offset_val, []).append(orig_idx)

        while pos < data_len:
            # Offsets functionality
            if pos in offset_at_pos:
                if stringer:
                    out_parts.append('#0-{}\n'.format(stringer.lstrip(' ')))
                    stringer = ''
                for orig_idx in offset_at_pos[pos]:
                    if self._debug:
                        out_parts.append("#2-{} {}\n".format(orig_idx, pos))
                    else:
                        out_parts.append("#2-{}\n".format(orig_idx))

            if pos in second_offsets_set:
                if stringer:
                    out_parts.append('#0-{}\n'.format(stringer.lstrip(' ')))
                    stringer = ''
                if self._debug:
                    out_parts.append("#3 {}\n".format(pos))
                else:
                    out_parts.append("#3\n")

            # Commands functionality
            current_byte = data[pos]
            pos += 1

            lookup = self._cmd_by_opcode.get(current_byte)
            if lookup is not None:
                lib_index, entry = lookup
                if stringer:
                    out_parts.append('#0-{}\n'.format(stringer.lstrip(' ')))
                    stringer = ''

                # Write command name
                cmd_name = entry[2]
                if cmd_name == '':
                    analyzer = '{:02x}'.format(current_byte)
                    out_parts.append("#1-")
                    out_parts.append(analyzer)
                else:
                    out_parts.append("#1-")
                    out_parts.append(cmd_name)

                if self._debug:
                    out_parts.append(' {}\n'.format(pos - 1))
                else:
                    out_parts.append('\n')

                # Parse arguments from binary data
                arguments_list, bytes_read = self._get_args_from_bytes(data, pos, entry[1], current_byte, self.encoding)
                pos += bytes_read

                # Handle offset resolution
                offset_entry = self._offset_by_opcode.get(current_byte)
                if offset_entry:
                    first_indexer = offset_entry[1]
                    evil_offset = self.get_true_offset(arguments_list[first_indexer])
                    indexer = initial_search_offset.index(evil_offset)
                    arguments_list[first_indexer] = initial_sorted_offset[indexer][0]

                if current_byte == 0x19:
                    arguments_list[0] = "*MESSAGE_NUMBER*"

                out_parts.append(json.dumps(arguments_list, ensure_ascii=False))
                out_parts.append('\n')
            else:
                stringer += ' {:02x}'.format(current_byte)

        if stringer:
            out_parts.append('#0-{}\n'.format(stringer.lstrip(' ')))

        with open(self._txt_name, 'w', encoding='utf-8-sig') as out_file:
            out_file.write(''.join(out_parts))

    @staticmethod
    def _get_args_from_bytes(data: bytes, pos: int, args: str, current_byte: int, encoding: str):
        """Parse arguments directly from bytes buffer. Returns (arguments_list, bytes_consumed)."""
        arguments_list = []
        start_pos = pos
        appendix = ""
        for argument in args:
            if argument in SilkyMesScript.technical_instances:
                appendix = argument
                continue

            if argument in ('I', 'i'):
                fmt = appendix + argument
                val = struct.unpack_from(fmt, data, pos)[0]
                pos += 4
                arguments_list.append(val)
            elif argument in ('H', 'h'):
                fmt = appendix + argument
                val = struct.unpack_from(fmt, data, pos)[0]
                pos += 2
                arguments_list.append(val)
            elif argument in ('B', 'b'):
                fmt = appendix + argument
                val = struct.unpack_from(fmt, data, pos)[0]
                pos += 1
                arguments_list.append(val)
            elif argument == 'S':
                # Read null-terminated string
                end = data.index(b'\x00', pos)
                raw = data[pos:end]
                pos = end + 1
                result = SilkyMesScript._decode_string(current_byte, raw, encoding)
                arguments_list.append(result)
            appendix = ""

        return arguments_list, pos - start_pos

    @staticmethod
    def _decode_string(mode: int, raw: bytes, encoding: str) -> str:
        """Decode a raw string based on mode (0x0A=encrypted, 0x0B/0x33=plain)."""
        if mode == 0x0A:
            enc_lower = encoding.lower().replace('-', '').replace('_', '')
            is_utf8 = enc_lower in ('utf8', 'utf8sig')
            decoded = bytearray()
            i = 0
            raw_len = len(raw)
            while i < raw_len:
                byte_val = raw[i]
                if not SilkyMesScript._is_multibyte_lead(byte_val, encoding):
                    # Single-byte: apply decryption
                    zlo = byte_val - 0x7D62
                    high = (zlo & 0xff00) >> 8
                    low = zlo & 0xff
                    decoded.append(high)
                    decoded.append(low)
                    i += 1
                else:
                    if is_utf8:
                        char_len = SilkyMesScript._utf8_byte_count(byte_val)
                        for j in range(char_len):
                            if i < raw_len:
                                decoded.append(raw[i])
                                i += 1
                    else:
                        decoded.append(raw[i])
                        i += 1
                        if i < raw_len:
                            decoded.append(raw[i])
                            i += 1
            try:
                return bytes(decoded).decode(encoding)
            except UnicodeDecodeError:
                return bytes(decoded).hex(' ')
        elif mode in (0x33, 0x0B):
            try:
                return raw.decode(encoding)
            except UnicodeDecodeError:
                return raw.hex(' ')
        else:
            return raw.hex(' ')

    def _diss_other_offsets(self) -> None:
        """Disassemble other offsets from the Silky Engine script."""
        pointer = self.get_true_offset(0)

        with open(self._mes_name, 'rb') as f:
            data = f.read()

        data_len = len(data)
        pos = pointer
        offsets_set = set(self._offsets)

        while pos < data_len:
            current_byte = data[pos]
            pos += 1

            lookup = self._cmd_by_opcode.get(current_byte)
            if lookup is not None:
                _, entry = lookup
                arguments_list, bytes_read = self._get_args_from_bytes(data, pos, entry[1], current_byte, self.encoding)
                pos += bytes_read

                offset_entry = self._offset_by_opcode.get(current_byte)
                if offset_entry:
                    good_offset = self.get_true_offset(arguments_list[offset_entry[1]])
                    if good_offset not in offsets_set:
                        self._offsets.append(good_offset)
                        offsets_set.add(good_offset)

    def _diss_header(self) -> tuple:
        """Disassemble Silky Engine mes header."""
        first_offsets = []
        second_offsets = []
        with open(self._mes_name, 'rb') as mes_file:
            prm = list(struct.unpack('II', mes_file.read(8)))
            for i in range(prm[0]):
                first_offsets.append(struct.unpack('I', mes_file.read(4))[0])
            for i in range(prm[1]):
                second_offsets.append(struct.unpack('I', mes_file.read(4))[0])

        return prm, first_offsets, second_offsets

    # Offsets methods.

    def get_true_offset(self, raw_offset: int) -> int:
        return raw_offset + self._prm[0] * 4 + self._prm[1] * 4 + 8

    def set_true_offset(self, raw_offset):
        return raw_offset - self._prm[0] * 4 - self._prm[1] * 4 - 8

    # Structure packing technicals methods.

    @staticmethod
    def set_args(argument_list, args: str, current_encoding: str, opcode: int = 0) -> bytes:
        args_bytes = b''
        appendix = ""
        current_argument = 0
        for argument in args:
            if argument in SilkyMesScript.technical_instances:
                appendix = argument
                continue

            if argument in SilkyMesScript.set_I.instances:
                args_bytes += SilkyMesScript.set_I(argument_list[current_argument], appendix+argument)
            elif argument in SilkyMesScript.set_H.instances:
                args_bytes += SilkyMesScript.set_H(argument_list[current_argument], appendix+argument)
            elif argument in SilkyMesScript.set_B.instances:
                args_bytes += SilkyMesScript.set_B(argument_list[current_argument], appendix+argument)
            elif argument in SilkyMesScript.set_S.instances:
                args_bytes += SilkyMesScript.set_S(argument_list[current_argument], current_encoding, opcode)
            current_argument += 1

        return args_bytes

    @staticmethod
    def set_B(arguments: int, command: str) -> bytes:
        return struct.pack(command, arguments)

    @staticmethod
    def set_H(arguments: int, command: str) -> bytes:
        return struct.pack(command, arguments)

    @staticmethod
    def set_I(arguments: int, command: str) -> bytes:
        return struct.pack(command, arguments)

    @staticmethod
    def set_S(arguments: str, encoding: str, opcode: int = 0) -> bytes:
        raw = arguments.encode(encoding)
        # 对 0x0A STR_CRYPT 做反向压缩：
        # SJIS 假名区 0x829F..0x831E 压回单字节 c = (v - 0x829E) (1..0x80)
        # 其他双字节透传，单字节也保持原样（GBK 中文 leadbyte 都 ≥0x81，不会冲突）
        if opcode == 0x0A:
            out = bytearray()
            i = 0
            n = len(raw)
            while i < n:
                if i + 1 < n:
                    v = (raw[i] << 8) | raw[i + 1]
                    if 0x829F <= v <= 0x831E:
                        c = v - 0x829E
                        if c < 0x81:  # 永真，但保险检查
                            out.append(c)
                            i += 2
                            continue
                # 不压缩：透传当前字节
                out.append(raw[i])
                i += 1
            raw = bytes(out)
        return raw + b'\x00'

    # Structure extraction technical methods (kept for compatibility).

    @staticmethod
    def get_args(in_file, args: str, current_byte: int, current_encoding: str) -> list:
        arguments_list = []
        appendix = ""
        for argument in args:
            if argument in SilkyMesScript.technical_instances:
                appendix = argument
            elif argument in SilkyMesScript.get_I.instances:
                arguments_list.append(SilkyMesScript.get_I(in_file, appendix+argument))
            elif argument in SilkyMesScript.get_H.instances:
                arguments_list.append(SilkyMesScript.get_H(in_file, appendix+argument))
            elif argument in SilkyMesScript.get_B.instances:
                arguments_list.append(SilkyMesScript.get_B(in_file, appendix+argument))
            elif argument in SilkyMesScript.get_S.instances:
                leng, result = SilkyMesScript.get_S(current_byte, in_file, current_encoding)
                arguments_list.append(result)
        return arguments_list

    @staticmethod
    def get_B(file_in, definer: str) -> int:
        return struct.unpack(definer, file_in.read(1))[0]

    @staticmethod
    def get_H(file_in, definer: str) -> int:
        return struct.unpack(definer, file_in.read(2))[0]

    @staticmethod
    def get_I(file_in, definer: str) -> int:
        return struct.unpack(definer, file_in.read(4))[0]

    @staticmethod
    def _is_multibyte_lead(byte_val: int, encoding: str) -> bool:
        enc = encoding.lower().replace('-', '').replace('_', '')
        if enc in ('gbk', 'gb2312', 'gb18030', 'cp932', 'shiftjis', 'shift_jis', 'sjis'):
            return byte_val >= 0x81
        elif enc in ('utf8', 'utf8sig'):
            return byte_val >= 0xC0
        else:
            return byte_val >= 0x81

    @staticmethod
    def _utf8_byte_count(lead_byte: int) -> int:
        if lead_byte < 0x80:
            return 1
        elif lead_byte < 0xC0:
            return 1
        elif lead_byte < 0xE0:
            return 2
        elif lead_byte < 0xF0:
            return 3
        else:
            return 4

    @staticmethod
    def get_S(mode: int, in_file, encoding: str) -> tuple:
        """Get string from the mode and input file."""
        length = 0
        string = b''
        byte = in_file.read(1)
        while byte != b'\x00':
            string += byte
            length += 1
            byte = in_file.read(1)
        result = SilkyMesScript._decode_string(mode, string, encoding)
        return length, result

    # --- Text extraction / import helpers ---

    # Name block detection pattern:
    # PUSH_STR["character_name"] + PUSH[83886080] + PUSH[486539264] + 18[] +
    # PUSH_STR["name"] + PUSH_STR["main.inc"] + ...
    # Known PUSH values that appear right after a character-name PUSH_STR


if __name__ == "__main__":
    import argparse, sys, os, glob

    ap = argparse.ArgumentParser(
        description="Silky MES script <-> opcode txt (单文件 或 目录批处理)"
    )
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_d = sub.add_parser("disasm", help="MES -> op.txt")
    p_d.add_argument("input", help="单个 .MES 文件，或包含 .MES 的目录")
    p_d.add_argument("output", help="单文件输出路径，或目录")
    p_d.add_argument("--encoding", default="cp932")
    p_d.add_argument("--verbose", action="store_true")
    p_d.add_argument("--pattern", default="*.MES",
                     help="目录模式下的 glob 通配符 (default: *.MES)")

    p_a = sub.add_parser("asm", help="op.txt -> MES")
    p_a.add_argument("input", help="单个 op.txt 文件，或包含 op.txt 的目录")
    p_a.add_argument("output", help="单文件输出路径，或目录")
    p_a.add_argument("--encoding", default="cp932")
    p_a.add_argument("--verbose", action="store_true")
    p_a.add_argument("--pattern", default="*.op.txt",
                     help="目录模式下的 glob 通配符 (default: *.op.txt)")

    args = ap.parse_args()

    def _do_disasm(in_mes, out_op):
        sm = SilkyMesScript(in_mes, out_op,
                            encoding=args.encoding, verbose=args.verbose)
        sm.disassemble()

    def _do_asm(in_op, out_mes):
        # SilkyMesScript 的构造参数顺序是 (mes_path, txt_path)
        sm = SilkyMesScript(out_mes, in_op,
                            encoding=args.encoding, verbose=args.verbose)
        sm.assemble()

    def _strip_ext(filename, exts):
        """去掉已知尾缀（如 .MES 或 .op.txt）。"""
        for e in exts:
            if filename.lower().endswith(e.lower()):
                return filename[:-len(e)]
        # 退回去 splitext
        return os.path.splitext(filename)[0]

    if args.cmd == "disasm":
        if os.path.isdir(args.input):
            os.makedirs(args.output, exist_ok=True)
            files = sorted(glob.glob(os.path.join(args.input, args.pattern)))
            print(f"[batch] {len(files)} 个文件 disasm -> {args.output}")
            for f in files:
                base = _strip_ext(os.path.basename(f), ['.MES'])
                out = os.path.join(args.output, base + '.op.txt')
                _do_disasm(f, out)
                print(f"  [+] {os.path.basename(f)} -> {os.path.basename(out)}")
            print(f"[batch] 完成 {len(files)} 个")
        else:
            _do_disasm(args.input, args.output)
            print(f"[+] disassembled {args.input} -> {args.output}")

    elif args.cmd == "asm":
        if os.path.isdir(args.input):
            os.makedirs(args.output, exist_ok=True)
            files = sorted(glob.glob(os.path.join(args.input, args.pattern)))
            print(f"[batch] {len(files)} 个文件 asm -> {args.output}")
            for f in files:
                base = _strip_ext(os.path.basename(f), ['.op.txt'])
                out = os.path.join(args.output, base + '.MES')
                _do_asm(f, out)
                print(f"  [+] {os.path.basename(f)} -> {os.path.basename(out)}")
            print(f"[batch] 完成 {len(files)} 个")
        else:
            _do_asm(args.input, args.output)
            print(f"[+] assembled {args.input} -> {args.output}")
