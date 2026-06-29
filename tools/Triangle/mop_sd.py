# -*- coding: utf-8 -*-
"""
mop_sd.py — MOP / EXD / KLH 系列引擎 .SD 脚本反汇编共享核心（多引擎自动识别 + 嵌入数据块鲁棒处理）

三套引擎(MOP.EXE / EXD.EXE / KLH.EXE)同源：栈式16位VM，无加密/无头/无size字段，IP从偏移0线性执行。
opcode=u16小端；操作数=u16/u32/NUL结尾cp932串。结构一致，但 opcode 编号与部分操作数布局各不相同，
故内置三套 profile 并自动选用。KLH 另有 MOP/EXD 没有的"嵌入式数据块"（图形菜单坐标表，被跳转跳过、
不在线性执行流中），用"跳转目标=指令边界"做锚点把它们切成不透明 data 块原样保留。

  特殊opcode（每套不同，见 PROFILES）：
    文本   选择肢  gosub  jmp      if   跳转表
    MOP 74 75     32     33/60    59   153/154
    EXD 74 75     32     33/60    59   150/151
    KLH 72 73     32     33/58    57   148/149
  文本：u16(段数)+若干NUL串；段首N/M/V/W/@为命令，其余为正文；V/v段尾再+6字节(u16+u32)
  选择肢：u16(个数)+若干NUL串
  GOSUB/JMP：u32 目标(相对base)  跳转表：u16+u16(N)+N*u32 目标
  IF：连续读高位0x8000的u16直到非高位  未映射opcode：2字节
"""

