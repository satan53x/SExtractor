#!/usr/bin/env python3
"""
Overflow SCR 脚本文本提取/导入工具
格式: UTF-16LE 编码, null 分隔 token 流
模式: chr_set → 【角色名】→ Setmes → 对话文本 → Putmes

用法:
  python scr_text.py extract  <scr文件> [json文件]
  python scr_text.py insert   <scr文件> <json文件> [输出scr]
  python scr_text.py batch_e  <scr目录> <json输出目录>
  python scr_text.py batch_i  <scr目录> <json目录> [输出目录]
"""

import sys, os, json, glob

# ─────────────────────────── 核心解析 ───────────────────────────

def scr_to_tokens(data: bytes) -> list:
    """将SCR二进制数据解析为UTF-16LE token列表"""
    return data.decode('utf-16-le').split('\x00')

def tokens_to_scr(tokens: list) -> bytes:
    """将token列表重新编码为SCR二进制"""
    return '\x00'.join(tokens).encode('utf-16-le')

def extract_messages(tokens: list) -> list:
    """
    从token流提取 name-message 配对
    返回: [{"name": str, "message": str, "_token_idx": int}, ...]
    _token_idx: 对话文本在token列表中的位置（用于导入时精确定位）
    """
    messages = []
    current_name = ""
    i = 0
    while i < len(tokens):
        t = tokens[i]

        if t == 'chr_set':
            if i + 1 < len(tokens):
                nxt = tokens[i + 1]
                if nxt.startswith('【'):
                    # 提取角色名 (去掉【】)
                    current_name = nxt[1:-1] if nxt.endswith('】') else nxt[1:]
                    i += 2
                    continue
                else:
                    # 无角色名 = 旁白
                    current_name = ""
                    i += 1
                    continue

        elif t == 'Setmes':
            if i + 1 < len(tokens):
                text = tokens[i + 1]
                # 过滤掉指令token，只取真正的对话文本
                if text and text not in ('Putmes', 'chr_set', 'Fade', 'Ldbg',
                                          'Ldev', 'Playbgm', 'Playse', 'Wait',
                                          'Stopbgm') \
                       and not (text.isascii() and len(text) < 20):
                    messages.append({
                        "name": current_name,
                        "message": text,
                        "_token_idx": i + 1
                    })
            i += 2
            continue

        i += 1

    return messages

def insert_messages(tokens: list, messages: list) -> list:
    """
    将翻译后的文本导入回token流
    messages 中每条需含 _token_idx 和 message (或 message_zh)
    """
    tokens = list(tokens)  # 不修改原始列表
    for m in messages:
        idx = m['_token_idx']
        # 优先使用 message_zh，否则用 message
        new_text = m.get('message_zh', m.get('message', ''))
        if 0 <= idx < len(tokens):
            tokens[idx] = new_text
        # 如果有翻译后的角色名
        if 'name_zh' in m and m['name_zh']:
            # 角色名在 _token_idx 往前找最近的【xxx】
            for j in range(idx - 1, max(idx - 5, -1), -1):
                if tokens[j].startswith('【'):
                    tokens[j] = '【' + m['name_zh'] + '】'
                    break
    return tokens

# ─────────────────────────── 命令实现 ───────────────────────────

def cmd_extract(scr_path, json_path=None):
    data = open(scr_path, 'rb').read()
    tokens = scr_to_tokens(data)
    messages = extract_messages(tokens)

    # 输出格式: GalTransl JSON
    output = []
    for m in messages:
        entry = {"name": m["name"], "message": m["message"], "_token_idx": m["_token_idx"]}
        output.append(entry)

    if json_path is None:
        json_path = os.path.splitext(scr_path)[0] + '.json'

    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"  {os.path.basename(scr_path)}: {len(output)} messages → {os.path.basename(json_path)}")
    return output

def cmd_insert(scr_path, json_path, out_path=None):
    data = open(scr_path, 'rb').read()
    tokens = scr_to_tokens(data)

    with open(json_path, 'r', encoding='utf-8') as f:
        messages = json.load(f)

    new_tokens = insert_messages(tokens, messages)
    new_data = tokens_to_scr(new_tokens)

    if out_path is None:
        out_path = scr_path

    with open(out_path, 'wb') as f:
        f.write(new_data)

    print(f"  {os.path.basename(scr_path)}: {len(messages)} messages → {os.path.basename(out_path)}")

