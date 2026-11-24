"""Lock the approved schematic, then validate and deliver. Standard library only.

lock    <project> <lock.json>
deliver <project> <out> --lock L --erc E --drc D --overlap O
"""
import argparse
import hashlib
import json
import re
import shutil
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
# Checks KiCad itself ignores by default. Anything else set to ignore hides a problem.
IGNORED = {"footprint_filters_mismatch", "footprint_type_mismatch", "missing_courtyard",
           "track_not_centered_on_via", "tuning_profile_track_geometries"}
KEEP = {".kicad_pro", ".kicad_sch", ".kicad_pcb", ".kicad_dru", ".kicad_sym", ".kicad_mod",
        ".kicad_wks", ".step", ".stp", ".wrl"}
SKIP_DIR = re.compile(r"(-backups|\.history|\.git|__pycache__)$", re.I)
TOKEN = re.compile(r'"((?:[^"\\]|\\.)*)"|([()])|([^\s()"]+)', re.S)
MARK = re.compile(r"(watermark|水印|https?://|www\.|claude|anthropic|chatgpt|openai|copilot|deepseek|"
                  r"(generated|made|designed|created|drawn|powered)\s+(by|with)|"
                  r"\bAI[\s-]*(generated|design|made)|AI\s*(生成|绘制|设计|制作)|"
                  r"(设计者|作者|绘制者|绘制人)\s*[:：])", re.I)


def parse(path):
    stack, root = [], None
    for m in TOKEN.finditer(path.read_text(encoding="utf-8")):
        q, p, a = m.groups()
        if p == "(":
            stack.append([])
        elif p == ")":
            if not stack:
                raise ValueError("unbalanced file: %s" % path.name)
            n = stack.pop()
            if stack:
                stack[-1].append(n)
            else:
                root = n
        elif stack:
            stack[-1].append(q if q is not None else a)
    if stack or root is None:
        raise ValueError("unbalanced file: %s" % path.name)
    return root


def walk(n):
    yield n
    for x in n:
        if isinstance(x, list) and x:
            yield from walk(x)


def kids(n, name):
    return [x for x in n if isinstance(x, list) and x and x[0] == name]


def listing(root):
    r = {}
    for p in sorted(root.rglob("*")):
        rel = p.relative_to(root)
        if p.is_file() and not any(SKIP_DIR.search(x) for x in rel.parts[:-1]) and \
                (p.suffix.lower() in KEEP or p.name in ("fp-lib-table", "sym-lib-table")) and \
                not p.name.startswith("_autosave"):
            r[rel.as_posix()] = p
    return r


def locked_hashes(root):
    return {k: hashlib.sha256(p.read_bytes()).hexdigest()
            for k, p in listing(root).items() if k.endswith(".kicad_sch")}


def marks(tree, name):
    errs = []
    for n in walk(tree):
        if n[0] == "image":
            errs.append("%s: 含图片，可能是水印" % name)
        elif n[0] in ("text", "text_box", "gr_text", "gr_text_box", "fp_text", "title", "company", "comment"):
            for s in n[1:]:
                if isinstance(s, str) and MARK.search(s):
                    errs.append("%s: 疑似水印 %r" % (name, s))
    for tb in kids(tree, "title_block"):
        for key in ("date", "company"):
            for x in kids(tb, key):
                if len(x) > 1 and x[-1]:
                    errs.append("%s: 标题栏 %s 应为空" % (name, key))
    return errs


def schematic_errors(root, main):
    errs, seen, todo, symbols, wiring = [], set(), [main], 0, 0
    while todo:
        f = todo.pop()
        if f in seen:
            continue
        seen.add(f)
        if not f.is_file():
            errs.append("子图缺失: " + f.name)
            continue
        t = parse(f)
        errs += marks(t, f.name)
        symbols += len(kids(t, "symbol"))
        wiring += len(kids(t, "wire"))
        for s in kids(t, "sheet"):
            for p in kids(s, "property"):
                if len(p) > 2 and p[1] in ("Sheetfile", "Sheet file"):
                    todo.append((f.parent / p[2]).resolve())
    if not symbols:
        errs.append("原理图没有器件")
    if not wiring:
        errs.append("原理图没有连线")
    if any(root != f and root not in f.parents for f in seen):
        errs.append("子图在工程目录之外")
    return errs


def report(path, newer_than, board_name):
    if any(path.stat().st_mtime < f.stat().st_mtime for f in newer_than):
        raise ValueError("%s 早于被检查文件，请重跑" % path.name)
    d = json.loads(path.read_text(encoding="utf-8"))
    if Path(d.get("source", "").replace("\\", "/")).name != board_name:
        raise ValueError("%s 不是本工程的报告" % path.name)
    return d