_TEMPLATE_MOP = {1:'W', 2:'', 3:'', 4:'SWWW', 5:'', 6:'W', 7:'WWW', 8:'WW', 9:'', 10:'W', 11:'', 12:'', 13:'WWWWWW', 14:'W', 15:'W', 16:'W', 17:'WWW', 18:'W', 19:'W', 22:'', 23:'WWWWWWW', 24:'WWWWWWW', 25:'W', 26:'WWWWWW', 27:'WWW', 28:'SSWWWW', 29:'W', 31:'W', 32:'D', 33:'D', 34:'SWWWWWWW', 35:'SWWWWWWW', 36:'SWWWW', 37:'SWWW', 38:'SSWWW', 39:'SWWW', 40:'SSWWW', 41:'SSSWWWWW', 42:'SWWWWWWWWW', 43:'SSSSWWWWWW', 44:'SWWW', 45:'SSWWW', 46:'SWWWWWWWWW', 47:'', 48:'SWWWW', 49:'SSWWWW', 50:'SSWWWW', 51:'SWWWWWWWWWWW', 52:'SSWWWWWWWWWWW', 53:'WWWWWWWWWWW', 54:'W', 55:'', 56:'', 57:'WW', 58:'W', 59:'WWD', 60:'D', 61:'W', 62:'WW', 63:'', 64:'W', 65:'', 66:'WW', 67:'WW', 68:'W', 69:'W', 70:'', 71:'', 72:'', 74:'WSWD', 75:'WS', 79:'WWW', 81:'W', 82:'W', 83:'', 84:'', 85:'', 86:'', 87:'WW', 88:'', 89:'', 91:'W', 92:'WWWS', 93:'WW', 94:'', 95:'W', 96:'S', 97:'W', 98:'WW', 99:'W', 100:'WW', 101:'W', 102:'W', 103:'', 104:'WWWWWW', 105:'WWWWWW', 106:'WW', 108:'WWW', 109:'W', 110:'WWW', 111:'WWWWW', 112:'WWWWWW', 113:'WWWWWW', 114:'WWWWWW', 115:'WWWWWW', 116:'WWWWWW', 117:'WWWWWW', 118:'WWWWWW', 119:'WWWWWW', 120:'WWWWWW', 121:'WWWWWWWW', 123:'SSWWWWWWW', 124:'WWWWWWWWWWW', 125:'WWWWWWWW', 126:'WWWWWW', 127:'WWWWWW', 128:'WWWWWW', 130:'WWWD', 131:'W', 132:'W', 133:'W', 134:'WW', 135:'W', 136:'W', 137:'W', 138:'W', 139:'W', 140:'', 141:'', 142:'', 143:'WW', 144:'WW', 145:'', 146:'WW', 147:'WW', 148:'WW', 149:'WW', 150:'WW', 151:'WWWW', 152:'WWWW', 153:'WWD', 154:'WWD', 155:'WWW', 156:'S', 157:'WWW', 158:'W', 160:'WW', 161:'W', 162:'W', 163:'WWW', 164:'', 165:'W', 166:'WWW', 167:'WWWWWWW', 168:'WWWWWWW', 169:'', 170:'WWWW', 171:'SWWWW', 172:'WWWWWW', 175:'S', 176:'SW', 177:'SSW', 178:'W', 179:'S', 180:'SW', 181:'SSW', 182:'S', 183:'SS', 184:'SW', 185:'SSW', 186:'W', 187:'SW', 188:'SSW', 189:'W'}
_TEMPLATE_EXD = {1:'W', 2:'', 3:'', 4:'SWWW', 5:'', 6:'W', 7:'WWW', 8:'WW', 9:'', 10:'W', 11:'', 12:'', 13:'WWWWWW', 14:'W', 15:'W', 16:'W', 17:'WWW', 18:'W', 19:'W', 22:'', 23:'WWWWWWW', 24:'WWWWWWW', 25:'W', 26:'WWWWWW', 27:'WWW', 28:'SSWWWW', 29:'W', 31:'W', 32:'D', 33:'D', 34:'SWWWWWWW', 35:'SWWWWWWW', 36:'SWWWW', 37:'SWWW', 38:'SSWWW', 39:'SWWW', 40:'SSWWW', 41:'SSSWWWWW', 42:'SWWWWWWWWW', 43:'SSSSWWWWWW', 44:'SWWW', 45:'SSWWW', 46:'SWWWWWWWWW', 47:'', 48:'SWWWW', 49:'SSWWWW', 50:'SSWWWW', 51:'SWWWWWWWWWWW', 52:'SSWWWWWWWWWWW', 53:'WWWWWWWWWWW', 54:'W', 55:'', 56:'', 57:'WW', 58:'W', 59:'WWD', 60:'D', 61:'W', 62:'WW', 63:'', 64:'W', 65:'', 66:'WW', 67:'WW', 68:'W', 69:'W', 70:'', 71:'', 72:'', 74:'WSWD', 75:'WS', 79:'WWW', 81:'W', 82:'W', 83:'', 84:'', 85:'', 86:'', 87:'WW', 88:'', 89:'', 91:'W', 92:'WWWS', 93:'WW', 94:'', 95:'W', 96:'S', 97:'W', 98:'WW', 99:'W', 100:'WW', 101:'W', 102:'W', 103:'', 104:'WWWWWW', 105:'WWWWWW', 106:'WW', 108:'WWW', 109:'W', 110:'WWW', 111:'WWWWW', 112:'WWWWWW', 113:'WWWWWW', 114:'WWWWWW', 115:'WWWWWW', 116:'WWWWWW', 117:'WWWWWW', 118:'WWWWWW', 119:'WWWWWW', 120:'WWWWWW', 121:'WWWWWWWW', 123:'SSWWWWWWW', 124:'WWWWWWWWWWW', 125:'WWWWWWWW', 126:'WWWWWW', 127:'WWWWWW', 128:'WWWWWW', 130:'WWWD', 131:'W', 132:'W', 133:'W', 134:'W', 135:'W', 136:'W', 137:'', 138:'', 139:'', 140:'WW', 141:'WW', 142:'', 143:'WW', 144:'WW', 145:'WW', 146:'WW', 147:'WW', 148:'WWWW', 149:'WWWW', 150:'WWD', 151:'WWD', 152:'WWW', 153:'WWW', 154:'W', 156:'WW', 157:'W', 158:'W', 159:'WWW', 160:'', 161:'W', 162:'WWW', 163:'WWWWWWW', 164:'WWWWWWW', 165:'', 166:'WWWW', 167:'SWWWW', 168:'WWWWWW', 171:'S', 172:'SW', 173:'SSW', 174:'W', 175:'S', 176:'SW', 177:'SSW', 178:'S', 179:'SS', 180:'SW', 181:'SSW', 182:'WW', 183:'SW', 184:'SSW', 185:'W'}
_TEMPLATE_KLH = {1:'W', 4:'SWWW', 5:'WWW', 6:'WW', 7:'', 8:'W', 9:'', 10:'', 11:'WWWWWW', 12:'SW', 13:'SWWW', 14:'W', 15:'W', 16:'W', 17:'WWW', 18:'W', 19:'W', 22:'', 23:'WWWWWWW', 24:'WWWWWWW', 25:'W', 26:'WWWWWW', 27:'WWW', 28:'SSWWWW', 29:'W', 31:'W', 32:'D', 33:'D', 34:'SWWWWWWW', 35:'SWWWWWWW', 36:'SWWWW', 37:'SWWW', 38:'SSWWW', 39:'SWWW', 40:'SSWWW', 41:'SSSWWWWW', 42:'SWWWWWWWWW', 43:'SSSSWWWWWW', 44:'SWWW', 45:'SSWWW', 46:'SWWWWWWWWW', 47:'', 48:'SWWWW', 49:'SSWWWW', 50:'SSWWWW', 51:'SWWWWWWWWWWW', 52:'SSWWWWWWWWWWW', 53:'WWWWWWWWWWW', 54:'W', 55:'WW', 56:'W', 57:'WWD', 58:'D', 59:'W', 60:'WW', 61:'', 62:'W', 63:'', 64:'WW', 65:'WW', 66:'W', 67:'W', 68:'', 69:'', 70:'', 72:'WSWD', 73:'WS', 74:'WS', 78:'WWW', 80:'W', 81:'W', 82:'', 83:'', 84:'', 85:'', 86:'WW', 87:'', 89:'W', 90:'WWWS', 91:'WW', 92:'', 93:'W', 94:'S', 95:'W', 96:'WW', 97:'W', 98:'W', 99:'WW', 100:'', 101:'W', 102:'WWWWWW', 103:'WWWWWW', 104:'WW', 106:'WWW', 107:'W', 108:'WWW', 109:'WWWWW', 110:'WWWWWW', 111:'WWWWWW', 112:'WWWWWW', 113:'WWWWWW', 114:'WWWWWW', 115:'WWWWWW', 116:'WWWWWW', 117:'WWWWWW', 118:'WWWWWW', 119:'WWWWWWWW', 121:'SSWWWWWWW', 122:'WWWWWWWWWWW', 123:'WWWWWWWW', 124:'WWWWWW', 125:'WWWWWW', 126:'WWWWWW', 128:'WWWD', 129:'W', 130:'W', 131:'W', 132:'W', 133:'WW', 134:'WWW', 135:'WWWD', 136:'', 137:'', 138:'WW', 139:'WW', 140:'', 141:'WW', 142:'WW', 143:'WW', 144:'WW', 145:'WW', 146:'WWWW', 147:'WWWW', 148:'WWD', 149:'WWD', 150:'WWW', 151:'WWW', 152:'W', 153:'W', 155:'WW', 156:'W', 157:'W', 158:'WWW', 159:'', 160:'W', 161:'WWW', 162:'WWWWWWW', 163:'WWWWWWW', 164:'', 165:'WWWW', 166:'SWWWW', 167:'WWWWWW', 170:'S', 171:'SW', 172:'SSW', 173:'W', 174:'S', 175:'SW', 176:'SSW', 177:'S', 178:'SS', 179:'SW', 180:'SSW', 181:'', 182:'WWWW', 183:'SW', 184:'SSW', 185:'W', 186:'', 187:'', 188:'', 189:'SWW'}

