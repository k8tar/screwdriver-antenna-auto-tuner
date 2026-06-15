#!/usr/bin/env python3
"""
Generate tuner.kicad_sch for KiCad 10  —  label-driven (netlist-style) schematic.

Design philosophy (why this is ERC-clean by construction):
  * KiCad's native grid is 1.27 mm (50 mil). ALL geometry is built on it.
  * Symbol pin tips are read directly from the installed library, so every
    coordinate is exact.
  * There are NO long inter-component wires. Every pin gets a short 2.54 mm
    stub terminated by either a net label (signals) or a power symbol
    (power/ground). Components connect purely by matching label names.
    => wires cannot "miss" a pin, and there are no dangling endpoints.
  * Unused MCU IO pins get explicit no-connect markers.
  * Each power net carries a PWR_FLAG so ERC sees it as driven.

Run from the project root (tuner/):  python3 scripts/gen_schematic.py
Validate: flatpak run --command=kicad-cli org.kicad.KiCad sch erc tuner.kicad_sch -o erc.json --format json
"""

import re, math, os

KICAD = os.path.abspath(os.path.join(          # the kicad project dir (../hardware/kicad)
    os.path.dirname(os.path.abspath(__file__)), "..", "hardware", "kicad"))
LIBDIR = ("/var/lib/flatpak/runtime/org.kicad.KiCad.Library.Symbols/x86_64/stable/"
          "3b7929bb14971a6b04bc640443a65ebdfa78dc56d399fae4f24c1834540307a9/files/symbols")

G    = 1.27       # KiCad native grid (mm)
STUB = 2 * G      # 2.54 mm pin stub length
# Global sheet offset so the drawing sits CENTRED on the A1 sheet (841x594mm).
# Multiples of G so pins stay on grid. (Content span ~588x446; these centre it.)
OX, OY = 86 * G, 41 * G    # 109.22, 52.07 mm
ROOT_UUID = "00000000-0000-0000-0000-000000000001"
PROJECT   = "tuner"

def instances_block(ref, unit=1, indent="    "):
    """Required so KiCad instantiates the symbol (connectivity + annotation)."""
    return (f'{indent}(instances\n'
            f'{indent}  (project "{PROJECT}"\n'
            f'{indent}    (path "/{ROOT_UUID}"\n'
            f'{indent}      (reference "{ref}") (unit {unit})\n'
            f'{indent}    )\n'
            f'{indent}  )\n'
            f'{indent})')

_pwr_ctr = [0]
def next_pwr_ref():
    _pwr_ctr[0] += 1
    return f"#PWR{_pwr_ctr[0]:04d}"

_flg_ctr = [0]
def next_flg_ref():
    _flg_ctr[0] += 1
    return f"#FLG{_flg_ctr[0]:04d}"

# ── Unique id counter (deterministic) ──────────────────────────────────────
_uid = 0
def uid():
    global _uid
    _uid += 1
    return f"00000000-0000-0000-0000-{_uid:012x}"

def gsnap(v):
    return round(round(v / G) * G, 4)

def sign(v):
    return 0 if abs(v) < 1e-9 else (1 if v > 0 else -1)

# ── Custom (locally-defined) symbols ───────────────────────────────────────
# For parts not in the installed libraries (e.g. a hand-wound current
# transformer). Each entry: name -> (lib_symbols_text, {num:(x,y,ang)}, {pname:num})
CUSTOM = {}

def _register_custom(name, body, pins):
    """pins: list of (num, pname, x, y, ang). Builds a minimal valid lib symbol."""
    pmap, n2n = {}, {}
    pin_sexprs = []
    for num, pname, x, y, ang in pins:
        pmap[num] = (x, y, ang)
        if pname:
            n2n[pname] = num
        pin_sexprs.append(
            f'      (pin passive line (at {x} {y} {ang}) (length 2.54)\n'
            f'        (name "{pname}" (effects (font (size 1.27 1.27))))\n'
            f'        (number "{num}" (effects (font (size 1.27 1.27)))))')
    text = (
        f'    (symbol "Tuner:{name}"\n'
        f'      (pin_names (offset 1.016)) (in_bom yes) (on_board yes)\n'
        f'      (property "Reference" "T" (at 0 7.62 0) (effects (font (size 1.27 1.27))))\n'
        f'      (property "Value" "{name}" (at 0 -7.62 0) (effects (font (size 1.27 1.27))))\n'
        f'      (property "Footprint" "" (at 0 0 0) (effects (font (size 1.27 1.27)) (hide yes)))\n'
        f'      (property "Datasheet" "" (at 0 0 0) (effects (font (size 1.27 1.27)) (hide yes)))\n'
        f'      (symbol "{name}_0_1"\n{body}\n      )\n'
        f'      (symbol "{name}_1_1"\n' + "\n".join(pin_sexprs) + '\n      )\n'
        f'    )')
    CUSTOM[name] = (text, pmap, n2n)

# Current transformer for the Bruene directional coupler (FT37-43, 1T:Ns,
# centre-tapped secondary). P1/P2 = through-line (1 turn); S1/SCT/S2 = secondary.
_register_custom(
    "CT_FT37_43",
    body=(
        '        (polyline (pts (xy -2.54 5.08) (xy -2.54 -5.08)) (stroke (width 0.3)))\n'
        '        (polyline (pts (xy  2.54 5.08) (xy  2.54 -5.08)) (stroke (width 0.3)))\n'
        '        (polyline (pts (xy -0.5 5.08) (xy 0.5 5.08)) (stroke (width 0)))\n'
        '        (polyline (pts (xy -0.5 -5.08) (xy 0.5 -5.08)) (stroke (width 0)))'),
    pins=[
        ("1", "P1",  -7.62,  2.54, 0),
        ("2", "P2",  -7.62, -2.54, 0),
        ("3", "S1",   7.62,  5.08, 180),
        ("4", "SCT",  7.62,  0.0,  180),
        ("5", "S2",   7.62, -5.08, 180),
    ])

# MP1584EN mini buck module (set to 3.3V). Socketed 4-pin module.
_register_custom(
    "BUCK_MP1584",
    body='        (rectangle (start -7.62 6.35) (end 7.62 -6.35) (stroke (width 0.254)) (fill (type background)))',
    pins=[
        ("1", "IN+",  -10.16,  3.81, 0),
        ("2", "IN-",  -10.16, -3.81, 0),
        ("3", "OUT+",  10.16,  3.81, 180),
        ("4", "OUT-",  10.16, -3.81, 180),
    ])

