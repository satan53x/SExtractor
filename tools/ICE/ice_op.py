#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ice_op.py — ICE Soft (エグゼキュート/ICE 引擎) 脚本 VM 底层模块
====================================================================
逆向自 エグゼキュート.exe（反编译三件套）。提供：
  · System.grp entry1 字符表加载（index<->SJIS<->cp932）
  · 83 个 opcode 的指令长度表 L（linear-sweep 在 207/207 脚本上完美对齐）
  · 反汇编 disasm()
  · 文本 token 编解码（已在 52451/52451 条真实文本上双射验证）
  · 相对跳转操作数规格 JUMPS（注入时重定位用）

文本编码（消息流，由 sub_40D680/渲染器逆出）：
  单字节 b<0xE7 或 b==0xE9         → 直接字符索引 b
  0xF7..0xFF + data                → 2 字节字符：idx = data + (256-prefix)<<8  （覆盖 256..2559）
  0xEA / 0xEB + 1 参数字节          → 换行/分页控制（参数常为 0x44）
  0xEC                             → 文本结束
  0xED（其后非0xED）                → 颜色/高亮起，单字节；0xED 0xED → 复位（2字节）
  0xEE..0xF6                       → 颜色控制（单字节）
  0xE7 / 0xE8                      → 自动名字 / 变量 插入（单字节）
