import os, sys, struct, json, argparse

ENC_R = 'cp932' 
ENC_W = 'gbk' 
BLOCK = 144
OP_DIALOG  = 0x64
OP_NAME    = 0x6A
OP_CHAPTER = 0x69
TEXT_OPS   = {OP_DIALOG, OP_NAME, OP_CHAPTER}
TEXT_OFF           = 1
TEXT_MAX_DIALOG    = 129
TEXT_MAX_NAME      = 143
NEWLINE_FLAG_OFF   = 130
SEL_OFF,  SEL_MAX  = 65, 65


def lzss_decompress(comp, decomp_size):
    out = bytearray(); ring = bytearray(4096); rp = 4096 - 18; i = 0
    while i < len(comp) and len(out) < decomp_size:
        flags = comp[i]; i += 1
        for bit in range(8):
            if i >= len(comp) or len(out) >= decomp_size: break
            if flags & (1 << bit):
                b = comp[i]; i += 1
                out.append(b); ring[rp & 0xFFF] = b; rp = (rp+1) & 0xFFF
            else:
                if i+1 >= len(comp): break
                b1=comp[i]; b2=comp[i+1]; i+=2
                ref=b1|((b2&0xF0)<<4); ln=(b2&0x0F)+3
                for _ in range(ln):
                    b=ring[ref&0xFFF]; out.append(b)
                    ring[rp&0xFFF]=b; rp=(rp+1)&0xFFF; ref=(ref+1)&0xFFF
    return bytes(out)

def lzss_compress(plain):
    out = bytearray(); i = 0
    while i < len(plain):
        n = min(8, len(plain)-i); out.append((1<<n)-1)
        for _ in range(n): out.append(plain[i]); i += 1
    return bytes(out)


def parse_cdt(data):
    if data[-12:-8] != b'RK1\x00': raise ValueError("非 CDT 格式")
    count   = struct.unpack_from('<I', data, len(data)-8)[0]
    idx_off = struct.unpack_from('<I', data, len(data)-4)[0]
    entries = []; pos = idx_off
    for _ in range(count):
        name      = data[pos:pos+0x10].split(b'\x00')[0].decode('ascii','replace')
        size      = struct.unpack_from('<I', data, pos+0x10)[0]
        unpacked  = struct.unpack_from('<I', data, pos+0x14)[0]
        is_packed = struct.unpack_from('<I', data, pos+0x18)[0]
        offset    = struct.unpack_from('<I', data, pos+0x1C)[0]
        entries.append((name, offset, size, unpacked, is_packed)); pos += 0x20
    return entries

def unpack(dat_path, out_dir):
    data = open(dat_path,'rb').read()
    entries = parse_cdt(data)
    os.makedirs(out_dir, exist_ok=True)
    lines = []
    for i, (name, offset, size, unpacked, is_packed) in enumerate(entries):
        raw = lzss_decompress(data[offset:offset+size], unpacked) if is_packed else data[offset:offset+size]
        open(os.path.join(out_dir, name),'wb').write(raw)
        lines.append(f"{i}\t{name}\t{is_packed}")
    with open(os.path.join(out_dir,'_order.txt'),'w',encoding='utf-8') as f:
        f.write("# idx\tname\tis_packed\n"); f.write('\n'.join(lines)+'\n')
    print(f"[解包] {dat_path} -> {out_dir}  ({len(entries)} 个文件)")