# Pololu DRV8871 single-brushed-DC motor driver carrier. Socketed module.
_register_custom(
    "DRV8871_CARRIER",
    body='        (rectangle (start -7.62 8.89) (end 7.62 -8.89) (stroke (width 0.254)) (fill (type background)))',
    pins=[
        ("1", "VIN",  -10.16,  6.35, 0),
        ("2", "GND",  -10.16,  3.81, 0),
        ("3", "IN1",  -10.16, -1.27, 0),
        ("4", "IN2",  -10.16, -3.81, 0),
        ("5", "OUT1",  10.16,  6.35, 180),
        ("6", "OUT2",  10.16,  3.81, 180),
    ])

# ── Library symbol extraction ──────────────────────────────────────────────
_LIB_CACHE = {}
def _libtext(lib_file):
    if lib_file not in _LIB_CACHE:
        _LIB_CACHE[lib_file] = open(f"{LIBDIR}/{lib_file}").read()
    return _LIB_CACHE[lib_file]

def _symbol_block(content, name):
    start = content.find(f'\t(symbol "{name}"\n')
    if start == -1:
        return None
    depth = 0
    for i in range(start, len(content)):
        if content[i] == '(':
            depth += 1
        elif content[i] == ')':
            depth -= 1
            if depth == 0:
                return content[start:i + 1]
    return None

def _iter_properties(block):
    """Yield (key, full_sexpr_text) for each top-level (property "K" ...) in block."""
    i = 0
    while True:
        j = block.find('(property "', i)
        if j == -1:
            return
        key = block[j + len('(property "'):block.find('"', j + len('(property "'))]
        depth = 0
        for k in range(j, len(block)):
            if block[k] == '(':
                depth += 1
            elif block[k] == ')':
                depth -= 1
                if depth == 0:
                    yield key, block[j:k + 1]
                    i = k + 1
                    break

def _overlay_properties(parent_block, child_block):
    """
    Make the flattened symbol's property SET exactly match the child's, so the
    schematic cache matches KiCad's own resolution of the extends (graphics from
    parent, properties from child). Replaces shared keys' values; appends
    child-only keys; drops parent-only keys.
    """
    child_props = list(_iter_properties(child_block))            # [(key, full_sexpr)]
    out = parent_block
    # Remove ALL parent property sexprs (with their trailing newline).
    for _, txt in list(_iter_properties(out)):
        out = out.replace('\n\t\t' + txt, '', 1)
        out = out.replace('\n      ' + txt, '', 1)
        out = out.replace(txt, '', 1)
    # Insert the child's properties (in the child's order) right after the header.
    nl = out.find('\n')
    block = ''.join('\n      ' + ctxt for _, ctxt in child_props)
    return out[:nl] + block + out[nl:]

def extract_lib_symbol(lib_file, name):
    """
    Return a FLATTENED (symbol ...) block for the lib_symbols section.

    KiCad's per-schematic symbol cache contains no '(extends ...)' — inheritance
    must be resolved. If the requested symbol extends a parent, we take the
    PARENT's geometry/pins (renaming its symbol+subunits to the child name) so
    the placed part actually has connectable pins.

    The top-level name carries the library nickname ("Device:Fuse") to match
    the lib_id used on placements; subunit names stay bare ("Fuse_0_1").
    """
    if lib_file == "custom":
        return CUSTOM[name][0]

    content = _libtext(lib_file)
    child = _symbol_block(content, name)
    if child is None:
        raise ValueError(f"symbol '{name}' not found in {lib_file}")

    ext = re.search(r'\(extends "([^"]+)"', child)
    if ext:
        parent_name = ext.group(1)
        parent = _symbol_block(content, parent_name)
        if parent is None:
            raise ValueError(f"parent '{parent_name}' of '{name}' not found in {lib_file}")
        # Use parent geometry; rename parent symbol + its subunits to the child name.
        block = parent.replace(f'(symbol "{parent_name}', f'(symbol "{name}')
        # Overlay the CHILD's property VALUES so the cache matches KiCad's own
        # resolution of the extends (geometry from parent, properties from child).
        block = _overlay_properties(block, child)
    else:
        block = child

    nick = lib_file.replace('.kicad_sym', '')
    block = block.replace(f'(symbol "{name}"', f'(symbol "{nick}:{name}"', 1)
    return '\n'.join('    ' + l[1:] if l.startswith('\t') else '    ' + l
                     for l in block.split('\n'))

def register_lib_as_custom(lib_file, name):
    """
    Flatten a stdlib (extends) symbol once and serve it from our own 'Tuner'
    library instead. The embedded copy is then compared by ERC against a library
    WE generate from the same source, so they are byte-identical -> no
    lib_symbol_mismatch warning (which otherwise dogs flattened stdlib parts).
    """
    text = extract_lib_symbol(lib_file, name)
    nick = lib_file.replace('.kicad_sym', '')
    text = text.replace(f'(symbol "{nick}:{name}"', f'(symbol "Tuner:{name}"', 1)
    pins, n2n = get_pins(lib_file, name)
    CUSTOM[name] = (text, pins, n2n)

def get_pins(lib_file, name):
    """
    Return ({pin_number: (x, y, angle)}, {pin_name: pin_number}) using the
    library's own coordinates. Follows (extends ...) and merges subunits.
    The (at) point is the electrical connection tip.
    """
    if lib_file == "custom":
        _, pmap, n2n = CUSTOM[name]
        return dict(pmap), dict(n2n)

    content = _libtext(lib_file)

    # resolve extends
    idx = content.find(f'"{name}"')
    ext = re.search(r'\(extends "([^"]+)"', content[idx:idx + 200]) if idx != -1 else None
    geom_name = ext.group(1) if ext else name

    pins = {}
    name2num = {}
    for sub in (geom_name, f"{geom_name}_0_1", f"{geom_name}_1_1", f"{geom_name}_0_0"):
        block = _symbol_block(content, sub)
        if not block:
            continue
        for m in re.finditer(
            r'\(pin\s+\w+\s+\w+\s+\(at\s+([\d.\-]+)\s+([\d.\-]+)\s+(\d+)\)\s+\(length\s+[\d.]+\)'
            r'.*?\(name\s+"([^"]*)".*?\(number\s+"([^"]+)"', block, re.DOTALL):
            x, y, ang = float(m.group(1)), float(m.group(2)), int(m.group(3))
            pname, num = m.group(4), m.group(5)
            pins[num] = (x, y, ang)
            if pname:
                name2num[pname] = num
    return pins, name2num

# ── Geometry ────────────────────────────────────────────────────────────────
def rot(x, y, deg):
    a = math.radians(deg)
    return (x * math.cos(a) - y * math.sin(a),
            x * math.sin(a) + y * math.cos(a))

# ── Emitters ────────────────────────────────────────────────────────────────
sheet = []   # every element string lands here

def emit(s):
    if s:
        sheet.append(s)

