# Sourcing & ordering

The board is sourced in two parts: a **Mouser cart** for all the passives, ICs,
connectors, diodes, fuse, buttons and the toroid core; plus three
**off-Mouser modules** (chosen so the board is hand-solderable — no QFN/thermal-pad
reflow) and the magnet wire for the toroid.

Panel RF connectors are listed directly in `BOM.csv` as Mini-UHF only:

- `P_RF_MINIUHF` = **Amphenol RF 172147** (Mini-UHF panel female), qty 2

The board uses `J3`/`J4` as 2-pin wire-off headers, with Mini-UHF bulkheads wired
by short pigtails.

## Panel RF + cable hardware (now included in BOM.csv)

The panel RF bulkheads are not board-mounted footprints; they are enclosure parts
wired by pigtail to `J3`/`J4`.

- `P_RF_MINIUHF` (Mini-UHF panel female) qty 2
- `W_RF_RG316` RG-316 50 ohm coax, qty 1 (1 m default)

Yes: the bulkheads need short coax pigtails. Use RG-316 and keep both pigtails
as short as practical.

Selected connector: Amphenol RF 172147 uses a threaded bushing + nut, so flange
screw holes are not required for the default enclosure build.

There is no dedicated coax board connector footprint for RF on this PCB: J3/J4 are
2-pin terminations (RF signal + GND), so the RG-316 pigtails land directly there.

If your station side is SO-239/PL-259, include Mini-UHF<->UHF adapters (one per
RF port) in your enclosure build kit.

Recommended adapter BOM item:

- `P_RF_ADAPT_UHF` = **Amphenol RF 242132**, qty 2
  (Mini-UHF male to UHF female / SO-239 side)

## Radio cable build materials (now included in BOM.csv)

Added offboard cable-build items for CI-V/CAT harnesses:

- `P_RADIO_GX16_PANEL` qty 1 (panel bulkhead)
- `P_RADIO_GX16_PLUG` qty 3 (one cable-side GX16 per radio cable)
- `W_RADIO_CTRL` qty 1 (shielded multicore control cable)
- `P_CIV_3P5MM` qty 1 (Icom CI-V plug)
- `P_CAT_DB9F` qty 1 (Kenwood CAT termination)
- `P_CAT_MINIDIN8` qty 1 (Yaesu CAT termination)

If your specific radio uses a different CAT connector style, substitute that
termination at cable-build time and keep the GX16 side pinout unchanged.

## Motor connector strategy (detachable, service-friendly)

For the antenna motor output, this build uses a detachable panel connector:

- `P_MOTOR_GX16_PANEL` = GX16-4 panel female bulkhead (enclosure side)
- `P_MOTOR_GX16_PLUG` = GX16-4 cable male plugs
- `W_MOTOR_4C` = 4-core 18-22 AWG cable stock

Use a short internal lead from J6 to the panel bulkhead, then build external
adapter leads from GX16-4 to whatever your antenna expects (Tarheel and other
screwdriver antennas vary by harness/end termination).

Why we are **not** standardizing the enclosure-side connector to Tarheel's Molex:

- The Tarheel Molex is an inline cable connector, not a panel bulkhead.
- Keeping GX16-4 on the enclosure preserves a rugged, detachable, generic panel
  interface while still allowing a Tarheel-specific adapter cable in the box.

### Tarheel adapter harness (supported out of the box)

Added BOM items for a Tarheel-compatible adapter lead:

- `P_MOTOR_TARHEEL_KIT` = Tarheel Molex Kit (vendor-supplied inline connector set)
- `W_MOTOR_4C` = 4-conductor cable stock for the Tarheel adapter harness and the
  primary antenna lead

Recommended ordering path:

- Buy the Tarheel Molex kit directly from Tarheel if available for your antenna.
- If ordering equivalent parts elsewhere, verify shell/pin style against your
  exact Tarheel connector before substituting.

## Mouser cart

**Saved cart:** https://www.mouser.com/Tools/SavedCart/Share?AccessID=fe3bac254c

**⚠ Cart corrections (design simplified to a pure auto-tuner — encoder / MODE
switch / memory button / hall sensor removed):**
- **Add** F1 — `1812L300/24SLER` (Littelfuse), Qty 1.
- **Remove** `PEC11R-4220F-S0024` (rotary encoder — gone).
- **Reduce** `PTS645VL58-2LFS` to **2** (SW1 TUNE, SW2 PARK); `61300311121` to **1**
  (J_TUNE only); `RC0805FR-0710KL` 10k to **9**; `RC0805FR-071KL` 1k to **3**;
  `CL21B104KBCNNNC` 100nF to **10**.
- **Set** `61300211121` → 3, `61300411121` → 3.
- Easiest: re-import the regenerated `BOM.csv` instead of hand-editing.

