"""silky_pipeline.py — Silky MES 一站式批量处理（多进程并行）。

把 4 步流水线合成 2 个命令：

  unpack:  *.MES -> op.txt + translate.txt   (反汇编 + 提取)
  pack:    op.txt + translate.txt -> *.MES   (注入 + 汇编)

每个 .MES 独立处理，自动用所有 CPU 核心并行（可用 -j 控制）。

CLI:
  python silky_pipeline.py unpack <MES目录> <工作目录> [-j N]
    会在 <工作目录> 下生成:
      op/         反汇编 op.txt
      translate/  待翻译 translate.txt   <-- 把这一堆扔给 GalTransl

  python silky_pipeline.py pack <MES目录> <工作目录> <输出目录> [-j N]
    会读 <工作目录>/op + <工作目录>/translate 注入译文,
    再把注入后的 op.txt 编回 *.MES, 写到 <输出目录>。
"""

import argparse
import glob
import os
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def _strip_ext(name, exts):
    for e in exts:
        if name.lower().endswith(e.lower()):
            return name[:-len(e)]
    return os.path.splitext(name)[0]


def _default_workers():
    n = os.cpu_count() or 4
    return max(1, n - 1)


def _worker_unpack(args_tuple):
    mes_path, op_path, tr_path, encoding = args_tuple
    import silky_op
    import silky_extract
    try:
        sm = silky_op.SilkyMesScript(mes_path, op_path, encoding=encoding)
        sm.disassemble()
        n = silky_extract.extract_text(op_path, tr_path)
        return (os.path.basename(mes_path), n, None)
    except Exception as e:
        return (os.path.basename(mes_path), 0, repr(e))


def _worker_pack(args_tuple):
    base, op_path, tr_path, op2_path, out_mes, encoding = args_tuple
    import silky_op
    import silky_inject
    try:
        n = silky_inject.import_text(op_path, tr_path, op2_path)
    except Exception as e:
        return (base, 0, f"inject: {e!r}")
    try:
        sm = silky_op.SilkyMesScript(out_mes, op2_path, encoding=encoding)
        sm.assemble()
    except Exception as e:
        return (base, n, f"asm: {e!r}")
    return (base, n, None)


def cmd_unpack(args):
    op_dir = os.path.join(args.workdir, "op")
    tr_dir = os.path.join(args.workdir, "translate")
    os.makedirs(op_dir, exist_ok=True)
    os.makedirs(tr_dir, exist_ok=True)

    files = sorted(glob.glob(os.path.join(args.mes_dir, "*.MES")))
    if not files:
        print(f"[!] {args.mes_dir} 下没有 .MES 文件")
        return 1

    workers = args.jobs or _default_workers()
    print(f"[unpack] {len(files)} 个 .MES 文件 / {workers} 进程并行")

    tasks = []
    for f in files:
        base = _strip_ext(os.path.basename(f), ['.MES'])
        op_path = os.path.join(op_dir, base + ".op.txt")
        tr_path = os.path.join(tr_dir, base + ".translate.txt")
        tasks.append((f, op_path, tr_path, args.encoding))

    total_entries = 0
    failed = []

    if workers == 1:
        for t in tasks:
            name, n, err = _worker_unpack(t)
            if err:
                failed.append((name, err))
            else:
                total_entries += n
    else:
        with ProcessPoolExecutor(max_workers=workers) as ex:
            futures = [ex.submit(_worker_unpack, t) for t in tasks]
            done = 0
            for fut in as_completed(futures):
                name, n, err = fut.result()
                done += 1
                if err:
                    failed.append((name, err))
                    print(f"  [!] ({done}/{len(tasks)}) {name}: ERROR {err}")
                else:
                    total_entries += n
                    print(f"  [+] ({done}/{len(tasks)}) {name}: {n} entries")

    print(f"[unpack] 完成 {len(files) - len(failed)}/{len(files)} 个, 共 {total_entries} 条文本")
    if failed:
        print(f"[!] 失败 {len(failed)} 个:")
        for name, err in failed[:5]:
            print(f"    {name}: {err}")
    print(f"[unpack] op.txt 在: {op_dir}")
    print(f"[unpack] translate.txt 在: {tr_dir}  <-- 翻译这里的 ◆ 行")
    return 0 if not failed else 2