def wire(x1, y1, x2, y2):
    x1, y1, x2, y2 = gsnap(x1), gsnap(y1), gsnap(x2), gsnap(y2)
    if (x1, y1) == (x2, y2):
        return
    emit(f'  (wire (pts (xy {x1} {y1}) (xy {x2} {y2}))\n'
         f'    (stroke (width 0) (type default)) (uuid "{uid()}"))')

def label(name, x, y, angle=0, justify="left bottom"):
    emit(f'  (label "{name}" (at {gsnap(x)} {gsnap(y)} {angle})\n'
         f'    (effects (font (size 1.27 1.27)) (justify {justify})) (uuid "{uid()}"))')

def power_symbol(net, x, y, angle=0):
    libid = {"+3V3": "power:+3V3", "+12V": "power:+12V", "GND": "power:GND"}[net]
    ref = next_pwr_ref()
    x, y = gsnap(x), gsnap(y)
    voff = y + 2.54 if net == "GND" else y - 2.54
    emit(f'  (symbol (lib_id "{libid}") (at {x} {y} {angle}) (unit 1)\n'
         f'    (in_bom no) (on_board no) (uuid "{uid()}")\n'
         f'    (property "Reference" "{ref}" (at {x} {y+5.08} 0)\n'
         f'      (effects (font (size 1.27 1.27)) (hide yes)))\n'
         f'    (property "Value" "{net}" (at {x} {voff} 0)\n'
         f'      (effects (font (size 1.27 1.27))))\n'
         f'{instances_block(ref)})')

def no_connect(x, y):
    emit(f'  (no_connect (at {gsnap(x)} {gsnap(y)}) (uuid "{uid()}"))')

def sch_text(s, x, y, size=1.27):
    for c in ('—', '–'):
        s = s.replace(c, '-')
    s = s.replace('→', '->').replace('"', "'")
    emit(f'  (text "{s}" (at {gsnap(x) + OX} {gsnap(y) + OY} 0)\n'
         f'    (effects (font (size {size} {size})) (justify left)) (uuid "{uid()}"))')

def flag_net(net, x, y):
    """Drop a PWR_FLAG (with a net label) onto an arbitrary net so ERC sees a
    power-input pin on that net as driven (e.g. a driver GND through a shunt)."""
    x, y = gsnap(x) + OX, gsnap(y) + OY
    label(net, x, y)
    wire(x, y, x, y - STUB)
    ref = next_flg_ref()
    emit(f'  (symbol (lib_id "power:PWR_FLAG") (at {x} {y - STUB} 180) (unit 1)\n'
         f'    (in_bom no) (on_board no) (uuid "{uid()}")\n'
         f'    (property "Reference" "{ref}" (at {x} {y - STUB - 2.54} 0)\n'
         f'      (effects (font (size 1.27 1.27)) (hide yes)))\n'
         f'    (property "Value" "PWR_FLAG" (at {x} {y - STUB + 2.54} 0)\n'
         f'      (effects (font (size 1.27 1.27)) (hide yes)))\n'
         f'{instances_block(ref)})')

def pwr_flag(net, x, y):
    """Place a power symbol + PWR_FLAG on a tiny wire so ERC sees the net driven."""
    x, y = gsnap(x) + OX, gsnap(y) + OY
    power_symbol(net, x, y)                       # net symbol, pin at (x,y)
    wire(x, y, x, y - STUB)                        # short wire down
    ref = next_flg_ref()
    # PWR_FLAG, pin at (0,0), pointing up so it lands on (x, y-STUB)
    emit(f'  (symbol (lib_id "power:PWR_FLAG") (at {x} {y - STUB} 180) (unit 1)\n'
         f'    (in_bom no) (on_board no) (uuid "{uid()}")\n'
         f'    (property "Reference" "{ref}" (at {x} {y - STUB - 2.54} 0)\n'
         f'      (effects (font (size 1.27 1.27)) (hide yes)))\n'
         f'    (property "Value" "PWR_FLAG" (at {x} {y - STUB + 2.54} 0)\n'
         f'      (effects (font (size 1.27 1.27)) (hide yes)))\n'
         f'{instances_block(ref)})')

# ── Component placement ─────────────────────────────────────────────────────
_refs = {}

class Comp:
    """A placed symbol. Pin tips are exact world coordinates."""
    def __init__(self, lib_file, lib_sym, ref, value, x, y, angle=0, props=None):
        self.x, self.y, self.angle = gsnap(x) + OX, gsnap(y) + OY, angle
        self.ref, self.value = ref, value
        if lib_file == "custom":
            self.libid = f"Tuner:{lib_sym}"
        else:
            self.libid = f"{lib_file.replace('.kicad_sym','')}:{lib_sym}"
        self.pins_raw, self.name2num = get_pins(lib_file, lib_sym)
        # emit the placement
        props = props or {}
        p = ''
        for k, v in props.items():
            p += (f'\n    (property "{k}" "{v}" (at {self.x} {self.y} 0)\n'
                  f'      (effects (font (size 1.27 1.27)) (hide yes)))')
        emit(f'  (symbol (lib_id "{self.libid}") (at {self.x} {self.y} {angle}) (unit 1)\n'
             f'    (in_bom yes) (on_board yes) (dnp no) (uuid "{uid()}")\n'
             f'    (property "Reference" "{ref}" (at {self.x + 6.35} {self.y - 1.27} 0)\n'
             f'      (effects (font (size 1.27 1.27)) (justify left)))\n'
             f'    (property "Value" "{value}" (at {self.x + 6.35} {self.y + 1.27} 0)\n'
             f'      (effects (font (size 1.27 1.27)) (justify left))){p}\n'
             f'{instances_block(ref)})')
        _refs[ref] = self

    def _resolve(self, key):
        """Accept a pin number or a pin name."""
        if key in self.pins_raw:
            return key
        if key in self.name2num:
            return self.name2num[key]
        raise KeyError(f"{self.ref}: no pin '{key}' (have numbers {list(self.pins_raw)} / "
                       f"names {list(self.name2num)})")

    def pin_xy(self, key):
        number = self._resolve(key)
        px, py, _ = self.pins_raw[number]
        # KiCad symbol libs are Y-up; the schematic sheet is Y-down.
        # KiCad negates pin Y on instantiation, then applies the placement
        # rotation in the sheet frame.
        rx, ry = rot(px, -py, self.angle)
        return gsnap(self.x + rx), gsnap(self.y + ry)

    def outward(self, number):
        """
        Unit outward (away-from-body) direction at a pin, derived from the pin's
        own ANGLE — so an edge pin always exits perpendicular to its edge,
        regardless of where it sits along that edge.
        Library frame is Y-up; sheet frame is Y-flip then component rotation.
        """
        num = self._resolve(number)
        _, _, ang = self.pins_raw[num]
        base = {0: (-1, 0), 90: (0, -1), 180: (1, 0), 270: (0, 1)}[ang % 360]
        fx, fy = base[0], -base[1]            # Y-flip
        rx, ry = rot(fx, fy, self.angle)      # placement rotation
        if abs(rx) >= abs(ry):
            return (sign(rx), 0)
        return (0, sign(ry))

    def connect(self, number, net):
        """
        net values:
          '+3V3' / '+12V' / 'GND'  -> power symbol
          'NC' or None             -> no-connect marker (no stub)
          other string             -> net label
        """
        px, py = self.pin_xy(number)
        if net in (None, 'NC'):
            no_connect(px, py)
            return
        ox, oy = self.outward(number)
        ex, ey = px + ox * STUB, py + oy * STUB
        wire(px, py, ex, ey)
        if net in ("+3V3", "+12V", "GND"):
            power_symbol(net, ex, ey)
        else:
            # Orient the label text so it runs AWAY from the component body.
            if ox < 0:                       # pin exits left  -> text extends left
                langle, just = 0, "right bottom"
            elif ox > 0:                     # pin exits right -> text extends right
                langle, just = 0, "left bottom"
            elif oy < 0:                     # pin exits up    -> text runs upward
                langle, just = 90, "left bottom"
            else:                            # pin exits down  -> text runs downward
                langle, just = 90, "right bottom"
            label(net, ex, ey, langle, just)

