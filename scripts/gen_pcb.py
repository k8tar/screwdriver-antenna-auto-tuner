#!/usr/bin/env python3
"""
Generate tuner.kicad_pcb from tuner.net (the schematic netlist) using the
pcbnew Python API.  Run INSIDE the KiCad flatpak:

  flatpak run --command=python3 org.kicad.KiCad gen_pcb.py

Produces a board with: outline, 4-layer stackup, net classes / design rules
(generic hand-solderable), all footprints loaded with nets assigned (ratsnest),
a block-grouped starting placement, and a ground zone.  Routing is done after
in the KiCad GUI (or Freerouting via DSN export).
"""
import re, os, pcbnew

HERE = os.path.abspath(os.path.join(           # the kicad project dir (../hardware/kicad)
    os.path.dirname(os.path.abspath(__file__)), "..", "hardware", "kicad"))
# Footprint libraries as mounted INSIDE the KiCad flatpak sandbox
FPROOT = "/app/extensions/Library/Footprints/footprints"

def fp_dir(lib):
    return os.path.join(HERE, "Tuner.pretty") if lib == "Tuner" else f"{FPROOT}/{lib}.pretty"

MM = pcbnew.FromMM
# Centre the 100x70 board on the A4 sheet (297x210): origin = half the margins.
# Baked into V() so the outline, footprints, holes and zones all shift together.
SHEET = (98.5, 70.0)
def V(x, y): return pcbnew.VECTOR2I(MM(x + SHEET[0]), MM(y + SHEET[1]))

# ── Parse the netlist ───────────────────────────────────────────────────────
net = open(os.path.join(HERE, "tuner.net")).read()

comps = {}   # ref -> (lib, fpname, value)
for block in net.split('\t(comp\n')[1:]:        # one block per component
    ref = re.search(r'\(ref "([^"]+)"', block)
    val = re.search(r'\(value "([^"]+)"', block)
    fpm = re.search(r'\(footprint "([^"]+)"', block)
    if not (ref and val and fpm):
        continue
    if ":" not in fpm.group(1):
        continue
    lib, name = fpm.group(1).split(":", 1)
    comps[ref.group(1)] = (lib, name, val.group(1))

nets = {}    # netname -> [(ref, pad)]
for blk in re.split(r'\t\t\(net\n', net)[1:]:
    nm = re.search(r'\(name "([^"]+)"', blk)
    if not nm:
        continue
    nodes = re.findall(r'\(ref "([^"]+)"\)\s*\n\s*\(pin "([^"]+)"', blk)
    nets[nm.group(1)] = nodes

# ── Deliberate floorplan on a 100 x 70 board ────────────────────────────────
# ESP32 DevKit stands vertically on the LEFT edge; rear connectors along the
# top; front-panel UI along the bottom; circuitry blocks grouped between.
# PLACE: ref -> (x_mm, y_mm, rotation_deg). Anything missing flows in a grid.
PLACE = {
    # ESP32 DevKit, upright (0deg = tall) on the left edge
    "U2": (16, 36, 0),
    # rear-edge connectors (top)
    "J3": (30, 8, 0), "J4": (38, 8, 0), "J1": (48, 8, 0), "J6": (58, 8, 0),
    "J8": (90, 8, 0), "J2": (95, 24, 0),
    # power band: fuse -> TVS -> input bulk -> regulator -> 3V3 bulk/bypass
    "F1": (40, 15, 0), "D1": (48, 15, 0),
    "C1": (41, 25, 0), "C2": (56, 27, 0), "C_VM": (60, 35, 0),
    "U1": (57, 19, 0), "C3": (67, 23, 90),
    # ESP32 decoupling column — clear to the RIGHT of U2 (bbox edge ~x32)
    "C4": (34, 33, 90), "C5": (34, 39, 90), "R_EN": (34, 45, 90),
    "C_EN": (34, 51, 90), "R_IO12": (34, 57, 90),
    # motor (centre) + low-side current sense, isolated from the big parts
    "U4": (48, 46, 0), "C6": (63, 34, 0),
    "U6": (57, 41, 0), "R_SH": (63, 44, 90), "C_INA": (57, 37, 0),
    # radio (top-right)
    "U3": (82, 30, 0), "C11": (77, 19, 0), "C12": (81, 19, 0), "C13": (85, 19, 0),
    "C14": (89, 19, 0), "C15": (93, 19, 0), "Q1": (76, 40, 0), "Q2": (80, 40, 0),
    # SWR coupler (right) + burden/divider at its primary
    "T1": (74, 47, 0), "R3": (70, 53, 90), "C7": (66, 47, 90),
    # right-edge array (3 cols): SWR detectors + CI-V resistors + UI pull-ups
    "D2": (84, 37, 0), "D3": (90, 37, 0),
    "C8": (84, 41, 90), "R4": (88, 41, 90), "C9": (92, 41, 90),
    "C10": (84, 45, 90), "R5": (88, 45, 90), "R6": (92, 45, 90),
    "R_CIV1": (84, 49, 90), "R_CIV2": (88, 49, 90), "R_CIV3": (92, 49, 90),
    "R7": (84, 53, 90), "R8": (88, 53, 90), "R12": (92, 53, 90),
    "R13": (84, 57, 90), "R_TU": (88, 57, 90), "R_TD": (92, 57, 90),
    # front-panel UI row (bottom): OLED, TUNE, PARK, jog rocker
    "J_OLED": (32, 59, 0), "SW1": (46, 59, 0), "SW2": (57, 59, 0), "J_TUNE": (68, 59, 0),
}
# Global centering offset (applied to every placed part).
OFFSET = (1.0, -1.0)
_fallback = [40, 64]   # cursor for anything not explicitly placed
def place_pos(ref):
    if ref in PLACE:
        x, y, r = PLACE[ref]
        return (x + OFFSET[0], y + OFFSET[1], r * 10)   # tenths of a degree
    x, y = _fallback
    _fallback[0] += 6
    if _fallback[0] > 96:
        _fallback[0] = 40; _fallback[1] += 5
    return (x + OFFSET[0], y + OFFSET[1], 0)