def cmd_pack(args):
    op_dir = os.path.join(args.workdir, "op")
    tr_dir = os.path.join(args.workdir, "translate")
    op2_dir = os.path.join(args.workdir, "op_injected")
    os.makedirs(op2_dir, exist_ok=True)
    os.makedirs(args.output_dir, exist_ok=True)

    if not os.path.isdir(op_dir):
        print(f"[!] {op_dir} 不存在, 请先 unpack")
        return 1
    if not os.path.isdir(tr_dir):
        print(f"[!] {tr_dir} 不存在, 请先 unpack")
        return 1

    op_files = sorted(glob.glob(os.path.join(op_dir, "*.op.txt")))
    if not op_files:
        print(f"[!] {op_dir} 下没有 .op.txt")
        return 1

    workers = args.jobs or _default_workers()
    print(f"[pack] {len(op_files)} 个 op.txt / {workers} 进程并行")

    tasks = []
    missing = []
    for op_path in op_files:
        base = _strip_ext(os.path.basename(op_path), ['.op.txt'])
        tr_path = os.path.join(tr_dir, base + ".translate.txt")
        if not os.path.isfile(tr_path):
            missing.append(base)
            continue
        op2_path = os.path.join(op2_dir, base + ".op.txt")
        out_mes = os.path.join(args.output_dir, base + ".MES")
        tasks.append((base, op_path, tr_path, op2_path, out_mes, args.encoding))

    total_entries = 0
    failed = []

    if workers == 1:
        for t in tasks:
            base, n, err = _worker_pack(t)
            if err:
                failed.append((base, err))
            else:
                total_entries += n
    else:
        with ProcessPoolExecutor(max_workers=workers) as ex:
            futures = [ex.submit(_worker_pack, t) for t in tasks]
            done = 0
            for fut in as_completed(futures):
                base, n, err = fut.result()
                done += 1
                if err:
                    failed.append((base, err))
                    print(f"  [!] ({done}/{len(tasks)}) {base}: ERROR {err}")
                else:
                    total_entries += n
                    print(f"  [+] ({done}/{len(tasks)}) {base}: {n} entries")

    success = len(tasks) - len(failed)
    print(f"[pack] 成功 {success}/{len(op_files)} 个, 共注入 {total_entries} 条")
    if missing:
        print(f"[!] 缺译文 {len(missing)} 个: {missing[:5]}{'...' if len(missing) > 5 else ''}")
    if failed:
        print(f"[!] 失败 {len(failed)} 个:")
        for name, err in failed[:5]:
            print(f"    {name}: {err}")
    print(f"[pack] 输出 .MES 在: {args.output_dir}")
    return 0 if not failed else 2


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Silky MES 一站式批量处理（并行）")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_u = sub.add_parser("unpack",
                         help="MES目录 -> 工作目录/op + 工作目录/translate")
    p_u.add_argument("mes_dir")
    p_u.add_argument("workdir")
    p_u.add_argument("--encoding", default="cp932")
    p_u.add_argument("-j", "--jobs", type=int, default=0,
                     help="并行进程数 (默认 CPU 核数 - 1, 1 = 单进程)")
    p_u.set_defaults(func=cmd_unpack)

    p_p = sub.add_parser("pack",
                         help="工作目录/op + 工作目录/translate -> 输出目录/*.MES")
    p_p.add_argument("mes_dir", help="（占位）")
    p_p.add_argument("workdir")
    p_p.add_argument("output_dir")
    p_p.add_argument("--encoding", default="cp932")
    p_p.add_argument("-j", "--jobs", type=int, default=0,
                     help="并行进程数 (默认 CPU 核数 - 1, 1 = 单进程)")
    p_p.set_defaults(func=cmd_pack)

    args = ap.parse_args()
    sys.exit(args.func(args))
