# Enclosure — 3D-printed, two-part

Parametric OpenSCAD box for the tuner PCB. **`enclosure.scad`** builds two parts:
a **base** tray (holds the PCB, carries the rear panel-mount connectors) and a
**lid** (the control panel — OLED, TUNE/PARK, jog).

## Dimensions
- Outer **110 × 80 × 34 mm** (fits the 100 × 70 board with 2 mm clearance).
- All driven by parameters at the top of the `.scad`; change `board_l/w`,
  `comp_clear` (headroom), `gap`, `wall`, `standoff_h` and everything re-derives.

## Rendering / exporting
```
openscad -D 'part="base"' -o base.stl  enclosure.scad
openscad -D 'part="lid"'  -o lid.stl   enclosure.scad
openscad -D 'part="both"' -o enclosure_full.stl enclosure.scad
openscad -D 'part="base"' -o base.3mf enclosure.scad
openscad -D 'part="lid"'  -o lid.3mf  enclosure.scad
openscad -D 'part="both"' -o enclosure_full.3mf enclosure.scad
# preview both side-by-side in the GUI: set part="both"
```

Pre-generated print files for the current repo revision:

- `base.stl`
- `lid.stl`
- `enclosure_full.stl` (base and lid exported together in one STL)
- `base.3mf`
- `lid.3mf`
- `enclosure_full.3mf` (base and lid exported together in one 3MF)

Additional preview modes in `enclosure.scad`:

- `part="assembled"` closed enclosure with installed board/components
- `part="lid_off"` lifted lid with wiring still connected
- `part="service_open"` lid fully moved to the side with long service loops

RF connector cutout in `enclosure.scad` is fixed for compact Mini-UHF bulkheads:

- `rf_bulkhead_d = 10.0` (Mini-UHF panel hole)
- Selected connector model: **Amphenol RF 172147** (Mouser)

Optional RF mounting screw-hole pattern:

- `rf_mount_holes = true` enables two M3 clearance holes per RF connector.
- `rf_mount_hole_d` sets the screw hole diameter.
- `rf_mount_hole_pitch` sets screw center-to-center spacing.

Set `rf_mount_holes = false` if your Mini-UHF connector uses only a threaded
bushing + nut and no flange screws.

Default in this repo is `rf_mount_holes = false` because Amphenol RF 172147 is a
threaded bulkhead style.

## What's on each part
**Base — rear wall (panel-mount, wired by flying lead to the board headers):**
| Cutout | Ø | For |
|--------|----|-----|
| RF IN | 10 mm | Mini-UHF bulkhead → board J3 |
| RF OUT | 10 mm | Mini-UHF bulkhead → board J4 |
| RADIO | 16 mm | **GX16 bulkhead** → board J2 (universal radio, see `../RADIO_CONNECTOR.md`) |
| POWER | 12 mm | 12 V panel jack → board J1 |

**Base — right side wall:** an antenna connector cutout (GX16-4 style, → J6). Vent slots on the
left side wall (buck/motor heat).

**Lid — control panel (panel-mounted UI, wired to the board headers):**
OLED window (30 × 17), two button holes (Ø6: TUNE / PARK), and a jog-rocker slot
(13 × 9). These are a clean ergonomic layout — the parts mount on the lid and
connect by flying lead to the J_OLED / SW1 / SW2 / J_TUNE headers, so the lid
layout is independent of where those headers sit on the PCB.

## Assembly
1. Screw the PCB onto the 4 floor standoffs (M3 × 6, from above).
2. Mount the panel connectors in the rear wall; solder their flying leads to the
   matching board headers (keep RF leads short; see RADIO_CONNECTOR.md for J2).
3. Fit the lid; secure with 4 × M3 into the corner bosses.
4. PCB mounting holes are at board (4.5, 4.5) (95.5, 4.5) (4.5, 65.5) (95.5, 65.5)
   — identical to `scripts/gen_pcb.py` HOLES, so the standoffs always line up.

## Print settings
- **Material:** PETG (recommended — survives a hot cab). PLA only for bench use.
- 0.2 mm layers, 3 perimeters, 20–30 % infill.
- Base prints open-side up (no supports). Lid prints face-down (cutouts need no
  support). Self-tapping M3 into the printed bosses; or melt in M3 heat-set
  inserts for repeated assembly (bump boss pilot to Ø4.0 for inserts).

## ⚠️ Verify before printing
- The UI is treated as **panel-mounted** (OLED, TUNE/PARK buttons, jog rocker on
  the lid, wired to headers). If you change panel components, verify body depth
  and nut clearances against `comp_clear`.
- The BOM's tactile buttons are the **right-angle** PTS645 variant; for a
  lid-mounted panel use **vertical** tactiles or separate panel buttons.
- Confirm `comp_clear` (20 mm headroom) against your tallest assembled part
  (ESP32 DevKit on its socket + the bulk caps).
