#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ice_text.py — ICE 引擎 文本 提取/注入（方案B：变长 + 相对跳转自动重定位）  v2
====================================================================
v2 修复：
  · 正确解析 op69「定位多行文本」(头部x/y、清屏、逐行重定位)，不再吐 の。』． 杂质
  · 首尾控制符({C}/{/C}/{NAME}/{VAR})分离进 meta，message 保持干净；
    控制符夹在文本中间则保留为内联标签并在提取时告警
  · 过滤纯空条目（清屏/占位指令不进翻译 JSON，注入时原样保留）
  · op72(条件名字,极少)整体原样保留，不翻译

命令：
  extract  bin_dir charset -o proj      提取 → proj/json/*.json + proj/meta/*.json
  check    proj charset                 注入前预检（不可编码字符 / 行数变化 / 中间控制符）
  inject   proj bin_dir charset -o out  注入（未改动单元原样复用=最小补丁）
配合 grp_tool.py 解包/封包。
"""
import sys, os, json, glob, struct, argparse, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ice_op as O

NAME_BEFORE={74,71}   # 紧跟消息前、作为说话人名字的 opcode

def _line_meta(ln, jid):
    d={"id":jid}
    if ln["lead"]: d["lead"]=ln["lead"]
    if ln["trail"]: d["trail"]=ln["trail"]
    if ln["brk"]: d["brk"]=list(ln["brk"])
    if ln["empty"]: d["empty"]=True
    return d

# ----------------------------------------------------------------- EXTRACT
def extract(bin_dir, charset_path, out_dir):
    cs=O.Charset(charset_path)
    os.makedirs(os.path.join(out_dir,'json'),exist_ok=True)
    os.makedirs(os.path.join(out_dir,'meta'),exist_ok=True)
    files=sorted(glob.glob(os.path.join(bin_dir,'*.bin')))
    grand=0; midwarn=[]
    for f in files:
        name=os.path.splitext(os.path.basename(f))[0]
        buf=open(f,'rb').read(); ins=O.disasm(buf)
        # 预解析所有文本单元
        parsed={pc:O.parse_unit(buf,pc,op,ln,cs) for pc,op,ln in ins if op in (68,69,71,72,74)}
        entries=[]; units=[]; nid=0
        i=0
        while i<len(ins):
            pc,op,ln=ins[i]
            if op in (68,69):
                u=parsed[pc]
                # 名字 = 前一条非空 op74/op71
                name_off=name_op=name_head=name_txt=None
                if i>0:
                    ppc,pop,pln=ins[i-1]
                    if pop in NAME_BEFORE:
                        pu=parsed[ppc]
                        if not pu['empty']:
                            name_off,name_op=ppc,pop
                            name_head=pu['head']
                            name_txt=''.join(l['lead']+l['core']+l['trail'] for l in pu['lines'])
                mlines=[]
                for li,line in enumerate(u['lines']):
                    if line['empty']:
                        mlines.append(_line_meta(line,None)); continue
                    e={"id":nid}
                    if name_txt is not None and not any('id' in m and m.get('_named') for m in mlines):
                        # 名字放在第一条非空行
                        if not any(('id' in mm and not mm.get('empty')) for mm in mlines):
                            e["name"]=name_txt
                    e["pre_jp"]=line['core']; e["message"]=line['core']
                    entries.append(e); mlines.append(_line_meta(line,nid))
                    if line['mid']: midwarn.append((name,nid,line['core']))
                    nid+=1
                units.append({"t":"msg","off":pc,"op":op,"head":u['head'],
                              "lead_clear":u['lead_clear'],
                              "name_off":name_off,"name_op":name_op,"name_head":name_head,
                              "lines":mlines})
                i+=1
            elif op in NAME_BEFORE and not parsed[pc]['empty']:
                nxt=ins[i+1][1] if i+1<len(ins) else None
                if nxt in (68,69):   # 作为下条消息的名字，跳过(上面处理)
                    i+=1; continue
                u=parsed[pc]; mlines=[]
                for line in u['lines']:
                    if line['empty']: mlines.append(_line_meta(line,None)); continue
                    e={"id":nid,"pre_jp":line['core'],"message":line['core']}
                    entries.append(e); mlines.append(_line_meta(line,nid))
                    if line['mid']: midwarn.append((name,nid,line['core']))
                    nid+=1
                units.append({"t":"imm","off":pc,"op":op,"head":u['head'],
                              "lead_clear":u['lead_clear'],"lines":mlines})
                i+=1
            else:
                i+=1
        json.dump(entries,open(os.path.join(out_dir,'json',name+'.json'),'w',encoding='utf-8'),ensure_ascii=False,indent=2)
        json.dump({"script":name,"size":len(buf),"units":units},
                  open(os.path.join(out_dir,'meta',name+'.json'),'w',encoding='utf-8'),ensure_ascii=False,indent=1)
        grand+=len(entries)
    json.dump({"charset":os.path.abspath(charset_path),"bin_dir":os.path.abspath(bin_dir)},
              open(os.path.join(out_dir,'project.json'),'w',encoding='utf-8'),ensure_ascii=False,indent=1)
    print('[提取完成] 脚本 %d 个，文本条目共 %d 条 → %s'%(len(files),grand,out_dir))
    if midwarn:
        print('[注意] %d 条文本中间含控制符(已保留为内联标签{C}等，翻译时请勿删改其相对位置)：'%len(midwarn))
        for s,i,t in midwarn[:8]: print('   %s id=%d  %r'%(s,i,t))
        if len(midwarn)>8: print('   ...')

# ----------------------------------------------------------------- INJECT
def _unit_lines(u, entries):
    """组装 emit_unit 需要的 lines(含core)。返回(lines, changed)"""
    out=[]; changed=False
    for m in u["lines"]:
        if m.get("id") is None:
            core=""
        else:
            e=entries[m["id"]]; core=e["message"]
            if e["message"]!=e["pre_jp"]: changed=True
        out.append({"lead":m.get("lead",""),"trail":m.get("trail",""),
                    "brk":tuple(m["brk"]) if m.get("brk") else None,"core":core})
    return out,changed

def inject(proj_dir, bin_dir, charset_path, out_dir):
    cs=O.Charset(charset_path); os.makedirs(out_dir,exist_ok=True)
    metas=sorted(glob.glob(os.path.join(proj_dir,'meta','*.json'))); allwarn=0
    for mf in metas:
        meta=json.load(open(mf,encoding='utf-8')); name=meta["script"]
        entries={e["id"]:e for e in json.load(open(os.path.join(proj_dir,'json',name+'.json'),encoding='utf-8'))}
        orig=open(os.path.join(bin_dir,name+'.bin'),'rb').read(); ins=O.disasm(orig)
        olen={pc:ln for pc,_,ln in ins}; warn=[]
        # 缺失 id 检查
        need=[m["id"] for u in meta["units"] for m in u["lines"] if m.get("id") is not None]
        miss=[i for i in need if i not in entries]
        if miss:
            print('  [%s] 错误：JSON 缺少 id %s，跳过该脚本'%(name,miss[:8])); continue
        repl={}
        for u in meta["units"]:
            lines,changed=_unit_lines(u,entries)
            if not changed:
                repl[u["off"]]=orig[u["off"]:u["off"]+olen[u["off"]]]
            else:
                try:
                    repl[u["off"]]=O.emit_unit(u["op"],u["head"],u["lead_clear"],lines,cs)
                except ValueError as ex:
                    print('  [%s] 编码失败(off %d): %s'%(name,u["off"],ex)); repl[u["off"]]=orig[u["off"]:u["off"]+olen[u["off"]]]
            if u["t"]=="msg" and u.get("name_off") is not None:
                # 名字
                nm=None
                for m in u["lines"]:
                    if m.get("id") is not None and "name" in entries[m["id"]]:
                        nm=entries[m["id"]]["name"]; break
                noff=u["name_off"]
                orig_nm_unit=O.parse_unit(orig,noff,u["name_op"],olen[noff],cs)
                orig_nm=''.join(l['lead']+l['core']+l['trail'] for l in orig_nm_unit['lines'])
                if nm is None or nm==orig_nm:
                    repl[noff]=orig[noff:noff+olen[noff]]
                else:
                    repl[noff]=O.emit_unit(u["name_op"],u["name_head"],False,
                                           [{"lead":"","trail":"","brk":None,"core":nm}],cs)
        # 新布局 + old->new
        newlen=[len(repl[pc]) if pc in repl else ln for pc,_,ln in ins]
        newoff={}; cur=0
        for k,(pc,op,ln) in enumerate(ins): newoff[pc]=cur; cur+=newlen[k]
        newoff[len(orig)]=cur
        out=bytearray()
        for k,(pc,op,ln) in enumerate(ins):
            if pc in repl: out+=repl[pc]
            elif op in O.JUMPS:
                b=bytearray(orig[pc:pc+ln]); entry=pc+1
                for doff,base in O.JUMPS[op]:
                    disp=struct.unpack_from('<h',orig,entry+doff)[0]; tgt=entry+base+disp
                    if tgt not in newoff: warn.append('跳转目标0x%X非边界'%tgt); continue
                    nd=newoff[tgt]-(newoff[pc]+1)-base
                    if not -32768<=nd<=32767: warn.append('位移溢出'); continue
                    struct.pack_into('<h',b,1+doff,nd)
                out+=bytes(b)
            else: out+=orig[pc:pc+ln]
        open(os.path.join(out_dir,name+'.bin'),'wb').write(bytes(out))
        if warn:
            allwarn+=len(warn)
            for w in warn[:3]: print('  [%s] 警告: %s'%(name,w))
    man=os.path.join(bin_dir,'_grp_manifest.json')
    if os.path.exists(man):
        import shutil; shutil.copy(man,os.path.join(out_dir,'_grp_manifest.json'))
    print('[注入完成] → %s （警告 %d 条）'%(out_dir,allwarn))

# ----------------------------------------------------------------- CHECK
def check(proj_dir, charset_path):
    cs=O.Charset(charset_path)
    metas=sorted(glob.glob(os.path.join(proj_dir,'meta','*.json')))
    bad_char=[]; mid=[]; n=0; ch=0
    for mf in metas:
        meta=json.load(open(mf,encoding='utf-8')); name=meta["script"]
        entries={e["id"]:e for e in json.load(open(os.path.join(proj_dir,'json',name+'.json'),encoding='utf-8'))}
        for u in meta["units"]:
            for m in u["lines"]:
                if m.get("id") is None: continue
                e=entries.get(m["id"])
                if e is None: bad_char.append((name,m["id"],'缺少条目')); continue
                n+=1
                if e["message"]!=e["pre_jp"]: ch+=1
                full=m.get("lead","")+e["message"]+m.get("trail","")
                try: O.str_to_bytes(full,cs)
                except ValueError as ex: bad_char.append((name,m["id"],str(ex)))
                if "name" in e:
                    try: O.str_to_bytes(e["name"],cs)
                    except ValueError as ex: bad_char.append((name,m["id"],'[name]'+str(ex)))
                if re.search(r'\{C\d?\}|\{/C\}|\{NAME\}|\{VAR\}', e["message"]):
                    mid.append((name,m["id"]))
    print('=== ICE 译文预检 ===')
    print('条目 %d，已改动 %d'%(n,ch))
    print('不可编码字符：%d 处'%len(bad_char))
    for x in bad_char[:25]: print('   %s id=%s  %s'%x)
    print('含内联控制符标签的条目：%d（注入会保留，翻译时勿删）'%len(mid))
    if not bad_char:
        print('通过：所有译文均可编码。'+('（注意上面内联标签条目）' if mid else ''))
    return len(bad_char)

# ----------------------------------------------------------------- BUILD_CHARSET
_TAG=re.compile(r'\{/C\}|\{C\d?\}|\{NAME\}|\{VAR\}')
def _scan_needed(proj_dir):
    """扫描译文 message+name，返回 (需要的字符集合, cp932不可编码字符集合)"""
    need=set(); cant=set()
    for jf in sorted(glob.glob(os.path.join(proj_dir,'json','*.json'))):
        for e in json.load(open(jf,encoding='utf-8')):
            for fld in ('message','name'):
                if fld not in e: continue
                for ch in _TAG.sub('',e[fld]):
                    try: ch.encode('cp932')
                    except UnicodeEncodeError: cant.add(ch); continue
                    need.add(ch)
    return need,cant

def build_charset(proj_dir, orig_charset, out_path):
    cs=O.Charset(orig_charset); orig=cs.idx2sjis; n=len(orig)
    need,cant=_scan_needed(proj_dir)
    if cant:
        print('[错误] 以下 %d 个字符无法用 cp932(Shift-JIS) 编码，需在译文/映射表中替换为日繁等价字形：'%len(cant))
        print('   '+' '.join(sorted(cant))); return 1
    need_sjis={}
    for ch in need:
        b=ch.encode('cp932'); need_sjis[(b[0] if len(b)==1 else (b[0]<<8)|b[1])]=ch
    ref=[i for i in range(n) if O.Charset._encodable(i) and i<2386]   # 内联可引用索引
    covered={orig[i] for i in ref if orig[i] in need_sjis}
    free=[i for i in ref if orig[i] not in need_sjis]
    to_place=[s for s in need_sjis if s not in covered]
    SEC_LO,SEC_HI=2386,4863                                            # 扩展节索引区(需EXE补丁)
    sec_cap=SEC_HI-SEC_LO+1
    print('=== 构建字符表 ===')
    print('译文独立字: %d   内联可引用槽位: %d(其中空闲%d)'%(len(need_sjis),len(ref),len(free)))
    print('已在原表: %d   需新增: %d'%(len(covered),len(to_place)))
    if len(to_place)>len(free)+sec_cap:
        print('[错误] 字库不足：需新增 %d，内联空闲%d + 扩展上限%d = %d。'%(len(to_place),len(free),sec_cap,len(free)+sec_cap))
        print('       请减少生僻字/异体字。'); return 1
    # 分配：新字优先填内联空闲(双字节区)，再溢出到扩展节
    free2=sorted(i for i in free if 256<=i<2386); free1=sorted(i for i in free if i<256)
    pool=free2+free1
    new=list(orig); sec=[]
    for s in to_place:
        if pool: new[pool.pop(0)]=s
        else: sec.append(s)                                            # 溢出到扩展节(索引2386+)
    full=new+sec                                                       # 完整表
    # 写完整表(给 inject + EXE补丁器)
    out=bytearray()
    for s in full: out+=bytes([s>>8,s&0xFF])
    open(out_path,'wb').write(bytes(out))
    # 写 System.grp 用的内联部分(前2386条=4772字节)
    sysp=os.path.splitext(out_path)[0]+'_sysgrp.bin'
    open(sysp,'wb').write(bytes(out[:n*2]))
    # 自检
    cs2=O.Charset(out_path); fail=[c for c in need if cs2.char_idx(c) is None]
    print('完整表: %d 条 (内联 %d + 扩展 %d)'%(len(full),n,len(sec)))
    if fail:
        print('[警告] 自检 %d 字仍不可编码: %s'%(len(fail),' '.join(fail[:20]))); return 1
    print('自检通过：全部 %d 个译文字符均可编码。'%len(need))
    print('  · 完整表(给 inject 和 EXE补丁器): %s'%out_path)
    print('  · System.grp 的 0001.bin(内联2386条):       %s'%sysp)
    if sec:
        print('[需要 EXE 补丁] 有 %d 个字溢出到扩展节。请执行：'%len(sec))
        print('    python ice_exe_patch.py エグゼキュート.exe %s -o エグゼキュート_patched.exe'%out_path)
    else:
        print('[无需 EXE 补丁] 全部装入内联表，直接替换 System.grp 的 0001.bin 即可。')
    return 0

def main():
    ap=argparse.ArgumentParser(description='ICE 引擎文本 提取/注入（方案B v2）')
    s=ap.add_subparsers(dest='cmd',required=True)
    pe=s.add_parser('extract'); pe.add_argument('bin_dir'); pe.add_argument('charset'); pe.add_argument('-o','--out',default='proj')
    pc=s.add_parser('check'); pc.add_argument('proj_dir'); pc.add_argument('charset')
    pi=s.add_parser('inject'); pi.add_argument('proj_dir'); pi.add_argument('bin_dir'); pi.add_argument('charset'); pi.add_argument('-o','--out',default='ev_patched')
    pb=s.add_parser('build_charset'); pb.add_argument('proj_dir'); pb.add_argument('charset'); pb.add_argument('-o','--out',default='0001_new.bin')
    a=ap.parse_args()
    if a.cmd=='extract': extract(a.bin_dir,a.charset,a.out)
    elif a.cmd=='check': check(a.proj_dir,a.charset)
    elif a.cmd=='build_charset': sys.exit(build_charset(a.proj_dir,a.charset,a.out))
    else: inject(a.proj_dir,a.bin_dir,a.charset,a.out)

if __name__=='__main__': main()
