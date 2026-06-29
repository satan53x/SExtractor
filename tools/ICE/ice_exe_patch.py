#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ice_exe_patch.py  v2 — 给 エグゼキュート.exe(ICE引擎) 打补丁，字符表扩到 3000+ 字
====================================================================
v2 改为「整表搬迁」更稳的方案(修正 v1 漏补 op68 渲染器导致的错字/变色)：
  · 把【完整字符表】整体放进新加的 PE 节 .xt (静态烘焙)
  · 把全部 4 个文本渲染器的取字指令就地改写为 直接读 .xt 节
      mov dest,[esi+eax+1184h]  →  mov dest,[eax+节VA]    (丢掉 this 基址，7→6字节+1NOP，无 cave)
  · 把全部 2 字节字符判定阈值 0xF7→0xEE (0xEE~0xF6 是真实脚本从未用过的颜色码)
      索引上限 2559→4863
  · System.grp 的 0001.bin 用【内联部分(前2386条)】，仅供 載入/禁则/动态名 用，显示走 .xt 节
4 个渲染器(全部已从二进制枚举，逐字节校验)：
  sub_40A2C0(op69) sub_40DB70(op68) sub_40F390(op74) 及 0x40C8xx
EXE 无 ASLR，镜像固定 0x400000，绝对寻址安全。
用法:
  python ice_exe_patch.py エグゼキュート.exe 0001_full.bin -o エグゼキュート_patched.exe
  --verify 只核对/反汇编，不写文件。
"""
import struct, argparse

IMG=0x400000
SEC_RVA=0x75000; SEC_F=0x43000; SVA=IMG+SEC_RVA      # 节内 idx0 的绝对VA
FALIGN=0x1000; SALIGN=0x1000; PE=0xD0

# 阈值: (文件偏移 of imm8)  —— 全部 F7→EE
THRESH=[0x0A403,0x0A4A0,0x0C8BF,0x0D803,0x0DC8C,0x0DF09,0x0F3D9]
# 取字: VA -> (原7字节, 新modrm, 是否低字节)  新指令 = 8a <modrm> <disp32> [+90]
READS={
 0x40A4E0:('8a8c068411 0000',0x88,0), 0x40A4F0:('8a84068511 0000',0x80,1),  # sub_40A2C0 (off=eax)
 0x40C8F9:('8a8c2e8411 0000',0x8E,0), 0x40C904:('8a942e8511 0000',0x96,1),  # 0x40C8xx (off=esi)
 0x40DF41:('8a8c308411 0000',0x88,0), 0x40DF4D:('8a84308511 0000',0x80,1),  # sub_40DB70 (off=eax)
 0x40F412:('8a8c288411 0000',0x88,0), 0x40F41D:('8a94288511 0000',0x90,1),  # sub_40F390 #1 (off=eax)
 0x40F46A:('8a8c288411 0000',0x88,0), 0x40F475:('8a94288511 0000',0x90,1),  # sub_40F390 #2 (off=eax)
}
def _b(h): return bytes.fromhex(h.replace(' ',''))

def al(x,a): return (x+a-1)//a*a

def patch(exe, charset, out, verify=False):
    d=bytearray(open(exe,'rb').read()); full=open(charset,'rb').read()
    nent=len(full)//2
    if nent>4864:
        print('[错误] 完整表 %d 条 超过本补丁上限 4863(索引0~4863)。'%nent); return 1
    # ---- 原始字节校验(防打错版本) ----
    err=[]
    for va,(h,_,_) in READS.items():
        fo=va-IMG
        if bytes(d[fo:fo+7])!=_b(h): err.append('取字 0x%X 原字节不符:%s≠%s'%(va,d[fo:fo+7].hex(),_b(h).hex()))
    for fo in THRESH:
        if d[fo]!=0xF7: err.append('阈值 0x%X 非F7:%02X'%(fo,d[fo]))
    if struct.unpack_from('<H',d,PE+6)[0]!=4: err.append('节数!=4(可能已被改过)')
    if len(d)!=SEC_F: err.append('文件长度!=0x%X'%SEC_F)
    if err:
        print('[错误] EXE 与预期不符(请用原版未改 EXE)：'); [print('   '+e) for e in err]; return 1
    print('=== 字符表整表搬迁补丁 v2 ===')
    print('完整表 %d 条 → 整体放入新节 .xt (VA=0x%X)'%(nent,SVA))
    print('取字点(10): '+' '.join('0x%X'%v for v in READS))
    print('阈值点(7):  '+' '.join('0x%X'%(f+IMG) for f in THRESH))
    if verify:
        for va,(h,modrm,lo) in READS.items():
            ni=bytes([0x8A,modrm])+struct.pack('<I',SVA+lo)+b'\x90'
            print('  0x%X: %s → %s (mov [off+0x%X])'%(va,_b(h).hex(),ni.hex(),SVA+lo))
        return 0
    # ---- 阈值 ----
    for fo in THRESH: d[fo]=0xEE
    # ---- 取字就地改写为绝对读 .xt ----
    for va,(h,modrm,lo) in READS.items():
        fo=va-IMG
        d[fo:fo+7]=bytes([0x8A,modrm])+struct.pack('<I',SVA+lo)+b'\x90'
    # ---- 加节(整表) ----
    struct.pack_into('<H',d,PE+6,5)
    sh=PE+0x18+0xE0+4*40
    raw=al(len(full),FALIGN)
    d[sh:sh+40]=b'.xt\x00\x00\x00\x00\x00'+struct.pack('<IIII',len(full),SEC_RVA,raw,SEC_F)+struct.pack('<IIHH',0,0,0,0)+struct.pack('<I',0x40000040)
    struct.pack_into('<I',d,PE+0x50,al(SEC_RVA+raw,SALIGN))   # SizeOfImage
    assert len(d)==SEC_F
    d+=full+b'\x00'*(raw-len(full))
    open(out,'wb').write(bytes(d))
    print('\n[完成] → %s (%d 字节)'%(out,len(d)))
    print('记得：System.grp 的 0001.bin 用 build_charset 的 *_sysgrp.bin(前2386条)；inject 用完整表。')
    print('三者(System.grp内联 / EXE节 / inject)必须同一次 build_charset。')
    return 0

if __name__=='__main__':
    ap=argparse.ArgumentParser(description='ICE引擎 EXE 字符表扩充补丁 v2(整表搬迁)')
    ap.add_argument('exe'); ap.add_argument('charset'); ap.add_argument('-o','--out',default='exe_patched.exe')
    ap.add_argument('--verify',action='store_true')
    a=ap.parse_args(); raise SystemExit(patch(a.exe,a.charset,a.out,a.verify))