# ── convenience helpers for 2-terminal parts ────────────────────────────────
def passive(lib_file, sym, ref, value, x, y, net1, net2, props=None, angle=0):
    c = Comp(lib_file, sym, ref, value, x, y, angle, props)
    c.connect("1", net1)
    c.connect("2", net2)
    return c

class Farm:
    """
    A collision-free grid of cells for loose 2-pin parts.  Cells are wide enough
    that a 2.54 mm stub + label text from one cell never reaches a neighbour.
    Connectivity is by net name, so position is purely cosmetic/safety.
    """
    def __init__(self, x0, y0, cols, dx=22.86, dy=15.24):
        self.x0, self.y0, self.cols, self.dx, self.dy = x0, y0, cols, dx, dy
        self.i = 0
    def cell(self):
        r, c = divmod(self.i, self.cols)
        self.i += 1
        return self.x0 + c * self.dx, self.y0 + r * self.dy
    def passive(self, lib_file, sym, ref, value, net1, net2, props=None, angle=0):
        x, y = self.cell()
        return passive(lib_file, sym, ref, value, x, y, net1, net2, props, angle)

# ════════════════════════════════════════════════════════════════════════════
# LAYOUT
# Positions are for readability only; connectivity is 100% by net name.
# Columns: ~50 (power), ~130 (ESP32 hub), ~210 (radio/io), blocks stacked in y.
# ════════════════════════════════════════════════════════════════════════════

# ── Power-net drivers (so ERC sees nets as driven) ──────────────────────────
sch_text("POWER NET FLAGS", 20, 16, 1.5)
pwr_flag("+12V", 20, 24)
pwr_flag("+3V3", 40, 24)
pwr_flag("GND",  60, 24)

# ─────────────────────────────────────────────────────────────────────────────
# BLOCK 1 — POWER SUPPLY  (MP1584 module, 12 V -> 3.3 V)
# ─────────────────────────────────────────────────────────────────────────────
sch_text("POWER SUPPLY  -  MP1584 module  12V -> 3.3V", 20, 40, 1.5)

# 12 V input connector
J1 = Comp("Connector_Generic.kicad_sym", "Conn_01x02", "J1", "12V_IN", 28, 56,
          props={"Footprint": "Connector_PinHeader_2.54mm:PinHeader_1x02_P2.54mm_Vertical",
                 "Description": "12V DC input"})
J1.connect("1", "12V_FUSED_IN")   # to fuse
J1.connect("2", "GND")

# Input protection: polyfuse + TVS + bulk cap
passive("Device.kicad_sym", "Fuse", "F1", "3A_PTC", 50, 56, "12V_FUSED_IN", "+12V",
        props={"Footprint": "Fuse:Fuse_1812_4532Metric", "MPN": "1812L300PR"}, angle=90)
passive("Device.kicad_sym", "D_TVS", "D1", "SMBJ13A", 68, 60, "+12V", "GND",
        props={"Footprint": "Diode_SMD:D_SMB", "MPN": "SMBJ13A-E3/52"}, angle=90)
passive("Device.kicad_sym", "C", "C1", "100uF_25V", 86, 60, "+12V", "GND",
        props={"Footprint": "Capacitor_SMD:CP_Elec_6.3x5.4"})

# Buck: MP1584EN mini module (preset to 3.3V). 12V -> 3.3V, ~0.5A rail.
BUCK = Comp("custom", "BUCK_MP1584", "U1", "MP1584_3V3", 130, 60,
            props={"Footprint": "Tuner:BUCK_MP1584",
                   "Description": "MP1584EN mini buck module, set to 3.3V output"})
BUCK.connect("IN+",  "+12V")
BUCK.connect("IN-",  "GND")
BUCK.connect("OUT+", "+3V3")
BUCK.connect("OUT-", "GND")
# 3V3 output bypass
passive("Device.kicad_sym", "C", "C3", "100nF", 160, 60, "+3V3", "GND",
        props={"Footprint": "Capacitor_SMD:C_0805_2012Metric"})
passive("Device.kicad_sym", "C", "C2", "47uF_10V", 175, 60, "+3V3", "GND",
        props={"Footprint": "Capacitor_SMD:CP_Elec_5x5.4", "Description": "3V3 bulk, SMD alu"})

# ─────────────────────────────────────────────────────────────────────────────
# BLOCK 2 — ESP32-WROOM-32E  (the hub)
# ─────────────────────────────────────────────────────────────────────────────
sch_text("ESP32-WROOM-32E  -  main controller", 290, 150, 1.5)
U2 = Comp("RF_Module.kicad_sym", "ESP32-WROOM-32E", "U2", "ESP32-WROOM-32E", 320, 195,
          props={"Footprint": "Tuner:ESP32_DevKit_30",
                 "MPN": "ESP32 DevKit V1 30-pin (DOIT/NodeMCU-32S)",
                 "Datasheet": "https://www.espressif.com/sites/default/files/documentation/esp32-wroom-32e_esp32-wroom-32ue_datasheet_en.pdf"})

