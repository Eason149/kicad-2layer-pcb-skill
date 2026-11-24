"""Generate the NE555 flasher schematic. argv: <kicad share dir> <project dir>"""
import json
import re
import sys
import uuid
from pathlib import Path

SHARE, OUT = Path(sys.argv[1]), Path(sys.argv[2])
NAME = "NE555_Flasher"
NS = uuid.UUID("5d0d3a4e-3a0c-4a6e-9a44-0d9f7c1a5550")
uid = lambda k: str(uuid.uuid5(NS, k))
ROOT = uid("root")


def lib_block(lib, name):
    t = (SHARE / "symbols" / (lib + ".kicad_sym")).read_text(encoding="utf-8")
    i = t.index('\n\t(symbol "%s"' % name) + 2
    depth, j, q = 0, i, False
    while True:
        c = t[j]
        if c == "\\" and q:
            j += 1
        elif c == '"':
            q = not q
        elif not q and c == "(":
            depth += 1
        elif not q and c == ")":
            depth -= 1
            if depth == 0:
                break
        j += 1
    return t[i:j + 1].replace('(symbol "%s"' % name, '(symbol "%s:%s"' % (lib, name), 1)


def lib_prop(lib, name, prop):
    m = re.search(r'\(property "%s" "((?:[^"\\]|\\.)*)"' % prop, lib_block(lib, name))
    return m[1] if m else ""


PINS = {"Timer:NE555D": [(0, -10.16), (2.54, 10.16), (-10.16, -5.08), (10.16, 0), (-10.16, 5.08), (0, 10.16),
                         (-10.16, -2.54), (-10.16, 2.54)],
        "Device:R": [(0, 3.81), (0, -3.81)], "Device:C": [(0, 3.81), (0, -3.81)],
        "Device:LED": [(-3.81, 0), (3.81, 0)], "Connector_Generic:Conn_01x02": [(-5.08, 0), (-5.08, -2.54)],
        "power:GND": [(0, 0)], "power:+5V": [(0, 0)], "power:PWR_FLAG": [(0, 0)], "Mechanical:MountingHole": []}
R, C = "Resistor_SMD:R_0805_2012Metric", "Capacitor_SMD:C_0805_2012Metric"
HOLE = "MountingHole:MountingHole_3.2mm_M3"
# lib id, ref, value, footprint, x, y, rot, mirror, ref pos, value pos
parts = [
    ("Timer:NE555D", "U1", "NE555D", "Package_SO:SOIC-8_3.9x4.9mm_P1.27mm", 152.4, 101.6, 0, "", (161.29, 92.71), (161.29, 95.25)),
    ("Device:R", "R1", "10k", R, 127, 86.36, 0, "", None, None),
    ("Device:R", "R2", "47k", R, 127, 102.87, 0, "", (119.38, 101.6), (119.38, 104.14)),
    ("Device:R", "R3", "470R", R, 170.18, 105.41, 0, "", None, None),
    ("Device:C", "C1", "10uF", C, 127, 118.11, 0, "", None, None),
    ("Device:C", "C2", "10nF", C, 142.24, 85.09, 0, "", None, None),
    ("Device:C", "C3", "100nF", C, 83.82, 95.25, 0, "", None, None),
    ("Device:C", "C4", "10uF", C, 99.06, 95.25, 0, "", None, None),
    ("Device:LED", "D1", "RED", "LED_SMD:LED_0805_2012Metric", 170.18, 113.03, 90, "", (173.99, 113.03), (173.99, 115.57)),
    ("Connector_Generic:Conn_01x02", "J1", "5V_IN", "Connector_PinHeader_2.54mm:PinHeader_1x02_P2.54mm_Vertical",
     50.8, 99.06, 0, "y", (48.26, 95.25), (48.26, 105.41)),
] + [("Mechanical:MountingHole", "H%d" % (i + 1), "M3", HOLE, 205.74 + 15.24 * i, 101.6, 0, "",
      (208.28 + 15.24 * i, 100.33), (208.28 + 15.24 * i, 102.87)) for i in range(4)]