def pack(src_dir, dat_path):
    order_file = os.path.join(src_dir,'_order.txt')
    items = []
    if os.path.exists(order_file):
        for line in open(order_file,encoding='utf-8'):
            line=line.strip()
            if not line or line.startswith('#'): continue
            parts=line.split('\t'); items.append((parts[1], int(parts[2]) if len(parts)>2 else 1))
    else:
        items = [(n,1) for n in sorted(os.listdir(src_dir)) if not n.startswith('_') and n.upper().endswith('.BIN')]
    out = bytearray(); idx = []
    for name, is_packed in items:
        plain = open(os.path.join(src_dir,name),'rb').read()
        off = len(out)
        if is_packed:
            comp = lzss_compress(plain); out += comp; idx.append((name,len(comp),len(plain),1,off))
        else:
            out += plain; idx.append((name,len(plain),len(plain),0,off))
    idx_off = len(out)
    for name,size,unp,pk,off in idx:
        out += name.encode('ascii')[:0x10].ljust(0x10,b'\x00')
        out += struct.pack('<IIII',size,unp,pk,off)
    out += b'RK1\x00' + struct.pack('<II',len(idx),idx_off)
    open(dat_path,'wb').write(out)
    print(f"[封包] {dat_path}  ({len(idx)} 个文件，0x{len(out):x} 字节)")


def _read_nt(data, off=0):
    end = data.find(b'\x00', off)
    return data[off:] if end == -1 else data[off:end]

def _is_sel(rec):
    if rec[0] in TEXT_OPS: return False
    if any(rec[2:65]): return False
    tail = _read_nt(rec, SEL_OFF)
    if not tail or not (0x81 <= tail[0] <= 0xFC): return False
    if not any(x > 0x7F for x in tail): return False
    try: tail.decode(ENC_R); return True
    except: return False

def parse_records(data):
    total = len(data) // BLOCK
    dialogs, sels = [], []
    last_name, last_name_idx = None, -999
    for i in range(total):
        rec = data[i*BLOCK:(i+1)*BLOCK]; op = rec[0]
        if op == OP_NAME:
            raw = _read_nt(rec, TEXT_OFF)
            if raw:
                try: last_name=raw.decode(ENC_R); last_name_idx=i
                except: pass
            continue
        if op == OP_DIALOG:
            raw = _read_nt(rec, TEXT_OFF)
            if not raw or not any(x>0x7F for x in raw): continue
            try: text=raw.decode(ENC_R)
            except: continue
            name = last_name if i-last_name_idx<=5 else None
            last_name, last_name_idx = None, -999
            dialogs.append({'record_idx':i,'name':name,'text':text,'is_chapter':False})
            continue
        if op == OP_CHAPTER:
            raw = _read_nt(rec, TEXT_OFF)
            if not raw: continue
            try: text=raw.decode(ENC_R)
            except: continue
            dialogs.append({'record_idx':i,'name':None,'text':text,'is_chapter':True})
            continue
        if _is_sel(rec):
            tail = _read_nt(rec, SEL_OFF)
            try: text=tail.decode(ENC_R)
            except: continue
            sels.append({'record_idx':i,'text':text})
    return dialogs, sels


def _can_enc(c):
    try: c.encode(ENC_W); return True
    except: return False

def _encode_trunc(text, max_bytes, eid, label=''):
    try: encoded = text.encode(ENC_W)
    except UnicodeEncodeError:
        print(f"  [错误] id={eid}{label} 编码失败: {[c for c in text if not _can_enc(c)]!r}"); return None
    if len(encoded) > max_bytes:
        cut = max_bytes
        while cut > 0:
            if cut >= 2 and (0x81 <= encoded[cut-2] <= 0xFE): cut -= 1; continue
            break
        encoded = encoded[:cut]
        print(f"  [截断] id={eid}{label} -> {cut}B")
    return encoded.ljust(max_bytes, b'\x00')