esp_nets = {
    "VDD":        "+3V3",
    "GND":        "GND",
    "EN":         "ESP_EN",
    "IO4":        "I2C_SDA",
    "IO5":        "I2C_SCL",
    "IO16":       "RADIO_RX",
    "IO17":       "RADIO_TX",
    "SENSOR_VP":  "ANT_SENSE_A",
    "SENSOR_VN":  "ANT_SENSE_B",
    "IO25":       "MTR_IN1",
    "IO26":       "MTR_IN2",
    "IO27":       "MTR_ISENSE",
    "IO32":       "BTN_TUNE",
    "IO33":       "BTN_PARK",    # PARK button -> drive antenna to bottom end-stop
    "IO34":       "SWR_FWD",
    "IO35":       "SWR_REV",
    "IO12":       "IO12_STRAP",  # boot strap (flash voltage) — must be LOW at boot
    "IO13":       "CIV_TX",      # UART1 TX -> CI-V buffer (Icom)
    "IO14":       "CIV_RX",      # UART1 RX <- CI-V buffer (Icom)
    "IO22":       "TUNE_UP",     # manual jog rocker — UP   (active-low)
    "IO23":       "TUNE_DOWN",   # manual jog rocker — DOWN (active-low)
    "TXD0/IO1":   "DBG_TX",
    "RXD0/IO3":   "DBG_RX",
}
# Build name -> [all pin numbers] (ESP32 has stacked GND on pins 1/15/38/39)
esp_name_all = {}
content_esp = _libtext("RF_Module.kicad_sym")
for sub in ("ESP32-WROOM-32E", "ESP32-WROOM-32E_0_1", "ESP32-WROOM-32E_1_1"):
    block = _symbol_block(content_esp, sub)
    if not block:
        continue
    for m in re.finditer(r'\(name\s+"([^"]+)".*?\(number\s+"([^"]+)"', block, re.DOTALL):
        esp_name_all.setdefault(m.group(1), [])
        if m.group(2) not in esp_name_all[m.group(1)]:
            esp_name_all[m.group(1)].append(m.group(2))

occupied = set()           # world coords already connected (skip NC there)
assigned_nums = set()
for pname, net in esp_nets.items():
    nums = esp_name_all.get(pname)
    if not nums:
        print(f"  WARN esp pin name not found: {pname}")
        continue
    # Connect the first pin of this name; stacked duplicates share its coordinate.
    U2.connect(nums[0], net)
    for n in nums:
        assigned_nums.add(n)
        occupied.add(U2.pin_xy(n))

# Every remaining ESP32 pin -> no-connect (unless it sits on an occupied coord)
for num in U2.pins_raw:
    if num in assigned_nums:
        continue
    if U2.pin_xy(num) in occupied:
        continue
    U2.connect(num, "NC")
    occupied.add(U2.pin_xy(num))

# EN pull-up + cap
passive("Device.kicad_sym", "R", "R_EN", "10k", 360, 150, "+3V3", "ESP_EN",
        props={"Footprint": "Resistor_SMD:R_0805_2012Metric"})
passive("Device.kicad_sym", "C", "C_EN", "100nF", 372, 150, "ESP_EN", "GND",
        props={"Footprint": "Capacitor_SMD:C_0805_2012Metric"})
# ESP32 bulk + bypass on VDD
passive("Device.kicad_sym", "C", "C4", "10uF", 384, 150, "+3V3", "GND",
        props={"Footprint": "Capacitor_SMD:C_0805_2012Metric"})
passive("Device.kicad_sym", "C", "C5", "100nF", 396, 150, "+3V3", "GND",
        props={"Footprint": "Capacitor_SMD:C_0805_2012Metric"})
# GPIO12 (MTDI) boot-strap pulldown: guarantees 3.3V flash mode at power-up
passive("Device.kicad_sym", "R", "R_IO12", "10k", 408, 150, "IO12_STRAP", "GND",
        props={"Footprint": "Resistor_SMD:R_0805_2012Metric"})

# ─────────────────────────────────────────────────────────────────────────────
# BLOCK 3 — MOTOR DRIVER  (DRV8871DDA)
# ─────────────────────────────────────────────────────────────────────────────
sch_text("MOTOR DRIVER  -  Pololu DRV8871 carrier + INA180 low-side sense", 15, 165, 1.5)
U4 = Comp("custom", "DRV8871_CARRIER", "U4", "DRV8871_CARRIER", 55, 185,
          props={"Footprint": "Tuner:DRV8871_CARRIER",
                 "Description": "Pololu DRV8871 carrier; ILIM set on-board"})
U4.connect("VIN",  "+12V")
U4.connect("GND",  "MTR_SNS")      # ground return through shunt (low-side sense)
U4.connect("IN1",  "MTR_IN1")
U4.connect("IN2",  "MTR_IN2")
U4.connect("OUT1", "MTR_OUT1")
U4.connect("OUT2", "MTR_OUT2")
# Low-side shunt: 0.05R x INA gain20 -> 0..3A = 0..3.0V at the ESP32 ADC.
sch_text("motor sense parts", 20, 395, 1.0)
mtr_farm = Farm(20, 400, cols=3)
mtr_farm.passive("Device.kicad_sym", "R", "R_SH", "0R05_1W", "MTR_SNS", "GND",
                 {"Footprint": "Resistor_SMD:R_2512_6332Metric"})
# Declare the shunt-side driver-ground node as driven (it feeds the carrier GND pin)
flag_net("MTR_SNS", 95, 205)
# INA180A1 (gain 20) current-sense amplifier
U6 = Comp("Amplifier_Current.kicad_sym", "INA180A1", "U6", "INA180A1", 120, 185,
          props={"Footprint": "Package_TO_SOT_SMD:SOT-23-5",
                 "MPN": "INA180A1IDBVR",
                 "Description": "Low-side motor current sense, gain 20 -> ESP32 GPIO27 ADC"})
U6.connect("V+", "+3V3")
U6.connect("GND", "GND")
U6.connect("+", "MTR_SNS")          # IN+ at shunt high side
U6.connect("-", "GND")              # IN- at board ground
U6.connect("1", "MTR_ISENSE")      # OUT -> ESP32 ADC
# INA180 supply bypass
passive("Device.kicad_sym", "C", "C_INA", "100nF", 110, 168, "+3V3", "GND",
        props={"Footprint": "Capacitor_SMD:C_0805_2012Metric"})
# VM bulk + bypass (THT radial electrolytic for hand assembly)
passive("Device.kicad_sym", "C", "C_VM", "100uF_25V", 26, 180, "+12V", "GND",
        props={"Footprint": "Capacitor_SMD:CP_Elec_6.3x5.4"})
passive("Device.kicad_sym", "C", "C6", "100nF", 18, 180, "+12V", "GND",
        props={"Footprint": "Capacitor_SMD:C_0805_2012Metric"})