PROFILES = {
  "MOP": dict(template=_TEMPLATE_MOP, text=74, choice=75, gosub=32, jmp=(33,60), if_op=59, jtable=(153,154)),
  "EXD": dict(template=_TEMPLATE_EXD, text=74, choice=75, gosub=32, jmp=(33,60), if_op=59, jtable=(150,151)),
  "KLH": dict(template=_TEMPLATE_KLH, text=72, choice=73, gosub=32, jmp=(33,58), if_op=57, jtable=(148,149)),
}

# 兼容旧调用：文本/选择肢 opcode（注意 KLH 不同，建议用 inst.kind 判断而非这些常量）
OP_TEXT, OP_CHOICE = 74, 75
OP_GOSUB = 32
OP_JMP = (33, 60)
OP_IF = 59

_CMD_BYTES = {0x4D,0x6D,0x4E,0x6E,0x56,0x76,0x57,0x77,0x40}  # M N V W @
_VOICE_BYTES = {0x56,0x76}

def _u16(d,p): return d[p]|(d[p+1]<<8)
def _u32(d,p): return d[p]|(d[p+1]<<8)|(d[p+2]<<16)|(d[p+3]<<24)

def is_text_seg(seg):
    if not seg: return False
    return seg[0] not in _CMD_BYTES

