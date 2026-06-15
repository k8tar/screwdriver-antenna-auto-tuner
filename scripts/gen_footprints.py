#!/usr/bin/env python3
"""
Generate the project's custom module footprints into Tuner.pretty/.
Run with plain python3 (no pcbnew needed):  python3 gen_footprints.py

These are SOCKETED-MODULE / hand-wound landing patterns. Dimensions are
documented-but-approximate — VERIFY against the actual modules before ordering.
Each footprint carries silk + a courtyard so DRC placement checks are meaningful.
"""
import os, math
KICAD = os.path.abspath(os.path.join(          # the kicad project dir (../hardware/kicad)
    os.path.dirname(os.path.abspath(__file__)), "..", "hardware", "kicad"))
OUT = os.path.join(KICAD, "Tuner.pretty")
os.makedirs(OUT, exist_ok=True)

def pad(num, x, y, first=False, drill=1.0, size=1.8):
    sh = "rect" if first else "circle"
    return (f'  (pad "{num}" thru_hole {sh} (at {x} {y}) (size {size} {size}) '
            f'(drill {drill}) (layers *.Cu *.Mask))')

def smd_pad(num, x, y, w, h, first=False):
    sh = "roundrect"
    return (f'  (pad "{num}" smd {sh} (at {x} {y}) (size {w} {h}) (roundrect_rratio 0.25) '
            f'(layers F.Cu F.Paste F.Mask))')

def rect(x1, y1, x2, y2, layer, width=0.12):
    return "\n".join(
        f'  (fp_line (start {a} {b}) (end {c} {d}) (stroke (width {width}) (type solid)) (layer "{layer}"))'
        for (a, b, c, d) in [(x1, y1, x2, y1), (x2, y1, x2, y2),
                             (x2, y2, x1, y2), (x1, y2, x1, y1)])

def courtyard(x1, y1, x2, y2):
    return rect(x1, y1, x2, y2, "F.CrtYd", 0.05)

def label(s, x, y, size=0.6):
    # Pin-name labels go on F.Fab: visible in KiCad for assembly reference, but
    # NOT on the manufactured silkscreen (keeps silk clean; no text_height DRC).
    return (f'  (fp_text user "{s}" (at {x} {y} 0) (layer "F.Fab") '
            f'(effects (font (size {size} {size}) (thickness 0.12))))')

def footprint(name, descr, body):
    return (f'(footprint "{name}" (version 20240108) (generator "gen_footprints") (layer "F.Cu")\n'
            f'  (descr "{descr}")\n  (attr through_hole)\n'
            f'  (property "Reference" "REF**" (at 0 -8 0) (layer "F.SilkS") '
            f'(effects (font (size 1 1) (thickness 0.15))))\n'
            f'  (property "Value" "{name}" (at 0 8 0) (layer "F.Fab") '
            f'(effects (font (size 1 1) (thickness 0.15))))\n'
            f'{body}\n)\n')

def write(name, descr, body):
    open(f"{OUT}/{name}.kicad_mod", "w").write(footprint(name, descr, body))

# ── Murata OKI-78SR fixed 3.3V SIP buck, TO-220 compatible pinout ───────────
b = [rect(-5.7, -1.8, 5.7, 7.2, "F.SilkS"), courtyard(-6.2, -2.3, 6.2, 7.7)]
for n, x, lbl in [("1", -2.54, "VIN"), ("2", 0.0, "GND"), ("3", 2.54, "VOUT")]:
    b += [pad(n, x, 0, first=(n=="1")), label(lbl, x, 3.9)]
write("REG_OKI78SR", "Murata OKI-78SR SIP regulator, TO-220 compatible pinout", "\n".join(b))

# ── Pololu DRV8871 carrier (~12.7 x 17.8 mm). 2 header rows ──────────────────
b = [rect(-9, -7, 9, 7, "F.SilkS"), courtyard(-9.5, -7.5, 9.5, 7.5)]
for n, x, y, lbl in [("1",-7.62,3.81,"VIN"),("2",-7.62,1.27,"GND"),
                     ("3",-7.62,-1.27,"IN1"),("4",-7.62,-3.81,"IN2"),
                     ("5",7.62,2.54,"OUT1"),("6",7.62,-2.54,"OUT2")]:
    b += [pad(n, x, y, first=(n=="1")), label(lbl, x+(2.6 if x<0 else -2.6), y)]
write("DRV8871_CARRIER", "Pololu DRV8871 carrier (verify pinout vs Pololu #2990)", "\n".join(b))

# ── ESP32 30-pin DevKit (NodeMCU-32S/DOIT V1): 2x15 @ 0.1in, 22.86mm rows ────
# Pad numbers = ESP32-WROOM-32E symbol pin numbers, per the standard devkit map.
LEFT  = [("3","EN"),("4","VP"),("5","VN"),("6","D34"),("7","D35"),("8","D32"),
         ("9","D33"),("10","D25"),("11","D26"),("12","D27"),("13","D14"),
         ("14","D12"),("15","GND"),("16","D13"),("VIN","VIN")]
RIGHT = [("2","3V3"),("1","GND"),("23","D15"),("24","D2"),("26","D4"),("27","D16"),
         ("28","D17"),("29","D5"),("30","D18"),("31","D19"),("33","D21"),
         ("34","RX0"),("35","TX0"),("36","D22"),("37","D23")]
ROW, PITCH = 22.86/2, 2.54
y0 = -(15-1)*PITCH/2
b = [rect(-ROW-2.5, y0-2.2, ROW+2.5, -y0+2.2, "F.SilkS"),
     courtyard(-ROW-3, y0-2.7, ROW+3, -y0+2.7),
     label("ESP32 DevKit 30p", 0, y0-3.4, 0.7)]
for i, (num, lbl) in enumerate(LEFT):
    y = y0 + i*PITCH
    b += [pad(num, -ROW, y, first=(i==0)), label(lbl, -ROW+3.6, y, 0.55)]
for i, (num, lbl) in enumerate(RIGHT):
    y = y0 + i*PITCH
    b += [pad(num, ROW, y), label(lbl, ROW-3.6, y, 0.55)]
write("ESP32_DevKit_30", "ESP32 30-pin DevKit; pads=WROOM pin numbers per devkit map. Verify row pitch.", "\n".join(b))

# ── Hand-wound FT37-43 current transformer: 5 THT leads + toroid silk ───────
pts = [(4.8*math.cos(math.radians(a)), 4.8*math.sin(math.radians(a))) for a in range(0, 360, 20)]
b = [courtyard(-9, -6.5, 9, 6.5),
     "\n".join(f'  (fp_line (start {pts[i][0]:.2f} {pts[i][1]:.2f}) '
               f'(end {pts[(i+1)%len(pts)][0]:.2f} {pts[(i+1)%len(pts)][1]:.2f}) '
            f'(stroke (width 0.08) (type solid)) (layer "F.SilkS"))' for i in range(len(pts)))]
for n, x, y, lbl in [("1",-7.62,2.54,"P1"),("2",-7.62,-2.54,"P2"),
                     ("3",7.62,3.81,"S1"),("4",7.62,0,"SCT"),("5",7.62,-3.81,"S2")]:
    b += [pad(n, x, y, first=(n=="1")), label(lbl, x+(2.4 if x<0 else -2.4), y)]
write("CT_FT37_43_Toroid", "Hand-wound FT37-43 current transformer: P1/P2 1T line, S1/SCT/S2 secondary", "\n".join(b))

print("Wrote footprints:", sorted(os.listdir(OUT)))
