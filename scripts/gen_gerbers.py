#!/usr/bin/env python3
"""
Export a fab package (Gerbers + Excellon drill + drill map) and zip it for
JLCPCB / PCBWay / OSH Park.  Run from the project root (tuner/):

    python3 scripts/gen_gerbers.py

Output: fab/gerbers/*  and  fab/tuner_gerbers.zip  (upload the .zip).

NOTE: run scripts/gen_pcb.py first, and ROUTE the board before ordering — an
unrouted board's copper layers have pads + ground pours but no signal traces.
"""
import os, subprocess, zipfile, glob

ROOT  = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
PCB   = os.path.join(ROOT, "hardware", "kicad", "tuner.kicad_pcb")
OUT   = os.path.join(ROOT, "fab", "gerbers")
ZIP   = os.path.join(ROOT, "fab", "tuner_gerbers.zip")
os.makedirs(OUT, exist_ok=True)

CLI = ["flatpak", "run", "--command=kicad-cli", "org.kicad.KiCad"]

# 4-layer board: copper + masks + silks + edge cuts (paste not needed for fab)
layers = ("F.Cu,In1.Cu,In2.Cu,B.Cu,"
          "F.Mask,B.Mask,F.Silkscreen,B.Silkscreen,Edge.Cuts")

def run(args):
    print("  $", " ".join(a.replace(CLI[3], "kicad-cli") for a in args if a not in CLI[:3]))
    subprocess.run(args, check=True)

print("Exporting Gerbers ...")
run(CLI + ["pcb", "export", "gerbers", "--layers", layers,
           "--no-protel-ext", "--output", OUT + os.sep, PCB])

print("Exporting drill (Excellon + map) ...")
run(CLI + ["pcb", "export", "drill", "--format", "excellon",
           "--drill-origin", "absolute", "--excellon-units", "mm",
           "--generate-map", "--map-format", "gerberx2",
           "--output", OUT + os.sep, PCB])

files = sorted(glob.glob(os.path.join(OUT, "*")))
with zipfile.ZipFile(ZIP, "w", zipfile.ZIP_DEFLATED) as z:
    for f in files:
        z.write(f, os.path.basename(f))
print(f"\nWrote {len(files)} files -> {os.path.relpath(ZIP, ROOT)}")
print("Upload the .zip to JLCPCB. Specify: 4 layers, 1.6mm, and the qty/colour you want.")
