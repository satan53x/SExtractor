"""SDT VM opcode and container definitions.

This module is intentionally data-oriented.  The disassembler and assembler import
it as the single source of opcode, descriptor, header, and command-table rules.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Tuple

MAGIC0 = 0x004C
MAGIC1 = 0x0046
HEADER_SIZE = 0x408
ENTRY_COUNT = 256
ENTRY_TABLE_OFFSET = 0x0008
DEFAULT_ENCODING = "cp932"

CMP_OPS = {
    0: "<",
    1: "<=",
    2: ">",
    3: ">=",
    4: "==",
    5: "!=",
}
CMP_VALUES = {v: k for k, v in CMP_OPS.items()}

DESC_NAMES = {
    1: "u8",
    2: "typed_i32",
    3: "str8",
    4: "str16",
    5: "out_local",
    6: "cmp_expr",
    7: "u8_alt",
    8: "u16",
    9: "u16_alt",
}
DESC_CODES = {v: k for k, v in DESC_NAMES.items()}

EXPR_OPS = {
    6: "EXPR_ADD",
    7: "EXPR_SUB",
    8: "EXPR_MUL",
    9: "EXPR_DIV",
    10: "EXPR_MOD",
}
EXPR_VALUES = {v: k for k, v in EXPR_OPS.items()}


@dataclass(frozen=True)
class BuiltinSpec:
    opcode: int
    mnemonic: str
    operands: Tuple[str, ...]
    length: int | str
    targets: Tuple[str, ...] = ()


@dataclass(frozen=True)
class ExternalCommand:
    opcode: int
    name: str
    descriptors: Tuple[int, ...]
    handler: str
    return_flag: int
    aux: int


BUILTIN_SPECS: Tuple[BuiltinSpec, ...] = (
    BuiltinSpec(0x0001, "END", (), 2),
    BuiltinSpec(0x0002, "MOV_LOCAL_LOCAL", ("dst", "src"), 4),
    BuiltinSpec(0x0003, "MOV_LOCAL_IMM32", ("dst", "value"), 7),
    BuiltinSpec(0x0004, "SWAP_LOCAL", ("a", "b"), 4),
    BuiltinSpec(0x0005, "RAND_LOCAL", ("dst",), 3),
    BuiltinSpec(0x0006, "JCC_LOCAL_LOCAL_SKIP", ("lhs", "cmp", "rhs", "target"), 9, ("target",)),
    BuiltinSpec(0x0007, "JCC_LOCAL_IMM32_SKIP", ("lhs", "cmp", "rhs", "target"), 12, ("target",)),
    BuiltinSpec(0x0008, "JCC_LOCAL_LOCAL_ELSE", ("lhs", "cmp", "rhs", "true", "false"), 13, ("true", "false")),
    BuiltinSpec(0x0009, "JCC_LOCAL_IMM32_ELSE", ("lhs", "cmp", "rhs", "true", "false"), 16, ("true", "false")),
    BuiltinSpec(0x000A, "LOOP_DEC_JNZ", ("counter", "target"), 7, ("target",)),
    BuiltinSpec(0x000B, "JMP", ("target",), 6, ("target",)),
    BuiltinSpec(0x000C, "INC_LOCAL", ("local",), 3),
    BuiltinSpec(0x000D, "DEC_LOCAL", ("local",), 3),
    BuiltinSpec(0x000E, "BITNOT_LOCAL", ("local",), 3),
    BuiltinSpec(0x000F, "NEG_LOCAL", ("local",), 3),
    BuiltinSpec(0x0010, "ADD_LOCAL_LOCAL", ("dst", "rhs"), 4),
    BuiltinSpec(0x0011, "ADD_LOCAL_IMM32", ("dst", "rhs"), 7),
    BuiltinSpec(0x0012, "SUB_LOCAL_LOCAL", ("dst", "rhs"), 4),
    BuiltinSpec(0x0013, "SUB_LOCAL_IMM32", ("dst", "rhs"), 7),
    BuiltinSpec(0x0014, "MUL_LOCAL_LOCAL", ("dst", "rhs"), 4),
    BuiltinSpec(0x0015, "MUL_LOCAL_IMM32", ("dst", "rhs"), 7),
    BuiltinSpec(0x0016, "DIV_LOCAL_LOCAL", ("dst", "rhs"), 4),
    BuiltinSpec(0x0017, "DIV_LOCAL_IMM32", ("dst", "rhs"), 7),
    BuiltinSpec(0x0018, "MOD_LOCAL_LOCAL", ("dst", "rhs"), 4),
    BuiltinSpec(0x0019, "MOD_LOCAL_IMM32", ("dst", "rhs"), 7),
    BuiltinSpec(0x001A, "AND_LOCAL_LOCAL", ("dst", "rhs"), 4),
    BuiltinSpec(0x001B, "AND_LOCAL_IMM32", ("dst", "rhs"), 7),
    BuiltinSpec(0x001C, "OR_LOCAL_LOCAL", ("dst", "rhs"), 4),
    BuiltinSpec(0x001D, "OR_LOCAL_IMM32", ("dst", "rhs"), 7),
    BuiltinSpec(0x001E, "XOR_LOCAL_LOCAL", ("dst", "rhs"), 4),
    BuiltinSpec(0x001F, "XOR_LOCAL_IMM32", ("dst", "rhs"), 7),
    BuiltinSpec(0x0020, "EVAL_EXPR", ("dst", "expr"), "expr"),
    BuiltinSpec(0x0021, "PUSH_LOCALS", (), 2),
    BuiltinSpec(0x0022, "POP_LOCALS", (), 2),
    BuiltinSpec(0x0023, "CALL_ENTRY", ("entry",), 3),
    BuiltinSpec(0x0024, "RET", (), 2),
    BuiltinSpec(0x0025, "WAIT_FRAMES", ("frames",), 4),
    BuiltinSpec(0x0026, "WAIT_TIME_MS", ("milliseconds",), 4),
    BuiltinSpec(0x0027, "YIELD_NOP", (), 2),
    BuiltinSpec(0x0028, "LOAD_SDT", ("filename",), "load_sdt"),
)

BUILTINS_BY_OPCODE: Dict[int, BuiltinSpec] = {spec.opcode: spec for spec in BUILTIN_SPECS}
BUILTINS_BY_NAME: Dict[str, BuiltinSpec] = {spec.mnemonic: spec for spec in BUILTIN_SPECS}


EXTERNAL_COMMAND_DATA: Tuple[Tuple[int, str, Tuple[int, ...], str, int, int], ...] = (
    (0x0040, 'LoadMap', (2, 2), 'sub_411220', 1, 0),
    (0x0041, 'ReleaseMap', (), 'sub_411250', 1, 0),
    (0x0042, 'SetMapObj', (2, 2, 2, 2, 2, 2, 2), 'sub_411270', 1, 2),
    (0x0043, 'SetMapObjEx', (2, 3, 3, 2, 2, 2, 2), 'sub_4112E0', 1, 2),
    (0x0044, 'SetMapObjNoLoad', (2, 2, 2, 2, 2, 2, 2), 'sub_411340', 1, 2),
    (0x0045, 'SetMapObjRev', (2, 2), 'sub_4113B0', 1, 0),
    (0x0046, 'SetMapObjLayer', (2, 2), 'sub_4113E0', 1, 0),
    (0x0047, 'SetMapObjMove', (2, 2, 2, 2, 2), 'sub_411410', 1, 0),
    (0x0048, 'SetMapObjZoom', (2, 2), 'sub_411450', 1, 0),
    (0x0049, 'SetMapObjParam', (2, 2, 2), 'sub_411480', 1, 0),
    (0x004A, 'PlayMapObj', (2, 2, 2, 2), 'sub_4114B0', 1, 0),
    (0x004B, 'ResetMapObj', (2, 2), 'sub_4114F0', 1, 1),
    (0x004C, 'SetBrightMap', (2, 2, 2, 2, 2), 'sub_411530', 1, 2),
    (0x004D, 'SetScrollMap', (2, 2, 2, 2, 2), 'sub_411590', 1, 3),
    (0x004E, 'SetScrollMapChar', (2, 2, 2, 2), 'sub_411600', 1, 3),
    (0x004F, 'WaitMap', (2,), 'sub_411660', 0, 1),
    (0x0050, 'StartBattle', (2, 2, 2, 2, 2, 2, 2), 'sub_4116B0', 1, 5),
    (0x0051, 'WaitBattleEnd', (), 'sub_411750', 0, 0),
    (0x0052, 'WaitBattleEndEx', (5,), 'sub_411790', 0, 0),
    (0x0053, 'SetMapCharPlayer', (2, 2, 2, 2, 2), 'sub_4117E0', 1, 1),
    (0x0054, 'SetMapChar', (2, 2, 2, 2, 2, 2, 2, 2, 2), 'sub_411830', 1, 3),
    (0x0055, 'SetMapCharEngun', (2, 2, 2, 2), 'sub_4118E0', 1, 1),
    (0x0056, 'SetMapCharItem', (2, 2, 2), 'sub_411920', 1, 0),
    (0x0057, 'SetMapCharThink', (2, 2, 2, 2, 2, 2), 'sub_411950', 1, 3),
    (0x0058, 'ResetMapChar', (2,), 'sub_4119A0', 1, 0),
    (0x0059, 'ResetMapCharAll', (), 'sub_4119D0', 1, 0),
    (0x005A, 'SetMapCharEvent', (2, 2, 2, 2), 'sub_4119F0', 1, 2),
    (0x005B, 'WaitMapCharEvent', (2,), 'sub_411A40', 0, 0),
    (0x005C, 'SetMapCharMove', (2, 2, 2, 2, 2, 2), 'sub_411A70', 1, 3),
    (0x005D, 'WaitMapCharMove', (2,), 'sub_411AE0', 0, 0),
    (0x005E, 'SetMapCharDisp', (2, 2), 'sub_411B10', 1, 0),
    (0x005F, 'B', (2, 2, 2, 2, 2, 2, 2, 2, 2), 'sub_411BF0', 0, 7),
    (0x0060, 'BT', (2, 2, 2, 2, 2, 2, 2, 2, 2), 'nullsub_1', 0, 7),
    (0x0061, 'BC', (2, 2, 2, 2, 2, 2, 2, 2, 2), 'sub_411CF0', 0, 7),
    (0x0062, 'BCT', (2, 2, 2, 2, 2, 2, 2, 2, 2), 'nullsub_2', 0, 7),
    (0x0063, 'V', (2, 2, 2, 2, 2, 2, 2, 2, 2), 'sub_411DF0', 0, 7),
    (0x0064, 'VT', (2, 2, 2, 2, 2, 2, 2, 2, 2), 'nullsub_3', 0, 7),
    (0x0065, 'H', (2, 2, 2, 2, 2, 2, 2, 2, 2), 'sub_411EF0', 0, 7),
    (0x0066, 'HT', (2, 2, 2, 2, 2, 2, 2, 2, 2), 'nullsub_4', 0, 7),
    (0x0067, 'S', (2, 2, 2, 2), 'nullsub_5', 0, 0),
    (0x0068, 'Z', (2, 2, 2, 2, 2, 2), 'nullsub_6', 0, 0),
    (0x0069, 'FI', (), 'default/no explicit handler', 0, 0),
    (0x006A, 'FIF', (2,), 'default/no explicit handler', 0, 0),
    (0x006B, 'FO', (), 'default/no explicit handler', 0, 0),
    (0x006C, 'FOF', (2,), 'default/no explicit handler', 0, 0),
    (0x006D, 'FB', (2, 2, 2, 2), 'default/no explicit handler', 0, 0),
    (0x006E, 'PFI', (2, 2, 2, 2, 2, 2), 'default/no explicit handler', 0, 2),
    (0x006F, 'PFO', (2, 2, 2, 2, 2, 2), 'default/no explicit handler', 0, 2),
    (0x0070, 'PWI', (2, 2, 2, 2, 2, 2), 'default/no explicit handler', 0, 2),
    (0x0071, 'PWO', (2, 2, 2, 2, 2, 2), 'default/no explicit handler', 0, 2),
    (0x0072, 'Q', (2, 2, 2, 2, 2), 'sub_412030', 0, 0),
    (0x0073, 'F', (2, 2, 2, 2, 2), 'default/no explicit handler', 0, 0),
    (0x0074, 'C', (2, 2, 2, 2, 2, 2, 2, 2), 'sub_412090', 0, 7),
    (0x0075, 'CR', (2, 2, 2), 'sub_412150', 0, 2),
    (0x0076, 'CP', (2, 2, 2), 'sub_4121F0', 0, 1),
    (0x0077, 'CL', (2, 2, 2), 'sub_412260', 0, 1),
    (0x0078, 'CY', (2, 2), 'sub_4122D0', 0, 0),
    (0x0079, 'CB', (2, 2, 2, 2, 2), 'sub_412320', 0, 0),
    (0x007A, 'CA', (2, 2, 2), 'sub_412390', 0, 0),
    (0x007B, 'CW', (2,), 'sub_4123F0', 0, 0),
    (0x007C, 'W', (2, 2), 'sub_412430', 1, 2),
    (0x007D, 'WR', (2, 2), 'sub_4124B0', 1, 2),
    (0x007E, 'WN', (3,), 'sub_412510', 1, 1),
    (0x007F, 'KW', (2,), 'default/no explicit handler', 1, 0),
    (0x0080, 'K', (), 'sub_412530', 0, 0),
    (0x0081, 'M', (2, 2, 2, 2), 'sub_412550', 1, 3),
    (0x0082, 'MS', (2,), 'sub_4125C0', 1, 1),
    (0x0083, 'MP', (2,), 'sub_4125F0', 1, 0),
    (0x0084, 'MV', (2, 2), 'sub_412610', 1, 0),
    (0x0085, 'MW', (), 'sub_412640', 0, 0),
    (0x0086, 'SE', (2, 2), 'sub_412680', 1, 1),
    (0x0087, 'SEP', (2, 2, 2, 2, 2), 'sub_4126C0', 1, 3),
    (0x0088, 'SES', (2, 2), 'sub_412730', 1, 1),
    (0x0089, 'SEW', (2,), 'sub_412790', 0, 0),
    (0x008A, 'SEV', (2, 2, 2), 'sub_412760', 1, 0),
    (0x008B, 'SEVW', (2,), 'sub_4127C0', 0, 0),
    (0x008C, 'VV', (2, 2, 2, 2, 9), 'sub_4127F0', 1, 5),
    (0x008D, 'VA', (2, 2, 2, 2, 9), 'sub_412860', 1, 5),
    (0x008E, 'VB', (2, 2, 2, 2, 9), 'sub_4128D0', 1, 5),
    (0x008F, 'VC', (2, 2, 2, 2, 9), 'sub_412940', 1, 5),
    (0x0090, 'VX', (2, 2, 2, 2, 2, 2), 'sub_4129B0', 1, 3),
    (0x0091, 'VW', (), 'sub_412A20', 0, 1),
    (0x0092, 'VS', (2, 2), 'sub_412A50', 1, 1),
    (0x0093, 'VI', (9, 2), 'sub_412AB0', 1, 2),
    (0x0094, 'R', (2, 2, 2), 'default/no explicit handler', 0, 0),
    (0x0095, 'RC', (2, 2, 2), 'default/no explicit handler', 0, 0),
    (0x0096, 'RR', (), 'default/no explicit handler', 0, 0),
    (0x0097, 'LF', (2, 2, 2), 'default/no explicit handler', 1, 0),
    (0x0098, 'WE', (2, 2, 2), 'default/no explicit handler', 0, 1),
    (0x0099, 'WER', (), 'default/no explicit handler', 1, 0),
    (0x009A, 'SetFlag', (2, 2), 'sub_410FB0', 1, 0),
    (0x009B, 'GetFlag', (2, 5), 'sub_410FE0', 1, 0),
    (0x009C, 'SetGameFlag', (2, 2), 'sub_411010', 1, 0),
    (0x009D, 'GetGameFlag', (2, 5), 'sub_411040', 1, 0),
    (0x009E, 'LoadScript', (3,), 'sub_411070', 0, 0),
    (0x009F, 'GameEnd', (2,), 'default/no explicit handler', 0, 1),
    (0x00A0, 'CallFunc', (2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2), 'sub_4110F0', 1, 14),
    (0x00A1, 'SetTimeMode', (2,), 'sub_411160', 1, 1),
    (0x00A2, 'SetChromaMode', (2, 2), 'sub_411190', 1, 2),
    (0x00A3, 'SetEffctMode', (3, 2), 'sub_4111E0', 1, 2),
    (0x00A4, 'SetMessage', (2, 3, 8), 'default/no explicit handler', 0, 0),
    (0x00A5, 'SetMessage2', (4, 7, 8), 'sub_411B40', 0, 0),
    (0x00A6, 'SetMessageEx', (2, 2, 3, 2, 8), 'default/no explicit handler', 0, 0),
    (0x00A7, 'SetChipMessage', (3, 8), 'default/no explicit handler', 1, 0),
    (0x00A8, 'AddMessage', (2, 3), 'default/no explicit handler', 0, 0),
    (0x00A9, 'AddMessage2', (4, 7), 'sub_411BA0', 0, 0),
    (0x00AA, 'SetMessageWait', (2,), 'default/no explicit handler', 0, 0),
    (0x00AB, 'ResetMessage', (), 'default/no explicit handler', 0, 0),
    (0x00AC, 'WaitKey', (), 'default/no explicit handler', 0, 0),
    (0x00AD, 'SetSelectMes', (3, 2, 2), 'sub_412C00', 1, 3),
    (0x00AE, 'SetSelectMesEx', (3, 3, 2, 2), 'default/no explicit handler', 1, 2),
    (0x00AF, 'SetSelect', (5, 2), 'sub_412C50', 0, 1),
    (0x00B0, 'SetSelectEx', (), 'default/no explicit handler', 0, 0),
    (0x00B1, 'PlayBgm', (2, 2), 'default/no explicit handler', 1, 0),
    (0x00B2, 'PlayBgmEx', (2, 2, 2, 2, 2), 'default/no explicit handler', 1, 0),
    (0x00B3, 'StopBgm', (2,), 'default/no explicit handler', 1, 0),
    (0x00B4, 'StopBgmEx', (2, 2), 'default/no explicit handler', 1, 0),
    (0x00B5, 'SetVolumeBgm', (2, 2), 'default/no explicit handler', 1, 0),
    (0x00B6, 'SetVolumeBgmEx', (2, 2, 2), 'default/no explicit handler', 1, 0),
    (0x00B7, 'PlaySe', (2,), 'default/no explicit handler', 1, 0),
    (0x00B8, 'PlaySeEx', (2, 2, 2, 2, 2), 'default/no explicit handler', 1, 0),
    (0x00B9, 'StopSeEx', (2, 2), 'default/no explicit handler', 1, 0),
    (0x00BA, 'SetVolumeSe', (2, 2, 2), 'default/no explicit handler', 1, 0),
    (0x00BB, 'SetWeather', (2, 2, 2, 2, 2), 'sub_412B10', 1, 1),
    (0x00BC, 'ChangeWeather', (2, 2, 2, 2), 'sub_412B60', 1, 1),
    (0x00BD, 'ResetWeather', (), 'sub_412BC0', 0, 0),
    (0x00BE, 'SetLensFrea', (2, 2, 2), 'default/no explicit handler', 1, 0),
    (0x00BF, 'SetWavEffect', (2, 2, 2), 'default/no explicit handler', 0, 3),
    (0x00C0, 'ResetWavEffect', (), 'default/no explicit handler', 1, 0),
    (0x00C1, 'SetWarp', (2, 2, 2, 2, 2, 2, 2, 2), 'default/no explicit handler', 0, 8),
    (0x00C2, 'ResetWarp', (2,), 'default/no explicit handler', 0, 1),
    (0x00C3, 'WaitFrame', (2,), 'sub_412CB0', 0, 0),
    (0x00C4, 'SetBmp', (2, 3, 2, 2, 2, 3, 2, 3), 'sub_412D00', 1, 5),
    (0x00C5, 'SetBmpEx', (2, 2, 3, 2, 2, 2, 3), 'default/no explicit handler', 1, 2),
    (0x00C6, 'SetBmp4Bmp', (2, 2, 2, 2), 'default/no explicit handler', 1, 0),
    (0x00C7, 'SetBmpPrim', (2, 2, 2, 2), 'default/no explicit handler', 1, 0),
    (0x00C8, 'ResetBmp', (2,), 'sub_412D80', 1, 0),
    (0x00C9, 'ResetBmpAll', (), 'sub_412DA0', 1, 0),
    (0x00CA, 'SetBmpAnime', (2, 3, 2, 3, 2, 3), 'sub_412DD0', 1, 3),
    (0x00CB, 'ResetBmpAnime', (2,), 'sub_412E70', 1, 0),
    (0x00CC, 'WaitBmpAnime', (2,), 'sub_412E40', 0, 0),
    (0x00CD, 'SetBmpAnimePlay', (2, 2, 2, 2), 'sub_412E90', 1, 3),
    (0x00CE, 'SetAvi', (2, 3, 2), 'sub_413170', 1, 0),
    (0x00CF, 'ResetAvi', (2,), 'default/no explicit handler', 1, 0),
    (0x00D0, 'WaitAvi', (2,), 'sub_4131A0', 0, 0),
    (0x00D1, 'SetAviFull', (2,), 'sub_4131D0', 1, 1),
    (0x00D2, 'WaitAviFull', (), 'sub_413200', 0, 0),
    (0x00D3, 'SetBmpDisp', (2, 2), 'sub_412EF0', 1, 0),
    (0x00D4, 'SetBmpLayer', (2, 2), 'sub_412F20', 1, 0),
    (0x00D5, 'SetBmpParam', (2, 2, 2), 'sub_412F50', 1, 1),
    (0x00D6, 'SetBmpRevParam', (2, 2), 'sub_412F90', 1, 0),
    (0x00D7, 'SetBmpBright', (2, 2, 2, 2), 'sub_412FC0', 1, 2),
    (0x00D8, 'SetBmpMove', (2, 2, 2), 'sub_413030', 1, 0),
    (0x00D9, 'SetBmpPos', (2, 2, 2, 2, 2, 2, 2), 'sub_413060', 1, 0),
    (0x00DA, 'SetBmpZoom', (2, 2, 2, 2, 2), 'sub_4130B0', 1, 0),
    (0x00DB, 'SetBmpZoom2', (2, 2, 2, 2), 'sub_4130F0', 1, 0),
    (0x00DC, 'SetTitle', (), 'default/no explicit handler', 0, 0),
    (0x00DD, 'SetEnding', (2, 2), 'default/no explicit handler', 0, 0),
    (0x00DE, 'NextGameStep', (2, 3), 'sub_411130', 1, 1),
    (0x00DF, 'SetDemoFlag', (2, 2), 'sub_413220', 1, 0),
    (0x00E0, 'SetSceneNo', (2,), 'default/no explicit handler', 1, 0),
    (0x00E1, 'SetEndingNo', (2,), 'default/no explicit handler', 1, 0),
    (0x00E2, 'SetReplayNo', (2,), 'default/no explicit handler', 1, 0),
    (0x00E3, 'SetSoundEvent', (2, 2, 2, 2, 2, 2, 2), 'default/no explicit handler', 1, 5),
    (0x00E4, 'SetSoundEventVolume', (2, 2, 2, 2), 'default/no explicit handler', 1, 2),
    (0x00E5, 'SetPotaPota', (2, 2, 2), 'default/no explicit handler', 0, 3),
    (0x00E6, 'GetTime', (5,), 'sub_413250', 1, 0),
    (0x00E7, 'WaitTime', (2,), 'sub_413270', 0, 0),
    (0x00E8, 'SetTextFormat', (2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2), 'default/no explicit handler', 1, 10),
    (0x00E9, 'SetTextSync', (2, 2), 'default/no explicit handler', 1, 0),
    (0x00EA, 'SetText', (2, 3), 'default/no explicit handler', 0, 0),
    (0x00EB, 'SetTextEx', (3,), 'default/no explicit handler', 0, 0),
    (0x00EC, 'ResetText', (2,), 'default/no explicit handler', 1, 0),
    (0x00ED, 'WaitText', (2,), 'default/no explicit handler', 0, 0),
    (0x00EE, 'ResetTextAll', (), 'default/no explicit handler', 1, 0),
    (0x00EF, 'SetDemoFadeFlag', (2,), 'default/no explicit handler', 1, 0),
    (0x00F0, 'Mov2', (5, 2), 'sub_413290', 1, 0),
    (0x00F1, 'Sin', (5, 2, 2), 'sub_4132B0', 1, 1),
    (0x00F2, 'Cos', (5, 2, 2), 'sub_413320', 1, 1),
    (0x00F3, 'Abs', (5, 2), 'sub_413390', 1, 0),
    (0x00F4, 'TestSetParam', (2,), 'sub_4133F0', 1, 0),
    (0x00F5, 'SetPartyChar', (2, 2, 2, 2), 'sub_413410', 1, 2),
    (0x00F6, 'GetPartyLevel', (2, 5), 'sub_413460', 1, 0),
    (0x00F7, 'SetMapBox', (2, 2, 2, 2, 2), 'nullsub_7', 1, 1),
    (0x00F8, 'SetCutCut', (2,), 'default/no explicit handler', 1, 0),
    (0x00F9, 'SetNoise', (2, 2, 2), 'default/no explicit handler', 0, 2),
    (0x00FA, 'T', (2, 2), 'default/no explicit handler', 1, 1),
    (0x00FB, 'SetUsoErr', (), 'default/no explicit handler', 1, 0),
    (0x00FC, 'LoadScriptNum', (2,), 'sub_4110B0', 0, 0),
    (0x00FD, 'SetRipple', (2, 2, 2), 'default/no explicit handler', 1, 0),
    (0x00FE, 'SetRippleSet', (2, 2, 2), 'default/no explicit handler', 1, 1),
    (0x00FF, 'WaitRipple', (), 'default/no explicit handler', 0, 0),
    (0x0100, 'SetRippleLost', (), 'default/no explicit handler', 0, 0),
    (0x0101, 'MLW', (), 'sub_412660', 0, 0),
    (0x0102, 'GetItem', (2, 2), 'sub_4134A0', 1, 0),
    (0x0103, 'CheckItem', (2, 5), 'sub_4134D0', 1, 0),
    (0x0104, 'SetMapCharName', (2, 3), 'sub_4118B0', 1, 0),
    (0x0105, 'SetBmpRoll', (2, 2, 2, 2), 'sub_413130', 1, 0),
    (0x0106, 'SetMovie', (), 'default/no explicit handler', 0, 0),
    (0x0107, 'DebugBox', (2, 3), 'sub_4133C0', 1, 1),
    (0x0108, 'VHFlag', (2, 2), 'sub_411FF0', 1, 0),
)

EXTERNALS_BY_OPCODE: Dict[int, ExternalCommand] = {
    opcode: ExternalCommand(opcode, name, descriptors, handler, return_flag, aux)
    for opcode, name, descriptors, handler, return_flag, aux in EXTERNAL_COMMAND_DATA
}
EXTERNALS_BY_NAME: Dict[str, ExternalCommand] = {cmd.name: cmd for cmd in EXTERNALS_BY_OPCODE.values()}
ALL_MNEMONICS = {**BUILTINS_BY_NAME, **EXTERNALS_BY_NAME}


def descriptor_name(code: int) -> str:
    try:
        return DESC_NAMES[code]
    except KeyError as exc:
        raise ValueError(f"unknown descriptor code {code}") from exc


def is_external_opcode(opcode: int) -> bool:
    return opcode in EXTERNALS_BY_OPCODE


def known_opcode(opcode: int) -> bool:
    return opcode in BUILTINS_BY_OPCODE or opcode in EXTERNALS_BY_OPCODE
