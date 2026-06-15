#!/usr/bin/env python3
"""
Generate ../BOM.csv from the current netlist (tuner.net), grouped by part number.
Columns: Ref,Qty,Value,Footprint,MPN,Designators
  Ref = one representative designator (short -> Mouser "Customer #", <21 chars)
  Designators = full comma-separated list for assembly
Run from the project root (tuner/):  python3 scripts/gen_bom.py
(refresh the netlist first if the schematic changed.)
"""
import os, re
from collections import defaultdict

HERE = os.path.abspath(os.path.join(           # the kicad project dir (../hardware/kicad)
    os.path.dirname(os.path.abspath(__file__)), "..", "hardware", "kicad"))
net = open(os.path.join(HERE, "tuner.net")).read()

# Verified Mouser-orderable MPNs (commodity passives — substitute equivalents OK).
RES = {  # Yageo RC0805FR-07 series, 1%
    "150R": "RC0805FR-07150RL", "1k": "RC0805FR-071KL",
    "4.7k": "RC0805FR-074K7L", "10k": "RC0805FR-0710KL",
    "0R05_1W": "WSL2512R0500FEA",                 # Vishay 0.05R 1W 2512 sense
}
CAP = {
    "100nF": "CL21B104KBCNNNC",                   # Samsung 100nF 0805
    "10uF": "GRM21BR61C106KE15L",                 # Murata 10uF 16V 0805
    "1nF": "CL21B102KBANNNC", "100pF_NP0": "CL21C101JBANNNC",
    "3p3_NP0": "08055A3R3CAT2A",                  # Kyocera AVX 3.3pF 50V C0G 0805
    "100uF_25V": "EEE-FK1E101P",                  # Panasonic FK 100uF 25V SMD
    "47uF_10V": "EEE-FK1C470P",                   # Panasonic FK 47uF 16V SMD (>10V, fits)
}
BYREF = {  # everything else, by reference
    "D1": "SMBJ13A-E3/52", "D2": "BAT46WS", "D3": "BAT46WS",   # Diotec BAT46WS SOD-323
    "Q1": "MMBT3904LT1G", "Q2": "MMBT3904LT1G",
    "U3": "MAX3232ESE+", "U6": "INA180A1IDBVR",
    "U1": "OKI-78SR-3.3/1.5-W36-C", "U2": "ESP32-DevKitV1-30pin", "U4": "POLOLU-2990",
    "T1": "5943000201",            # Fair-Rite FT37-43 core (Mouser); hand-wind 30T 0.3mm
    "ENC1": "PEC11R-4220F-S0024",
    "SW1": "PTS645VL58-2LFS", "SW2": "PTS645VL58-2LFS", "SW_ENC": "PTS645VL58-2LFS",
    "J1": "61300211121", "J3": "61300211121", "J4": "61300211121",
    "J7": "61300311121", "SW3": "61300311121", "J_TUNE": "61300311121",
    "J6": "61300411121", "J8": "61300411121", "J_OLED": "61300411121", "J2": "61300611121",
}
# Override a wrong schematic-embedded MPN (takes priority over the netlist field).
OVERRIDE = {"F1": "1812L300/24SLER",              # Littelfuse 3A-hold 24V PTC, 1812
            "D2": "BAT46WS", "D3": "BAT46WS"}     # Diotec BAT46WS (schematic had BAT46WJ)

def mpn_for(ref, value, sym):
    if sym == "R": return RES.get(value, "")
    if sym == "C": return CAP.get(value, "")
    return BYREF.get(ref, "")

def natkey(ref):
    m = re.match(r"([A-Za-z_]+)(\d*)", ref)
    return (m.group(1), int(m.group(2)) if m.group(2) else 0)

# Parse one row per component, then group by ORDERABLE PART NUMBER so each Mouser
# line is one row with the correct total quantity (parts sharing an MPN but with
# different function-values — e.g. 2.54mm headers — must NOT split into separate
# lines, or a BOM re-import under-counts them).
groups = defaultdict(lambda: {"refs": [], "values": set(), "fps": set()})
for block in net.split("\t(comp\n")[1:]:
    ref = re.search(r'\(ref "([^"]+)"', block)
    val = re.search(r'\(value "([^"]+)"', block)
    fp  = re.search(r'\(footprint "([^"]*)"', block)
    part = re.search(r'\(libsource\s*\(lib "[^"]*"\)\s*\(part "([^"]+)"', block)
    mpn = re.search(r'\(field\s*\(name "MPN"\)\s*"([^"]*)"', block)
    if not (ref and val):
        continue
    r, value, footprint = ref.group(1), val.group(1), (fp.group(1) if fp else "")
    m = OVERRIDE.get(r) or (mpn.group(1) if mpn and mpn.group(1)
                            else mpn_for(r, value, part.group(1) if part else ""))
    key = m if m else f"{value}|{footprint}"          # group by MPN (fallback)
    g = groups[key]
    g["refs"].append(r); g["values"].add(value); g["fps"].add(footprint)
    g["mpn"] = m

rows = []
for g in groups.values():
    refs = sorted(g["refs"], key=natkey)
    value = " / ".join(sorted(g["values"]))           # join differing function-values
    footprint = " / ".join(sorted(g["fps"]))
    rows.append((refs, len(refs), value, footprint, g["mpn"]))
rows.sort(key=lambda x: natkey(x[0][0]))

# 'Ref' = one representative designator per part (short, <21 chars) -> use as the
# Mouser "Customer #". 'Designators' = the full list (for assembly reference).
out = ["Ref,Qty,Value,Footprint,MPN,Designators"]
for refs, qty, value, footprint, mpn in rows:
    out.append(f'{refs[0]},{qty},{value},{footprint},{mpn},"{",".join(refs)}"')
open(os.path.join(HERE, "..", "BOM.csv"), "w").write("\n".join(out) + "\n")
print(f"Wrote BOM.csv: {len(rows)} line items, {sum(r[1] for r in rows)} parts total")