n5, ng, nf = [(127, 78.74), (134.62, 78.74), (154.94, 78.74), (73.66, 91.44)], \
    [(127, 124.46), (142.24, 88.9), (152.4, 124.46), (170.18, 124.46), (73.66, 106.68)], [(66.04, 91.44), (66.04, 106.68)]
for lst, lid, pre in ((n5, "power:+5V", "#PWR0"), (ng, "power:GND", "#PWR1"), (nf, "power:PWR_FLAG", "#FLG0")):
    for i, (x, y) in enumerate(lst):
        dy = 3.81 if lid == "power:GND" else -3.81
        parts.append((lid, pre + str(i + 1), lid.split(":")[1], "", x, y, 0, "", None, (x, y + dy)))

wires = [
    [(127, 82.55), (127, 78.74)], [(127, 90.17), (127, 99.06)], [(127, 99.06), (142.24, 99.06)],
    [(127, 106.68), (142.24, 106.68)], [(142.24, 104.14), (139.7, 104.14), (139.7, 106.68)],
    [(127, 106.68), (127, 114.3)], [(127, 121.92), (127, 124.46)],
    [(142.24, 96.52), (134.62, 96.52), (134.62, 78.74)], [(154.94, 91.44), (154.94, 78.74)],
    [(152.4, 91.44), (152.4, 81.28), (142.24, 81.28)], [(162.56, 101.6), (170.18, 101.6)],
    [(170.18, 116.84), (170.18, 124.46)], [(152.4, 111.76), (152.4, 124.46)],
    [(55.88, 99.06), (60.96, 99.06), (60.96, 91.44), (99.06, 91.44)],
    [(55.88, 101.6), (60.96, 101.6), (60.96, 106.68), (99.06, 106.68)],
    [(83.82, 99.06), (83.82, 106.68)], [(99.06, 99.06), (99.06, 106.68)],
]


def pin_points(p):
    lid, x, y, rot, mir = p[0], p[4], p[5], p[6], p[7]
    for a, b in PINS[lid]:
        if rot == 90:
            a, b = -b, a
        if mir == "y":
            a = -a
        yield (round(x + a, 2), round(y - b, 2))


ends = [pt for p in parts for pt in pin_points(p)] + [w[k] for w in wires for k in range(len(w))]
segs = []
for w in wires:
    for (x1, y1), (x2, y2) in zip(w, w[1:]):
        on = {(x, y) for x, y in ends if min(x1, x2) <= x <= max(x1, x2) and min(y1, y2) <= y <= max(y1, y2)}
        on = sorted(on)
        segs += list(zip(on, on[1:]))
count = {}
for s in segs:
    for pt in s:
        count[pt] = count.get(pt, 0) + 1
for p in parts:
    for pt in pin_points(p):
        if pt in count:
            count[pt] += 1
junctions = [p for p, n in count.items() if n >= 3]

FX = "(effects (font (size 1.27 1.27))%s)"


def prop(n, v, x, y, ang=0, hide=False, just=" (justify left)"):
    return '\t\t(property "%s" "%s" (at %g %g %g)%s %s)\n' % (
        n, v, x, y, ang, " (hide yes)" if hide else "", FX % just)


o = ['(kicad_sch (version 20250114) (generator "eeschema") (generator_version "9.0")\n\t(uuid "%s")\n\t(paper "A4")\n'
     '\t(title_block (title "NE555 LED Flasher") (rev "1"))\n\t(lib_symbols\n' % ROOT]
for lid in PINS:
    o.append("\t" + lib_block(*lid.split(":")) + "\n")
