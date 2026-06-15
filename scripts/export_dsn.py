#!/usr/bin/env python3
"""
Export tuner.kicad_pcb to Specctra DSN for Freerouting.
Run inside the KiCad flatpak:
  flatpak run --command=python3 org.kicad.KiCad export_dsn.py

Then in Freerouting: open tuner.dsn, autoroute, export a .ses session file,
and back in KiCad Pcbnew: File > Import > Specctra Session to pull the routes in.
"""
import os, pcbnew
HERE = os.path.abspath(os.path.join(           # the kicad project dir (../hardware/kicad)
    os.path.dirname(os.path.abspath(__file__)), "..", "hardware", "kicad"))
DSN = os.path.join(HERE, "tuner.dsn")
b = pcbnew.LoadBoard(os.path.join(HERE, "tuner.kicad_pcb"))
ok = pcbnew.ExportSpecctraDSN(b, DSN)

# ── Inject wide-track net classes (KiCad's standalone DSN export drops them) ──
# Freerouting honours these per-net width rules (micrometres).
WIDE = {                       # class name -> (width_um, [nets])
    "power": (1000, ["+12V", "/12V_FUSED_IN", "/MTR_OUT1", "/MTR_OUT2"]),
    "rf":    (800,  ["/RF_LINE_IN", "/RF_LINE_OUT"]),
    "p3v3":  (600,  ["+3V3", "/MTR_SNS"]),   # sense line: wider than signal, fits the shunt area
}
moved = {n for _, nets in WIDE.values() for n in nets}
d = open(DSN).read()
h0 = d.index("(class kicad_default"); h1 = d.index("(circuit", h0)
header, rest = d[h0:h1], d[h1:]
for n in moved:                                # drop wide nets from the default class
    header = header.replace(" " + n + "\n", "\n").replace(" " + n + " ", " ")
blocks = ""
for name, (w, nets) in WIDE.items():
    blocks += (f'    (class {name} {" ".join(nets)}\n'
               f'      (circuit\n        (use_via "Via[0-3]_800:400_um")\n      )\n'
               f'      (rule\n        (width {w})\n        (clearance 250)\n      )\n    )\n')
d = d[:h0] + header + rest
d = d.replace("\n  )\n  (wiring", "\n" + blocks + "  )\n  (wiring", 1)
open(DSN, "w").write(d)

print("DSN export:", "OK" if ok else "FAILED", "-", os.path.getsize(DSN), "bytes",
      "(+wide classes:", ", ".join(WIDE), ")")