def extract_bin(bin_path, out_dir):
    fname = os.path.basename(bin_path)
    base  = os.path.splitext(fname)[0]
    data  = open(bin_path,'rb').read()
    dialogs, sels = parse_records(data)
    if not dialogs and not sels:
        print(f"  [跳过] {fname}: 0 条文本"); return
    combined = sorted(
        [('dialog', d['record_idx'], d) for d in dialogs] +
        [('sel',    s['record_idx'], s) for s in sels],
        key=lambda x: x[1]
    )
    json_items, meta_items = [], []
    for eid, (kind, _, item) in enumerate(combined):
        if kind == 'dialog':
            if item['name']:
                e = {'id':eid,'name':item['name'],'pre_jp':item['text'],'message':item['text']}
            else:
                e = {'id':eid,'pre_jp':item['text'],'message':item['text']}
            json_items.append(e)
            meta_items.append({'id':eid,'kind':'chapter' if item['is_chapter'] else 'dialog',
                               'record_idx':item['record_idx'],'text_off':TEXT_OFF,
                               'text_max':TEXT_MAX_NAME if item['is_chapter'] else TEXT_MAX_DIALOG})
        else:
            json_items.append({'id':eid,'pre_jp':item['text'],'message':item['text'],'kind':'sel'})
            meta_items.append({'id':eid,'kind':'sel','record_idx':item['record_idx'],
                               'text_off':SEL_OFF,'text_max':SEL_MAX})
    os.makedirs(out_dir, exist_ok=True)
    json_path = os.path.join(out_dir, base+'.json')
    meta_path = os.path.join(out_dir, base+'.json.meta.json')
    json.dump(json_items, open(json_path,'w',encoding='utf-8'), ensure_ascii=False, indent=2)
    json.dump({'file':fname,'entries':meta_items}, open(meta_path,'w',encoding='utf-8'), ensure_ascii=False, indent=2)
    sel_cnt   = sum(1 for e in json_items if e.get('kind')=='sel')
    named_cnt = sum(1 for e in json_items if e.get('name'))
    print(f"  [提取] {fname}: {len(json_items)} 条（对话 {len(json_items)-sel_cnt}，选项 {sel_cnt}，有名字 {named_cnt}）")

def do_extract(args):
    if os.path.isfile(args.input):
        extract_bin(args.input, args.output)
    else:
        files = sorted(f for f in os.listdir(args.input) if f.upper().endswith('.BIN') and not f.startswith('_'))
        if not files: print(f"[警告] {args.input} 中无 .BIN 文件"); return
        os.makedirs(args.output, exist_ok=True); n = 0
        for fname in files:
            try: extract_bin(os.path.join(args.input,fname), args.output); n+=1
            except Exception as e: print(f"  [错误] {fname}: {e}")
        print(f"[提取完成] 共 {n} 个文件")


def inject_bin(orig_path, json_path, out_path):
    fname = os.path.basename(orig_path)
    data  = bytearray(open(orig_path,'rb').read())
    trans = json.load(open(json_path,encoding='utf-8'))
    meta_path = json_path+'.meta.json'
    if not os.path.exists(meta_path):
        print(f"  [警告] 缺少 meta: {meta_path}，跳过"); return
    meta     = json.load(open(meta_path,encoding='utf-8'))
    tr_map   = {t['id']:t for t in trans}
    meta_map = {m['id']:m for m in meta['entries']}

    total_recs = len(data) // BLOCK
    last_name_rec = -1
    dialog_to_name_rec = {}
    for i in range(total_recs):
        op = data[i*BLOCK]
        if op == OP_NAME:
            last_name_rec = i
        elif op == OP_DIALOG and last_name_rec != -1 and i - last_name_rec <= 5:
            dialog_to_name_rec[i] = last_name_rec
            last_name_rec = -1

    ok=trunc=skip=0
    for eid, m in meta_map.items():
        tr = tr_map.get(eid)
        if tr is None: skip+=1; continue
        msg = tr.get('message','').strip()
        if not msg: skip+=1; continue
        kind = m.get('kind','dialog')
        safe_max = m.get('text_max', TEXT_MAX_DIALOG if kind == 'dialog' else (SEL_MAX if kind == 'sel' else TEXT_MAX_NAME))
        enc = _encode_trunc(msg, safe_max, eid, f' ({fname})')
        if enc is None: skip+=1; continue
        rec_base = m['record_idx'] * BLOCK
        off = rec_base + m['text_off']
        data[off:off+safe_max] = enc
        if kind == 'dialog':
            data[rec_base+131:rec_base+144] = bytes(13)
            new_name = tr.get('name','').strip()
            if new_name and m['record_idx'] in dialog_to_name_rec:
                name_rec_idx = dialog_to_name_rec[m['record_idx']]
                enc_name = _encode_trunc(new_name, TEXT_MAX_NAME, eid, f' name ({fname})')
                if enc_name is not None:
                    data[name_rec_idx*BLOCK + TEXT_OFF : name_rec_idx*BLOCK + TEXT_OFF + TEXT_MAX_NAME] = enc_name
        elif kind == 'sel':
            data[rec_base+131:rec_base+144] = bytes(13)
        if len(msg.encode(ENC_W,'replace')) > safe_max: trunc+=1
        else: ok+=1
    os.makedirs(os.path.dirname(out_path) or '.', exist_ok=True)
    open(out_path,'wb').write(data)
    print(f"  [注入] {fname}: {ok} ok，{trunc} 截断，{skip} 跳过")

