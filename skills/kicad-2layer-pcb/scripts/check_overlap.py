"""Find overlaps that a clean DRC can still hide. Run with KiCad's bundled Python. Read-only.
argv: <board.kicad_pcb> [report.json]. Exit 1 if anything is found."""
import hashlib
import json
import os
import sys

import pcbnew

sys.stdout.reconfigure(encoding="utf-8")
with open(sys.argv[1], "rb") as fh:
    digest = hashlib.sha256(fh.read()).hexdigest()
b = pcbnew.LoadBoard(os.path.abspath(sys.argv[1]))
MM = 1e6
SILK = {pcbnew.F_SilkS: pcbnew.F_Cu, pcbnew.B_SilkS: pcbnew.B_Cu}
errs = []


def box(i):
    q = i.GetBoundingBox()
    return q.GetLeft(), q.GetTop(), q.GetRight(), q.GetBottom()


def over(p, q, slack=0.0):
    s = slack * MM
    return min(p[2], q[2]) - max(p[0], q[0]) > s and min(p[3], q[3]) - max(p[1], q[1]) > s


def at(i):
    p = i.GetPosition()
    return "(%.2f, %.2f)" % (p.x / MM, p.y / MM)


fps = list(b.GetFootprints())
for layer in (pcbnew.F_CrtYd, pcbnew.B_CrtYd):
    cy = []
    for f in fps:
        f.BuildCourtyardCaches()
        c = f.GetCourtyard(layer)
        if c.OutlineCount():
            cy.append((f, c))
    for i, (f, c) in enumerate(cy):
        for g, d in cy[i + 1:]:
            x = pcbnew.SHAPE_POLY_SET(c)
            x.BooleanIntersection(d)
            if x.Area() > 1e6:
                errs.append("器件重叠: %s 与 %s" % (f.GetReference(), g.GetReference()))
for f in fps:
    f.BuildCourtyardCaches()
    if not f.GetCourtyard(pcbnew.F_CrtYd).OutlineCount() and not f.GetCourtyard(pcbnew.B_CrtYd).OutlineCount():
        errs.append("器件没有 courtyard，DRC 查不到它的重叠: " + f.GetReference())

# Copper running on top of copper of the same net: invisible to clearance checks.
segs = [t for t in b.GetTracks() if t.Type() == pcbnew.PCB_TRACE_T]
vias = [t for t in b.GetTracks() if t.Type() == pcbnew.PCB_VIA_T]
for t in segs:
    if t.GetLength() == 0:
        errs.append("零长度走线 %s" % at(t))


def collinear_overlap(s, t):
    a, c, d, e = s.GetStart(), s.GetEnd(), t.GetStart(), t.GetEnd()
    ux, uy = c.x - a.x, c.y - a.y
    n = (ux * ux + uy * uy) ** 0.5
    if not n:
        return 0
    if any(abs((p.x - a.x) * uy - (p.y - a.y) * ux) / n > 1000 for p in (d, e)):
        return 0
    lo, hi = sorted(((p.x - a.x) * ux + (p.y - a.y) * uy) / n for p in (d, e))
    return min(n, hi) - max(0, lo)


for i, s in enumerate(segs):
    for t in segs[i + 1:]:
        if s.GetLayer() == t.GetLayer() and s.GetNetCode() == t.GetNetCode() and collinear_overlap(s, t) > 1000:
            errs.append("走线重叠: %s %s %s" % (s.GetNetname(), b.GetLayerName(s.GetLayer()), at(s)))
for i, v in enumerate(vias):
    for w in vias[i + 1:]:
        p, q = v.GetPosition(), w.GetPosition()
        if (p.x - q.x) ** 2 + (p.y - q.y) ** 2 < (v.GetDrillValue() / 2 + w.GetDrillValue() / 2 + 0.2 * MM) ** 2:
            errs.append("过孔重叠或过近: %s %s" % (at(v), at(w)))
    for f in fps:
        for p in f.Pads():
            if p.HitTest(v.GetPosition(), int(v.GetDrillValue() / 2)):
                errs.append("过孔在焊盘上: %s.%s %s" % (f.GetReference(), p.GetNumber(), at(v)))

# Silkscreen text against pads, vias, other text, outlines, part bodies and the board edge.
texts = [(d, d.GetText()) for d in b.GetDrawings() if isinstance(d, pcbnew.PCB_TEXT) and d.GetLayer() in SILK]
for f in fps:
    texts += [(x, x.GetShownText(False)) for x in f.GetFields() if x.IsVisible() and x.GetLayer() in SILK]
    texts += [(g, g.GetText()) for g in f.GraphicalItems() if isinstance(g, pcbnew.PCB_TEXT) and g.GetLayer() in SILK]
edge = b.GetBoardEdgesBoundingBox()
eb = (edge.GetLeft(), edge.GetTop(), edge.GetRight(), edge.GetBottom())
for i, (t, s) in enumerate(texts):
    p, lay = box(t), t.GetLayer()
    if p[0] < eb[0] or p[1] < eb[1] or p[2] > eb[2] or p[3] > eb[3]:
        errs.append("丝印出板框: " + s)
    for u, r in texts[i + 1:]:
        if u.GetLayer() == lay and over(p, box(u)):
            errs.append("丝印文字重叠: %s 与 %s" % (s, r))
    for v in vias:
        if over(p, box(v), 0.05):
            errs.append("丝印压在过孔上: %s %s" % (s, at(v)))
    for f in fps:
        for pad in f.Pads():
            if pad.IsOnLayer(SILK[lay]) and over(p, box(pad)):
                errs.append("丝印压在焊盘上: %s 与 %s.%s" % (s, f.GetReference(), pad.GetNumber()))
        for g in f.GraphicalItems():
            if g.GetLayer() == lay and not isinstance(g, pcbnew.PCB_TEXT) and over(p, box(g), 0.02):
                errs.append("丝印压在外框线上: %s 与 %s" % (s, f.GetReference()))
        c = f.GetCourtyard(pcbnew.F_CrtYd if lay == pcbnew.F_SilkS else pcbnew.B_CrtYd)
        if c.OutlineCount():
            q = c.BBox()
            if over(p, (q.GetLeft(), q.GetTop(), q.GetRight(), q.GetBottom()), 0.3):
                errs.append("丝印被器件遮挡: %s 与 %s" % (s, f.GetReference()))

for f in fps:
    for g in f.GraphicalItems():
        if g.GetLayer() in SILK and not isinstance(g, pcbnew.PCB_TEXT):
            for v in vias:
                if g.HitTest(v.GetPosition(), int(v.GetDrillValue() / 2)):
                    errs.append("丝印图形压在过孔上: %s %s" % (f.GetReference(), at(v)))

errs = sorted(set(errs))
out = json.dumps({"ok": not errs, "board_sha256": digest, "errors": errs}, ensure_ascii=False, indent=1)
print(out)
if len(sys.argv) > 2:
    with open(sys.argv[2], "w", encoding="utf-8") as fh:
        fh.write(out)
sys.exit(1 if errs else 0)