class Inst:
    __slots__=('off','op','length','kind','segs','opts','reloc')
    def __init__(s,off,op,length,kind):
        s.off=off; s.op=op; s.length=length; s.kind=kind
        s.segs=None; s.opts=None; s.reloc=None

# ----- 单条指令解析（profile 相关），返回 (length, op, reloc_list) -----
class _Engine:
    def __init__(s,data,prof):
        s.d=data; s.N=len(data); s.T=prof["template"]; s.MAX=max(s.T)
        s.GOS=prof["gosub"]; s.JMP=set(prof["jmp"]); s.IFO=prof["if_op"]
        s.TXT=prof["text"]; s.CHO=prof["choice"]; s.JT=set(prof["jtable"])
    def span(s,p):
        d=s.d; N=s.N; op=d[p]|(d[p+1]<<8); q=p+2; rel=[]
        if op==s.GOS or op in s.JMP:
            rel.append((q,_u32(d,q))); q+=4
        elif op==s.IFO:
            while q+1<N and (d[q]|(d[q+1]<<8))&0x8000: q+=2
        elif op==s.TXT:
            c=d[q]|(d[q+1]<<8); q+=2; r=0
            while r<c:
                st=q
                while q<N and d[q]: q+=1
                cc=d[st] if q>st else 0; q+=1; r+=1
                if cc in _VOICE_BYTES: q+=6
        elif op==s.CHO:
            c=d[q]|(d[q+1]<<8); q+=2
            for _ in range(c):
                while q<N and d[q]: q+=1
                q+=1
        elif op in s.JT:
            q+=2; c=d[q]|(d[q+1]<<8); q+=2
            for _ in range(c): rel.append((q,_u32(d,q))); q+=4
        else:
            t=s.T.get(op)
            if t is None: return 2,op,rel
            for ch in t:
                if ch=='W': q+=2
                elif ch=='D': q+=4
                else:
                    while q<N and d[q]: q+=1
                    q+=1
        return q-p,op,rel
    def lands(s,a,b):
        q=a
        while q<b:
            L,op,rel=s.span(q)
            if L<=0 or q+L>b: return False
            q+=L
        return q==b
    def spans(s,a,b):
        out=[]; q=a
        while q<b:
            L,op,rel=s.span(q); out.append((q,L)); q+=L
        return out
    def _clean_run(s,c,lim=6):
        q=c; g=0
        while q<s.N-1 and g<lim:
            if (s.d[q]|(s.d[q+1]<<8))>s.MAX: break
            L,op,rel=s.span(q)
            if L<=0: break
            q+=L; g+=1
        return g
    def try_gap(s,a,b,win=8192,force=False,faults=()):
        if not force and s.lands(a,b): return [(q,L,'inst') for (q,L) in s.spans(a,b)]
        if b-a>win: return None
        e=a; hit_imp=False
        while e<b:
            if (s.d[e]|(s.d[e+1]<<8))>s.MAX: hit_imp=True; break
            L,op,rel=s.span(e)
            if L<=0 or e+L>b: break
            e+=L
        if not hit_imp:
            if s.lands(a,b): return [(q,L,'inst') for (q,L) in s.spans(a,b)]
            return None          # 区间内无"不可能opcode"=>非嵌入数据块；b 可能是伪锚点，跳过不切
        # 重同步点必须越过本 gap 内所有已知"伪指令"偏移，且其后是一段真正干净的代码
        floor=max([e]+[f+1 for f in faults if a<=f<b])
        sfx=None; c=floor
        while c<=b:
            if s.lands(c,b) and (c==b or s._clean_run(c)>=4): sfx=c; break
            c+=1
        if sfx is None: return None
        out=[(q,L,'inst') for (q,L) in s.spans(a,e)]
        if sfx>e: out.append((e,sfx-e,'data'))
        out+= [(q,L,'inst') for (q,L) in s.spans(sfx,b)]
        return out

