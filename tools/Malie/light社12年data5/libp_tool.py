#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
libp_tool.py — Malie 引擎 LIBP 加密封包 解包/封包/验证/列表 工具
================================================================
支持 Camellia-128 和 CFI 两种加密方式，密钥从内置数据库自动匹配。

用法:
  python libp_tool.py unpack  <封包文件> [输出目录]
  python libp_tool.py pack    <输入目录> <输出封包> [--key <密钥名>]
  python libp_tool.py verify  <封包文件> [临时目录]
  python libp_tool.py list    <封包文件>

拖放: 将 .dat/.lib 文件拖放到本脚本上自动执行 unpack。

依赖: 与 libp_crypto.py (加解密核心) 放在同一目录。
"""

import sys, os, struct, json, hashlib, time

# ═══════════════════════════════════════════════════════════════
#  加解密核心 (内联, 避免拆文件导致拖放失败)
# ═══════════════════════════════════════════════════════════════

_M = 0xFFFFFFFF

def _rl(v, s):
    s %= 32
    return ((v << s) | (v >> (32 - s))) & _M

def _rr(v, s):
    s %= 32
    return ((v >> s) | (v << (32 - s))) & _M

def _mv(v):
    return (_rl(v, 8) & 0x00FF00FF) | (_rr(v, 8) & 0xFF00FF00)

# ── Camellia S-Box (完整, 直接嵌入) ──
# fmt: off
_S1=[0x70707000,0x82828200,0x2C2C2C00,0xECECEC00,0xB3B3B300,0x27272700,0xC0C0C000,0xE5E5E500,0xE4E4E400,0x85858500,0x57575700,0x35353500,0xEAEAEA00,0x0C0C0C00,0xAEAEAE00,0x41414100,0x23232300,0xEFEFEF00,0x6B6B6B00,0x93939300,0x45454500,0x19191900,0xA5A5A500,0x21212100,0xEDEDED00,0x0E0E0E00,0x4F4F4F00,0x4E4E4E00,0x1D1D1D00,0x65656500,0x92929200,0xBDBDBD00,0x86868600,0xB8B8B800,0xAFAFAF00,0x8F8F8F00,0x7C7C7C00,0xEBEBEB00,0x1F1F1F00,0xCECECE00,0x3E3E3E00,0x30303000,0xDCDCDC00,0x5F5F5F00,0x5E5E5E00,0xC5C5C500,0x0B0B0B00,0x1A1A1A00,0xA6A6A600,0xE1E1E100,0x39393900,0xCACACA00,0xD5D5D500,0x47474700,0x5D5D5D00,0x3D3D3D00,0xD9D9D900,0x01010100,0x5A5A5A00,0xD6D6D600,0x51515100,0x56565600,0x6C6C6C00,0x4D4D4D00,0x8B8B8B00,0x0D0D0D00,0x9A9A9A00,0x66666600,0xFBFBFB00,0xCCCCCC00,0xB0B0B000,0x2D2D2D00,0x74747400,0x12121200,0x2B2B2B00,0x20202000,0xF0F0F000,0xB1B1B100,0x84848400,0x99999900,0xDFDFDF00,0x4C4C4C00,0xCBCBCB00,0xC2C2C200,0x34343400,0x7E7E7E00,0x76767600,0x05050500,0x6D6D6D00,0xB7B7B700,0xA9A9A900,0x31313100,0xD1D1D100,0x17171700,0x04040400,0xD7D7D700,0x14141400,0x58585800,0x3A3A3A00,0x61616100,0xDEDEDE00,0x1B1B1B00,0x11111100,0x1C1C1C00,0x32323200,0x0F0F0F00,0x9C9C9C00,0x16161600,0x53535300,0x18181800,0xF2F2F200,0x22222200,0xFEFEFE00,0x44444400,0xCFCFCF00,0xB2B2B200,0xC3C3C300,0xB5B5B500,0x7A7A7A00,0x91919100,0x24242400,0x08080800,0xE8E8E800,0xA8A8A800,0x60606000,0xFCFCFC00,0x69696900,0x50505000,0xAAAAAA00,0xD0D0D000,0xA0A0A000,0x7D7D7D00,0xA1A1A100,0x89898900,0x62626200,0x97979700,0x54545400,0x5B5B5B00,0x1E1E1E00,0x95959500,0xE0E0E000,0xFFFFFF00,0x64646400,0xD2D2D200,0x10101000,0xC4C4C400,0x00000000,0x48484800,0xA3A3A300,0xF7F7F700,0x75757500,0xDBDBDB00,0x8A8A8A00,0x03030300,0xE6E6E600,0xDADADA00,0x09090900,0x3F3F3F00,0xDDDDDD00,0x94949400,0x87878700,0x5C5C5C00,0x83838300,0x02020200,0xCDCDCD00,0x4A4A4A00,0x90909000,0x33333300,0x73737300,0x67676700,0xF6F6F600,0xF3F3F300,0x9D9D9D00,0x7F7F7F00,0xBFBFBF00,0xE2E2E200,0x52525200,0x9B9B9B00,0xD8D8D800,0x26262600,0xC8C8C800,0x37373700,0xC6C6C600,0x3B3B3B00,0x81818100,0x96969600,0x6F6F6F00,0x4B4B4B00,0x13131300,0xBEBEBE00,0x63636300,0x2E2E2E00,0xE9E9E900,0x79797900,0xA7A7A700,0x8C8C8C00,0x9F9F9F00,0x6E6E6E00,0xBCBCBC00,0x8E8E8E00,0x29292900,0xF5F5F500,0xF9F9F900,0xB6B6B600,0x2F2F2F00,0xFDFDFD00,0xB4B4B400,0x59595900,0x78787800,0x98989800,0x06060600,0x6A6A6A00,0xE7E7E700,0x46464600,0x71717100,0xBABABA00,0xD4D4D400,0x25252500,0xABABAB00,0x42424200,0x88888800,0xA2A2A200,0x8D8D8D00,0xFAFAFA00,0x72727200,0x07070700,0xB9B9B900,0x55555500,0xF8F8F800,0xEEEEEE00,0xACACAC00,0x0A0A0A00,0x36363600,0x49494900,0x2A2A2A00,0x68686800,0x3C3C3C00,0x38383800,0xF1F1F100,0xA4A4A400,0x40404000,0x28282800,0xD3D3D300,0x7B7B7B00,0xBBBBBB00,0xC9C9C900,0x43434300,0xC1C1C100,0x15151500,0xE3E3E300,0xADADAD00,0xF4F4F400,0x77777700,0xC7C7C700,0x80808000,0x9E9E9E00]
_S2=[0x00E0E0E0,0x00050505,0x00585858,0x00D9D9D9,0x00676767,0x004E4E4E,0x00818181,0x00CBCBCB,0x00C9C9C9,0x000B0B0B,0x00AEAEAE,0x006A6A6A,0x00D5D5D5,0x00181818,0x005D5D5D,0x00828282,0x00464646,0x00DFDFDF,0x00D6D6D6,0x00272727,0x008A8A8A,0x00323232,0x004B4B4B,0x00424242,0x00DBDBDB,0x001C1C1C,0x009E9E9E,0x009C9C9C,0x003A3A3A,0x00CACACA,0x00252525,0x007B7B7B,0x000D0D0D,0x00717171,0x005F5F5F,0x001F1F1F,0x00F8F8F8,0x00D7D7D7,0x003E3E3E,0x009D9D9D,0x007C7C7C,0x00606060,0x00B9B9B9,0x00BEBEBE,0x00BCBCBC,0x008B8B8B,0x00161616,0x00343434,0x004D4D4D,0x00C3C3C3,0x00727272,0x00959595,0x00ABABAB,0x008E8E8E,0x00BABABA,0x007A7A7A,0x00B3B3B3,0x00020202,0x00B4B4B4,0x00ADADAD,0x00A2A2A2,0x00ACACAC,0x00D8D8D8,0x009A9A9A,0x00171717,0x001A1A1A,0x00353535,0x00CCCCCC,0x00F7F7F7,0x00999999,0x00616161,0x005A5A5A,0x00E8E8E8,0x00242424,0x00565656,0x00404040,0x00E1E1E1,0x00636363,0x00090909,0x00333333,0x00BFBFBF,0x00989898,0x00979797,0x00858585,0x00686868,0x00FCFCFC,0x00ECECEC,0x000A0A0A,0x00DADADA,0x006F6F6F,0x00535353,0x00626262,0x00A3A3A3,0x002E2E2E,0x00080808,0x00AFAFAF,0x00282828,0x00B0B0B0,0x00747474,0x00C2C2C2,0x00BDBDBD,0x00363636,0x00222222,0x00383838,0x00646464,0x001E1E1E,0x00393939,0x002C2C2C,0x00A6A6A6,0x00303030,0x00E5E5E5,0x00444444,0x00FDFDFD,0x00888888,0x009F9F9F,0x00656565,0x00878787,0x006B6B6B,0x00F4F4F4,0x00232323,0x00484848,0x00101010,0x00D1D1D1,0x00515151,0x00C0C0C0,0x00F9F9F9,0x00D2D2D2,0x00A0A0A0,0x00555555,0x00A1A1A1,0x00414141,0x00FAFAFA,0x00434343,0x00131313,0x00C4C4C4,0x002F2F2F,0x00A8A8A8,0x00B6B6B6,0x003C3C3C,0x002B2B2B,0x00C1C1C1,0x00FFFFFF,0x00C8C8C8,0x00A5A5A5,0x00202020,0x00898989,0x00000000,0x00909090,0x00474747,0x00EFEFEF,0x00EAEAEA,0x00B7B7B7,0x00151515,0x00060606,0x00CDCDCD,0x00B5B5B5,0x00121212,0x007E7E7E,0x00BBBBBB,0x00292929,0x000F0F0F,0x00B8B8B8,0x00070707,0x00040404,0x009B9B9B,0x00949494,0x00212121,0x00666666,0x00E6E6E6,0x00CECECE,0x00EDEDED,0x00E7E7E7,0x003B3B3B,0x00FEFEFE,0x007F7F7F,0x00C5C5C5,0x00A4A4A4,0x00373737,0x00B1B1B1,0x004C4C4C,0x00919191,0x006E6E6E,0x008D8D8D,0x00767676,0x00030303,0x002D2D2D,0x00DEDEDE,0x00969696,0x00262626,0x007D7D7D,0x00C6C6C6,0x005C5C5C,0x00D3D3D3,0x00F2F2F2,0x004F4F4F,0x00191919,0x003F3F3F,0x00DCDCDC,0x00797979,0x001D1D1D,0x00525252,0x00EBEBEB,0x00F3F3F3,0x006D6D6D,0x005E5E5E,0x00FBFBFB,0x00696969,0x00B2B2B2,0x00F0F0F0,0x00313131,0x000C0C0C,0x00D4D4D4,0x00CFCFCF,0x008C8C8C,0x00E2E2E2,0x00757575,0x00A9A9A9,0x004A4A4A,0x00575757,0x00848484,0x00111111,0x00454545,0x001B1B1B,0x00F5F5F5,0x00E4E4E4,0x000E0E0E,0x00737373,0x00AAAAAA,0x00F1F1F1,0x00DDDDDD,0x00595959,0x00141414,0x006C6C6C,0x00929292,0x00545454,0x00D0D0D0,0x00787878,0x00707070,0x00E3E3E3,0x00494949,0x00808080,0x00505050,0x00A7A7A7,0x00F6F6F6,0x00777777,0x00939393,0x00868686,0x00838383,0x002A2A2A,0x00C7C7C7,0x005B5B5B,0x00E9E9E9,0x00EEEEEE,0x008F8F8F,0x00010101,0x003D3D3D]
_S3=[0x38003838,0x41004141,0x16001616,0x76007676,0xD900D9D9,0x93009393,0x60006060,0xF200F2F2,0x72007272,0xC200C2C2,0xAB00ABAB,0x9A009A9A,0x75007575,0x06000606,0x57005757,0xA000A0A0,0x91009191,0xF700F7F7,0xB500B5B5,0xC900C9C9,0xA200A2A2,0x8C008C8C,0xD200D2D2,0x90009090,0xF600F6F6,0x07000707,0xA700A7A7,0x27002727,0x8E008E8E,0xB200B2B2,0x49004949,0xDE00DEDE,0x43004343,0x5C005C5C,0xD700D7D7,0xC700C7C7,0x3E003E3E,0xF500F5F5,0x8F008F8F,0x67006767,0x1F001F1F,0x18001818,0x6E006E6E,0xAF00AFAF,0x2F002F2F,0xE200E2E2,0x85008585,0x0D000D0D,0x53005353,0xF000F0F0,0x9C009C9C,0x65006565,0xEA00EAEA,0xA300A3A3,0xAE00AEAE,0x9E009E9E,0xEC00ECEC,0x80008080,0x2D002D2D,0x6B006B6B,0xA800A8A8,0x2B002B2B,0x36003636,0xA600A6A6,0xC500C5C5,0x86008686,0x4D004D4D,0x33003333,0xFD00FDFD,0x66006666,0x58005858,0x96009696,0x3A003A3A,0x09000909,0x95009595,0x10001010,0x78007878,0xD800D8D8,0x42004242,0xCC00CCCC,0xEF00EFEF,0x26002626,0xE500E5E5,0x61006161,0x1A001A1A,0x3F003F3F,0x3B003B3B,0x82008282,0xB600B6B6,0xDB00DBDB,0xD400D4D4,0x98009898,0xE800E8E8,0x8B008B8B,0x02000202,0xEB00EBEB,0x0A000A0A,0x2C002C2C,0x1D001D1D,0xB000B0B0,0x6F006F6F,0x8D008D8D,0x88008888,0x0E000E0E,0x19001919,0x87008787,0x4E004E4E,0x0B000B0B,0xA900A9A9,0x0C000C0C,0x79007979,0x11001111,0x7F007F7F,0x22002222,0xE700E7E7,0x59005959,0xE100E1E1,0xDA00DADA,0x3D003D3D,0xC800C8C8,0x12001212,0x04000404,0x74007474,0x54005454,0x30003030,0x7E007E7E,0xB400B4B4,0x28002828,0x55005555,0x68006868,0x50005050,0xBE00BEBE,0xD000D0D0,0xC400C4C4,0x31003131,0xCB00CBCB,0x2A002A2A,0xAD00ADAD,0x0F000F0F,0xCA00CACA,0x70007070,0xFF00FFFF,0x32003232,0x69006969,0x08000808,0x62006262,0x00000000,0x24002424,0xD100D1D1,0xFB00FBFB,0xBA00BABA,0xED00EDED,0x45004545,0x81008181,0x73007373,0x6D006D6D,0x84008484,0x9F009F9F,0xEE00EEEE,0x4A004A4A,0xC300C3C3,0x2E002E2E,0xC100C1C1,0x01000101,0xE600E6E6,0x25002525,0x48004848,0x99009999,0xB900B9B9,0xB300B3B3,0x7B007B7B,0xF900F9F9,0xCE00CECE,0xBF00BFBF,0xDF00DFDF,0x71007171,0x29002929,0xCD00CDCD,0x6C006C6C,0x13001313,0x64006464,0x9B009B9B,0x63006363,0x9D009D9D,0xC000C0C0,0x4B004B4B,0xB700B7B7,0xA500A5A5,0x89008989,0x5F005F5F,0xB100B1B1,0x17001717,0xF400F4F4,0xBC00BCBC,0xD300D3D3,0x46004646,0xCF00CFCF,0x37003737,0x5E005E5E,0x47004747,0x94009494,0xFA00FAFA,0xFC00FCFC,0x5B005B5B,0x97009797,0xFE00FEFE,0x5A005A5A,0xAC00ACAC,0x3C003C3C,0x4C004C4C,0x03000303,0x35003535,0xF300F3F3,0x23002323,0xB800B8B8,0x5D005D5D,0x6A006A6A,0x92009292,0xD500D5D5,0x21002121,0x44004444,0x51005151,0xC600C6C6,0x7D007D7D,0x39003939,0x83008383,0xDC00DCDC,0xAA00AAAA,0x7C007C7C,0x77007777,0x56005656,0x05000505,0x1B001B1B,0xA400A4A4,0x15001515,0x34003434,0x1E001E1E,0x1C001C1C,0xF800F8F8,0x52005252,0x20002020,0x14001414,0xE900E9E9,0xBD00BDBD,0xDD00DDDD,0xE400E4E4,0xA100A1A1,0xE000E0E0,0x8A008A8A,0xF100F1F1,0xD600D6D6,0x7A007A7A,0xBB00BBBB,0xE300E3E3,0x40004040,0x4F004F4F]
_S4=[0x70700070,0x2C2C002C,0xB3B300B3,0xC0C000C0,0xE4E400E4,0x57570057,0xEAEA00EA,0xAEAE00AE,0x23230023,0x6B6B006B,0x45450045,0xA5A500A5,0xEDED00ED,0x4F4F004F,0x1D1D001D,0x92920092,0x86860086,0xAFAF00AF,0x7C7C007C,0x1F1F001F,0x3E3E003E,0xDCDC00DC,0x5E5E005E,0x0B0B000B,0xA6A600A6,0x39390039,0xD5D500D5,0x5D5D005D,0xD9D900D9,0x5A5A005A,0x51510051,0x6C6C006C,0x8B8B008B,0x9A9A009A,0xFBFB00FB,0xB0B000B0,0x74740074,0x2B2B002B,0xF0F000F0,0x84840084,0xDFDF00DF,0xCBCB00CB,0x34340034,0x76760076,0x6D6D006D,0xA9A900A9,0xD1D100D1,0x04040004,0x14140014,0x3A3A003A,0xDEDE00DE,0x11110011,0x32320032,0x9C9C009C,0x53530053,0xF2F200F2,0xFEFE00FE,0xCFCF00CF,0xC3C300C3,0x7A7A007A,0x24240024,0xE8E800E8,0x60600060,0x69690069,0xAAAA00AA,0xA0A000A0,0xA1A100A1,0x62620062,0x54540054,0x1E1E001E,0xE0E000E0,0x64640064,0x10100010,0x00000000,0xA3A300A3,0x75750075,0x8A8A008A,0xE6E600E6,0x09090009,0xDDDD00DD,0x87870087,0x83830083,0xCDCD00CD,0x90900090,0x73730073,0xF6F600F6,0x9D9D009D,0xBFBF00BF,0x52520052,0xD8D800D8,0xC8C800C8,0xC6C600C6,0x81810081,0x6F6F006F,0x13130013,0x63630063,0xE9E900E9,0xA7A700A7,0x9F9F009F,0xBCBC00BC,0x29290029,0xF9F900F9,0x2F2F002F,0xB4B400B4,0x78780078,0x06060006,0xE7E700E7,0x71710071,0xD4D400D4,0xABAB00AB,0x88880088,0x8D8D008D,0x72720072,0xB9B900B9,0xF8F800F8,0xACAC00AC,0x36360036,0x2A2A002A,0x3C3C003C,0xF1F100F1,0x40400040,0xD3D300D3,0xBBBB00BB,0x43430043,0x15150015,0xADAD00AD,0x77770077,0x80800080,0x82820082,0xECEC00EC,0x27270027,0xE5E500E5,0x85850085,0x35350035,0x0C0C000C,0x41410041,0xEFEF00EF,0x93930093,0x19190019,0x21210021,0x0E0E000E,0x4E4E004E,0x65650065,0xBDBD00BD,0xB8B800B8,0x8F8F008F,0xEBEB00EB,0xCECE00CE,0x30300030,0x5F5F005F,0xC5C500C5,0x1A1A001A,0xE1E100E1,0xCACA00CA,0x47470047,0x3D3D003D,0x01010001,0xD6D600D6,0x56560056,0x4D4D004D,0x0D0D000D,0x66660066,0xCCCC00CC,0x2D2D002D,0x12120012,0x20200020,0xB1B100B1,0x99990099,0x4C4C004C,0xC2C200C2,0x7E7E007E,0x05050005,0xB7B700B7,0x31310031,0x17170017,0xD7D700D7,0x58580058,0x61610061,0x1B1B001B,0x1C1C001C,0x0F0F000F,0x16160016,0x18180018,0x22220022,0x44440044,0xB2B200B2,0xB5B500B5,0x91910091,0x08080008,0xA8A800A8,0xFCFC00FC,0x50500050,0xD0D000D0,0x7D7D007D,0x89890089,0x97970097,0x5B5B005B,0x95950095,0xFFFF00FF,0xD2D200D2,0xC4C400C4,0x48480048,0xF7F700F7,0xDBDB00DB,0x03030003,0xDADA00DA,0x3F3F003F,0x94940094,0x5C5C005C,0x02020002,0x4A4A004A,0x33330033,0x67670067,0xF3F300F3,0x7F7F007F,0xE2E200E2,0x9B9B009B,0x26260026,0x37370037,0x3B3B003B,0x96960096,0x4B4B004B,0xBEBE00BE,0x2E2E002E,0x79790079,0x8C8C008C,0x6E6E006E,0x8E8E008E,0xF5F500F5,0xB6B600B6,0xFDFD00FD,0x59590059,0x98980098,0x6A6A006A,0x46460046,0xBABA00BA,0x25250025,0x42420042,0xA2A200A2,0xFAFA00FA,0x07070007,0x55550055,0xEEEE00EE,0x0A0A000A,0x49490049,0x68680068,0x38380038,0xA4A400A4,0x28280028,0x7B7B007B,0xC9C900C9,0xC1C100C1,0xE3E300E3,0xF4F400F4,0xC7C700C7,0x9E9E009E]
# fmt: on

def _cam_dec(pB, kt, off=0):
    """Camellia-128 单块解密"""
    dst = list(struct.unpack('<IIII', pB))
    rb = ((off >> 4) & 0xF) + 16
    dst[0] = _rl(dst[0], rb); dst[1] = _rr(dst[1], rb)
    dst[2] = _rl(dst[2], rb); dst[3] = _rr(dst[3], rb)
    dst = [_mv(x) for x in dst]
    k = 0
    for i in range(4): dst[i] ^= kt[k + i]
    k += 4
    for i in range(3):
        for j in range(3):
            t = kt[k+2] ^ dst[0]; U = _S3[(t>>8)&0xFF]^_S4[t&0xFF]^_S2[(t>>16)&0xFF]^_S1[(t>>24)&0xFF]
            t = kt[k+3] ^ dst[1]; D = _S4[(t>>8)&0xFF]^_S1[t&0xFF]^_S3[(t>>16)&0xFF]^_S2[(t>>24)&0xFF]
            dst[2] ^= (U^D)&_M; dst[3] ^= (U^D^_rr(U,8))&_M
            t = kt[k] ^ dst[2]; U = _S3[(t>>8)&0xFF]^_S4[t&0xFF]^_S2[(t>>16)&0xFF]^_S1[(t>>24)&0xFF]
            t = kt[k+1] ^ dst[3]; D = _S4[(t>>8)&0xFF]^_S1[t&0xFF]^_S3[(t>>16)&0xFF]^_S2[(t>>24)&0xFF]
            dst[0] ^= (U^D)&_M; dst[1] ^= (U^D^_rr(U,8))&_M
            k += 4
        if i < 2:
            dst[1] ^= _rl(dst[0]&kt[k+2],1); dst[0] ^= (dst[1]|kt[k+3])
            dst[2] ^= (dst[3]|kt[k+1]); dst[3] ^= _rl(dst[2]&kt[k],1)
            k += 4
    dst[0],dst[2] = dst[2],dst[0]; dst[1],dst[3] = dst[3],dst[1]
    for i in range(4): dst[i] ^= kt[k+i]
    dst = [_mv(x) for x in dst]
    return struct.pack('<IIII', *[x&_M for x in dst])

def _cam_enc(pB, kt, off=0):
    """Camellia-128 单块加密"""
    dst = list(struct.unpack('<IIII', pB))
    dst = [_mv(x) for x in dst]
    k = 51
    dst[0] ^= kt[k-3]; dst[1] ^= kt[k-2]; dst[2] ^= kt[k-1]; dst[3] ^= kt[k]
    k -= 4
    for i in range(3):
        for j in range(3):
            t = kt[k-3] ^ dst[0]; U = _S3[(t>>8)&0xFF]^_S4[t&0xFF]^_S2[(t>>16)&0xFF]^_S1[(t>>24)&0xFF]
            t = kt[k-2] ^ dst[1]; D = _S4[(t>>8)&0xFF]^_S1[t&0xFF]^_S3[(t>>16)&0xFF]^_S2[(t>>24)&0xFF]
            dst[2] ^= (U^D)&_M; dst[3] ^= (U^D^_rr(U,8))&_M
            t = kt[k-1] ^ dst[2]; U = _S3[(t>>8)&0xFF]^_S4[t&0xFF]^_S2[(t>>16)&0xFF]^_S1[(t>>24)&0xFF]
            t = kt[k] ^ dst[3]; D = _S4[(t>>8)&0xFF]^_S1[t&0xFF]^_S3[(t>>16)&0xFF]^_S2[(t>>24)&0xFF]
            dst[0] ^= (U^D)&_M; dst[1] ^= (U^D^_rr(U,8))&_M
            k -= 4
        if i < 2:
            dst[1] ^= _rl(dst[0]&kt[k-3],1); dst[0] ^= (dst[1]|kt[k-2])
            dst[2] ^= (dst[3]|kt[k]); dst[3] ^= _rl(dst[2]&kt[k-1],1)
            k -= 4
    dst[0],dst[2] = dst[2],dst[0]; dst[1],dst[3] = dst[3],dst[1]
    dst[0] ^= kt[k-3]; dst[1] ^= kt[k-2]; dst[2] ^= kt[k-1]; dst[3] ^= kt[k]
    dst = [_mv(x) for x in dst]
    rb = ((off >> 4) & 0xF) + 16
    dst[0] = _rr(dst[0], rb); dst[1] = _rl(dst[1], rb)
    dst[2] = _rr(dst[2], rb); dst[3] = _rl(dst[3], rb)
    return struct.pack('<IIII', *[x&_M for x in dst])

def decrypt_data(data, kt, offset=0):
    """解密 bytearray，16字节对齐"""
    total = len(data)
    out = bytearray()
    t0 = time.time()
    for off in range(0, total - 15, 16):
        out.extend(_cam_dec(bytes(data[off:off+16]), kt, offset + off))
        if off > 0 and off % 1048576 == 0:
            mb = off / 1048576; mb_t = total / 1048576
            el = time.time() - t0; sp = mb/max(el,0.001)
            print(f'\r[解密] {mb:.0f}/{mb_t:.0f} MB ({mb*100/mb_t:.0f}%) '
                  f'{el:.0f}s [{sp:.1f} MB/s]', end='', flush=True)
    if total > 2097152: print()
    return out

def encrypt_data(data, kt, offset=0):
    """加密 bytearray，16字节对齐"""
    total = len(data)
    out = bytearray()
    t0 = time.time()
    for off in range(0, total - 15, 16):
        out.extend(_cam_enc(bytes(data[off:off+16]), kt, offset + off))
        if off > 0 and off % 1048576 == 0:
            mb = off / 1048576; mb_t = total / 1048576
            el = time.time() - t0; sp = mb/max(el,0.001)
            print(f'\r[加密] {mb:.0f}/{mb_t:.0f} MB ({mb*100/mb_t:.0f}%) '
                  f'{el:.0f}s [{sp:.1f} MB/s]', end='', flush=True)
    if total > 2097152: print()
    return out

# ═══════════════════════════════════════════════════════════════
#  密钥数据库 (从 database_malie.py 动态加载)
# ═══════════════════════════════════════════════════════════════

def _load_database():
    """从同目录的 database_malie.py 加载密钥库"""
    db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'database_malie.py')
    if not os.path.exists(db_path):
        print(f'[错误] 找不到密钥数据库: {db_path}')
        sys.exit(1)
    ns = {}
    with open(db_path, 'r', encoding='utf-8') as f:
        exec(f.read(), ns)
    return ns.get('database_malie', {})

def _find_key(enc_header_16):
    """用加密后的前16字节自动匹配密钥"""
    db = _load_database()
    for name, item in db.items():
        if 'RotateKey' in item:
            continue  # 暂不支持 CFI
        kt = item['Key'][:52]
        plain = _cam_dec(bytes(enc_header_16), kt, 0)
        if plain[:4] == b'LIBP':
            return name, item
    return None, None

# ═══════════════════════════════════════════════════════════════
#  LIBP 格式解析
# ═══════════════════════════════════════════════════════════════

class LibpArchive:
    """LIBP 封包的完整内存表示"""

    def __init__(self):
        self.key_name = ''
        self.keytable = []
        self.align = 1024
        self.count = 0          # 索引条目数
        self.offset_count = 0   # 偏移表条目数
        self.index_entries = []  # [(name, flags, idx, size), ...]
        self.offset_table = []   # [u32, ...]
        self.data_start = 0     # 数据区起始偏移
        self.files = []         # [(path, abs_offset, size), ...]

    def read_header(self, fh, key_name=None):
        """从文件句柄读取并解密头部"""
        enc16 = fh.read(16)
        if len(enc16) < 16:
            print('[错误] 文件太小，不是有效的 LIBP 封包')
            return False

        if key_name:
            db = _load_database()
            if key_name not in db:
                print(f'[错误] 密钥 "{key_name}" 不在数据库中')
                return False
            item = db[key_name]
            self.key_name = key_name
        else:
            self.key_name, item = _find_key(enc16)
            if not item:
                print('[错误] 无法匹配密钥，请用 --key 指定')
                return False

        self.keytable = item['Key'][:52]
        self.align = item.get('Align', 1024)
        print(f'[信息] 密钥: {self.key_name}')
        print(f'[信息] 对齐: 0x{self.align:X}')

        # 解密 LIBP 头
        plain0 = _cam_dec(enc16, self.keytable, 0)
        if plain0[:4] != b'LIBP':
            print('[错误] 解密后不是 LIBP 签名')
            return False

        self.count = struct.unpack_from('<I', plain0, 4)[0]
        self.offset_count = struct.unpack_from('<I', plain0, 8)[0]
        print(f'[信息] 索引条目: {self.count}, 偏移表条目: {self.offset_count}')

        # 计算需要读取的总头部大小
        idx_size = self.count * 0x20
        ot_size = self.offset_count * 4
        header_size = 0x10 + idx_size + ot_size
        # 对齐到16字节
        header_read = (header_size + 15) & ~15

        fh.seek(0)
        enc_all = fh.read(header_read)
        dec_all = decrypt_data(bytearray(enc_all), self.keytable, 0)

        # 解析索引
        self.index_entries = []
        for i in range(self.count):
            base = 0x10 + i * 0x20
            name_raw = dec_all[base:base+0x14]
            ne = name_raw.find(b'\x00')
            name = name_raw[:ne].decode('cp932', errors='replace') if ne >= 0 else name_raw.decode('cp932', errors='replace')
            flags = struct.unpack_from('<I', dec_all, base + 0x14)[0]
            idx = struct.unpack_from('<I', dec_all, base + 0x18)[0]
            size = struct.unpack_from('<I', dec_all, base + 0x1C)[0]
            self.index_entries.append((name, flags, idx, size))

        # 解析偏移表
        ot_start = 0x10 + idx_size
        self.offset_table = []
        for i in range(self.offset_count):
            val = struct.unpack_from('<I', dec_all, ot_start + i * 4)[0]
            self.offset_table.append(val)

        # 数据区起始
        raw_end = ot_start + ot_size
        self.data_start = (raw_end + self.align - 1) & ~(self.align - 1)
        print(f'[信息] 数据区起始: 0x{self.data_start:X}')

        # 递归构建文件列表
        self.files = []
        self._walk(0, 1, '')
        print(f'[信息] 文件总数: {len(self.files)}')
        return True

    def _walk(self, entry_idx, cnt, path):
        for i in range(cnt):
            name, flags, idx, size = self.index_entries[entry_idx + i]
            if name.startswith('/'):
                name = name[1:]
            full = os.path.join(path, name) if name else path
            is_file = (flags & 0x30000) != 0
            if is_file:
                abs_off = self.data_start + (self.offset_table[idx] << 10)
                self.files.append((full, abs_off, size))
            else:
                if idx > entry_idx:
                    self._walk(idx, size, full)

# ═══════════════════════════════════════════════════════════════
#  unpack 命令
# ═══════════════════════════════════════════════════════════════

def cmd_unpack(arc_path, out_dir=None, key_name=None):
    if out_dir is None:
        out_dir = os.path.splitext(arc_path)[0] + '_unpacked'

    file_size = os.path.getsize(arc_path)
    print(f'[信息] 封包大小: {file_size/1048576:.1f} MB')

    # ── 步骤1: 读取整个封包 ──
    t0 = time.time()
    print(f'[读取] 正在载入封包...')
    with open(arc_path, 'rb') as fh:
        raw = fh.read()
    t_read = time.time() - t0
    print(f'[读取] 完成 ({t_read:.1f}s)')

    # ── 步骤2: 匹配密钥 ──
    if key_name:
        db = _load_database()
        if key_name not in db:
            print(f'[错误] 密钥 "{key_name}" 不在数据库中')
            return False
        item = db[key_name]
        kn = key_name
    else:
        kn, item = _find_key(raw[:16])
        if not item:
            print('[错误] 无法匹配密钥，请用 --key 指定')
            return False
    kt = item['Key'][:52]
    align_val = item.get('Align', 1024)
    print(f'[信息] 密钥: {kn}, 对齐: 0x{align_val:X}')

    # ── 步骤3: 全量解密 ──
    t1 = time.time()
    print(f'[解密] 全量解密 {file_size/1048576:.1f} MB ...')
    dec = decrypt_data(bytearray(raw), kt, 0)
    del raw  # 释放原始数据内存
    t_dec = time.time() - t1
    print(f'[解密] 完成 ({t_dec:.1f}s, {file_size/1048576/max(t_dec,0.001):.0f} MB/s)')

    # ── 步骤4: 解析头部 ──
    if dec[:4] != b'LIBP':
        print('[错误] 解密后不是 LIBP 签名')
        return False

    count = struct.unpack_from('<I', dec, 4)[0]
    offset_count = struct.unpack_from('<I', dec, 8)[0]
    print(f'[信息] 索引条目: {count}, 偏移表条目: {offset_count}')

    # 解析索引
    index_entries = []
    for i in range(count):
        base = 0x10 + i * 0x20
        nr = dec[base:base+0x14]
        ne = nr.find(b'\x00')
        name = nr[:ne].decode('cp932', errors='replace') if ne >= 0 else nr.decode('cp932', errors='replace')
        flags = struct.unpack_from('<I', dec, base + 0x14)[0]
        idx = struct.unpack_from('<I', dec, base + 0x18)[0]
        size = struct.unpack_from('<I', dec, base + 0x1C)[0]
        index_entries.append((name, flags, idx, size))

    # 偏移表
    ot_start = 0x10 + count * 0x20
    offset_table = []
    for i in range(offset_count):
        offset_table.append(struct.unpack_from('<I', dec, ot_start + i * 4)[0])

    # 数据区起始
    raw_end = ot_start + offset_count * 4
    data_start = (raw_end + align_val - 1) & ~(align_val - 1)

    # 递归遍历目录树
    files = []
    def walk(entry_idx, cnt, path):
        for i in range(cnt):
            nm, fl, idx, sz = index_entries[entry_idx + i]
            if nm.startswith('/'): nm = nm[1:]
            full = os.path.join(path, nm) if nm else path
            if (fl & 0x30000) != 0:
                abs_off = data_start + (offset_table[idx] << 10)
                files.append((full, abs_off, sz))
            else:
                if idx > entry_idx:
                    walk(idx, sz, full)
    walk(0, 1, '')
    print(f'[信息] 文件总数: {len(files)}')

    # ── 步骤5: 从已解密缓冲区提取文件（无需再解密） ──
    os.makedirs(out_dir, exist_ok=True)
    total = len(files)
    t2 = time.time()

    # 预创建所有目录
    dir_set = set()
    for rel_path, _, _ in files:
        d = os.path.dirname(os.path.join(out_dir, rel_path.replace('/', os.sep)))
        if d not in dir_set:
            os.makedirs(d, exist_ok=True)
            dir_set.add(d)

    for i, (rel_path, abs_off, size) in enumerate(files):
        out_path = os.path.join(out_dir, rel_path.replace('/', os.sep))
        with open(out_path, 'wb') as wf:
            wf.write(dec[abs_off:abs_off + size])

        if (i + 1) % 2000 == 0 or i == total - 1:
            elapsed = time.time() - t2
            print(f'\r[写出] {i+1}/{total} ({(i+1)*100//total}%) {elapsed:.1f}s', end='', flush=True)

    print()

    # ── 清单 + 原始头部二进制 ──
    # 保存解密后的原始头部 (索引+偏移表), pack 时直接还原
    header_bin_path = os.path.join(out_dir, '_libp_header.bin')
    with open(header_bin_path, 'wb') as hf:
        hf.write(dec[:data_start])
    print(f'[完成] 原始头部: _libp_header.bin ({data_start} 字节)')

    # 偏移表索引 → 文件路径 的映射 (pack 时用来找文件数据)
    ot_to_path = {}
    for rel_path, abs_off, size in files:
        for nm, fl, idx, sz in index_entries:
            if (fl & 0x30000) != 0 and sz == size:
                file_off = data_start + (offset_table[idx] << 10)
                if file_off == abs_off:
                    ot_to_path[str(idx)] = rel_path
                    break

    manifest = {
        'tool': 'libp_tool',
        'format': 'LIBP (Malie Camellia-128)',
        'key_name': kn,
        'align': align_val,
        'count': count,
        'offset_count': offset_count,
        'data_start': data_start,
        'file_count': len(files),
        'source_size': file_size,
        'ot_to_path': ot_to_path,
        'files': [{'path': p, 'offset': o, 'size': s} for p, o, s in files],
    }
    manifest_path = os.path.join(out_dir, '_libp_manifest.json')
    with open(manifest_path, 'w', encoding='utf-8') as mf:
        json.dump(manifest, mf, ensure_ascii=False, indent=2)

    total_time = time.time() - t0
    print(f'[完成] 解包 {total} 个文件到 {out_dir}')
    print(f'[完成] 耗时: 读取 {t_read:.1f}s + 解密 {t_dec:.1f}s + 写出 {time.time()-t2:.1f}s = 总计 {total_time:.1f}s')
    print(f'[完成] 清单: _libp_manifest.json')
    return True

# ═══════════════════════════════════════════════════════════════
#  pack 命令
# ═══════════════════════════════════════════════════════════════

def cmd_pack(in_dir, out_path, key_name=None):
    manifest_path = os.path.join(in_dir, '_libp_manifest.json')
    header_bin_path = os.path.join(in_dir, '_libp_header.bin')

    if not os.path.exists(manifest_path):
        print(f'[错误] 找不到清单: {manifest_path}')
        return False
    if not os.path.exists(header_bin_path):
        print(f'[错误] 找不到原始头部: {header_bin_path}')
        print('       请用最新版工具重新 unpack。')
        return False

    with open(manifest_path, 'r', encoding='utf-8') as f:
        manifest = json.load(f)
    with open(header_bin_path, 'rb') as f:
        header = bytearray(f.read())

    kn = key_name or manifest.get('key_name', '')
    db = _load_database()
    if kn not in db:
        print(f'[错误] 密钥 "{kn}" 不在数据库中')
        return False
    item = db[kn]
    if 'RotateKey' in item:
        print('[错误] 暂不支持 CFI 加密封包')
        return False
    kt = item['Key'][:52]
    align_val = item.get('Align', manifest.get('align', 1024))

    count = manifest['count']
    ot_count = manifest['offset_count']
    data_start = manifest['data_start']
    ot_to_path = manifest.get('ot_to_path', {})
    print(f'[信息] 密钥: {kn}, 对齐: 0x{align_val:X}')
    print(f'[信息] 索引条目: {count}, 偏移表条目: {ot_count}')
    print(f'[信息] 数据区起始: 0x{data_start:X}')

    # ── 读取文件数据, 按偏移表顺序 ──
    file_data_map = {}
    for ot_idx_str, rel_path in ot_to_path.items():
        ot_idx = int(ot_idx_str)
        fp = os.path.join(in_dir, rel_path.replace('/', os.sep))
        if os.path.exists(fp):
            with open(fp, 'rb') as rf:
                file_data_map[ot_idx] = rf.read()
        else:
            print(f'[警告] 缺失: {fp}')
            file_data_map[ot_idx] = b''

    # ── 更新索引中文件的 size ──
    idx_start = 0x10
    ot_start = idx_start + count * 0x20
    for i in range(count):
        base = idx_start + i * 0x20
        fl = struct.unpack_from('<I', header, base + 0x14)[0]
        if (fl & 0x30000) != 0:
            ot_idx = struct.unpack_from('<I', header, base + 0x18)[0]
            if ot_idx in file_data_map:
                struct.pack_into('<I', header, base + 0x1C, len(file_data_map[ot_idx]))

    # ── 构建数据区, 更新偏移表 ──
    # 读取原版偏移表，按原版物理顺序写入文件
    orig_ot = []
    for i in range(ot_count):
        orig_ot.append(struct.unpack_from('<I', header, ot_start + i * 4)[0])

    # 按原版偏移值排序 → 保持文件在数据区内的物理顺序
    sorted_indices = sorted(range(ot_count), key=lambda i: orig_ot[i])

    def pad_align(buf, a):
        rem = len(buf) % a
        if rem: buf.extend(b'\x00' * (a - rem))

    data_section = bytearray()
    t0 = time.time()

    for progress_i, ot_idx in enumerate(sorted_indices):
        raw_val = len(data_section) >> 10
        struct.pack_into('<I', header, ot_start + ot_idx * 4, raw_val)
        fdata = file_data_map.get(ot_idx, b'')
        data_section.extend(fdata)
        pad_align(data_section, align_val)
        if (progress_i + 1) % 2000 == 0 or progress_i == ot_count - 1:
            print(f'\r[封包] 收集文件 {progress_i+1}/{ot_count}', end='', flush=True)
    print()

    full_data = header + data_section
    pad_align(full_data, 16)

    print(f'[加密] 总大小: {len(full_data)} 字节 ({len(full_data)/1048576:.1f} MB)')
    enc_data = encrypt_data(full_data, kt, 0)

    with open(out_path, 'wb') as wf:
        wf.write(enc_data)

    elapsed = time.time() - t0
    print(f'[完成] 封包写入: {out_path} ({len(enc_data)} 字节), 耗时 {elapsed:.1f}s')
    return True

# ═══════════════════════════════════════════════════════════════
#  list 命令
# ═══════════════════════════════════════════════════════════════

def cmd_list(arc_path, key_name=None):
    arc = LibpArchive()
    with open(arc_path, 'rb') as fh:
        if not arc.read_header(fh, key_name):
            return False

    total_size = 0
    for rel_path, abs_off, size in arc.files:
        print(f'  {size:>12,d}  0x{abs_off:08X}  {rel_path}')
        total_size += size

    print(f'\n  共 {len(arc.files)} 个文件, 总大小 {total_size:,d} 字节 ({total_size/1048576:.1f} MB)')
    return True

# ═══════════════════════════════════════════════════════════════
#  verify 命令
# ═══════════════════════════════════════════════════════════════

def cmd_verify(arc_path, tmp_dir=None, key_name=None):
    if tmp_dir is None:
        tmp_dir = os.path.splitext(arc_path)[0] + '_verify_tmp'

    print('=== 步骤 1/3: 解包 ===')
    if not cmd_unpack(arc_path, tmp_dir, key_name):
        return False

    print('\n=== 步骤 2/3: 重新封包 ===')
    rebuild_path = os.path.splitext(arc_path)[0] + '.rebuild' + os.path.splitext(arc_path)[1]
    if not cmd_pack(tmp_dir, rebuild_path, key_name):
        return False

    print('\n=== 步骤 3/3: 比对 ===')
    # 比对方式: 解包重建封包，再解包，逐文件比对内容
    # （因为封包结构可能有微小差异，直接比对整文件不现实）
    tmp_dir2 = tmp_dir + '_rebuild'
    if not cmd_unpack(rebuild_path, tmp_dir2, key_name):
        return False

    # 逐文件比对
    manifest1 = os.path.join(tmp_dir, '_libp_manifest.json')
    manifest2 = os.path.join(tmp_dir2, '_libp_manifest.json')

    with open(manifest1, 'r') as f: m1 = json.load(f)
    with open(manifest2, 'r') as f: m2 = json.load(f)

    files1 = {e['path'] for e in m1['files']}
    files2 = {e['path'] for e in m2['files']}

    if files1 != files2:
        missing = files1 - files2
        extra = files2 - files1
        if missing: print(f'[差异] 重建缺少 {len(missing)} 个文件')
        if extra: print(f'[差异] 重建多出 {len(extra)} 个文件')
        return False

    diff_count = 0
    for fe in m1['files']:
        p1 = os.path.join(tmp_dir, fe['path'].replace('/', os.sep))
        p2 = os.path.join(tmp_dir2, fe['path'].replace('/', os.sep))
        if not os.path.exists(p2):
            diff_count += 1
            continue
        with open(p1, 'rb') as f: d1 = f.read()
        with open(p2, 'rb') as f: d2 = f.read()
        if d1 != d2:
            diff_count += 1
            print(f'[差异] {fe["path"]}: {len(d1)} vs {len(d2)} 字节')

    if diff_count == 0:
        print(f'\n✅ 验证通过: {len(files1)} 个文件内容完全一致')
    else:
        print(f'\n❌ 验证失败: {diff_count} 个文件内容不一致')

    # 清理
    import shutil
    shutil.rmtree(tmp_dir, ignore_errors=True)
    shutil.rmtree(tmp_dir2, ignore_errors=True)
    if os.path.exists(rebuild_path):
        os.remove(rebuild_path)

    return diff_count == 0

# ═══════════════════════════════════════════════════════════════
# ═══════════════════════════════════════════════════════════════
#  主入口
# ═══════════════════════════════════════════════════════════════

def print_usage():
    print('Malie LIBP 封包工具 (Camellia-128 加密)')
    print()
    print('用法:')
    print('  python libp_tool.py unpack  <封包文件> [输出目录] [--key <密钥名>]')
    print('  python libp_tool.py pack    <输入目录> <输出封包> [--key <密钥名>]')
    print('  python libp_tool.py verify  <封包文件> [--key <密钥名>]')
    print('  python libp_tool.py list    <封包文件> [--key <密钥名>]')
    print()
    print('拖放: 将 .dat/.lib 文件拖放到本脚本上自动执行 unpack。')

def main():
    # ── numpy 加速: 在 main() 里导入, 避免循环导入 ──
    try:
        import libp_accel; libp_accel.patch(sys.modules[__name__])
    except ImportError:
        pass
    except Exception as e:
        print(f'[提示] numpy 加速未启用: {e}')

    args = sys.argv[1:]

    # 解析 --key 参数
    key_name = None
    if '--key' in args:
        ki = args.index('--key')
        if ki + 1 < len(args):
            key_name = args[ki + 1]
            args = args[:ki] + args[ki+2:]

    if len(args) == 0:
        print_usage()
        return

    # 拖放支持: 如果只有一个参数且是文件，自动 unpack
    if len(args) == 1 and os.path.isfile(args[0]):
        cmd_unpack(args[0], key_name=key_name)
        input('\n按回车退出...')
        return

    cmd = args[0].lower()

    if cmd == 'unpack' and len(args) >= 2:
        out = args[2] if len(args) >= 3 else None
        cmd_unpack(args[1], out, key_name)

    elif cmd == 'pack' and len(args) >= 3:
        cmd_pack(args[1], args[2], key_name)

    elif cmd == 'verify' and len(args) >= 2:
        cmd_verify(args[1], key_name=key_name)

    elif cmd == 'list' and len(args) >= 2:
        cmd_list(args[1], key_name)

    else:
        print_usage()

if __name__ == '__main__':
    main()