o.append("\t)\n")
for x, y, t in ((45.72, 81.28, "POWER INPUT 5V"), (119.38, 68.58, "ASTABLE OSCILLATOR"), (205.74, 93.98, "MOUNTING")):
    o.append('\t(text "%s" (exclude_from_sim no) (at %g %g 0) (effects (font (size 2 2)) (justify left)) (uuid "%s"))\n'
             % (t, x, y, uid(t)))
for x, y in junctions:
    o.append('\t(junction (at %g %g) (diameter 0) (color 0 0 0 0) (uuid "%s"))\n' % (x, y, uid("j%s%s" % (x, y))))
for a, b in segs:
    o.append('\t(wire (pts (xy %g %g) (xy %g %g)) (stroke (width 0) (type default)) (uuid "%s"))\n'
             % (*a, *b, uid("w%s%s" % (a, b))))
for lid, ref, val, fp, x, y, rot, mir, rp, vp in parts:
    power = lid.startswith("power:")
    rp, vp2 = rp or (x + 2.54, y - 1.27), vp or (x + 2.54, y + 1.27)
    just = "" if power else (" (justify left)" if not (mir or ref in ("R2",)) else "")
    ang = 90 if rot == 90 else 0
    if rot == 90:
        just = " (justify right)"
    o.append('\t(symbol (lib_id "%s") (at %g %g %d)%s (unit 1) (exclude_from_sim no) (in_bom %s) (on_board yes) (dnp no)\n'
             '\t\t(uuid "%s")\n' % (lid, x, y, rot, " (mirror y)" if mir else "", "no" if ref[0] == "H" else "yes", uid(ref)))
    o.append(prop("Reference", ref, *rp, ang, power, just) + prop("Value", val, *vp2, ang, False, just) +
             prop("Footprint", fp, x, y, 0, True) +
             prop("Datasheet", lib_prop(*lid.split(":"), "Datasheet"), x, y, 0, True) +
             prop("Description", lib_prop(*lid.split(":"), "Description"), x, y, 0, True))
    for n in range(len(PINS[lid])):
        o.append('\t\t(pin "%d" (uuid "%s"))\n' % (n + 1, uid(ref + "p%d" % n)))
    o.append('\t\t(instances (project "%s" (path "/%s" (reference "%s") (unit 1))))\n\t)\n' % (NAME, ROOT, ref))
o.append('\t(sheet_instances (path "/" (page "1")))\n)\n')
OUT.mkdir(parents=True, exist_ok=True)
(OUT / (NAME + ".kicad_sch")).write_text("".join(o), encoding="utf-8")
(OUT / (NAME + ".kicad_pro")).write_text(json.dumps({
    "board": {"design_settings": {"rules": {
        "min_clearance": 0.2, "min_track_width": 0.2, "min_copper_edge_clearance": 0.3,
        "min_via_diameter": 0.6, "min_through_hole_diameter": 0.3}}},
    "schematic": {"page_layout_descr_file": "sheet.kicad_wks"},
    "pcbnew": {"page_layout_descr_file": "sheet.kicad_wks"},
    "meta": {"filename": NAME + ".kicad_pro", "version": 3},
    "net_settings": {"classes": [{"name": "Default", "clearance": 0.2, "track_width": 0.2,
                                  "via_diameter": 0.6, "via_drill": 0.3}], "meta": {"version": 4}},
}, indent=2), encoding="utf-8")
(OUT / "sheet.kicad_wks").write_text(
    '(kicad_wks (version 20231118) (generator "pl_editor") (generator_version "9.0")\n'
    '  (setup (textsize 1.5 1.5) (linewidth 0.15) (textlinewidth 0.15) (left_margin 10) (right_margin 10) '
    '(top_margin 10) (bottom_margin 10))\n  (rect (name "") (start 0 0 ltcorner) (end 0 0))\n'
    '  (tbtext "${TITLE}  Rev ${REVISION}" (name "") (pos 4 5) (justify right))\n)\n', encoding="utf-8")
print("segments", len(segs), "junctions", len(junctions))