# Antenna motor + sensor connector. Sensor interface assumes a passive contact or
# open-collector pulse pair; firmware counts pulses after a stall-home park.
J6 = Comp("Connector_Generic.kicad_sym", "Conn_01x04", "J6", "ANT_CTRL", 90, 198,
       props={"Footprint": "Connector_PinHeader_2.54mm:PinHeader_1x04_P2.54mm_Vertical",
           "Description": "To antenna: 1=MTR_OUT1 2=MTR_OUT2 3=sense A 4=sense B"})
J6.connect("1", "MTR_OUT1")
J6.connect("2", "MTR_OUT2")
J6.connect("3", "ANT_SENSE_A_RAW")
J6.connect("4", "ANT_SENSE_B_RAW")
sch_text("antenna pulse feedback conditioning", 20, 412, 1.0)
fb_farm = Farm(20, 417, cols=4)
fb_farm.passive("Device.kicad_sym", "R", "R_SA", "1k",  "ANT_SENSE_A_RAW", "ANT_SENSE_A",
          {"Footprint": "Resistor_SMD:R_0805_2012Metric"})
fb_farm.passive("Device.kicad_sym", "R", "R_SB", "1k",  "ANT_SENSE_B_RAW", "ANT_SENSE_B",
          {"Footprint": "Resistor_SMD:R_0805_2012Metric"})
fb_farm.passive("Device.kicad_sym", "R", "R_SA_PU", "10k", "+3V3", "ANT_SENSE_A",
          {"Footprint": "Resistor_SMD:R_0805_2012Metric"})
fb_farm.passive("Device.kicad_sym", "R", "R_SB_PD", "10k", "ANT_SENSE_B", "GND",
          {"Footprint": "Resistor_SMD:R_0805_2012Metric"})

# ─────────────────────────────────────────────────────────────────────────────
# BLOCK 4 — SWR DIRECTIONAL COUPLER + EXTERNAL SWR INPUT
# ─────────────────────────────────────────────────────────────────────────────
sch_text("SWR COUPLER  -  Bruene bridge (CT FT37-43 + capacitive V-sample)", 15, 288, 1.5)
# RF through-line: TX (J3) --- 1-turn CT primary --- antenna (J4).  Full power passes.
J3 = Comp("Connector_Generic.kicad_sym", "Conn_01x02", "J3", "RF_IN_SO239", 25, 305,
          props={"Footprint": "Connector_PinHeader_2.54mm:PinHeader_1x02_P2.54mm_Vertical",
                 "Description": "SO-239 RF input from transmitter"})
J3.connect("1", "RF_LINE_IN"); J3.connect("2", "GND")
J4 = Comp("Connector_Generic.kicad_sym", "Conn_01x02", "J4", "RF_OUT_SO239", 25, 325,
          props={"Footprint": "Connector_PinHeader_2.54mm:PinHeader_1x02_P2.54mm_Vertical",
                 "Description": "SO-239 RF output to antenna"})
J4.connect("1", "RF_LINE_OUT"); J4.connect("2", "GND")
# Current transformer (FT37-43, 1T primary in the through-line, ~30T CT secondary)
T1 = Comp("custom", "CT_FT37_43", "T1", "FT37-43_1:30", 58, 310,
          props={"Footprint": "Tuner:CT_FT37_43_Toroid",
                 "Description": "Bruene current transformer, 1T primary : ~30T CT secondary"})
T1.connect("P1", "RF_LINE_IN")     # through-line in  (1-turn primary)
T1.connect("P2", "RF_LINE_OUT")    # through-line out
T1.connect("S1", "FWD_AC")         # secondary end -> forward detector
T1.connect("S2", "REV_AC")         # secondary end -> reflected detector
T1.connect("SCT", "VSAMPLE")       # secondary centre tap = voltage-sample injection
# Secondary burden (sets current-sample level; tune for 50ohm balance)
passive("Device.kicad_sym", "R", "R3", "150R", 78, 305, "FWD_AC", "REV_AC",
        props={"Footprint": "Resistor_SMD:R_0805_2012Metric"})
# Capacitive voltage divider: line voltage sample -> VSAMPLE (CT centre)
passive("Device.kicad_sym", "C", "C7", "3p3_NP0", 40, 322, "RF_LINE_OUT", "VSAMPLE",
        props={"Footprint": "Capacitor_SMD:C_0805_2012Metric"}, angle=90)
passive("Device.kicad_sym", "C", "C8", "100pF_NP0", 50, 332, "VSAMPLE", "GND",
        props={"Footprint": "Capacitor_SMD:C_0805_2012Metric"})
passive("Device.kicad_sym", "R", "R4", "1k", 60, 332, "VSAMPLE", "GND",
        props={"Footprint": "Resistor_SMD:R_0805_2012Metric"})
# Detectors: FWD_AC = V+I, REV_AC = V-I -> rectify to DC.
# D_Schottky pin1=K(out) pin2=A(in): anode at AC node, cathode at DC output.
passive("Device.kicad_sym", "D_Schottky", "D2", "BAT46", 92, 305, "SWR_FWD", "FWD_AC",
        props={"Footprint": "Diode_SMD:D_SOD-323", "MPN": "BAT46WJ"})
passive("Device.kicad_sym", "D_Schottky", "D3", "BAT46", 92, 318, "SWR_REV", "REV_AC",
        props={"Footprint": "Diode_SMD:D_SOD-323", "MPN": "BAT46WJ"})
# Detector filter + bleed (load) on each DC output — farmed clear of the bridge
sch_text("SWR detector RC loads", 130, 395, 1.0)
det_farm = Farm(130, 400, cols=4)
det_farm.passive("Device.kicad_sym", "C", "C9",  "1nF",  "SWR_FWD", "GND",
                 {"Footprint": "Capacitor_SMD:C_0805_2012Metric"})
det_farm.passive("Device.kicad_sym", "R", "R5",  "4.7k", "SWR_FWD", "GND",
                 {"Footprint": "Resistor_SMD:R_0805_2012Metric"})
det_farm.passive("Device.kicad_sym", "C", "C10", "1nF",  "SWR_REV", "GND",
                 {"Footprint": "Capacitor_SMD:C_0805_2012Metric"})
det_farm.passive("Device.kicad_sym", "R", "R6",  "4.7k", "SWR_REV", "GND",
                 {"Footprint": "Resistor_SMD:R_0805_2012Metric"})
# External SWR 3.5 mm jack (Tip=FWD, Ring=REV, Sleeve=GND)
J5 = Comp("Connector_Audio.kicad_sym", "AudioJack3", "J5", "EXT_SWR", 130, 310,
          props={"Footprint": "Connector_Audio:Jack_3.5mm_CUI_SJ1-3533NG_Horizontal",
                 "Description": "External SWR: Tip=FWD Ring=REV Sleeve=GND"})
