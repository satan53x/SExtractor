#!/usr/bin/env python3
"""
srv2_xml_text.py - サマーラディッシュバケーション2 XML脚本 文本提取/导入工具

XML脚本结构:
  <RESOURCE no="N">
    <CREATE type="INT">0</CREATE>            <!-- 字段0 -->
    <CREATE type="GSCRIPT">N</CREATE>        <!-- 序号 -->
    <CREATE type="STR">台词文本</CREATE>      <!-- 文本 -->
    <CREATE type="INT">角色ID</CREATE>        <!-- 角色 -->
    <CREATE type="INT">1</CREATE>            <!-- 字段4 -->
    <CREATE type="STR">voice路径</CREATE>     <!-- voice -->
  </RESOURCE>
  <FUNCTION name="MESSAGE"/>                  <!-- 显示指令 -->

角色对照表 (从全65个XML台词内容+路线文件名推断):
  -1=旁白  0=りでる  1=りでるの母  2=さゆ  3=空  4=時姉
  5=空の母  6=間  7=理央  8=理香  9=斗真  51=神楽  ...

提取格式: GalTransl JSON (UTF-8)

用法:
  python srv2_xml_text.py extract  input.xml  [output.json]
  python srv2_xml_text.py insert   input.xml  input.json  [output.xml]
  python srv2_xml_text.py batch_e  xml_dir    [json_dir]
  python srv2_xml_text.py batch_i  xml_dir    json_dir    [out_dir]
"""

import json, sys, os, glob
import xml.etree.ElementTree as ET

# ============================================================
# 角色对照表
# ============================================================

CHAR_NAMES = {
    -1: "",
    0:  "りでる",
    1:  "りでるの母",
    2:  "さゆ",
    3:  "空",
    4:  "時姉",
    5:  "空の母",
    6:  "間",
    7:  "理央",
    8:  "理香",
    9:  "斗真",
    10: "妹キャラ",
    11: "妹の付添",
    12: "お料理くん",
    13: "客A",
    14: "客B",
    15: "モブ",
    16: "赤ちゃん",
    17: "客C",
    18: "客D",
    19: "女性客",
    20: "救急隊員",
    21: "行列の人",
    51: "神楽",
    333: "空",
}


# ============================================================
# 提取
# ============================================================

def extract(xml_path, json_path=None):
    """提取XML文本到GalTransl JSON"""
    if json_path is None:
        json_path = os.path.splitext(xml_path)[0] + '.json'

    tree = ET.parse(xml_path)
    root = tree.getroot()

    entries = []
    idx = 0
    for res in root.iter('RESOURCE'):
        creates = list(res.iter('CREATE'))
        if len(creates) < 4:
            continue

        text = creates[2].text or ''
        if not text.strip():
            continue

        try:
            char_id = int(creates[3].text)
        except (ValueError, TypeError):
            char_id = -1

        voice = creates[5].text if len(creates) >= 6 else ''
        res_no = res.get('no', '')
        name = CHAR_NAMES.get(char_id, str(char_id))

        entry = {
            "name": name,
            "message": text,
            "_idx": idx,
            "_res_no": res_no,
        }
        if voice:
            entry["_voice"] = voice

        entries.append(entry)
        idx += 1

    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(entries, f, ensure_ascii=False, indent=2)

    basename = os.path.basename(xml_path)
    outname = os.path.basename(json_path)
    msg_count = sum(1 for e in entries if e.get('message', '').strip())
    print(f"  {basename}: {len(entries)} entries, {msg_count} messages -> {outname}")
    return entries


# ============================================================
# 导入
# ============================================================