def _find_boundaries(data,prof):
    """鲁棒地求出指令边界与 data 块；返回 list[(off,length,kind)]，kind in inst/data。"""
    e=_Engine(data,prof); N=e.N
    anchors=set([0]); p=0
    while p<N:
        L,op,rel=e.span(p)
        if L<=0 or p+L>N: break
        for (f,t) in rel:
            if 0<=t<N: anchors.add(t)
        p+=L
    force_off=set()   # 需要强制切分的伪指令偏移（其reloc目标越界 => 实为数据块内误读）
    spans=[]; bounds=set(); tg=set()
    for _ in range(16):
        A=sorted(set([0,N])|{a for a in anchors if 0<a<N})
        spans=[]; i=0
        while i<len(A)-1:
            a=A[i]; b1=A[i+1]
            frc=any(a<=fo<b1 for fo in force_off)
            res=None; j=i+1; jmax=min(len(A), i+1+16)
            while j<jmax:
                res=e.try_gap(a,A[j],force=(frc and j==i+1),faults=force_off)
                if res is not None: i=j; break
                j+=1
            if res is None:
                res=[(q,L,'inst') for (q,L) in e.spans(a,b1)]; i+=1
            spans+=res
        bounds={o for (o,L,k) in spans}
        tg=set(); newforce=set(); bad=set()
        for (o,L,k) in spans:
            if k=='inst':
                _,_,rel=e.span(o)
                for (f,t) in rel:
                    if 0<=t<N:
                        tg.add(t)
                        if t not in bounds: bad.add(t); newforce.add(o)
        if not bad: return spans,bounds,tg
        progressed=False
        if not newforce<=force_off: force_off|=newforce; progressed=True
        if not tg<=anchors: anchors|=tg; progressed=True
        if not progressed: return spans,bounds,tg
    return spans,bounds,tg