J5.connect("T", "SWR_FWD"); J5.connect("R", "SWR_REV"); J5.connect("S", "GND")

# ─────────────────────────────────────────────────────────────────────────────
# BLOCK 5 — RADIO INTERFACE  (MAX3232  CI-V / Yaesu / Kenwood)
# ─────────────────────────────────────────────────────────────────────────────
sch_text("RADIO I/F  -  MAX3232  CI-V + Yaesu/Kenwood CAT", 430, 48, 1.5)
U3 = Comp("Interface_UART.kicad_sym", "MAX3232", "U3", "MAX3232", 480, 70,
          props={"Footprint": "Package_SO:SOIC-16_3.9x9.9mm_P1.27mm",
                 "MPN": "MAX3232ESE+"})
U3.connect("VCC", "+3V3")
U3.connect("GND", "GND")
U3.connect("T1IN",  "RADIO_TX")     # from ESP32 TX
U3.connect("R1OUT", "RADIO_RX")     # to ESP32 RX
U3.connect("T1OUT", "RS232_TX")     # to DE-9
U3.connect("R1IN",  "RS232_RX")     # from DE-9
U3.connect("C1+", "CP_C1P"); U3.connect("C1-", "CP_C1N")
U3.connect("C2+", "CP_C2P"); U3.connect("C2-", "CP_C2N")
U3.connect("VS+", "CP_VSP"); U3.connect("VS-", "CP_VSN")
# 2nd channel unused
for p in ("T2IN", "R2IN"):
    U3.connect(p, "NC")
for p in ("T2OUT", "R2OUT"):
    U3.connect(p, "NC")
# charge-pump + bypass caps placed in a clear farm well clear of U3's tall body
sch_text("MAX3232 charge-pump / bypass caps", 430, 113, 1.0)
cp_farm = Farm(430, 120, cols=5)
_fp = {"Footprint": "Capacitor_SMD:C_0805_2012Metric"}
cp_farm.passive("Device.kicad_sym", "C", "C11", "100nF", "CP_C1P", "CP_C1N", _fp)
cp_farm.passive("Device.kicad_sym", "C", "C12", "100nF", "CP_C2P", "CP_C2N", _fp)
cp_farm.passive("Device.kicad_sym", "C", "C13", "100nF", "CP_VSP", "+3V3", _fp)
cp_farm.passive("Device.kicad_sym", "C", "C14", "100nF", "CP_VSN", "GND", _fp)
cp_farm.passive("Device.kicad_sym", "C", "C15", "100nF", "+3V3", "GND", _fp)
# DE-9F radio connector (4-pin subset used: TXD,RXD,GND)
# Universal radio header -> panel bulkhead connector (GX16) via flying leads.
# One connector, per-radio cables use only the pins they need; firmware auto-
# detects the radio by probing CI-V + CAT.  Kenwood = RS-232 CAT (same path as
# Yaesu), distinguished in firmware (e.g. Kenwood "ID;" command).
J2 = Comp("Connector_Generic.kicad_sym", "Conn_01x06", "J2", "RADIO_UNIVERSAL", 560, 70,
          props={"Footprint": "Connector_PinHeader_2.54mm:PinHeader_1x06_P2.54mm_Vertical",
                 "Description": "Universal radio: 1=GND 2=CAT_TX 3=CAT_RX 4=CIV 5=+3V3 6=GND -> panel GX16"})
J2.connect("1", "GND")
J2.connect("2", "RS232_TX")     # CAT TXD -> radio RXD (Yaesu/Kenwood)
J2.connect("3", "RS232_RX")     # CAT RXD <- radio TXD (Yaesu/Kenwood)
J2.connect("4", "CIV_BUS")      # Icom CI-V single-wire bus
J2.connect("5", "+3V3")         # spare power for any active cable
J2.connect("6", "GND")

# ── CI-V buffer (Icom) ───────────────────────────────────────────────────────
# Single-wire 5V TTL half-duplex bus on its own UART1 (IO13/IO14). Two MMBT3904
# inverting stages; idle/polarity handled by inverting UART1 TX & RX in firmware
# (esp uart_set_line_inverse). Radio supplies the ~5V CI-V bus pull-up.
sch_text("CI-V BUFFER (Icom) - shares DE-9 pin4; invert UART1 in firmware", 430, 162, 1.2)
register_lib_as_custom("Transistor_BJT.kicad_sym", "MMBT3904")  # serve from Tuner lib
QT = Comp("custom", "MMBT3904", "Q1", "MMBT3904", 470, 180,
          props={"Footprint": "Package_TO_SOT_SMD:SOT-23",
                 "Description": "CI-V TX open-collector: pulls CI-V bus low"})
QT.connect("B", "CIV_Q1B"); QT.connect("E", "GND"); QT.connect("C", "CIV_BUS")
QR = Comp("custom", "MMBT3904", "Q2", "MMBT3904", 495, 180,
          props={"Footprint": "Package_TO_SOT_SMD:SOT-23",
                 "Description": "CI-V RX inverter: bus -> ESP32 UART1 RX"})
QR.connect("B", "CIV_Q2B"); QR.connect("E", "GND"); QR.connect("C", "CIV_RX")
# CI-V buffer resistors (farmed clear)
sch_text("CI-V buffer resistors", 560, 395, 1.0)
_rp0402 = {"Footprint": "Resistor_SMD:R_0805_2012Metric"}
civ_farm = Farm(560, 400, cols=3)
civ_farm.passive("Device.kicad_sym", "R", "R_CIV1", "4.7k", "CIV_TX",  "CIV_Q1B", _rp0402)  # TX base
civ_farm.passive("Device.kicad_sym", "R", "R_CIV2", "10k",  "CIV_BUS", "CIV_Q2B", _rp0402)  # RX base
civ_farm.passive("Device.kicad_sym", "R", "R_CIV3", "4.7k", "+3V3",    "CIV_RX",  _rp0402)   # RX pull-up

# ─────────────────────────────────────────────────────────────────────────────
# BLOCK 6 — USER INTERFACE  (OLED, buttons, debug)
# ─────────────────────────────────────────────────────────────────────────────
sch_text("USER INTERFACE + I/O", 430, 238, 1.5)
# OLED I2C connector
JO = Comp("Connector_Generic.kicad_sym", "Conn_01x04", "J_OLED", "SSD1306", 455, 250,
          props={"Footprint": "Connector_PinHeader_2.54mm:PinHeader_1x04_P2.54mm_Vertical",
                 "Description": "GND VCC SCL SDA  128x64 OLED addr 0x3C"})