"""
import struct, os

# ---------------- 字符表 ----------------
def load_charset(path):
    d=open(path,'rb').read()
    return [struct.unpack_from('>H',d,i)[0] for i in range(0,len(d)-1,2)]

class Charset:
    def __init__(self, path):
        self.idx2sjis=load_charset(path)
        self.sjis2enc={}
        for i,c in enumerate(self.idx2sjis):
            if self._encodable(i):
                self.sjis2enc.setdefault(c,i)
    @staticmethod
    def _encodable(idx):
        return idx<0xE7 or idx==0xE9 or 256<=idx<=4863
    def idx_char(self, idx):
        if idx>=len(self.idx2sjis): return None
        c=self.idx2sjis[idx]
        try: return bytes([c>>8,c&0xFF]).decode('cp932')
        except: return None
    def char_idx(self, ch):
        b=ch.encode('cp932')
        sj=b[0] if len(b)==1 else (b[0]<<8)|b[1]
        return self.sjis2enc.get(sj)
    @staticmethod
    def encode_idx(idx):
        if idx<0xE7 or idx==0xE9: return bytes([idx])
        if 256<=idx<=4863:                       # 2字节: 阈值0xF7→0xEE(需EXE补丁支持>2559)
            return bytes([256-(idx>>8), idx&0xFF])
        raise ValueError('索引 %d 不可编码'%idx)

# ---------------- opcode 指令长度表（207/207 验证） ----------------
L={0:1,1:3,2:4,3:3,4:1,5:3,6:3,7:5,8:5,9:4,10:3,11:3,12:5,13:5,14:5,15:5,16:5,17:5,18:5,19:5,
20:4,21:3,22:3,23:1,24:3,25:2,26:2,27:3,28:1,29:2,30:1,31:9,32:3,33:1,34:1,35:3,36:4,37:4,38:4,
39:3,40:4,41:7,42:2,43:4,44:1,45:None,46:5,47:3,48:3,49:3,50:1,51:2,52:1,53:3,54:4,55:4,56:3,
57:4,58:4,59:5,60:5,61:2,62:4,63:2,64:2,65:2,66:1,67:1,73:4,74:0,75:1,76:1,77:1,78:2,79:8,80:None,81:2,82:4}

MSG_OPS={68,69}; NAME_OPS={71,72}; IMM_OP=74     # 文本承载 opcode
# 相对跳转：op -> [(disp字段相对entryPC偏移, 基址)]；目标(偏移) = entryPC + 基址 + disp(int16)
JUMPS={1:[(0,2)],2:[(1,3)],3:[(0,2)],7:[(2,4)],8:[(2,4)],
       12:[(2,4)],13:[(2,4)],14:[(2,4)],15:[(2,4)],16:[(2,4)],17:[(2,4)],18:[(2,4)],19:[(2,4)],
       27:[(0,2)],73:[(1,3)],82:[(1,3)],31:[(0,2),(2,4),(4,6),(6,8)]}

def _scan_text(buf,pc,terms):
    i=pc;n=len(buf)
    while i<n:
        b=buf[i]
        if b in terms: return i-pc+1
        i+= 2 if b>=0xF7 else 1
    return i-pc

def insn_len(buf,pc):
    op=buf[pc]
    if op==68: return 1+_scan_text(buf,pc+1,(0xEC,))
    if op==69: return 1+4+_scan_text(buf,pc+5,(0xEC,))
    if op==70: return 1+1+_scan_text(buf,pc+2,(0xEA,0xEB,0xEC))
    if op==74: return 1+_scan_text(buf,pc+1,(0xEC,))
    if op==71: return 1+2+_scan_text(buf,pc+3,(0xEC,))
    if op==72: return 1+1+_scan_text(buf,pc+2,(0xEC,))
    l=L.get(op)
    if l is None: raise ValueError('未知 opcode %d @ 0x%X'%(op,pc))
    return l

def disasm(buf):
    pc=0;n=len(buf);out=[]
    while pc<n:
        ln=insn_len(buf,pc)
        out.append((pc,buf[pc],ln)); pc+=ln
    return out

# 文本承载 opcode 的「正文起点」相对指令起点的偏移
def text_start(op):
    return {68:1,74:1,69:5,71:3,72:2,70:2}[op]

# ---------------- token 编解码 + 内联标签 ----------------
# 内联标签（出现在 message 字符串里，翻译时需原样保留）：
#   {C}=高亮起(0xED)  {/C}=复位(0xED 0xED)  {C2}..{C9}=颜色(0xEE..0xF6)
#   {NAME}=自动名字(0xE7)  {VAR}=变量(0xE8)
def tokenize(buf,pc,end):
    """返回 (tokens, breaks)。tokens 不含换行；breaks=[(marker,param),...] 按出现顺序，
    用于把多行重新拼接。换行把 tokens 切成多段：返回 segments(list of token-list)。"""
    segs=[[]]; breaks=[]; i=pc
    while i<end:
        b=buf[i]
        if b==0xEC: break
        if b in (0xEA,0xEB):
            breaks.append((b,buf[i+1])); segs.append([]); i+=2; continue
        if b==0xED and i+1<end and buf[i+1]==0xED:
            segs[-1].append(('creset',)); i+=2; continue
        if 0xED<=b<=0xF6:
            segs[-1].append(('col',b)); i+=1; continue
        if b in (0xE7,0xE8):
            segs[-1].append(('ins',b)); i+=1; continue
        if b>=0xF7:
            segs[-1].append(('ch',buf[i+1]+((256-b)<<8))); i+=2; continue
        segs[-1].append(('ch',b)); i+=1
    return segs,breaks

def seg_to_str(seg, cs):
    out=[]
    for t in seg:
        if t[0]=='ch':
            ch=cs.idx_char(t[1]); out.append(ch if ch is not None else '\ufffd')
        elif t[0]=='creset': out.append('{/C}')
        elif t[0]=='col':
            out.append('{C}' if t[1]==0xED else '{C%d}'%(t[1]-0xED+1))
        elif t[0]=='ins': out.append('{NAME}' if t[1]==0xE7 else '{VAR}')
    return ''.join(out)

import re as _re
_TAG=_re.compile(r'\{/C\}|\{C\d?\}|\{NAME\}|\{VAR\}')
def str_to_bytes(s, cs):
    """把（翻译后的）一行文本编码为 token 字节（不含换行/EC）。"""
    out=bytearray(); pos=0
    for m in _TAG.finditer(s):
        # 标签前的普通文字
        for ch in s[pos:m.start()]:
            idx=cs.char_idx(ch)
            if idx is None: raise ValueError('字符 %r(U+%04X) 不在字符表中，无法编码'%(ch,ord(ch)))
            out+=cs.encode_idx(idx)
        tag=m.group()
        if tag=='{/C}': out+=bytes([0xED,0xED])
        elif tag=='{C}': out.append(0xED)
        elif tag.startswith('{C'): out.append(0xED+int(tag[2:-1])-1)
        elif tag=='{NAME}': out.append(0xE7)
        elif tag=='{VAR}': out.append(0xE8)
        pos=m.end()
    for ch in s[pos:]:
        idx=cs.char_idx(ch)
        if idx is None: raise ValueError('字符 %r(U+%04X) 不在字符表中，无法编码'%(ch,ord(ch)))
        out+=cs.encode_idx(idx)
    return bytes(out)

# ==================================================================
# 行级解析（v2）：把文本指令解析为 行结构，首尾控制符可分离进 meta
#   op68/op74: [op]<text…EC>
#   op69     : [69][x0:u16][y0:u16] [EB(清屏)]? 行 (EB 45 x:u16 y:u16 重定位 行)* EC
#   op71     : [71][count][param]<name…EC>     op72 不在此处理(原样保留)
# ==================================================================
def _u16(b,o): return b[o]|(b[o+1]<<8)
_EDGE={'col','creset','ins'}
def _tok_tag(t):
    if t[0]=='creset': return '{/C}'
    if t[0]=='col': return '{C}' if t[1]==0xED else '{C%d}'%(t[1]-0xED+1)
    if t[0]=='ins': return '{NAME}' if t[1]==0xE7 else '{VAR}'
    return ''

def parse_unit(buf,pc,op,ln,cs):
    end=pc+ln
    unit={'op':op,'off':pc,'head':None,'lead_clear':False,'lines':[],'empty':True}
    if op==69:
        unit['head']=[_u16(buf,pc+1),_u16(buf,pc+3)]; i=pc+5
        if i<end and buf[i]==0xEC: return unit
        if i<end and buf[i]==0xEB: unit['lead_clear']=True; i+=1
    elif op==71: unit['head']=[buf[pc+1],buf[pc+2]]; i=pc+3
    elif op==72: unit['head']=[buf[pc+1]]; i=pc+2
    else: i=pc+1
    def read_line(i):
        toks=[]
        while i<end:
            b=buf[i]
            if b==0xEC: return toks,i,('end',)
            if op==69 and b==0xEB and i+1<end and buf[i+1]==0x45:
                return toks,i+6,('repos',_u16(buf,i+2),_u16(buf,i+4))
            if op!=69 and b in (0xEA,0xEB): return toks,i+2,('brk',b,buf[i+1])
            if b==0xED and i+1<end and buf[i+1]==0xED: toks.append(('creset',)); i+=2; continue
            if 0xED<=b<=0xF6: toks.append(('col',b)); i+=1; continue
            if b in (0xE7,0xE8): toks.append(('ins',b)); i+=1; continue
            if b>=0xF7: toks.append(('ch',buf[i+1]+((256-b)<<8))); i+=2; continue
            toks.append(('ch',b)); i+=1
        return toks,i,('end',)
    pend=None; term=('end',)
    while i<end and buf[i]!=0xEC:
        toks,i,term=read_line(i)
        a=0; b=len(toks)
        while a<b and toks[a][0] in _EDGE: a+=1
        while b>a and toks[b-1][0] in _EDGE: b-=1
        lead=''.join(_tok_tag(t) for t in toks[:a]); trail=''.join(_tok_tag(t) for t in toks[b:])
        core=toks[a:b]; mid=any(t[0] in _EDGE for t in core)
        coretext=''.join((cs.idx_char(t[1]) or '\ufffd') if t[0]=='ch' else _tok_tag(t) for t in core)
        unit['lines'].append({'lead':lead,'trail':trail,'core':coretext,'brk':pend,'mid':mid,'empty':coretext==''})
        pend=term if term[0] in ('brk','repos') else None
    unit['empty']=(not unit['lines']) or all(l['empty'] for l in unit['lines'])
    return unit

def emit_unit(op,head,lead_clear,lines,cs):
    """lines: [{lead,trail,brk,core}]  (core 已是最终文本)"""
    out=bytearray([op])
    if op==69 and head: out+=bytes([head[0]&0xFF,head[0]>>8,head[1]&0xFF,head[1]>>8])
    elif op in (71,72) and head: out+=bytes(head)
    if lead_clear: out.append(0xEB)
    for ln in lines:
        brk=ln.get('brk')
        if brk:
            if brk[0]=='brk': out+=bytes([brk[1],brk[2]])
            elif brk[0]=='repos': out+=bytes([0xEB,0x45,brk[1]&0xFF,brk[1]>>8,brk[2]&0xFF,brk[2]>>8])
        out+=str_to_bytes(ln['lead']+ln['core']+ln['trail'],cs)
    out.append(0xEC)
    return bytes(out)
