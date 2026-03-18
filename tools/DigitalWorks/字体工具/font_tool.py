#!/usr/bin/env python3
"""
BunBun Engine font32.dat 字体重绘工具

基于subs_cn_jp.json替换表：
  - 遍历原始font32.dat的每个JIS槽位
  - 该槽位的字符在替换表中 → 用TTF渲染对应的中文字符写入同一槽位
  - 不在替换表中 → 从原始dat原样复制字形
  
SJIS编码不变，脚本文本不用改，只替换字体中的字形。

font32.dat格式:
  89页×256×256 BGRA32, 每页10×10=100字符, 每字符24×24像素
  白色(255,255,255) + Alpha通道抗锯齿

用法:
  python font_tool.py dump   <font32.dat> <output.txt>
  python font_tool.py build  <原始font32.dat> <subs.json> <字体.ttf> <输出font32.dat> [--size 22]
"""

import struct, sys, os, argparse, json

PAGE_SIZE  = 0x40000
PAGE_W     = 256
CHAR_W     = 24
CHAR_H     = 24
COLS       = 10
PER_PAGE   = 100
TOTAL_PAGES = 89
TOTAL_SLOTS = TOTAL_PAGES * PER_PAGE


def jis_to_sjis(jhi, jlo):
    s1 = (jhi + 1) // 2 + (0x70 if jhi <= 0x5E else 0xB0)
    if jhi % 2 == 1:
        s2 = jlo + (0x1F if jlo <= 0x5F else 0x20)
    else:
        s2 = jlo + 0x7E
    return s1, s2


def slot_to_char(idx):
    """线性槽位 → Unicode字符"""
    val = idx + 3135
    jhi, jlo = val // 94, val % 94
    if not (0x21 <= jhi <= 0x7E and 0x21 <= jlo <= 0x7E):
        return None
    s1, s2 = jis_to_sjis(jhi, jlo)
    try:
        return bytes([s1, s2]).decode('cp932')
    except:
        return None