JO.connect("1", "GND"); JO.connect("2", "+3V3")
JO.connect("3", "I2C_SCL"); JO.connect("4", "I2C_SDA")
# Front-panel buttons to GND (active-low; pull-ups below). Pure auto-tuner:
# TUNE starts an SWR-seek; PARK drives the antenna to the bottom end-stop.
SW1 = Comp("Connector_Generic.kicad_sym", "Conn_01x02", "SW1", "TUNE", 490, 290,
           props={"Footprint": "Connector_PinHeader_2.54mm:PinHeader_1x02_P2.54mm_Vertical"})
SW1.connect("1", "BTN_TUNE"); SW1.connect("2", "GND")
SW2 = Comp("Connector_Generic.kicad_sym", "Conn_01x02", "SW2", "PARK", 490, 305,
           props={"Footprint": "Connector_PinHeader_2.54mm:PinHeader_1x02_P2.54mm_Vertical"})
SW2.connect("1", "BTN_PARK"); SW2.connect("2", "GND")
# Manual-tune momentary rocker (mom-OFF-mom): COM=GND, UP/DOWN -> ESP32.
# Firmware reverses motor polarity through the DRV8871 H-bridge while showing
# live SWR on the OLED.
J_TUNE = Comp("Connector_Generic.kicad_sym", "Conn_01x03", "J_TUNE", "JOG_ROCKER", 560, 290,
              props={"Footprint": "Connector_PinHeader_2.54mm:PinHeader_1x03_P2.54mm_Vertical",
                     "Description": "Manual jog: pin1=UP pin2=COM(GND) pin3=DOWN, momentary centre-off"})
J_TUNE.connect("1", "TUNE_UP"); J_TUNE.connect("2", "GND"); J_TUNE.connect("3", "TUNE_DOWN")

# All UI pull-ups / filters in a clear farm (collision-free; merge by net name)
sch_text("UI pull-ups / filters", 430, 425, 1.0)
ui_farm = Farm(430, 430, cols=4)
_rp = {"Footprint": "Resistor_SMD:R_0805_2012Metric"}
ui_farm.passive("Device.kicad_sym", "R", "R12", "4.7k", "+3V3", "I2C_SDA", _rp)
ui_farm.passive("Device.kicad_sym", "R", "R13", "4.7k", "+3V3", "I2C_SCL", _rp)
ui_farm.passive("Device.kicad_sym", "R", "R7",  "10k",  "+3V3", "BTN_TUNE", _rp)
ui_farm.passive("Device.kicad_sym", "R", "R8",  "10k",  "+3V3", "BTN_PARK", _rp)
ui_farm.passive("Device.kicad_sym", "R", "R_TU", "10k",  "+3V3", "TUNE_UP", _rp)
ui_farm.passive("Device.kicad_sym", "R", "R_TD", "10k",  "+3V3", "TUNE_DOWN", _rp)
# Debug UART header
J8 = Comp("Connector_Generic.kicad_sym", "Conn_01x04", "J8", "DEBUG_UART", 560, 250,
          props={"Footprint": "Connector_PinHeader_2.54mm:PinHeader_1x04_P2.54mm_Vertical",
                 "Description": "GND 3V3 TX RX  (CP2102/CH340 to flash)"})
J8.connect("1", "GND"); J8.connect("2", "+3V3")
J8.connect("3", "DBG_TX"); J8.connect("4", "DBG_RX")

# ════════════════════════════════════════════════════════════════════════════
# ASSEMBLE
# ════════════════════════════════════════════════════════════════════════════
NEEDED = [
    ("RF_Module.kicad_sym",            "ESP32-WROOM-32E"),
    ("Interface_UART.kicad_sym",       "MAX3232"),
    ("Device.kicad_sym",               "R"),
    ("Device.kicad_sym",               "C"),
    ("Device.kicad_sym",               "D_Schottky"),
    ("Device.kicad_sym",               "D_TVS"),
    ("Device.kicad_sym",               "Fuse"),
    ("Connector_Generic.kicad_sym",    "Conn_01x02"),
    ("Connector_Generic.kicad_sym",    "Conn_01x03"),
    ("Connector_Generic.kicad_sym",    "Conn_01x04"),
    ("Connector_Generic.kicad_sym",    "Conn_01x06"),
    ("Connector_Audio.kicad_sym",      "AudioJack3"),
    ("Amplifier_Current.kicad_sym",    "INA180A1"),
    ("custom",                         "MMBT3904"),
    ("custom",                         "CT_FT37_43"),
    ("custom",                         "BUCK_MP1584"),
    ("custom",                         "DRV8871_CARRIER"),
    ("power.kicad_sym",                "+3V3"),
    ("power.kicad_sym",                "+12V"),
    ("power.kicad_sym",                "GND"),
    ("power.kicad_sym",                "PWR_FLAG"),
]
lib_syms = []
for lf, sn in NEEDED:
    lib_syms.append(extract_lib_symbol(lf, sn))
lib_block = "  (lib_symbols\n" + "\n".join(lib_syms) + "\n  )"

header = [
    "(kicad_sch",
    "  (version 20231120)",
    '  (generator "eeschema")',
    '  (generator_version "7.0")',
    f'  (uuid "{ROOT_UUID}")',
    '  (paper "A1")',
    "  (title_block",
    '    (title "ESP32 Screwdriver Antenna Tuner")',
    '    (date "2026-06-14")',
    '    (rev "0.2")',
    '    (comment 1 "Auto (CI-V/CAT) + semi-auto (SWR) + manual; label-driven netlist")',
    "  )",
    "",
    lib_block,
    "",
]
footer = (
    '\n  (sheet_instances\n'
    '    (path "/" (page "1"))\n'
    '  )\n'
    ')\n'
)
out = "\n".join(header) + "\n" + "\n".join(sheet) + footer
with open(os.path.join(KICAD, "tuner.kicad_sch"), "w") as f:
    f.write(out)
print(f"Written tuner.kicad_sch  ({len(out):,} bytes, {out.count(chr(10))} lines)")
print(f"Components placed: {len(_refs)}")

# Write the project-local 'Tuner' symbol library from the SAME custom defs that
# are embedded, so ERC sees no library/cache mismatch.
tuner_syms = "\n".join(CUSTOM[n][0].replace('    (symbol', '  (symbol', 1) for n in CUSTOM)
tuner_lib = ('(kicad_symbol_lib\n'
             '  (version 20231120)\n'
             '  (generator "gen_schematic")\n'
             '  (generator_version "7.0")\n'
             f'{tuner_syms}\n)\n')
with open(os.path.join(KICAD, "Tuner.kicad_sym"), "w") as f:
    f.write(tuner_lib)
print(f"Written Tuner.kicad_sym  ({len(CUSTOM)} custom symbols: {', '.join(CUSTOM)})")
