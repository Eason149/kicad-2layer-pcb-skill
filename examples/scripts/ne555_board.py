"""Build, place (simulated annealing), route (2-layer A*), pour. KiCad Python only.
argv: <kicad share> <netlist.xml> <board.kicad_pcb>"""
import heapq
import math
import os
import random
import sys
import xml.etree.ElementTree as ET

import pcbnew

SHARE, NET, PCB = sys.argv[1:4]
W, H, OX, OY = 40.0, 30.0, 100.0, 80.0
mm, to = pcbnew.FromMM, pcbnew.ToMM
V = lambda x, y: pcbnew.VECTOR2I(mm(x), mm(y))
random.seed(7)

# ---- build -------------------------------------------------------------
if os.path.exists(PCB):
    os.remove(PCB)
b = pcbnew.NewBoard(os.path.abspath(PCB))
b.SetCopperLayerCount(2)
root = ET.parse(NET).getroot()
nets, padnet = {}, {}
for n in root.find("nets"):
    item = pcbnew.NETINFO_ITEM(b, n.get("name"))
    b.Add(item)
    nets[n.get("name")] = item
    for x in n.findall("node"):
        padnet[x.get("ref"), x.get("pin")] = n.get("name")
fps = {}
for c in root.find("components"):
    ref = c.get("ref")
    lib, name = c.findtext("footprint").split(":")
    fp = pcbnew.FootprintLoad(os.path.join(SHARE, "footprints", lib + ".pretty"), name)
    if fp is None:
        sys.exit("missing footprint %s:%s" % (lib, name))
    fp.SetFPID(pcbnew.LIB_ID(lib, name))
    fp.SetReference(ref)
    fp.SetValue(c.findtext("value"))
    fp.SetPath(pcbnew.KIID_PATH("/" + c.findtext("tstamps").split()[0]))
    fp.SetSheetname("/")
    fp.SetSheetfile("NE555_Flasher.kicad_sch")
    for f in c.findall("fields/field"):
        if f.get("name") in ("Datasheet", "Description"):
            fp.SetField(f.get("name"), f.text or "")
            fp.GetField(f.get("name")).SetVisible(False)
    b.Add(fp)
    fps[ref] = fp
    for p in fp.Pads():
        k = padnet.get((ref, p.GetNumber()))
        if k:
            p.SetNet(nets[k])

# ---- place -------------------------------------------------------------
fixed = {"H1": (4, 4), "H2": (W - 4, 4), "H3": (4, H - 4), "H4": (W - 4, H - 4), "J1": (4, H / 2 - 1.27)}
movable = [r for r in fps if r not in fixed]
for r, (x, y) in fixed.items():
    fps[r].SetPosition(V(OX + x, OY + y))


def shape(fp):
    """Relative courtyard box and pads for the four rotations."""
    out = []
    fp.SetPosition(V(0, 0))
    for a in (0, 90, 180, 270):
        fp.SetOrientationDegrees(a)
        fp.BuildCourtyardCaches()
        q = fp.GetCourtyard(pcbnew.F_CrtYd).BBox()
        out.append(((to(q.GetLeft()), to(q.GetTop()), to(q.GetRight()), to(q.GetBottom())),
                    [(p.GetNetname(), p.GetNumber(), to(p.GetPosition().x), to(p.GetPosition().y)) for p in fp.Pads()]))
    return out


shapes = {r: shape(fps[r]) for r in fps}
st = {r: (x, y, 0) for r, (x, y) in fixed.items()}
for r in movable:
    st[r] = (random.uniform(10, 32), random.uniform(6, 24), 0)
GAP = 0.6


def box(r):
    x, y, a = st[r]
    q = shapes[r][a][0]
    return x + q[0], y + q[1], x + q[2], y + q[3]


def pad_at(r, num):
    x, y, a = st[r]
    return next((x + p[2], y + p[3]) for p in shapes[r][a][1] if p[1] == num)


def dist(a, c):
    return math.hypot(a[0] - c[0], a[1] - c[1])