def _classify(data,prof,off,length):
    """把一个 inst span 解析成完整 Inst（含 segs/opts/reloc）。"""
    e=_Engine(data,prof); d=data; N=len(data)
    op=d[off]|(d[off+1]<<8); q=off+2
    if op==e.GOS or op in e.JMP:
        ins=Inst(off,op,length,'jump'); ins.reloc=[(q,_u32(d,q))]
    elif op==e.IFO:
        ins=Inst(off,op,length,'plain')
    elif op==e.TXT:
        cnt=d[q]|(d[q+1]<<8); q+=2; segs=[]; r=0
        while r<cnt:
            st=q
            while q<N and d[q]: q+=1
            raw=d[st:q]; q+=1; r+=1
            extra=b''
            if raw and raw[0] in _VOICE_BYTES: extra=d[q:q+6]; q+=6
            segs.append((raw,extra))
        ins=Inst(off,op,length,'text'); ins.segs=segs
    elif op==e.CHO:
        cnt=d[q]|(d[q+1]<<8); q+=2; opts=[]
        for _ in range(cnt):
            st=q
            while q<N and d[q]: q+=1
            opts.append(d[st:q]); q+=1
        ins=Inst(off,op,length,'choice'); ins.opts=opts
    elif op in e.JT:
        q+=2; cnt=d[q]|(d[q+1]<<8); q+=2; rel=[]
        for _ in range(cnt): rel.append((q,_u32(d,q))); q+=4
        ins=Inst(off,op,length,'jtable'); ins.reloc=rel
    else:
        ins=Inst(off,op,length,'plain')
    return ins

LAST_PROFILE=None

def _count_impossible(data,prof):
    """快速线性扫一遍，统计 op>maxop 出现次数（用于引擎判别）。"""
    e=_Engine(data,prof); N=e.N; MAX=e.MAX; p=0; bad=0
    while p<N:
        op=data[p]|(data[p+1]<<8)
        L,_,_=e.span(p)
        if L<=0 or p+L>N: break
        if op>MAX: bad+=1
        p+=L
    return bad

def detect_profile(data):
    """选 op>maxop 最少的 profile（正确引擎在数据块外几乎不出现不可能opcode）。"""
    best=None
    for name in PROFILES:
        try: c=_count_impossible(data,PROFILES[name])
        except Exception: c=1<<30
        if best is None or c<best[1]: best=(name,c)
    return best[0]

def disassemble(data,profile=None):
    """鲁棒反汇编整个 .SD，自动识别引擎。返回 (insts, boundaries)。insts 含 kind=='data' 的不透明块。"""
    global LAST_PROFILE
    name=profile or detect_profile(data)
    LAST_PROFILE=name
    prof=PROFILES[name]
    spans,bounds,_=_find_boundaries(data,prof)
    insts=[]
    for (o,L,k) in spans:
        if k=='data':
            ins=Inst(o,-1,L,'data'); insts.append(ins)
        else:
            insts.append(_classify(data,prof,o,L))
    return insts,bounds

def iter_messages(inst):
    assert inst.kind=='text'
    out=[]; cur=[]; cur_name=None; last_name=None
    for idx,(raw,extra) in enumerate(inst.segs):
        if is_text_seg(raw):
            if not cur: cur_name=last_name
            cur.append(idx)
        else:
            if raw and raw[0] in (0x4E,0x6E):
                last_name=raw[1:].decode('latin1','ignore') or None
            if cur:
                joined=b''.join(inst.segs[i][0] for i in cur)
                out.append((cur,joined,cur_name)); cur=[]
    if cur:
        joined=b''.join(inst.segs[i][0] for i in cur)
        out.append((cur,joined,cur_name))
    return out

def decode_cp932(b):
    try: return b.decode('cp932')
    except Exception: return b.decode('cp932','replace')

def self_test(path):
    data=open(path,'rb').read()
    insts,bnd=disassemble(data)
    out=b''.join(data[i.off:i.off+i.length] for i in insts)
    ok=(out==data); bad=0; ndata=0
    for i in insts:
        if i.kind=='data': ndata+=1
        if i.reloc:
            for (_f,t) in i.reloc:
                if t not in bnd: bad+=1
    return ok,len(insts),bad,LAST_PROFILE,ndata

if __name__=='__main__':
    import sys
    ok,n,bad,name,nd=self_test(sys.argv[1])
    print("engine:",name,"| zero-mutation:",ok,"| instructions:",n,"| data-blocks:",nd,"| off-boundary:",bad)
