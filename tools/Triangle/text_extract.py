# -*- coding: utf-8 -*-
"""
text_extract.py  ——  从 MOP 引擎 .SD 脚本提取待翻译文本（旁白/对话 + 选择肢）

用法:
    python text_extract.py MOPN.SD                 # 生成 MOPN.json + MOPN.meta.json
    python text_extract.py MOPN.SD out.json         # 指定输出 json

输出 json 格式（GalTransl 兼容）：
    [{"id":0, "pre_jp":"日文原文", "message":"日文原文"}, ...]
  - 一条 op74 消息（多正文行已拼接、删除换行）为一条；一个 op75 选项为一条。
  - 按文件出现顺序连续编号，对话与选择肢混排。
  - 人名为引用式索引(N值)，真正的名字串(如 男の声)不在 .SD 内，故不输出 name 字段；
    N 索引记录在 meta 内，便于将来若拿到名字池再做映射。

同时生成 *.meta.json（注入时定位每个 id 的位置；也供调试）。
"""
import sys, os, json
import mop_sd as M


def extract(path):
    data = open(path, 'rb').read()
    insts, _ = M.disassemble(data)

    entries = []     # 输出给翻译的条目
    meta = []        # 每条的定位信息
    nid = 0
    for ii, inst in enumerate(insts):
        if inst.kind == 'text':
            for (seg_idx, joined, name_idx) in M.iter_messages(inst):
                txt = M.decode_cp932(joined)
                entries.append({"id": nid, "pre_jp": txt, "message": txt})
                meta.append({"id": nid, "type": "msg",
                             "inst": ii, "off": inst.off,
                             "seg": seg_idx, "name_idx": name_idx})
                nid += 1
        elif inst.kind == 'choice':
            for oi, raw in enumerate(inst.opts):
                txt = M.decode_cp932(raw)
                entries.append({"id": nid, "pre_jp": txt, "message": txt})
                meta.append({"id": nid, "type": "opt",
                             "inst": ii, "off": inst.off, "opt": oi})
                nid += 1
    return entries, meta


def main():
    if len(sys.argv) < 2:
        print(__doc__); sys.exit(1)
    path = sys.argv[1]
    base = os.path.splitext(os.path.basename(path))[0]
    out_json = sys.argv[2] if len(sys.argv) > 2 else base + ".json"
    meta_json = os.path.splitext(out_json)[0] + ".meta.json"

    entries, meta = extract(path)

    with open(out_json, 'w', encoding='utf-8') as f:
        json.dump(entries, f, ensure_ascii=False, indent=2)
    with open(meta_json, 'w', encoding='utf-8') as f:
        json.dump({"source": os.path.basename(path), "count": len(entries),
                   "items": meta}, f, ensure_ascii=False, indent=2)

    n_msg = sum(1 for m in meta if m["type"] == "msg")
    n_opt = sum(1 for m in meta if m["type"] == "opt")
    print("已提取 %d 条： 消息 %d / 选择肢 %d" % (len(entries), n_msg, n_opt))
    print("  -> %s" % out_json)
    print("  -> %s" % meta_json)


if __name__ == '__main__':
    main()
