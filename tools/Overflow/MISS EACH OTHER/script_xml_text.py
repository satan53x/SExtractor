#!/usr/bin/env python3
"""
Script XML 文本提取/导入工具
格式: <Script><TextResource><TextRes NO="N">文本</TextRes>...
对话: <Frame><Log NAME="角色编号" MESS="对话编号" />
通过 TextRes NO 引用角色名和对话文本

用法:
  python script_xml_text.py extract  <xml文件> [json文件]
  python script_xml_text.py insert   <xml文件> <json文件> [输出xml]
  python script_xml_text.py batch_e  <xml目录> <json输出目录>
  python script_xml_text.py batch_i  <xml目录> <json目录> [输出目录]
"""

import sys, os, json, glob, re
import xml.etree.ElementTree as ET

# ─────────────────────────── 核心解析 ───────────────────────────

def extract_messages(tree):
    """
    从XML提取对话: Log节点的 NAME/MESS 引用 TextRes
    返回: [{"name":str, "message":str, "name_id":str, "mess_id":str}, ...]
    """
    root = tree.getroot()

    # 构建 TextRes 映射
    text_res = {}
    for tr in root.findall('.//TextRes'):
        no = tr.get('NO')
        if no is not None:
            text_res[no] = tr.text or ''

    # 提取所有 Log 节点
    results = []
    seen = set()  # 去重 (同一 MESS 可能出现多次)
    for log in root.findall('.//Log'):
        name_id = log.get('NAME', '')
        mess_id = log.get('MESS', '')

        if not mess_id or mess_id in seen:
            continue
        seen.add(mess_id)

        name = text_res.get(name_id, '')
        message = text_res.get(mess_id, '')

        if not message:
            continue

        results.append({
            'name': name,
            'message': message,
            'name_id': name_id,
            'mess_id': mess_id,
        })

    return results, text_res


def insert_messages(tree, messages):
    """
    将翻译导入回XML: 修改 TextRes 节点的文本内容
    通过 mess_id 精确定位
    """
    root = tree.getroot()

    # 建立 mess_id → 翻译 的映射
    trans_map = {}
    name_trans = {}
    for m in messages:
        mid = m.get('mess_id', '')
        if mid:
            new_text = m.get('message_zh', m.get('message', ''))
            trans_map[mid] = new_text
        # 角色名翻译
        nid = m.get('name_id', '')
        if nid and 'name_zh' in m and m['name_zh']:
            name_trans[nid] = m['name_zh']

    # 修改 TextRes 节点
    for tr in root.findall('.//TextRes'):
        no = tr.get('NO')
        if no in trans_map:
            tr.text = trans_map[no]
        if no in name_trans:
            tr.text = name_trans[no]

    return tree

# ─────────────────────────── 命令实现 ───────────────────────────

def cmd_extract(xml_path, json_path=None):
    tree = ET.parse(xml_path)
    messages, _ = extract_messages(tree)

    output = [{
        "name": m["name"],
        "message": m["message"],
        "name_id": m["name_id"],
        "mess_id": m["mess_id"],
    } for m in messages]

    if json_path is None:
        json_path = os.path.splitext(xml_path)[0] + '.json'

    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"  {os.path.basename(xml_path)}: {len(output)} messages → {os.path.basename(json_path)}")
    return output


def cmd_insert(xml_path, json_path, out_path=None):
    tree = ET.parse(xml_path)

    with open(json_path, 'r', encoding='utf-8') as f:
        messages = json.load(f)

    tree = insert_messages(tree, messages)

    if out_path is None:
        out_path = xml_path

    tree.write(out_path, encoding='UTF-8', xml_declaration=True)

    print(f"  {os.path.basename(xml_path)}: {len(messages)} entries → {os.path.basename(out_path)}")


def cmd_batch_extract(xml_dir, json_dir):
    os.makedirs(json_dir, exist_ok=True)

    xml_files = sorted([
        os.path.join(xml_dir, f) for f in os.listdir(xml_dir)
        if f.lower().endswith('.xml')
    ])

    total_msgs = 0
    total_files = 0

    for xml_path in xml_files:
        basename = os.path.splitext(os.path.basename(xml_path))[0]
        json_path = os.path.join(json_dir, basename + '.json')

        try:
            tree = ET.parse(xml_path)
            messages, _ = extract_messages(tree)

            if not messages:
                continue

            output = [{
                "name": m["name"],
                "message": m["message"],
                "name_id": m["name_id"],
                "mess_id": m["mess_id"],
            } for m in messages]

            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(output, f, ensure_ascii=False, indent=2)

            total_msgs += len(output)
            total_files += 1
            print(f"  {basename}.xml: {len(output)} messages")

        except Exception as e:
            print(f"  {basename}.xml: ERROR - {e}")

    print(f"\nTotal: {total_files} files, {total_msgs} messages")


def cmd_batch_insert(xml_dir, json_dir, out_dir=None):
    if out_dir is None:
        out_dir = xml_dir
    os.makedirs(out_dir, exist_ok=True)

    json_files = sorted([
        f for f in os.listdir(json_dir)
        if f.lower().endswith('.json')
    ])

    total = 0
    ok = 0
    fail = 0

    for jf in json_files:
        basename = os.path.splitext(jf)[0]
        json_path = os.path.join(json_dir, jf)

        # 查找对应xml (大小写不敏感)
        xml_path = None
        for f in os.listdir(xml_dir):
            if f.lower() == basename.lower() + '.xml':
                xml_path = os.path.join(xml_dir, f)
                break

        if xml_path is None:
            print(f"  {basename}: xml not found, skip")
            fail += 1
            continue

        try:
            tree = ET.parse(xml_path)

            with open(json_path, 'r', encoding='utf-8') as f:
                messages = json.load(f)

            tree = insert_messages(tree, messages)

            out_name = os.path.basename(xml_path)
            out_path = os.path.join(out_dir, out_name)
            tree.write(out_path, encoding='UTF-8', xml_declaration=True)

            ok += 1
            total += len(messages)
            print(f"  {basename}: {len(messages)} entries")

        except Exception as e:
            print(f"  {basename}: ERROR - {e}")
            fail += 1

    print(f"\nTotal: {ok} files, {total} entries, {fail} errors")

# ─────────────────────────── 入口 ───────────────────────────

def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)

    cmd = sys.argv[1].lower()

    if cmd in ('extract', 'e'):
        xml_f = sys.argv[2]
        json_out = sys.argv[3] if len(sys.argv) > 3 else None
        cmd_extract(xml_f, json_out)

    elif cmd in ('insert', 'i'):
        if len(sys.argv) < 4:
            print("Usage: insert <xml> <json> [output_xml]")
            sys.exit(1)
        cmd_insert(sys.argv[2], sys.argv[3], sys.argv[4] if len(sys.argv) > 4 else None)

    elif cmd in ('batch_e', 'be'):
        xml_dir = sys.argv[2]
        json_dir = sys.argv[3] if len(sys.argv) > 3 else os.path.join(sys.argv[2], 'json_out')
        cmd_batch_extract(xml_dir, json_dir)

    elif cmd in ('batch_i', 'bi'):
        if len(sys.argv) < 4:
            print("Usage: batch_i <xml_dir> <json_dir> [out_dir]")
            sys.exit(1)
        cmd_batch_insert(sys.argv[2], sys.argv[3], sys.argv[4] if len(sys.argv) > 4 else None)

    else:
        print(f"Unknown command: {cmd}")
        print(__doc__)
        sys.exit(1)

if __name__ == '__main__':
    main()