def cost():
    boxes, over = {r: box(r) for r in st}, 0.0
    rs = list(boxes)
    for i, r in enumerate(rs):
        p = boxes[r]
        if r in movable:
            over += sum(max(0, d) for d in (1 - p[0], 1 - p[1], p[2] - W + 1, p[3] - H + 1))
        for s in rs[i + 1:]:
            q = boxes[s]
            dx, dy = min(p[2], q[2]) - max(p[0], q[0]) + GAP, min(p[3], q[3]) - max(p[1], q[1]) + GAP
            if dx > 0 and dy > 0:
                over += min(dx, dy) + 0.2
    pts = {}
    for r in st:
        x, y, a = st[r]
        for n, _, px, py in shapes[r][a][1]:
            if n and n != "GND":
                pts.setdefault(n, []).append((x + px, y + py))
    wl = sum(max(p[0] for p in v) - min(p[0] for p in v) + max(p[1] for p in v) - min(p[1] for p in v) for v in pts.values())
    wl += 3 * dist(pad_at("C3", "1"), pad_at("U1", "8")) + dist(pad_at("C3", "2"), pad_at("U1", "1"))
    wl += 2 * dist(pad_at("C2", "1"), pad_at("U1", "5")) + dist(pad_at("C4", "1"), pad_at("J1", "1"))
    ux, uy, _ = st["U1"]
    return wl + 60 * over + 0.5 * dist((ux, uy), (W / 2, H / 2)), over


cur, over = cost()
best, best_st = (cur, over), dict(st)
N = 60000
for i in range(N):
    T = 30 * (0.0005 ** (i / N))
    old = dict(st)
    r = random.choice(movable)
    x, y, a = st[r]
    k = random.random()
    if k < 0.7:
        s = 0.3 + 6 * (1 - i / N)
        st[r] = (x + random.gauss(0, s), y + random.gauss(0, s), a)
    elif k < 0.85:
        st[r] = (x, y, random.randrange(4))
    else:
        q = random.choice(movable)
        st[r], st[q] = (*st[q][:2], a), (x, y, st[q][2])
    c, o = cost()
    if c < cur or random.random() < math.exp((cur - c) / T):
        cur = c
        if c < best[0]:
            best, best_st = (c, o), dict(st)
    else:
        st = old
st = best_st
for r in movable:
    x, y, a = st[r]
    st[r] = (round(x * 10) / 10, round(y * 10) / 10, a)
final, o = cost()
print("placement cost %.1f overlap %.3f" % (final, o))
for r, (x, y, a) in st.items():
    fps[r].SetOrientationDegrees(a * 90)
    fps[r].SetPosition(V(OX + x, OY + y))

# ---- outline, rules ----------------------------------------------------
e = pcbnew.PCB_SHAPE(b, pcbnew.SHAPE_T_RECT)
e.SetStart(V(OX, OY))
e.SetEnd(V(OX + W, OY + H))
e.SetLayer(pcbnew.Edge_Cuts)
e.SetWidth(mm(0.1))
b.Add(e)

# ---- route -------------------------------------------------------------
G, CLR, EDGE, VIA, DRILL = 0.1, 0.2, 0.3, 0.6, 0.3
NX, NY = int(W / G) + 1, int(H / G) + 1
obst = []  # (layers, x1, y1, x2, y2, extra radius, net)
for r, fp in fps.items():
    for p in fp.Pads():
        q = p.GetBoundingBox()
        layers = (0, 1) if p.GetDrillSize().x else (0,)
        obst.append((layers, to(q.GetLeft()) - OX, to(q.GetTop()) - OY, to(q.GetRight()) - OX, to(q.GetBottom()) - OY,
                     0.1 if not p.GetNetname() else 0.0, p.GetNetname()))


silk = []
for fp in fps.values():
    for g in fp.GraphicalItems():
        if g.GetLayer() == pcbnew.F_SilkS and not isinstance(g, pcbnew.PCB_TEXT):
            q = g.GetBoundingBox()
            silk.append((to(q.GetLeft()) - OX, to(q.GetTop()) - OY, to(q.GetRight()) - OX, to(q.GetBottom()) - OY))


def paint(net, half):
    m = [bytearray(NX * NY), bytearray(NX * NY)]
    k = EDGE + half + 0.05
    for j in range(NY):
        for i in range(NX):
            if not (k <= i * G <= W - k and k <= j * G <= H - k):
                m[0][j * NX + i] = m[1][j * NX + i] = 1
    for layers, x1, y1, x2, y2, ex, n in obst:
        if n == net and n:
            continue
        d = CLR + half + ex + 0.01
        for j in range(max(0, int((y1 - d) / G)), min(NY, int((y2 + d) / G) + 2)):
            for i in range(max(0, int((x1 - d) / G)), min(NX, int((x2 + d) / G) + 2)):
                dx, dy = max(x1 - i * G, 0, i * G - x2), max(y1 - j * G, 0, j * G - y2)
                if dx * dx + dy * dy < d * d:
                    for L in layers:
                        m[L][j * NX + i] = 1
    return m


DIRS = [(1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1), (0, -1), (1, -1)]


