#!/usr/bin/env python3
"""
XML 脚本文本提取/导入工具
格式: XML (<SCRIPT><BLOCK>...<RESOURCE>...<FUNCTION name="MESSAGE"/>)
对话: RESOURCE[INT=0] + GSCRIPT + STR(文本) → FUNCTION MESSAGE
选择: RESOURCE[INT=1] + GSCRIPT + STR(选项) × N → FUNCTION SELECT
角色: FUNCTION LOADCHAR → STR(角色立绘ID) 作为当前角色标识

用法:
  python xml_text.py extract  <xml文件> [json文件]
  python xml_text.py insert   <xml文件> <json文件> [输出xml]
  python xml_text.py batch_e  <xml目录> <json输出目录>
  python xml_text.py batch_i  <xml目录> <json目录> [输出目录]
"""

import sys, os, json, glob
import xml.etree.ElementTree as ET

# ─────────────────────────── 核心解析 ───────────────────────────

def extract_messages(tree):
    """
    递归遍历XML树，提取对话和选择肢
    返回: [{"name":str, "message":str, "resource_no":str, "gscript":str, "type":"message"|"select"}, ...]
    """
    root = tree.getroot()
    results = []

    def walk(elem, current_char=''):
        for child in elem:
            if child.tag == 'FUNCTION':
                name = child.get('name')
                if name == 'LOADCHAR':
                    params = [c.text for c in child.findall('CREATE')]
                    if params and params[0]:
                        current_char = params[0]

            elif child.tag == 'RESOURCE':
                creates = list(child.findall('CREATE'))
                if not creates:
                    continue

                int0 = creates[0].text if creates[0].get('type') == 'INT' else '?'
                strs = [c.text or '' for c in creates if c.get('type') == 'STR']
                gs = [c.text or '' for c in creates if c.get('type') == 'GSCRIPT']
                no = child.get('no', '?')

                if int0 == '0' and strs:
                    # 对话
                    results.append({
                        'type': 'message',
                        'name': current_char,
                        'message': strs[0],
                        'resource_no': no,
                        'gscript': gs[0] if gs else '',
                    })
                elif int0 == '1' and strs:
                    # 选择肢
                    results.append({
                        'type': 'select',
                        'name': '',
                        'message': '|'.join(strs),  # 选项用|分隔
                        'resource_no': no,
                        'gscript': gs[0] if gs else '',
                    })

            elif child.tag in ('IFBLOCK', 'IF', 'ELSE', 'BLOCK'):
                walk(child, current_char)

    walk(root)
    return results


def insert_messages(tree, messages):
    """
    将翻译后的文本导入回XML树
    通过 resource_no + gscript 精确定位RESOURCE节点
    """
    root = tree.getroot()

    # 建立 resource_no → 翻译文本 的映射
    trans_map = {}
    for m in messages:
        key = m['resource_no']
        trans_map[key] = m

    # 遍历所有RESOURCE节点
    def walk_insert(elem):
        for child in elem:
            if child.tag == 'RESOURCE':
                no = child.get('no', '?')
                if no in trans_map:
                    t = trans_map[no]
                    new_text = t.get('message_zh', t.get('message', ''))

                    creates = list(child.findall('CREATE'))
                    int0 = creates[0].text if creates and creates[0].get('type') == 'INT' else '?'

                    if int0 == '0':
                        # 对话: 替换第一个STR
                        for c in creates:
                            if c.get('type') == 'STR':
                                c.text = new_text
                                break
                    elif int0 == '1':
                        # 选择肢: 用|分隔的文本还原多个STR
                        new_options = new_text.split('|')
                        str_creates = [c for c in creates if c.get('type') == 'STR']
                        for i, sc in enumerate(str_creates):
                            if i < len(new_options):
                                sc.text = new_options[i]

            elif child.tag in ('IFBLOCK', 'IF', 'ELSE', 'BLOCK'):
                walk_insert(child)

    walk_insert(root)
    return tree

# ─────────────────────────── 命令实现 ───────────────────────────

def cmd_extract(xml_path, json_path=None):
    tree = ET.parse(xml_path)
    messages = extract_messages(tree)

    output = []
    for i, m in enumerate(messages):
        entry = {
            "name": m["name"],
            "message": m["message"],
            "resource_no": m["resource_no"],
            "_type": m["type"],
        }
        output.append(entry)

    if json_path is None:
        json_path = os.path.splitext(xml_path)[0] + '.json'

    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    n_msg = sum(1 for m in messages if m['type'] == 'message')
    n_sel = sum(1 for m in messages if m['type'] == 'select')
    print(f"  {os.path.basename(xml_path)}: {n_msg} messages, {n_sel} selects → {os.path.basename(json_path)}")
    return output


def cmd_insert(xml_path, json_path, out_path=None):
    tree = ET.parse(xml_path)

    with open(json_path, 'r', encoding='utf-8') as f:
        messages = json.load(f)

    tree = insert_messages(tree, messages)

    if out_path is None:
        out_path = xml_path

    # 写入时保持XML声明
    tree.write(out_path, encoding='unicode', xml_declaration=True)

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
            messages = extract_messages(tree)

            if not messages:
                continue

            output = [{
                "name": m["name"],
                "message": m["message"],
                "resource_no": m["resource_no"],
                "_type": m["type"],
            } for m in messages]

            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(output, f, ensure_ascii=False, indent=2)

            n_msg = sum(1 for m in messages if m['type'] == 'message')
            total_msgs += n_msg
            total_files += 1
            print(f"  {basename}.XML: {n_msg} messages, {sum(1 for m in messages if m['type']=='select')} selects")

        except Exception as e:
            print(f"  {basename}.XML: ERROR - {e}")

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

        # 查找对应xml
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
            tree.write(out_path, encoding='unicode', xml_declaration=True)

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