def cmd_batch_extract(scr_dir, json_dir):
    os.makedirs(json_dir, exist_ok=True)

    scr_files = sorted(glob.glob(os.path.join(scr_dir, '*.scr')))
    if not scr_files:
        # 大小写不敏感
        scr_files = sorted(glob.glob(os.path.join(scr_dir, '*.SCR')))
    if not scr_files:
        # os.listdir fallback
        scr_files = sorted([
            os.path.join(scr_dir, f) for f in os.listdir(scr_dir)
            if f.lower().endswith('.scr')
        ])

    total_msgs = 0
    total_files = 0

    for scr_path in scr_files:
        basename = os.path.splitext(os.path.basename(scr_path))[0]
        json_path = os.path.join(json_dir, basename + '.json')

        try:
            data = open(scr_path, 'rb').read()
            tokens = scr_to_tokens(data)
            messages = extract_messages(tokens)

            if not messages:
                continue

            output = [{"name": m["name"], "message": m["message"],
                       "_token_idx": m["_token_idx"]} for m in messages]

            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(output, f, ensure_ascii=False, indent=2)

            total_msgs += len(output)
            total_files += 1
            print(f"  {basename}.scr: {len(output)} messages")

        except Exception as e:
            print(f"  {basename}.scr: ERROR - {e}")

    print(f"\nTotal: {total_files} files, {total_msgs} messages")

def cmd_batch_insert(scr_dir, json_dir, out_dir=None):
    if out_dir is None:
        out_dir = scr_dir
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

        # 查找对应的scr文件（大小写不敏感）
        scr_path = None
        for ext in ['.scr', '.SCR']:
            candidate = os.path.join(scr_dir, basename + ext)
            if os.path.exists(candidate):
                scr_path = candidate
                break
        if scr_path is None:
            # listdir搜索
            for f in os.listdir(scr_dir):
                if f.lower() == basename.lower() + '.scr':
                    scr_path = os.path.join(scr_dir, f)
                    break

        if scr_path is None:
            print(f"  {basename}: scr not found, skip")
            fail += 1
            continue

        try:
            data = open(scr_path, 'rb').read()
            tokens = scr_to_tokens(data)

            with open(json_path, 'r', encoding='utf-8') as f:
                messages = json.load(f)

            new_tokens = insert_messages(tokens, messages)
            new_data = tokens_to_scr(new_tokens)

            out_name = os.path.basename(scr_path)
            out_path = os.path.join(out_dir, out_name)
            with open(out_path, 'wb') as f:
                f.write(new_data)

            ok += 1
            total += len(messages)
            print(f"  {basename}: {len(messages)} messages")

        except Exception as e:
            print(f"  {basename}: ERROR - {e}")
            fail += 1

    print(f"\nTotal: {ok} files, {total} messages, {fail} errors")

# ─────────────────────────── 入口 ───────────────────────────

def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)

    cmd = sys.argv[1].lower()

    if cmd in ('extract', 'e'):
        scr = sys.argv[2]
        json_out = sys.argv[3] if len(sys.argv) > 3 else None
        cmd_extract(scr, json_out)

    elif cmd in ('insert', 'i'):
        if len(sys.argv) < 4:
            print("Usage: insert <scr> <json> [output_scr]")
            sys.exit(1)
        scr = sys.argv[2]
        jp = sys.argv[3]
        out = sys.argv[4] if len(sys.argv) > 4 else None
        cmd_insert(scr, jp, out)

    elif cmd in ('batch_e', 'be'):
        scr_dir = sys.argv[2]
        json_dir = sys.argv[3] if len(sys.argv) > 3 else os.path.join(sys.argv[2], 'json_out')
        cmd_batch_extract(scr_dir, json_dir)

    elif cmd in ('batch_i', 'bi'):
        if len(sys.argv) < 4:
            print("Usage: batch_i <scr_dir> <json_dir> [out_dir]")
            sys.exit(1)
        scr_dir = sys.argv[2]
        json_dir = sys.argv[3]
        out_dir = sys.argv[4] if len(sys.argv) > 4 else None
        cmd_batch_insert(scr_dir, json_dir, out_dir)

    else:
        print(f"Unknown command: {cmd}")
        print(__doc__)
        sys.exit(1)

if __name__ == '__main__':
    main()