def via_mask(net, half):
    """Where a via may go: clear of other nets, and never in an SMD pad (solder would wick away)."""
    m = paint(net, half)
    for layers, x1, y1, x2, y2, _, n in obst[:base]:
        d = half + 0.1
        for j in range(max(0, int((y1 - d) / G)), min(NY, int((y2 + d) / G) + 2)):
            for i in range(max(0, int((x1 - d) / G)), min(NX, int((x2 + d) / G) + 2)):
                if x1 - d < i * G < x2 + d and y1 - d < j * G < y2 + d:
                    m[0][j * NX + i] = m[1][j * NX + i] = 1
    for x1, y1, x2, y2 in silk:
        for j in range(max(0, int((y1 - half) / G)), min(NY, int((y2 + half) / G) + 2)):
            for i in range(max(0, int((x1 - half) / G)), min(NX, int((x2 + half) / G) + 2)):
                m[0][j * NX + i] = m[1][j * NX + i] = 1
    return m


def astar(sources, goals, m, vm):
    gx = sum(g[0] for g in goals) / len(goals)
    gy = sum(g[1] for g in goals) / len(goals)
    goal = set(goals)
    h = lambda i, j: min(max(abs(i - g[0]), abs(j - g[1])) for g in goals)
    heap, seen, came, t = [], {}, {}, 0
    for s in sources:
        st_ = (s[0], s[1], s[2], -1)
        seen[st_] = 0
        heapq.heappush(heap, (h(s[0], s[1]), t, 0, st_))
        t += 1
    while heap:
        _, _, g, s = heapq.heappop(heap)
        if g > seen[s]:
            continue
        i, j, L, d = s
        if (i, j, L) in goal:
            path = [s]
            while path[-1] in came:
                path.append(came[path[-1]])
            return [p[:3] for p in reversed(path)]
        for nd, (di, dj) in enumerate(DIRS):
            turn = 0 if d < 0 else min((nd - d) % 8, (d - nd) % 8)
            if turn > 2 or (turn == 2):
                continue
            a, c = i + di, j + dj
            if not (0 <= a < NX and 0 <= c < NY) or m[L][c * NX + a]:
                continue
            ng = g + (1.414 if di and dj else 1) + turn * 2 + (0.3 if L else 0)
            n = (a, c, L, nd)
            if ng < seen.get(n, 1e9):
                seen[n] = ng
                came[n] = s
                t += 1
                heapq.heappush(heap, (ng + h(a, c), t, ng, n))
        if not vm[0][j * NX + i] and not vm[1][j * NX + i]:
            n = (i, j, 1 - L, -1)
            if g + 60 < seen.get(n, 1e9):
                seen[n] = g + 60
                came[n] = s
                t += 1
                heapq.heappush(heap, (g + 60 + h(i, j), t, g + 60, n))
    return None


added = []


def track(p, q, L, w, net):
    if p == q:
        return
    t = pcbnew.PCB_TRACK(b)
    t.SetStart(V(OX + p[0], OY + p[1]))
    t.SetEnd(V(OX + q[0], OY + q[1]))
    t.SetLayer(pcbnew.B_Cu if L else pcbnew.F_Cu)
    t.SetWidth(mm(w))
    t.SetNet(nets[net])
    b.Add(t)
    added.append(t)
    n = max(1, int(dist(p, q) / 0.1))
    for k in range(n + 1):
        x, y = p[0] + (q[0] - p[0]) * k / n, p[1] + (q[1] - p[1]) * k / n
        obst.append(((L,), x, y, x, y, w / 2, net))


def via(x, y, net):
    v = pcbnew.PCB_VIA(b)
    v.SetPosition(V(OX + x, OY + y))
    v.SetWidth(mm(VIA))
    v.SetDrill(mm(DRILL))
    v.SetNet(nets[net])
    b.Add(v)
    added.append(v)
    obst.append(((0, 1), x, y, x, y, VIA / 2, net))


def pads_of(net):
    return [(to(p.GetPosition().x) - OX, to(p.GetPosition().y) - OY, bool(p.GetDrillSize().x), r)
            for r, fp in fps.items() for p in fp.Pads() if p.GetNetname() == net]