# ── Build the board ─────────────────────────────────────────────────────────
board = pcbnew.BOARD()   # default page is A4 (297x210); centred via SHEET in V()

# 4 layers
board.SetCopperLayerCount(4)
ds = board.GetDesignSettings()
ds.SetCopperLayerCount(4)

# Net classes / design rules (generic hand-solderable)
nc = board.GetAllNetClasses()
default = nc["Default"]
default.SetClearance(MM(0.25))
default.SetTrackWidth(MM(0.3))
default.SetViaDiameter(MM(0.8))
default.SetViaDrill(MM(0.4))

io = pcbnew.PCB_IO_MGR.FindPlugin(pcbnew.PCB_IO_MGR.KICAD_SEXP)

# Create / fetch nets
netmap = {}
for netname in nets:
    ni = pcbnew.NETINFO_ITEM(board, netname)
    board.Add(ni)
    netmap[netname] = ni
# pad -> net lookup
pad_net = {}
for netname, nodes in nets.items():
    for ref, pad in nodes:
        pad_net[(ref, pad)] = netname

# Place footprints
placed = 0
for ref, (lib, name, value) in comps.items():
    try:
        fp = io.FootprintLoad(fp_dir(lib), name)
    except Exception as e:
        print(f"  FP LOAD FAIL {ref} {lib}:{name}: {e}")
        continue
    if fp is None:
        print(f"  FP NONE {ref} {lib}:{name}")
        continue
    board.Add(fp)
    fp.SetReference(ref)
    fp.SetValue(value)
    # ── silkscreen cleanup ──
    fp.Value().SetVisible(False)                       # values clutter the silk
    rt = fp.Reference()                                # uniform, valid-size refs
    rt.SetTextSize(pcbnew.VECTOR2I(MM(0.8), MM(0.8)))
    rt.SetTextThickness(MM(0.15))
    x, y, rot = place_pos(ref)
    fp.SetPosition(V(x, y))
    if rot:
        fp.SetOrientationDegrees(rot / 10.0)
    # assign nets to pads
    for p in fp.Pads():
        key = (ref, p.GetNumber())
        if key in pad_net:
            p.SetNet(netmap[pad_net[key]])
    placed += 1

# Board outline 100 x 70 on Edge.Cuts
W, H = 100, 70
edge = pcbnew.PCB_LAYER_ID_COUNT  # placeholder; use Edge.Cuts id
EDGE = pcbnew.Edge_Cuts
for (x1, y1, x2, y2) in [(0,0,W,0),(W,0,W,H),(W,H,0,H),(0,H,0,0)]:
    seg = pcbnew.PCB_SHAPE(board)
    seg.SetShape(pcbnew.SHAPE_T_SEGMENT)
    seg.SetStart(V(x1, y1)); seg.SetEnd(V(x2, y2))
    seg.SetLayer(EDGE); seg.SetWidth(MM(0.15))
    board.Add(seg)

# M3 mounting holes at the four corners (NPTH cutouts on Edge.Cuts).
# These positions are mirrored by the enclosure standoffs (enclosure/enclosure.scad).
HOLES = [(4.5, 4.5), (95.5, 4.5), (4.5, 65.5), (95.5, 65.5)]
for (hx, hy) in HOLES:
    circ = pcbnew.PCB_SHAPE(board)
    circ.SetShape(pcbnew.SHAPE_T_CIRCLE)
    circ.SetCenter(V(hx, hy)); circ.SetEnd(V(hx + 1.6, hy))   # r = 1.6mm (M3 free)
    circ.SetLayer(EDGE); circ.SetWidth(MM(0.15))
    board.Add(circ)

# Ground zone on In1.Cu (and bottom) tied to GND
if "GND" in netmap:
    for layer in (pcbnew.In1_Cu, pcbnew.B_Cu):
        zone = pcbnew.ZONE(board)
        zone.SetLayer(layer)
        zone.SetNet(netmap["GND"])
        zone.SetIsRuleArea(False)
        poly = pcbnew.VECTOR_VECTOR2I()
        for (px, py) in [(0,0),(W,0),(W,H),(0,H)]:
            poly.append(V(px, py))
        zone.AddPolygon(poly)
        zone.SetLocalClearance(MM(0.3))
        board.Add(zone)

pcbnew.SaveBoard(os.path.join(HERE, "tuner.kicad_pcb"), board)
print(f"Saved tuner.kicad_pcb  ({placed}/{len(comps)} footprints placed, "
      f"{len(nets)} nets)")
