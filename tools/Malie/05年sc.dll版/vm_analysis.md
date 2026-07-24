# -*- coding: utf-8 -*-
"""Malie sc.dll exec.dat VM analysis (松島枇杷子は改造人間である。).

Truth source: sc.dll IDA export (ScenarioProcessor_LoadExecImage / Step)
             + malie.exe import wrappers
Target script: system/exec.dat (1,849,786 bytes)
"""

# sispara2-era docs in older tools do NOT apply. This title uses the classic
# sc.dll Malie bytecode layout from ~2005.

## 0.1 VM type

| Item | Conclusion |
|------|------------|
| Architecture | Custom Malie script VM in sc.dll |
| Execution model | Stream opcodes + inline expression VM; control flow via label table |
| Storage | Harvard-like: IdentScope globals / linked funcs / labels / code / msg pool / estr pool |
| Endian | Little-endian |
| Host load | ScenarioProcessor_LoadExecImage (sc.dll 0x10010170) |
| Host save | ScenarioProcessor_SaveExecImage (sc.dll 0x10010330) |
| Step loop | ScenarioProcessor_Step (sc.dll 0x10011260); fetch via sub_10011240 |

## 0.2 File layout (this build)

```
# IdentScope_CreateFromFILE
u32 global_count
Global[global_count]
u32 data_size

# FunctionMan name table
u32 linked_func_count
LenString linked_func[linked_func_count]

# Labels
u32 label_count
Label[label_count]

# Expression AST pool (usually 0)
u32 expr_count
ExpressionTree[expr_count]   # kind is 1 byte, NOT u32

# Code
u32 code_size
u8  code[code_size]

# Msg string pool (OP_TEXT targets)
u32 msg_size
u8  msg[msg_size]

# Expression string pool (eval push_estr*)
u32 estr_size
u8  estr[estr_size]
```

### Global / Identifer
LenString name; VariableType type_chain; u32 flags; u32 reserved; u32 offset

### VariableType
u32 kind; if kind!=0: u32 value; VariableType next

### Label
LenString name; u32 code_offset  (relative to code[0])

### LenString
u32 nbytes; bytes[nbytes]  # includes trailing NUL

### ExpressionTree (sc.dll byte-kind)
kind = u8
- 'U' (0x55): empty/null
- 'V' (0x56) / 'X' (0x58): LenString
- 'W' (0x57): u32 int
- other: binary (left, right) recursive

## 0.3 Measured sample (松島枇杷子)

- globals=109, data_size=1320
- linked_funcs=49
- labels=273
- exprs=0
- code=899684
- msg=879692
- estr=59204
- instrs=104529, texts=12662

## 0.4 Code opcodes (ScenarioProcessor_Step)

| opcode | mnemonic     | operand | role |
|-------:|--------------|---------|------|
| 2 | eval        | u16 len + blob | run inline expression VM (sub_10011440 / sub_100072B0) |
| 3 | jmp         | u32 label index | unconditional jump |
| 4 | jz          | u32 label index | jump if last eval == 0 |
| 5 | jnz         | u32 label index | jump if last eval != 0 |
| 6 | text        | u32 msg offset | queue dialogue/msg string at msg[offset] |
| 7 | call        | u32 label index | call label (push return) |
| 8 | messageout  | none | host handler: present line / mark read |
| 9 | ret         | none | return from call |
| 10 | page       | none | host handler: page break |
| 11 | clear      | none | host handler: clear window/state |
| 12 | endtext    | none | host handler: finalize text unit (compiler also closes msg string) |
| 13 | sync       | none | host handler: rare sync/wait |

Jump/call operands are **label indices**, not byte offsets.

Typical dialogue sequence:
```
eval ...          ; optional name/voice prep
text <msg_off>    ; body (may start with 07 08 voice id entry)
page
endtext
messageout
```

### Special effect mapping
Effects are **not** separate opcodes. They are scenario labels invoked via `call`:

| label | role |
|-------|------|
| CG / CG_H / CG_BG / CGWAIT / CGFILTER | CG display / filter / wait macros |
| CHARA_SHOW / CHARA_SHOW_DRESS / CHARA_HIDE / FACE_SHOW* | character layer macros |
| CHARA_* position variants (L/R/C/LO/...) | placement helpers |
| FADEOUT / FADEIN / CLEAR_BATTLE | fade / battle clear |
| CHARFILTER | character filter |

Host-linked functions (`.linked_func`) implement runtime APIs used by eval blobs, e.g.
`System_TakeScreen`, `FrameLayer_SendMessage`, `Fade_Out`, `Sound_Load`, ...

Effect macros from MLS (`effectcommand.mls`) expand to those APIs / labels:
- `_shake2` / `_maskflash` / `_blood` → System_TakeScreen + wipe + `&ol`
- `texteffectex` → FrameLayer_SendMessage effect manager
- `ENDING_MOVIE` / `STAFFROLL` → movie layer path

## 0.5 Msg pool control bytes

| bytes | semantic |
|-------|----------|
| 07 08 + "v_xxx" + 00 | voice id entry |
| 07 09 07 06 | voiced line tail |
| 07 06 | plain line tail / mid hard wait `$k` |
| 07 01 base 0A reading 00 | ruby `$r{base\|reading}` |
| 07 04 | soft newline `$e` |
| 07 0C NN | runtime insert `$N` (rare in this title) |
| lone 06 (chunk end) | multi-chunk `%haato` |

### Voice prefix → speaker (this title)

| prefix | speaker |
|--------|---------|
| v_bw | 松島枇杷子 |
| v_ak | 星山亜紀 |
| v_as | 朝日麻紀 |
| v_mr | 森永栗子 |
| v_ks | 勝屋萌菜香 |
| v_hj | 天野霞 |
| v_mt | 松原美穂 |
| v_wo | 矢追敏美 |
| v_kt / v_bb / v_bk | 黒服系 |
| v_uc | 声 |
| v_ja/jb/jc | 女生徒１/２/３ |
| v_an | アナウンサー |

## 0.6 Inline expression VM (eval blob)

Fetched as u16 length then blob. Interpreter: sub_100072B0.

Notable ops:
- 0/1/2: relative jmp / jz / jnz (u32 target)
- 3/4: call host/local with argc
- 5/6: return true/false (end blob)
- 7/8: load/store memory
- 9/14: push u32
- 10/11/13: push pointer into estr pool (u8/u16/u32 offset)
- 18: push u8
- 19..44: arithmetic / compare / inc/dec

## 0.7 Tools

- `opcode.py` / `disassembler.py` / `assembler.py`
- default encoding cp932; special bytes `{{XX}}`
- round-trip requirement: disassemble → assemble must SHA256-match original

## 0.8 Acceptance

```
python disassembler.py exec.dat -o exec.asm.txt
python assembler.py exec.asm.txt -o exec.rebuild
# exec.rebuild == exec.dat (byte exact)
```

Expected stats on this sample:
- texts≈12662, labels=273, linked_funcs=49, instrs≈104529
- asm shows Japanese dialogue and effect labels via `call CG` etc.