def emit(path, w, net, start=None, end=None):
    pt = lambda s: (s[0] * G, s[1] * G)
    if start:
        track(start, pt(path[0]), path[0][2], w, net)
    k = 0
    for i in range(1, len(path)):
        if path[i][2] != path[i - 1][2]:
            track(pt(path[k]), pt(path[i - 1]), path[k][2], w, net)
            via(*pt(path[i]), net)
            k = i
        elif i + 1 == len(path) or path[i + 1][2] != path[i][2] or \
                (path[i + 1][0] - path[i][0], path[i + 1][1] - path[i][1]) != (path[i][0] - path[i - 1][0], path[i][1] - path[i - 1][1]):
            track(pt(path[k]), pt(path[i]), path[k][2], w, net)
            k = i
    if end:
        track(pt(path[-1]), end, path[-1][2], w, net)


def route(net, w):
    pads = pads_of(net)
    cell = lambda p: (round(p[0] / G), round(p[1] / G))
    tree = {(*cell(pads[0]), L): pads[0] for L in ((0, 1) if pads[0][2] else (0,))}
    left = pads[1:]
    while left:
        m, vm = paint(net, w / 2), via_mask(net, VIA / 2)
        goals = {(*cell(p), L): p for p in left for L in ((0, 1) if p[2] else (0,))}
        path = astar(list(tree), list(goals), m, vm)
        if path is None:
            return False
        s, g = tree[path[0]], goals[path[-1]]
        emit(path, w, net, s[:2] if s else None, g[:2])
        for q in path:
            tree.setdefault(q, None)
        for L in ((0, 1) if g[2] else (0,)):
            tree[(*cell(g), L)] = g
        left.remove(g)
    return True


widths = {"+5V": 0.5}
order = ["+5V"] + sorted((n for n in nets if n not in ("+5V", "GND", "")), key=lambda n: -len(pads_of(n)))
base = len(obst)
for attempt in range(20):
    bad = [n for n in order if not route(n, widths.get(n, 0.25))]
    if not bad:
        break
    print("retry, failed", bad)
    for t in added:
        b.Delete(t)
    added.clear()
    del obst[base:]
    order = bad + [n for n in order if n not in bad]
else:
    sys.exit("routing failed: %s" % bad)

# ---- ground: a via beside every SMD GND pad, stitching, two pours ------
m_via, m_trk = None, None
for px, py, th, ref in pads_of("GND"):
    if th:
        continue
    vm, tm = via_mask("GND", VIA / 2), paint("GND", 0.2)
    sx, sy = round(px / G), round(py / G)
    own = [q for q in obst[:base] if q[6] == "GND" and q[1] <= px <= q[3] and q[2] <= py <= q[4]][0]
    ok = []
    for j in range(max(0, sy - 40), min(NY, sy + 41)):
        for i in range(max(0, sx - 40), min(NX, sx + 41)):
            x, y = i * G, j * G
            gap = math.hypot(max(own[1] - x, 0, x - own[3]), max(own[2] - y, 0, y - own[4]))
            if gap > 0.45 and not vm[0][j * NX + i] and not vm[1][j * NX + i]:
                ok.append((dist((x, y), (px, py)), i, j))
    for _, i, j in sorted(ok)[:60]:
        path = astar([(sx, sy, 0)], [(i, j, 0)], tm, [bytearray(b"\1" * (NX * NY))] * 2)
        if path and len(path) < 60:
            emit(path, 0.4, "GND", (px, py))
            via(i * G, j * G, "GND")
            break
    else:
        sys.exit("no GND via for " + ref)
stitch = 0
for y in range(3, int(H), 6):
    for x in range(8, int(W) - 2, 8):
        vm = via_mask("GND", VIA / 2 + 0.1)
        k = round(y / G) * NX + round(x / G)
        near = any(q[6] == "GND" and dist((x, y), ((q[1] + q[3]) / 2, (q[2] + q[4]) / 2)) < 2 for q in obst)
        if not vm[0][k] and not vm[1][k] and not near:
            via(x, y, "GND")
            stitch += 1


def merge_collinear():
    """Replace collinear overlapping tracks by one track covering the same copper."""
    ts = [t for t in b.GetTracks() if t.Type() == pcbnew.PCB_TRACE_T]
    for i, s in enumerate(ts):
        a, c = s.GetStart(), s.GetEnd()
        ux, uy = c.x - a.x, c.y - a.y
        n = math.hypot(ux, uy)
        for t in ts[i + 1:]:
            if (s.GetLayer(), s.GetNetCode(), s.GetWidth()) != (t.GetLayer(), t.GetNetCode(), t.GetWidth()):
                continue
            q = [t.GetStart(), t.GetEnd()]
            if any(abs((p.x - a.x) * uy - (p.y - a.y) * ux) / n > 1000 for p in q):
                continue
            pos = sorted([(0, a.x, a.y), (n, c.x, c.y)] + [(((p.x - a.x) * ux + (p.y - a.y) * uy) / n, p.x, p.y) for p in q])
            lo, hi = sorted(((p.x - a.x) * ux + (p.y - a.y) * uy) / n for p in q)
            if min(n, hi) - max(0, lo) <= 1000:
                continue
            s.SetStart(pcbnew.VECTOR2I(int(pos[0][1]), int(pos[0][2])))
            s.SetEnd(pcbnew.VECTOR2I(int(pos[-1][1]), int(pos[-1][2])))
            b.Delete(t)
            return True
    return False