def slot_rect(idx):
    """槽位 → (page, cx, cy)"""
    page = idx // PER_PAGE
    pos  = idx % PER_PAGE
    cx   = (pos % COLS) * CHAR_W
    cy   = (pos // COLS) * CHAR_H
    return page, cx, cy


def has_real_glyph(data, idx):
    PLACEHOLDER = ((8,11,132),(9,11,132),(8,12,252),(9,12,252),(8,13,180),(9,13,180))
    page, cx, cy = slot_rect(idx)
    base = page * PAGE_SIZE
    pixels = []
    for y in range(CHAR_H):
        for x in range(CHAR_W):
            a = data[base + ((cy+y)*PAGE_W+(cx+x))*4 + 3]
            if a != 0:
                pixels.append((x, y, a))
    return len(pixels) > 0 and tuple(pixels) != PLACEHOLDER


def cmd_dump(args):
    with open(args.font_dat, 'rb') as f:
        data = f.read()
    chars = []
    for idx in range(TOTAL_SLOTS):
        ch = slot_to_char(idx)
        if ch and has_real_glyph(data, idx):
            chars.append(ch)
    with open(args.output_txt, 'w', encoding='utf-8') as f:
        f.write(''.join(chars))
    print(f"Exported {len(chars)} characters to {args.output_txt}")


def sjis_to_slot(s1, s2):
    """引擎算法: SJIS双字节 → font32.dat线性槽位"""
    if 0x81 <= s1 <= 0x9F:
        hi = s1 - 0x81
    elif 0xE0 <= s1 <= 0xEF:
        hi = s1 - 0xC1
    else:
        return None
    if 0x40 <= s2 <= 0x7E:
        jis = hi * 0x200 + s2 + 0x20E1
    elif 0x80 <= s2 <= 0x9E:
        jis = hi * 0x200 + s2 + 0x20E0
    elif 0x9F <= s2 <= 0xFC:
        jis = (hi * 2 + 1) * 0x100 + 0x2121 + (s2 - 0x9F)
    else:
        return None
    return ((jis & 0xFF) - 0xC3F) + (jis >> 8) * 0x5E


def char_to_slot(ch):
    """Unicode字符 → font32.dat槽位"""
    try:
        b = ch.encode('cp932')
    except:
        return None
    if len(b) != 2:
        return None
    return sjis_to_slot(b[0], b[1])


def cmd_build(args):
    try:
        from PIL import Image, ImageFont, ImageDraw
    except ImportError:
        sys.exit("pip install Pillow")

    # 读原始font32.dat
    with open(args.orig_dat, 'rb') as f:
        orig = f.read()
    if len(orig) != TOTAL_PAGES * PAGE_SIZE:
        sys.exit(f"原始font32.dat大小不对: {len(orig)}")

    # 读替换表: {中文: 日文} → 反转为 {日文: 中文}
    with open(args.subs_json, 'r', encoding='utf-8') as f:
        subs_cn_jp = json.load(f)
    jp_to_cn = {v: k for k, v in subs_cn_jp.items()}
    print(f"替换表: {len(jp_to_cn)} 条 (日文→中文)")

    # 加载TTF字体
    font_size = args.size
    try:
        font = ImageFont.truetype(args.ttf_font, font_size)
    except IOError:
        sys.exit(f"无法加载字体: {args.ttf_font}")
    print(f"字体: {args.ttf_font}  字号: {font_size}")

    # 从原始dat复制全部数据作为基础
    output = bytearray(orig)

    # 遍历替换表，用SJIS编码直接算槽位
    replaced = 0
    skipped = 0
    for jp_char, cn_char in jp_to_cn.items():
        idx = char_to_slot(jp_char)
        if idx is None or idx < 0 or idx >= TOTAL_SLOTS:
            skipped += 1
            continue

        page, cx, cy = slot_rect(idx)

        # 用TTF渲染中文字符 24×24
        tmp = Image.new('RGBA', (CHAR_W, CHAR_H), (0, 0, 0, 0))
        draw = ImageDraw.Draw(tmp)
        bbox = font.getbbox(cn_char)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        tx = (CHAR_W - tw) // 2 - bbox[0]
        ty = (CHAR_H - th) // 2 - bbox[1]
        draw.text((tx, ty), cn_char, font=font, fill=(255, 255, 255, 255))

        # 写入对应槽位 (BGRA)
        base = page * PAGE_SIZE
        for y in range(CHAR_H):
            for x in range(CHAR_W):
                r, g, b, a = tmp.getpixel((x, y))
                off = base + ((cy+y)*PAGE_W + (cx+x)) * 4
                output[off]   = b
                output[off+1] = g
                output[off+2] = r
                output[off+3] = a

        replaced += 1
        if replaced % 500 == 0:
            print(f"  已替换 {replaced}/{len(jp_to_cn)}...")

    with open(args.output_dat, 'wb') as f:
        f.write(output)

    print(f"完成: {replaced} 个字符重绘, {skipped} 个跳过, 其余原样保留")
    print(f"输出: {args.output_dat} ({len(output)} bytes)")


def main():
    p = argparse.ArgumentParser(description='BunBun font32.dat 重绘工具')
    sub = p.add_subparsers(dest='cmd')

    s1 = sub.add_parser('dump', help='提取字符表')
    s1.add_argument('font_dat'); s1.add_argument('output_txt')

    s2 = sub.add_parser('build', help='基于替换表重绘font32.dat')
    s2.add_argument('orig_dat', help='原始font32.dat')
    s2.add_argument('subs_json', help='subs_cn_jp.json替换表')
    s2.add_argument('ttf_font', help='中文TTF字体')
    s2.add_argument('output_dat', help='输出font32.dat')
    s2.add_argument('--size', type=int, default=22, help='字号(默认22)')

    args = p.parse_args()
    {'dump': cmd_dump, 'build': cmd_build}.get(args.cmd, lambda a: p.print_help())(args)

if __name__ == '__main__':
    main()