def insert(xml_path, json_path, out_path=None):
    """将翻译后的JSON导入XML"""
    if out_path is None:
        out_path = xml_path

    with open(json_path, 'r', encoding='utf-8') as f:
        entries = json.load(f)

    # 建立 res_no -> new_text 映射
    text_map = {}
    for e in entries:
        res_no = str(e.get('_res_no', ''))
        if res_no:
            text_map[res_no] = e.get('message', '')

    tree = ET.parse(xml_path)
    root = tree.getroot()

    replaced = 0
    for res in root.iter('RESOURCE'):
        res_no = res.get('no', '')
        if res_no not in text_map:
            continue

        creates = list(res.iter('CREATE'))
        if len(creates) >= 3:
            creates[2].text = text_map[res_no]
            replaced += 1

    # 写出时保持XML声明
    tree.write(out_path, encoding='unicode', xml_declaration=True)

    basename = os.path.basename(xml_path)
    outname = os.path.basename(out_path)
    print(f"  {basename}: {replaced} entries replaced -> {outname}")


# ============================================================
# 批量
# ============================================================

def batch_extract(xml_dir, json_dir=None):
    """批量提取"""
    if json_dir is None:
        json_dir = xml_dir
    os.makedirs(json_dir, exist_ok=True)

    files = sorted(glob.glob(os.path.join(xml_dir, '*.XML')) +
                   glob.glob(os.path.join(xml_dir, '*.xml')))
    total = 0
    for fpath in files:
        bn = os.path.splitext(os.path.basename(fpath))[0]
        jp = os.path.join(json_dir, bn + '.json')
        entries = extract(fpath, jp)
        total += len(entries)

    print(f"\nTotal: {len(files)} files, {total} entries")


def batch_insert(xml_dir, json_dir, out_dir=None):
    """批量导入"""
    if out_dir is None:
        out_dir = xml_dir
    os.makedirs(out_dir, exist_ok=True)

    json_files = sorted(glob.glob(os.path.join(json_dir, '*.json')) +
                        glob.glob(os.path.join(json_dir, '*.JSON')))
    for jpath in json_files:
        bn = os.path.splitext(os.path.basename(jpath))[0]
        xp = os.path.join(xml_dir, bn + '.XML')
        if not os.path.exists(xp):
            xp = os.path.join(xml_dir, bn + '.xml')
        if not os.path.exists(xp):
            print(f"  WARNING: {bn}.XML not found, skipped")
            continue
        op = os.path.join(out_dir, bn + '.XML')
        insert(xp, jpath, op)


# ============================================================
# 主入口
# ============================================================

def print_usage():
    print("srv2_xml_text.py - サマーラディッシュバケーション2 XML脚本 文本提取/导入工具")
    print()
    print("提取格式: GalTransl JSON (UTF-8)")
    print('  { "name": "角色名", "message": "台词", "_idx": 0, "_res_no": "0" }')
    print()
    print("用法:")
    print("  python srv2_xml_text.py extract  input.xml  [output.json]")
    print("  python srv2_xml_text.py insert   input.xml  input.json  [output.xml]")
    print("  python srv2_xml_text.py batch_e  xml_dir    [json_dir]")
    print("  python srv2_xml_text.py batch_i  xml_dir    json_dir    [out_dir]")


if __name__ == '__main__':
    if len(sys.argv) < 3:
        print_usage()
        sys.exit(0)

    cmd = sys.argv[1].lower()

    if cmd == 'extract':
        extract(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else None)
    elif cmd == 'insert':
        if len(sys.argv) < 4:
            print("Error: insert requires input.xml and input.json"); sys.exit(1)
        insert(sys.argv[2], sys.argv[3], sys.argv[4] if len(sys.argv) > 4 else None)
    elif cmd in ('batch_e', 'batch_extract'):
        batch_extract(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else None)
    elif cmd in ('batch_i', 'batch_insert'):
        if len(sys.argv) < 4:
            print("Error: batch_i requires xml_dir and json_dir"); sys.exit(1)
        batch_insert(sys.argv[2], sys.argv[3], sys.argv[4] if len(sys.argv) > 4 else None)
    else:
        print(f"Unknown command: {cmd}"); print_usage(); sys.exit(1)