while merge_collinear():
    pass
for L in (pcbnew.F_Cu, pcbnew.B_Cu):
    z = pcbnew.ZONE(b)
    z.SetLayer(L)
    z.SetNet(nets["GND"])
    z.SetLocalClearance(mm(0.25))
    z.SetMinThickness(mm(0.25))
    z.SetThermalReliefGap(mm(0.3))
    z.SetThermalReliefSpokeWidth(mm(0.4))
    z.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_ALWAYS)
    for x, y in ((0.4, 0.4), (W - 0.4, 0.4), (W - 0.4, H - 0.4), (0.4, H - 0.4)):
        z.AppendCorner(V(OX + x, OY + y), -1)
    b.Add(z)

# ---- silkscreen: keep references off pads and each other -----------------
taken = []
for fp in fps.values():
    for p in fp.Pads():
        q = p.GetBoundingBox()
        taken.append((to(q.GetLeft()), to(q.GetTop()), to(q.GetRight()), to(q.GetBottom())))
    for g in fp.GraphicalItems():
        if g.GetLayer() == pcbnew.F_SilkS:
            q = g.GetBoundingBox()
            taken.append((to(q.GetLeft()), to(q.GetTop()), to(q.GetRight()), to(q.GetBottom())))
hit = lambda p: any(min(p[2], q[2]) - max(p[0], q[0]) > -0.15 and min(p[3], q[3]) - max(p[1], q[1]) > -0.15 for q in taken) \
    or p[0] < OX + 0.6 or p[1] < OY + 0.6 or p[2] > OX + W - 0.6 or p[3] > OY + H - 0.6


def put(t, cx, cy, what):
    t.SetTextAngleDegrees(0)
    t.SetTextSize(V(0.8, 0.8))
    t.SetTextThickness(mm(0.12))
    t.SetHorizJustify(pcbnew.GR_TEXT_H_ALIGN_CENTER)
    for d in [x * 0.2 for x in range(5, 40)]:
        for a in range(0, 360, 15):
            t.SetPosition(V(cx + d * math.cos(math.radians(a)), cy + d * math.sin(math.radians(a))))
            q = t.GetBoundingBox()
            p = (to(q.GetLeft()), to(q.GetTop()), to(q.GetRight()), to(q.GetBottom()))
            if not hit(p):
                taken.append(p)
                return
    print("no silk spot", what)


# Polarity labels sit level with their own pin; an ambiguous label invites reversed power.
for num, label in (("1", "5V"), ("2", "GND")):
    p = next(p for p in fps["J1"].Pads() if p.GetNumber() == num)
    t = pcbnew.PCB_TEXT(b)
    t.SetText(label)
    t.SetLayer(pcbnew.F_SilkS)
    t.SetTextSize(V(0.8, 0.8))
    t.SetTextThickness(mm(0.12))
    t.SetHorizJustify(pcbnew.GR_TEXT_H_ALIGN_LEFT)
    t.SetPosition(V(to(p.GetPosition().x) + 1.8, to(p.GetPosition().y)))
    b.Add(t)
    q = t.GetBoundingBox()
    taken.append((to(q.GetLeft()), to(q.GetTop()), to(q.GetRight()), to(q.GetBottom())))
for r, (x, y, a) in st.items():
    q = box(r)
    taken.append((OX + q[0], OY + q[1], OX + q[2], OY + q[3]))
for r, fp in fps.items():
    if r[0] == "H":
        fp.Reference().SetVisible(False)
        continue
    put(fp.Reference(), to(fp.GetPosition().x), to(fp.GetPosition().y), r)
pcbnew.ZONE_FILLER(b).Fill(b.Zones())
if not pcbnew.SaveBoard(os.path.abspath(PCB), b, True):
    sys.exit("save failed")
print("tracks", sum(1 for t in b.GetTracks() if t.Type() == pcbnew.PCB_TRACE_T), "vias",
      sum(1 for t in b.GetTracks() if t.Type() == pcbnew.PCB_VIA_T), "stitch", stitch)
