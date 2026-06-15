#!/usr/bin/env python3
"""
Import a Freerouting session (.ses) back into the board, refill the ground
zones, and save.  Run inside the KiCad flatpak from the project root (tuner/):

    flatpak run --command=python3 org.kicad.KiCad scripts/import_ses.py

Full routing loop:
    1. python3 scripts/gen_pcb.py                  # (re)build the board
    2. flatpak run ... scripts/export_dsn.py        # board -> tuner.dsn
    3. java -jar freerouting.jar -de tuner.dsn -do tuner.ses -mp 30   # route
    4. flatpak run ... scripts/import_ses.py        # tuner.ses -> board (this)
"""
import os, pcbnew
K = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                 "..", "hardware", "kicad"))
b = pcbnew.LoadBoard(os.path.join(K, "tuner.kicad_pcb"))
ok = pcbnew.ImportSpecctraSES(b, os.path.join(K, "tuner.ses"))
pcbnew.ZONE_FILLER(b).Fill(b.Zones())          # refill GND pours around new tracks
pcbnew.SaveBoard(os.path.join(K, "tuner.kicad_pcb"), b)
seg = sum(1 for t in b.Tracks() if t.Type() == pcbnew.PCB_TRACE_T)
via = sum(1 for t in b.Tracks() if t.Type() == pcbnew.PCB_VIA_T)
print(f"Imported SES: {ok}  ->  {seg} track segments, {via} vias; zones refilled.")
