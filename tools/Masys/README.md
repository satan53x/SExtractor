# MEG tools
由`Steins;Gate`提供

## 1.py (string XOR dump/import)
```bat
python 1.py key Megu.exe
python 1.py dump Megu.exe meg out
python 1.py import Megu.exe new out
python 1.py Megu.exe new out
```

Key is extracted by code signature from the exe (not fixed offset).
Only expression atom 0x62 strings are XOR-crypted; header and bytecode stay plain.

## Version note
- Ver ~150 (game1): body ends on final RET (0xFF).
- Ver ~300 (game2): body appends 8-byte footer after final RET:
  00 | u32 | u8 | BF | 01 (often 3F BF 01).
  1.py / disassembler skip this footer; assembler restores via .meg_footer_hex.

## Full disasm after dump
```bat
python 1.py dump Megu.exe meg meg_dec
python disassembler.py meg_dec txt
python assembler.py txt meg_plain
python 1.py import Megu.exe meg_plain meg_out
```

Each STR("...") is shown on its own line; assembler rejoins indented continuations.
FE-prefixed opcodes disassemble as EXT_xx.