def validate(root, lock, erc, drc, overlap):
    all_files, errs = listing(root), []
    one = {}
    for ext in (".kicad_pro", ".kicad_pcb"):
        hits = [p for k, p in all_files.items() if k.endswith(ext)]
        if len(hits) != 1:
            return ["需要且只能有一个 " + ext]
        one[ext] = hits[0]
    board, sch = one[".kicad_pcb"], one[".kicad_pro"].with_suffix(".kicad_sch")
    if board.stem != sch.stem:
        errs.append("工程、原理图、PCB 必须同名")
    if not sch.is_file():
        return errs + ["缺少原理图"]
    if json.loads(lock.read_text(encoding="utf-8")) != locked_hashes(root):
        errs.append("原理图与用户确认时不一致")
    errs += schematic_errors(root.resolve(), sch.resolve())
    t = parse(board)
    errs += marks(t, board.name)
    layers = kids(t, "layers")[0]
    cu = [r[1] for r in layers[1:] if isinstance(r, list) and r[1].endswith(".Cu")]
    if sorted(cu) != ["B.Cu", "F.Cu"]:
        errs.append("不是双层板: %s" % cu)
    if any({"blind", "buried", "micro"} & {x for x in v if isinstance(x, str)} for v in kids(t, "via")):
        errs.append("含盲埋孔或微孔")
    if not kids(t, "footprint"):
        errs.append("PCB 没有器件")
    if not kids(t, "segment") and not kids(t, "arc") and not kids(t, "zone"):
        errs.append("PCB 没有走线或铺铜")
    if not any(["layer", "Edge.Cuts"] in n for n in walk(t)):
        errs.append("没有板框")
    for k, p in all_files.items():
        if p.name in ("fp-lib-table", "sym-lib-table"):
            for uri in re.findall(r'\(uri\s+"?([^")]+)', p.read_text(encoding="utf-8")):
                if not uri.startswith("${"):
                    errs.append("%s 使用了不可移植路径: %s" % (k, uri))
                elif uri.startswith("${KIPRJMOD}") and not (root / uri[len("${KIPRJMOD}"):].lstrip("/")).exists():
                    errs.append("%s 的库不存在: %s" % (k, uri))
    for m in (n[1] for n in walk(t) if n[0] == "model" and len(n) > 1):
        if not m.startswith("${"):
            errs.append("3D 模型路径不可移植: " + m)
    schs = [p for k, p in all_files.items() if k.endswith(".kicad_sch")]
    e = report(erc, schs, sch.name)
    if not isinstance(e.get("sheets"), list):
        raise ValueError("无法识别的 ERC 报告")
    n = sum(v.get("severity") == "error" for s in e["sheets"] for v in s.get("violations", []))
    if n:
        errs.append("ERC error: %d" % n)
    d = report(drc, schs + [board, one[".kicad_pro"]], board.name)
    for key in ("violations", "unconnected_items", "schematic_parity"):
        if not isinstance(d.get(key), list):
            raise ValueError("DRC 报告缺少 " + key)
    n = sum(v.get("severity") == "error" or v.get("type") == "shorting_items" for v in d["violations"])
    for label, count in (("DRC error", n), ("未连线", len(d["unconnected_items"])),
                         ("PCB 与原理图不一致", len(d["schematic_parity"]))):
        if count:
            errs.append("%s: %d" % (label, count))
    ds = json.loads(one[".kicad_pro"].read_text(encoding="utf-8")).get("board", {}).get("design_settings", {})
    off = {k for k, v in ds.get("rule_severities", {}).items() if v == "ignore"} - IGNORED
    if off:
        errs.append("DRC 检查项被关闭: " + ", ".join(sorted(off)))
    if ds.get("drc_exclusions"):
        errs.append("存在 DRC 排除项")
    o = json.loads(overlap.read_text(encoding="utf-8"))
    if o.get("board_sha256") != hashlib.sha256(board.read_bytes()).hexdigest():
        errs.append("重叠检查不是针对当前板文件，请重跑")
    if o.get("ok") is not True:
        errs += o.get("errors") or ["重叠检查未通过"]
    return errs


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("lock")
    s.add_argument("project", type=Path)
    s.add_argument("lock", type=Path)
    s = sub.add_parser("deliver")
    s.add_argument("project", type=Path)
    s.add_argument("out", type=Path)
    for x in ("lock", "erc", "drc", "overlap"):
        s.add_argument("--" + x, type=Path, required=True)
    a = ap.parse_args()
    try:
        if a.cmd == "lock":
            h = locked_hashes(a.project)
            errs = [] if h else ["没有原理图"]
            if h:
                a.lock.write_text(json.dumps(h, ensure_ascii=False), encoding="utf-8")
        else:
            src, out = a.project.resolve(), a.out.resolve()
            errs = validate(src, a.lock, a.erc, a.drc, a.overlap)
            if out.exists():
                errs.append("输出目录已存在，不覆盖")
            if src in out.parents or out in src.parents:
                errs.append("输出目录不能与工程目录嵌套")
            if not errs:
                for k, p in listing(src).items():
                    (out / k).parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(p, out / k)
    except (OSError, ValueError, KeyError, IndexError) as ex:
        errs = ["%s: %s" % (type(ex).__name__, ex)]
    print(json.dumps({"ok": not errs, "errors": errs}, ensure_ascii=False, indent=2))
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main())
