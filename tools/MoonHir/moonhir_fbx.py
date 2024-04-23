#Garbro解开fpk之后，fbx默认是未压缩的，进行pack之前需要添加文件后缀.uncomp
import io

Filename = 'sce01.fbx' #压缩后的文件名
#Filename = 'system.fbx' 
FilenameUncompress = Filename + '.uncomp' #未压缩时的文件名

def main():
    test_pack()
    #test_unpack()

#------------------------------------------
def test_pack():
    fs = open(FilenameUncompress, 'rb')
    umcomp = fs.read()
    fs.close
    print('umcomp', hex(len(umcomp)))
    lenUncomp = len(umcomp)
    comp = pack_fbx(umcomp, lenUncomp)
    print('comp', hex(len(comp)))
    fs = open(Filename, 'wb')
    #写入头部
    fs.write(b'FBX\x01gkx\x10')
    fs.write(len(comp).to_bytes(4, byteorder='little'))
    fs.write(lenUncomp.to_bytes(4, byteorder='little'))
    #写入正文
    fs.write(comp)
    fs.close()
    print('Done')

def pack_fbx(input, inputLen):
    output = bytearray()
    pos = 0

    while pos < inputLen:
        ctrl = 0
        count = 0x80
        tmp = b''
        remain = inputLen - pos
        if remain <= 0x200:
            count = 0xF0
        for i in range(4):
            if pos >= inputLen:
                #即将结束，添加C0，表示跳出当前ctrl
                ctrl += 3 << i*2
                tmp += b'\xC0'
                break
            if pos + count > inputLen:
                count = inputLen - pos
            tmp += (count - 2).to_bytes(1)
            data = input[pos:pos+count]
            tmp += data
            pos += count
            ctrl += 1 << i*2
        output.extend(ctrl.to_bytes(1))
        output.extend(tmp)
    #添加ctrl和C0，两次C0表示结束
    output.append(0xFF)
    output.append(0xC0)
    return output

#------------------------------------------
def test_unpack():
    fs = open(Filename, 'rb')
    #读取头部
    fs.seek(0x07)
    start = int.from_bytes(fs.read(1))
    packed_size = int.from_bytes(fs.read(4), byteorder='little')
    unpacked_size = int.from_bytes(fs.read(4), byteorder='little')
    print('comp', packed_size)
    fs.seek(start)
    uncomp = unpack_fbx(fs, packed_size, unpacked_size)
    fs.close()
    print('uncomp', hex(len(uncomp)))
    fs = open(FilenameUncompress, 'wb')
    fs.write(uncomp)
    fs.close
    print('Done')

def unpack_fbx(input_stream:io.BytesIO, packed_size, unpacked_size):
    output = bytearray()
    dst = 0
    ctl = 1

    while dst < unpacked_size:
        if ctl == 1:
            ctl = input_stream.read(1)
            if not ctl:
                break
            ctl = ord(ctl) | 0x100

        control = ctl & 3

        if control == 0:
            output.extend(input_stream.read(1))
            dst += 1
        elif control == 1:
            count = ord(input_stream.read(1))
            if count == -1:
                return output
            count = min(count + 2, unpacked_size - dst)
            data = input_stream.read(count)
            output.extend(data)
            dst += count
        elif control == 2:
            offset = ord(input_stream.read(1)) << 8
            offset |= ord(input_stream.read(1))
            if offset == -1:
                return output
            count = min((offset & 0x1F) + 4, unpacked_size - dst)
            offset >>= 5
            for i in range(count):
                data = output[dst - offset - 1]
                output.append(data)
                dst += 1
            pass
        elif control == 3:
            exctl = ord(input_stream.read(1))
            if exctl == -1:
                return output
            count = exctl & 0x3F
            exctl >>= 6

            if exctl == 0:
                count = (count << 8) | ord(input_stream.read(1))
                if count == -1:
                    return output
                count = min(count + 0x102, unpacked_size - dst)
                data = input_stream.read(count)
                output.extend(data)
                dst += count
            elif exctl == 1:
                offset = ord(input_stream.read(1)) << 8
                offset |= ord(input_stream.read(1))
                count = (count << 5) | (offset & 0x1F)
                count = min(count + 0x24, unpacked_size - dst)
                offset >>= 5
                for i in range(count):
                    data = output[dst - offset - 1]
                    output.append(data)
                    dst += 1
                pass
            elif exctl == 3:
                input_stream.seek(count, 1)
                ctl = 1 << 2

        ctl >>= 2

    return output

#------------------------------------------
main()