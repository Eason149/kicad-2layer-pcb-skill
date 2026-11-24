"""Run with KiCad's bundled Python. export-dsn and fill tested on KiCad 10.0.6; import-ses is untested."""
import argparse
import os
import sys

import pcbnew


def load(path):
    board = pcbnew.LoadBoard(os.path.abspath(path))
    if board is None:
        sys.exit("cannot load " + path)
    if board.GetCopperLayerCount() != 2:
        sys.exit("not a 2-layer board")
    return board


def save(path, board):
    # True = skip settings, so the .kicad_pro file is not rewritten.
    if not pcbnew.SaveBoard(os.path.abspath(path), board, True):
        sys.exit("save failed")


def fill(board):
    board.BuildConnectivity()
    if not pcbnew.ZONE_FILLER(board).Fill(board.Zones()):
        sys.exit("zone fill failed")


ap = argparse.ArgumentParser()
sub = ap.add_subparsers(dest="cmd", required=True)
for name in ("export-dsn", "import-ses"):
    s = sub.add_parser(name)
    s.add_argument("board")
    s.add_argument("file")
sub.add_parser("fill").add_argument("board")
a = ap.parse_args()

b = load(a.board)
if a.cmd == "export-dsn":
    if not pcbnew.ExportSpecctraDSN(b, os.path.abspath(a.file)) or not os.path.exists(a.file):
        sys.exit("DSN export failed")
elif a.cmd == "import-ses":
    if not pcbnew.ImportSpecctraSES(b, os.path.abspath(a.file)):
        sys.exit("SES import failed")
    save(a.board, b)
else:
    fill(b)
    save(a.board, b)
print("ok")