def do_inject(args):
    if os.path.isfile(args.input):
        inject_bin(args.input, args.json_dir, args.out_dir)
    else:
        files = sorted(f for f in os.listdir(args.json_dir) if f.endswith('.json') and not f.endswith('.meta.json'))
        if not files: print(f"[警告] {args.json_dir} 中无 JSON"); return
        os.makedirs(args.out_dir, exist_ok=True); n=0
        for jf in files:
            scr = jf.replace('.json','.BIN')
            orig = os.path.join(args.input, scr)
            if not os.path.exists(orig):
                orig2 = os.path.join(args.input, scr.upper())
                if os.path.exists(orig2): orig=orig2
                else: print(f"  [警告] 找不到: {scr}"); continue
            try:
                inject_bin(orig, os.path.join(args.json_dir,jf), os.path.join(args.out_dir,os.path.basename(orig))); n+=1
            except Exception as e: print(f"  [错误] {jf}: {e}")
        print(f"[注入完成] 共 {n} 个文件")


def main():
    ap = argparse.ArgumentParser(description='NEJII script.dat 工具 (读CP932/写GBK)')
    sub = ap.add_subparsers(dest='cmd', required=True)
    p=sub.add_parser('unpack');  p.add_argument('dat'); p.add_argument('out')
    p=sub.add_parser('pack');    p.add_argument('src'); p.add_argument('dat')
    p=sub.add_parser('verify');  p.add_argument('dat')
    p=sub.add_parser('list');    p.add_argument('dat')
    p=sub.add_parser('extract'); p.add_argument('input'); p.add_argument('-o','--output',required=True)
    p=sub.add_parser('inject');  p.add_argument('input'); p.add_argument('json_dir'); p.add_argument('-o','--out-dir',required=True,dest='out_dir')
    args = ap.parse_args()

    if args.cmd == 'unpack':
        unpack(args.dat, args.out)
    elif args.cmd == 'pack':
        pack(args.src, args.dat)
    elif args.cmd == 'list':
        data = open(args.dat,'rb').read(); entries = parse_cdt(data)
        print(f"{args.dat}: {len(entries)} 个文件")
        for i,(name,off,size,unp,pk) in enumerate(entries):
            print(f"  [{i:3d}] {name:16s} @0x{off:06x} {size:6d}B -> {unp:6d}B {'LZSS' if pk else 'raw'}")
    elif args.cmd == 'verify':
        import tempfile
        data = open(args.dat,'rb').read(); entries = parse_cdt(data)
        with tempfile.TemporaryDirectory() as td:
            unpack(args.dat, td); ok=True
            for name,off,size,unp,pk in entries:
                orig_dec = lzss_decompress(data[off:off+size],unp) if pk else data[off:off+size]
                if orig_dec != open(os.path.join(td,name),'rb').read():
                    print(f"  [FAIL] {name}"); ok=False
            print(f"\n*** {'全部验证通过' if ok else '存在差异'} ({len(entries)} 个文件) ***")
    elif args.cmd == 'extract':
        do_extract(args)
    elif args.cmd == 'inject':
        do_inject(args)

if __name__ == '__main__':
    main()
