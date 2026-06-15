# Universal Radio Connector — wiring, cables & auto-detection

One panel-mounted connector handles **all** supported radios. You build a short
adapter cable per radio; the firmware figures out which radio is attached by
probing. Kenwood and Yaesu are electrically identical (RS-232 CAT) and are told
apart in software.

---

## 1. Signal set (what the board provides)

The board exposes the radio signals on header **J2 (`RADIO_UNIVERSAL`, 1×06)**,
which you wire with flying leads to a **panel bulkhead connector** (recommended:
**GX16 aviation**, 6- or 8-pin). Nothing radio-specific lives on the PCB — the
cable does the adapting.

| J2 pin | Net | Direction | Used by |
|:------:|-----|-----------|---------|
| 1 | `GND` | — | all |
| 2 | `RS232_TX` | board → radio RXD | Yaesu / Kenwood CAT (via U3 MAX3232) |
| 3 | `RS232_RX` | radio TXD → board | Yaesu / Kenwood CAT |
| 4 | `CIV_BUS` | bidirectional | Icom CI-V (via Q1/Q2 TTL buffer) |
| 5 | `+3V3` | board → cable | optional power for an active cable |
| 6 | `GND` | — | shield / 2nd ground |

`RS232_TX/RX` are **true RS-232 levels** (±5–10 V) out of the MAX3232.
`CIV_BUS` is **single-wire 5 V-tolerant TTL**, open-drain, half-duplex.
**Never wire CI-V to the RS-232 pins** — different electrical standards.

---

## 2. Panel connector (GX16) — recommended pinout

Wire J2 → GX16 1:1 so every cable sees the same panel pinout:

| GX16 pin | Signal | GX16 pin | Signal |
|:--------:|--------|:--------:|--------|
| 1 | GND | 4 | CIV_BUS |
| 2 | RS232_TX | 5 | +3V3 |
| 3 | RS232_RX | 6 | GND |

GX16 mounts through a ~16 mm hole in the printed enclosure, locks with a knurled
ring, and is keyed so the cable can only insert one way. A GX16-8 gives two spare
pins for future expansion (e.g. PTT or a CABLE_ID resistor).

> **Bulkhead wiring:** keep the J2-to-GX16 flying leads short and twist
> RS232_TX/RX together and CIV/GND together. If you ever see RF pickup on the
> CI-V line during TX, add a clip-on ferrite on the radio cable.

---

## 3. Per-radio adapter cables

Each cable is **GX16 plug → radio's connector**. Only the pins that radio needs
are populated; the rest are left unconnected.

### Cable parts list (per this repo BOM)

Use these offboard BOM items when building cable sets:

- `P_RADIO_GX16_PANEL` x1: enclosure panel bulkhead (board side)
- `P_RADIO_GX16_PLUG` x1 per cable: cable-side GX16 male plug
- `W_RADIO_CTRL`: shielded multicore cable stock
- `P_CIV_3P5MM`: Icom CI-V termination plug
- `P_CAT_MINIDIN8`: Yaesu CAT termination plug
- `P_CAT_DB9F`: Kenwood CAT termination connector

If a radio uses a different CAT plug than the defaults above, substitute that
radio-end connector and keep the GX16 pin mapping in Section 2 unchanged.

### Icom (CI-V) — 3.5 mm mono/stereo plug
| GX16 | → | Radio CI-V jack |
|------|---|-----------------|
| 4 (CIV_BUS) | → | tip (CI-V data) |
| 1 (GND) | → | sleeve (ground) |

### Yaesu (CAT, RS-232) — e.g. mini-DIN / CAT jack, varies by model
| GX16 | → | Radio CAT |
|------|---|-----------|
| 2 (RS232_TX) | → | radio **RXD / CAT-IN** |
| 3 (RS232_RX) | → | radio **TXD / CAT-OUT** |
| 1 (GND) | → | ground |

### Kenwood (CAT, RS-232) — e.g. DB-9 / 6-pin DIN, varies by model
| GX16 | → | Radio CAT |
|------|---|-----------|
| 2 (RS232_TX) | → | radio **RXD (pin 2 on a DB-9 male radio)** |
| 3 (RS232_RX) | → | radio **TXD (pin 3)** |
| 1 (GND) | → | ground (pin 5) |

> Yaesu and Kenwood cables are wired the **same way** electrically — the only
> difference is the connector on the radio end and the CAT command set. Watch
> TX/RX direction: it's always **board-TX → radio-RX** (a null-modem swap if the
> radio is DTE). If you get no response, swap pins 2↔3 at the radio end.

Some rigs (older Yaesu FT-8x7, etc.) expose **TTL-level** CAT, not RS-232. For
those, put a small TTL↔RS-232 adapter (or a level shifter) **in the cable**, and
use pin 5 (+3V3) / pin 1 (GND) to power it. That's exactly what the spare power
pin is for.

---

## 4. Firmware auto-detection (probe sequence)

The two interfaces are on independent UARTs, so the firmware can probe both
without any hardware switching:

- **CI-V** → ESP32 UART1 (GPIO13/14) → Q1/Q2 buffer → `CIV_BUS`
- **CAT**  → ESP32 UART2 (GPIO16/17) → MAX3232 → `RS232_TX/RX`

Detection routine on boot (and on a "re-scan" menu item):

```
for baud in [CI-V 19200, 9600, 4800]:
    send CI-V "read frequency" (cmd 0x03) to broadcast addr 0x00
    if valid CI-V frame returns  ->  ICOM, remember the responding address
for baud in [9600, 4800, 38400, 57600, 115200]:
    send Kenwood "ID;"           # returns "ID019;" etc.
    if "ID" response             ->  KENWOOD, decode model id
    send Yaesu read-status / read-freq (model-appropriate)
    if valid response            ->  YAESU
-> none responded: stay in MANUAL / SEMI-AUTO (SWR-only) mode
```

Notes that make this reliable:
- **Kenwood `ID;`** is the cleanest fingerprint — it returns a numeric model
  code, so you get exact identification, not just "a Kenwood."
- **Icom** is identified by *any* CI-V reply; capture the source address so you
  can address it directly afterwards.
- **Yaesu** varies most by model — start with the common FT-8x7/9x7/DX command
  forms; treat "responds to CAT but not Kenwood ID" as Yaesu.
- Probe CI-V and CAT **concurrently** (both UARTs listening) to cut detect time.
- Cache the detected radio + baud in NVS so subsequent boots skip the scan
  (with a "forget radio" option in the menu).

This belongs in the firmware stage; the hardware already routes both interfaces
to the single universal connector, so no board change is needed to add radios —
only new cables and new protocol handlers.

---

## 5. Summary

- **One** bulkhead connector (GX16) on the enclosure, wired remotely from J2.
- **Passive** per-radio cables (except optional TTL-CAT level shifter).
- Adding a radio = new cable + firmware protocol, **no PCB change**.
- Kenwood support is firmware-only (same RS-232 path as Yaesu).