**Subtotal: ≈ $15** _(estimate for single-build qty; confirm in the corrected cart —
the shared-cart page can't be read programmatically.)_

The cart should contain these **25 unique part numbers / 54 pieces** (consolidated
from `BOM.csv`; multiple board designators share one part number). Compare against
the cart to confirm nothing's missing:

| Qty | MPN | Part | Designators |
|----:|-----|------|-------------|
| 10 | CL21B104KBCNNNC | 100nF 0805 | C3,C5,C6,C11–C15,C_EN,C_INA |
| 7 | RC0805FR-0710KL | 10k 0805 | R7,R8,R_CIV2,R_EN,R_IO12,R_TD,R_TU |
| 6 | RC0805FR-074K7L | 4.7k 0805 | R5,R6,R12,R13,R_CIV1,R_CIV3 |
| 3 | 61300211121 | 1×02 header | J1,J3,J4 |
| 1 | 61300311121 | 1×03 header | J_TUNE |
| 2 | PTS645VL58-2LFS | tactile button | SW1,SW2 |
| 2 | EEE-FK1E101P | 100µF 25V SMD alu | C1,C_VM |
| 2 | CL21B102KBANNNC | 1nF 0805 | C9,C10 |
| 2 | BAT46WS | Schottky SOD-323 | D2,D3 |
| 3 | 61300411121 | 1×04 header | J6,J8,J_OLED |
| 2 | MMBT3904LT1G | NPN SOT-23 | Q1,Q2 |
| 1 | EEE-FK1C470P | 47µF 16V SMD alu | C2 |
| 1 | GRM21BR61C106KE15L | 10µF 0805 | C4 |
| 1 | 08055A3R3CAT2A | 3.3pF 0805 C0G | C7 |
| 1 | CL21C101JBANNNC | 100pF 0805 C0G | C8 |
| 1 | SMBJ13A-E3/52 | TVS | D1 |
| 1 | 1812L300/24SLER | 3A PTC fuse 1812 | F1 |
| 1 | 61300611121 | 1×06 header | J2 |
| 1 | SJ1-3533NG | 3.5mm jack | J5 |
| 1 | WSL2512R0500FEA | 0.05Ω 1W shunt | R_SH |
| 1 | RC0805FR-07150RL | 150Ω 0805 | R3 |
| 1 | RC0805FR-071KL | 1k 0805 | R4 |
| 1 | 5943000201 | FT37-43 toroid core | T1 |
| 1 | MAX3232ESE+ | RS-232 xcvr SOIC-16 | U3 |
| 1 | INA180A1IDBVR | current-sense amp | U6 |

> Order a few spares of the 0805 passives — they're pennies and easy to lose.

> **Mouser import:** `BOM.csv` has a short **Ref** column (one representative
> designator per part, e.g. `C3` for the eleven 100nF caps) — map that to Mouser's
> *Customer #* (it stays under Mouser's 21-char limit). The full position list for
> each part is in the **Designators** column for assembly.

## Off-Mouser modules & wire

| Ref | Part | Price | Pack | Per unit | Source |
|-----|------|-------|------|----------|--------|
| **U2** | ESP32 DevKit V1 (30-pin) | $19.07 shipped | 1 | **$19.07** | [Amazon B0CNYK7WT2](https://www.amazon.com/dp/B0CNYK7WT2) |
| **U1** | MP1584EN buck module | $20.13 shipped | 12 | **$1.68** | [Amazon B07RVG34WR](https://www.amazon.com/dp/B07RVG34WR) |
| **U4** | Pololu DRV8871 carrier #2990 | $60.90 (FedEx 2-day) | 10 | **$6.09** | [Pololu #2990](https://www.pololu.com/product/2990) |

**Per-board module cost ≈ $26.84** (1× each).

Notes:
- U1 and U4 come in multi-packs — the per-unit cost above assumes you use the
  whole pack across multiple builds. One board needs 1 of each.
- Set the MP1584 module's output to **3.3 V** with its trimpot before fitting.
- The MP1584 module is acceptable for prototype builds, but for a more robust
  production version prefer a **fixed-output 3.3 V switching regulator** so the
  rail does not depend on a trim pot. A solid Mouser-friendly target for the next
  board spin is **Murata OKI-78SR-3.3/1.5-W36-C**: 7-36 V input, fixed 3.3 V
  output, 1.5 A max, about 4.95 W output power.
- The suggested fixed-output alternatives are **not drop-in compatible** with the
  current U1 footprint; they are recommendations for a future hardware revision,
  not this PCB as-shipped.
- A plain linear regulator is **not recommended** for the full board supply from
  12 V. At only 250 mA load it would burn about `(12 - 3.3) * 0.25 = 2.18 W` as
  heat; at 500 mA it would burn about `4.35 W`, which is not practical in this
  enclosure without serious heatsinking.
- Verify each module's pin pitch against the custom footprints
  (`Tuner.pretty/`) before ordering boards — they're documented-but-approximate.

## 3.3 V rail and input power budget

- **Current 3.3 V design target:** about **0.5 A** continuous logic rail budget.
- That corresponds to about **1.65 W** on the 3.3 V rail.
- The 12 V board input path itself is protected by a **3 A PTC**, so the overall
  board input path is in the rough **36 W class** at 12 V, but most of that is for
  the **motor path**, not the logic rail.
- Practical reading: the logic supply is a low-watt rail, while the motor section
  is what drives the higher input current requirement.

**T1 magnet wire:** the toroid *core* (5943000201) is in the Mouser cart; you also
need ~30 turns of **0.3 mm (≈30 AWG) enamelled copper** for the secondary (any
small spool — Amazon, or Remington Industries magnet wire on Mouser). The 1-turn
primary is just the through-line wire passing through the core.

## Cost summary (per board)

| Source | Cost |
|--------|------|
| Mouser cart (25 parts) | **≈ $15** _(est.; confirm in corrected cart)_ |
| ESP32 DevKit V1 (U2) | $19.07 |
| MP1584 module (U1) | $1.68 |
| Pololu DRV8871 #2990 (U4) | $6.09 |
| Magnet wire (T1 secondary) | ~$1 (spool covers many) |
| **Modules + wire subtotal** | **≈ $26.84** |
| **Grand total per board** | **≈ $45** (+ bare PCB ~$2–10) |

_Not included:_ the bare 4-layer PCB (≈$2–10/board from JLCPCB, qty-dependent — see
`fab/tuner_gerbers.zip`), and the panel-mount hardware wired by flying lead (2×
Mini-UHF bulkheads, GX16 radio bulkhead, 12 V jack, the enclosure) — your choice of vendor;
see `RADIO_CONNECTOR.md` and `enclosure/README.md`.
