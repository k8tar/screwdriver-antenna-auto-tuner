# ESP32 Screwdriver Antenna Tuner — PCB Routing Guide

Board: `kicad/tuner.kicad_pcb` — 100 × 70 mm, 4-layer, generic hand-solderable rules.
This guide covers the layer stackup, net priorities/trace widths, grounding,
the RF/SWR section, and the Freerouting workflow.

---

## 1. Layer stackup (4-layer)

| Layer | Use |
|-------|-----|
| **F.Cu** (top) | Signal + component pads. Short signal routes, RF/SWR. |
| **In1.Cu** | **Solid GND plane** — keep unbroken under the ESP32, RF coupler, and MCU signals. |
| **In2.Cu** | **Power plane** — pour `+3V3`; route `+12V` / motor as wide fills or fat traces here. |
| **B.Cu** (bottom) | Signal + a secondary GND pour. Cross-unders, power, slower signals. |

Inner ground (In1) is already poured as a `GND` zone; bottom has a `GND` pour too.
The most important rule: **don't slot the In1 ground plane** under the RF coupler
or the ESP32 — keep return paths continuous.

---

## 2. Net classes & trace widths

Set these in **Board Setup → Net Classes** before routing (Freerouting reads them).

| Net class | Nets | Track width | Clearance | Notes |
|-----------|------|-------------|-----------|-------|
| **Power_12V** | `+12V`, `MTR_OUT1`, `MTR_OUT2`, `MTR_SNS` | **1.0–1.5 mm** | 0.3 mm | Motor current (up to ~3 A). Wide, short, on In2/bottom. |
| **Power_3V3** | `+3V3` | **0.6 mm** | 0.25 mm | Logic rail. Pour on In2 where possible. |
| **Default** | all signals (I²C, UART, SWR, GPIO, CI-V) | 0.3 mm | 0.25 mm | Hand-solderable generic. |
| **RF** | `RF_LINE_IN`, `RF_LINE_OUT` | 0.6–0.8 mm | 0.3 mm | Keep short; see §4. |

Vias: 0.8 mm pad / 0.4 mm drill (already the default). Use plenty to stitch GND.

---

## 3. Grounding strategy

- **One continuous ground** (In1 plane) is the reference for everything. Avoid
  cuts; if you must cross a plane gap with a signal, don't — reroute.
- **Star the high-current return**: the motor return goes carrier-GND →
  `MTR_SNS` → shunt `R_SH` → board GND at a **single point** near the shunt. Do
  NOT let motor return current share copper with the INA180 input or the MCU
  analog grounds — that's what the shunt + single-point tie is for.
- **Stitch** the top/bottom GND pours to In1 with vias every ~5–10 mm, especially
  a ring of vias around the RF coupler and under the ESP32.
- Keep the **buck (U1) input loop** (12V → U1 → GND) tight; put C1 close to U1 IN.

---

## 4. RF / SWR section (the part that needs care)

The Bruene bridge measures forward/reflected power, so its layout affects accuracy.

- **Through-line first.** `RF_LINE_IN` (J3) → **T1 primary (1 turn)** → `RF_LINE_OUT`
  (J4) is the main RF path carrying full TX power. Route it as a **short, wide,
  direct** trace (0.6–0.8 mm) on the top layer with solid ground beneath. This is
  the "1 turn" through the toroid — physically the wire passes through T1's core.
- **Keep the secondary tiny.** T1 `S1/SCT/S2` to the burden `R3`, divider
  `C7/C8/R4`, and detectors `D2/D3` should be a **compact cluster right at T1** —
  short leads keep the sample clean and the bridge balanced.
- **Symmetry matters.** Route `FWD_AC` (D2) and `REV_AC` (D3) paths as
  symmetrically as possible — equal lengths — so forward/reflected track each other.
- `SWR_FWD` / `SWR_REV` are slow DC after the detectors; route them quietly to the
  ESP32 ADC (GPIO34/35), away from the motor/buck switching nodes.
- RF connectors are **flying leads**: J3/J4 are pads where you solder short coax
  pigtails to panel Mini-UHF bulkheads. Keep those pads near the board edge.

> Calibration: the CT turns ratio, C7/C8 divider, and R3 burden are bench-tuned
> for a 50 Ω null. The layout just needs to be short and symmetric.

---

## 5. Placement notes (already done, refine as you route)

- ESP32 DevKit stands **upright (tall) on the left edge** (socketed on female headers).
- Rear edge = connectors (power, antenna motor/sensor, ext-SWR, debug, and the
  **universal radio header J2** → panel bulkhead, see `RADIO_CONNECTOR.md`).
- Front edge = UI (OLED, encoder, TUNE/MEM buttons, MODE, jog rocker).
- Buck (U1), motor carrier (U4), MAX3232 (U3) are **socketed modules** — leave
  clearance for the daughterboards and their headers.
- A handful of courtyard overlaps remain in the dense SWR/motor clusters; nudge
  parts apart as you route (this is normal final-placement work).

---

## 6. Freerouting workflow (autorouting) — DONE, reproducible

The board is **already autorouted** (Freerouting 2.2.4): 0 unrouted nets,
469 track segments + 56 vias, 0 electrical DRC errors. To re-route after edits:

```
# from the project root (tuner/).  Freerouting 2.2.4 needs Java 25.
flatpak run --command=python3 org.kicad.KiCad scripts/export_dsn.py     # board -> tuner.dsn
java -jar freerouting.jar -de hardware/kicad/tuner.dsn \
     -do hardware/kicad/tuner.ses -mp 30                                # route (headless)
flatpak run --command=python3 org.kicad.KiCad scripts/import_ses.py     # .ses -> board, refill zones
```

`import_ses.py` calls `pcbnew.ImportSpecctraSES` + `ZONE_FILLER` and saves.
Re-run `scripts/gen_gerbers.py` afterwards to refresh the fab package.

> Prefer hand-routing or want to pre-place critical nets? Lock the RF through-line
> and motor-power tracks first, then autoroute the rest. Order: RF through-line →
> motor power → 3V3/12V → I²C/UART → remaining GPIO.

---

## 7. Before you order

- Run **DRC** to zero (placement overlaps + clearance).
- **Verify the three module footprints** against the real parts you buy
  (ESP32 DevKit row pitch, MP1584 pad pitch, DRV8871 carrier pinout) — these are
  documented-but-approximate and flagged on each footprint's silkscreen.
- Export **Gerbers + drill**:
  `flatpak run --command=kicad-cli org.kicad.KiCad pcb export gerbers tuner.kicad_pcb -o gerbers/`
  `flatpak run --command=kicad-cli org.kicad.KiCad pcb export drill tuner.kicad_pcb -o gerbers/`
- Generic 4-layer, 0.3 mm/0.25 mm rules are within every cheap fab's process.
