# ESP32 Screwdriver Antenna Tuner — Firmware Specification

This is a **self-contained** implementation spec for the firmware. The hardware
(schematic + 4-layer PCB) is complete and frozen; this document is the contract
between it and the firmware. Implement to this; don't assume access to other
project files except where referenced.

> **Revision (single-mode auto-tuner):** the design is a **single-mode automatic
> tuner** — no operating-mode switch, no rotary encoder, and no memory buttons.
> The controls are **TUNE**, **PARK**, a **jog rocker**, and the OLED. The board
> also exposes an **optional 2-wire antenna pulse-feedback input** for Tarheel-style
> sensors. Firmware must still work when no sensor pulses are present by falling
> back to the original stall-only sweep behavior.

---

## 1. What the product does

A controller for a **motorized "screwdriver" HF antenna** (a variable inductor
whose resonance is changed by a DC motor). It drives the motor to the **lowest
SWR**, automatically, with the radio in the loop:

**Core tune sequence** — triggered by the front-panel **TUNE** button *or* by the
radio requesting a tune over CAT/CI-V:
1. Command the radio (over CAT/CI-V) to **drop to minimum power (~1 W)** and key a
   carrier (or AM/FM/CW tune tone).
2. **Sweep the motor** while reading SWR; find the position of lowest SWR
  (gradient/hill-climb — §10). Detect mechanical travel limits by **motor stall
  current** and, when pulse feedback is available, use that count to return to
  the best point more accurately.
3. **Unkey** and **restore the radio's previous power level.**
4. Show the result (final SWR) on the OLED.

Other controls: **PARK** drives the antenna fully **down** to the bottom end-stop
(for travel/stowing); the **jog rocker** moves the motor up/down by hand for setup.
SWR is measured with an on-board Bruene directional coupler. The firmware
**auto-detects which radio brand/protocol is attached** (Icom CI-V / Kenwood /
Yaesu). There is **no band memory** — every tune is a fresh sweep.

---

## 2. Target hardware & toolchain

- **MCU:** ESP32-WROOM-32E on a 30-pin DevKit (DOIT/NodeMCU-32S), 3.3 V logic.
- **Recommended framework:** **Arduino-ESP32 via PlatformIO** (rich libraries:
  U8g2 for the OLED, hardware UARTs, LEDC PWM, Preferences/NVS). ESP-IDF is
  acceptable if preferred; this spec is framework-neutral.
- **Suggested libraries:** `U8g2` (SSD1306), `Preferences` (NVS). No heavyweight
  CAT library is assumed — protocol handling is small and is specified below.

---

## 3. Pin map (authoritative — taken from the netlist)

| GPIO | Net | Function | Direction / peripheral |
|-----:|-----|----------|------------------------|
| 4  | I2C_SDA | OLED SSD1306 data | I2C0 SDA |
| 5  | I2C_SCL | OLED SSD1306 clock | I2C0 SCL |
| 16 | RADIO_RX | CAT receive (from MAX3232 ROUT) | **UART2 RX** |
| 17 | RADIO_TX | CAT transmit (to MAX3232 TIN) | **UART2 TX** |
| 13 | CIV_TX | CI-V transmit (to transistor buffer) | **UART1 TX** |
| 14 | CIV_RX | CI-V receive (from transistor buffer) | **UART1 RX** |
| 25 | MTR_IN1 | DRV8871 IN1 | LEDC PWM out |
| 26 | MTR_IN2 | DRV8871 IN2 | LEDC PWM out |
| 27 | MTR_ISENSE | motor current (INA180 out) | **ADC1** in |
| 34 | SWR_FWD | forward detector voltage | **ADC1** in (input-only) |
| 35 | SWR_REV | reflected detector voltage | **ADC1** in (input-only) |
| 36 | ANT_SENSE_A | antenna pulse feedback A | input-only |
| 39 | ANT_SENSE_B | antenna pulse feedback B / return sense | input-only |
| 32 | BTN_TUNE | TUNE button (start a tune) | input, active-low |
| 33 | BTN_PARK | PARK button (drive to bottom end-stop) | input, active-low |
| 22 | TUNE_UP | jog rocker up (10k pull-up) | input, active-low |
| 23 | TUNE_DOWN | jog rocker down (10k pull-up) | input, active-low |
| 1  | DBG_TX | debug/console (J8) | UART0 TX |
| 3  | DBG_RX | debug/console (J8) | UART0 RX |
| 12 | IO12_STRAP | **boot strap, 10k pulldown — leave as input, do NOT drive high at boot** | — |
| 18, 19, 21, 2, 15 | (NC) | **spare** | — |

Notes:
- BTN_TUNE/BTN_PARK have **external** 10k pull-ups (R7/R8); the jog rocker pins
  have external 10k pull-ups (R_TU/R_TD). All four are **active-low**.
- GPIO34/35/36/39 are **input-only**.
- GPIO12 is a boot strapping pin; the board pulls it down. Configure as input.
- The antenna feedback pair is biased on-board for a **pulse/contact-style**
  sensor. If no pulses appear, firmware must fall back to stall-only behavior.

---

## 4. Peripheral configuration

### 4.1 OLED display
- SSD1306 128×64 over I2C0 (SDA=4, SCL=5), default address `0x3C`. Plugs into
  `J_OLED`. Use U8g2 (page or full buffer). ~30 fps is plenty.

### 4.2 CAT UART (Yaesu / Kenwood) — UART2
- GPIO17 = TX → MAX3232 → radio RXD; GPIO16 = RX ← MAX3232 ← radio TXD.
- True RS-232 levels are handled by the on-board MAX3232; firmware just uses TTL
  UART2. **8N1.** Baud is discovered (see §7). Idle non-inverted (RS-232 path).

### 4.3 CI-V UART (Icom) — UART1
- GPIO13 = TX, GPIO14 = RX, through a 2-transistor open-drain buffer to a single
  half-duplex 5 V-tolerant bus.
- **The buffer inverts the signal — configure UART1 inverted** (invert both TX and
  RX) so the line idles correctly. (Verify polarity on a scope on first bring-up;
  if framing is garbage, toggle the invert flags.) **8N1.**
- Single-wire half-duplex: you will read back your own transmitted bytes (echo) —
  discard the echo before parsing the reply.

### 4.4 ADC inputs
- Use ADC1 (ADC2 is unusable when Wi-Fi is on). 12-bit, 11 dB attenuation
  (0–~3.3 V). **Oversample/average** (e.g., 32–64 samples) — SWR DC lines are slow.
- `SWR_FWD` (34), `SWR_REV` (35): detector DC after the Schottky + RC filter.
- `MTR_ISENSE` (27): INA180A1 output = `I_motor × 0.05 Ω × 20` (gain 20). So
  **A per volt = 1 / (0.05 × 20) = 1.0 A/V** at the ADC.

### 4.5 Motor PWM (DRV8871 carrier)
- IN-IN drive: to go one direction PWM `MTR_IN1` while `MTR_IN2`=0; reverse =
  PWM `MTR_IN2` while `MTR_IN1`=0; brake = both high; coast = both low.
- LEDC, **~20 kHz** (above audio), 8–10 bit duty. Hardware current limit is set
  by the carrier (ILIM resistor); firmware adds soft-start and stall logic (§9).

### 4.6 Position feedback
- Optional **2-wire pulse feedback** on `ANT_SENSE_A` (36) / `ANT_SENSE_B` (39).
- Hardware biasing assumes a **dry contact or open-collector pulse pair** from the
  antenna harness. Firmware should count pulses while the motor is moving.
- `PARK` still bottoms the antenna by **stall current**. After a successful park,
  firmware should treat the current pulse count as **home = 0** and then use pulse
  counts for relative positioning during later tune sweeps.
- If no pulses are ever observed, firmware must revert to the original stall-only,
  time-step tune algorithm.

### 4.7 Front-panel controls (all active-low, external 10k pull-ups)
- `BTN_TUNE` = 32 — start a tune sequence (§6).
- `BTN_PARK` = 33 — drive the antenna fully **down** to the bottom end-stop, then
  stop. Long-hold not required; a single press runs the park to completion (abort
  on any other control or stall-confirmed limit).
- Jog rocker `J_TUNE`: `TUNE_UP` = 22 / `TUNE_DOWN` = 23, **momentary** (motor runs
  only while held). Debounce all buttons ~20 ms.

---

## 5. System architecture

A cooperative loop or a few FreeRTOS tasks — either is fine. Suggested split:

- **UI task / loop (≈30 Hz):** read the buttons + jog rocker, render OLED.
- **Measurement (≈50–100 Hz):** average ADCs → Vfwd, Vrev → SWR; read current.
- **Motor control (≈1 kHz service):** ramp PWM, stall watchdog.
- **Radio task:** detect the rig at boot; poll for a tune request; issue power/key
  commands during a tune.
- **Tune/park state machine:** orchestrates the sequences in §6.

Keep motor commands funnelled through one `motor_set(direction, duty)` so the
stall watchdog and limit logic can't be bypassed.

---

## 6. Operation (single mode — there is no mode switch)

The unit sits **IDLE** showing SWR/status until a trigger occurs.

### TUNE  (trigger: `BTN_TUNE`, or a radio tune-request — §7)
The firmware drives the whole sequence, controlling the radio over CAT/CI-V:
1. **Read & remember** the radio's current power level (so it can be restored).
2. **Set power to minimum (~1 W)** and **key a carrier** (CW/AM/FM tune tone — the
   command set per protocol is in §7). If there is no radio (or it can't be
   commanded), instead prompt on the OLED "KEY CARRIER" and proceed once forward
   power is detected.
3. Wait for forward power, then run the **SWR sweep** (§10.1): sweep the motor,
   track SWR, home in on the minimum. Travel ends are found by **stall current**.
4. **Unkey**, **restore the saved power level**, and BRAKE the motor at the dip.
5. Show the final SWR (and "TUNE OK" / "NO DIP" / "TIMEOUT").
- **Abort** on any button/jog press, loss of forward power, or the time-box (§15);
  always unkey and restore power on abort.

### PARK  (trigger: `BTN_PARK`)
- Drive the motor **down** continuously until the bottom **stall** end-stop, then
  BRAKE. This fully retracts the antenna for travel/stow. Abort on any other press.

### JOG  (trigger: jog rocker held)
- While `TUNE_UP`/`TUNE_DOWN` held → motor up/down (ramped); release → BRAKE. Show
  the **live SWR meter** while jogging. For manual bench setup/override.

No menus, no encoder, no memory. Calibration (§8) and "re-scan radio" are entered
by a **TUNE + PARK chord held at power-up** (or over the debug console).

---

## 7. Radio interface & auto-detection

Two independent UARTs let you probe both buses. **Detection runs at boot** (and
from the menu's "Re-scan"). Result (brand, protocol, baud, CI-V address) is cached
in NVS so later boots skip the scan unless "forget radio" is chosen.

### Detection algorithm
```
for baud in [19200, 9600, 4800]:                 # CI-V (UART1, inverted)
    send CI-V read-frequency (cmd 0x03) to addr 0x00 (broadcast) from 0xE0
    if a valid CI-V frame (FE FE … FD) returns:  -> ICOM, store responding addr & baud
for baud in [9600, 4800, 38400, 57600, 115200]:  # CAT (UART2)
    send Kenwood "ID;"        -> "ID019;" etc.    -> KENWOOD, decode model id, store baud
    send Yaesu read (model-appropriate, see below)
    if a valid reply:                             -> YAESU, store baud
if nothing answered: radio = NONE (AUTO degrades to SEMI)
```
Probe CI-V and CAT concurrently if convenient (separate UARTs). Use short
per-attempt timeouts (~150 ms) and a couple of retries.

### CI-V (Icom)
- Frame: `FE FE <to> <from> <cmd> [data] FD`. Controller address `0xE0` (default).
- Read frequency: cmd `0x03`; reply data is BCD frequency, little-endian by byte.
- Discard the half-duplex echo of your own frame before reading the reply.
- Default radio address depends on model (e.g. 0x94, 0xA2, 0x76…); during
  detection use broadcast `0x00` and learn the responder's `<from>` address.

### Kenwood CAT
- ASCII, terminated by `;`. **`ID;` → `IDnnn;`** is the cleanest fingerprint
  (returns a numeric model code). Read frequency: **`FA;` → `FAxxxxxxxxxxx;`** (11
  digits, Hz). Typical bauds 9600/57600.

### Yaesu CAT
- Varies by model. Newer rigs (FTDX/FT-991/FT-891) accept Kenwood-style ASCII
  (`FA;`, `ID;`) — treat "responds to ASCII but ID differs from Kenwood codes" as
  Yaesu. Older FT-817/857/897 use a 5-byte binary CAT (last byte = opcode, e.g.
  `0x03` read-freq returns BCD) at 4800/38400 — implement this as a secondary
  Yaesu path. Make the per-model command set a small table so radios are easy to add.

**Adding a radio later = new cable + a protocol-table entry; no hardware change.**

### Radio TX control during a tune (the core mechanism)
Each protocol entry must also provide **power read/set** and **key/unkey** so the
TUNE sequence (§6) can run hands-free. Save the current power, set ~1 W, key, sweep,
unkey, restore. Per protocol:
- **Icom CI-V:** power = cmd `0x14 0x0A` (read) / `0x14 0x0A <bcd>` (set, 0000–0255
  scaled to 0–100 %); set near the minimum. Key/unkey = cmd `0x1C 0x00 0x01/0x00`
  (PTT on/off). Pick a mode the rig emits carrier in (CW/AM/RTTY/FM) via `0x06`.
- **Kenwood:** power `PC;`/`PCxxx;`; key/unkey `TX;`/`RX;`. (Use CW/FM for a steady
  carrier.)
- **Yaesu:** newer rigs `PC;`/`PCxxx;` + `TX1;`/`TX0;`; FT-8x7 binary opcodes for
  PTT and (limited) power.
- **No-radio fallback:** can't command power/key → prompt the operator to set low
  power and key manually; start the sweep when forward power is seen, and just show
  "UNKEY" when done. **Time-box the keyed period** (e.g. ≤ a few seconds of search,
  hard cap) and **always send unkey + restore power** on completion *and* on abort.

> Tune-request trigger: simplest is the front-panel TUNE button. If you also want
> the rig to start it, watch for the radio's tuner-request over CAT (model-specific)
> or a band/frequency change — but the button is the guaranteed path.

---

## 8. SWR measurement & calibration

The coupler outputs two DC voltages proportional to forward and reflected RF
(Schottky-detected, RC-filtered). After averaging the ADCs:

```
Vf = adc_volts(SWR_FWD)        # detected forward
Vr = adc_volts(SWR_REV)        # detected reflected
# correct for Schottky offset/curvature with a calibration function f():
Pf = detector_to_power(Vf)     # see calibration
Pr = detector_to_power(Vr)
gamma = sqrt(Pr / Pf)          # reflection coefficient magnitude (0..1)
SWR   = (1 + gamma) / (1 - gamma)     # clamp gamma < ~0.99
```
- Guard against `Vf` near zero (no carrier) — report "no RF" and never act on a
  divide-by-zero.
- **Calibration routine** (menu): with a known load (50 Ω → SWR 1.0, and an open
  or known mismatch), capture detector readings to fit `detector_to_power()`
  (a simple piecewise/quadratic fit handles the Schottky knee). Store coefficients
  in NVS. A usable default: treat the detector as square-law above the knee and
  linear below; ship reasonable defaults so it works uncalibrated, refine in cal.
- Display SWR as a bargraph (1.0–3.0+ zoomed) plus numeric (e.g. "1.4:1").

---

## 9. Motor control & end-stops (no position sensor)

- `motor_set(dir, duty)`: dir ∈ {UP, DOWN, BRAKE, COAST}; duty 0–max. Soft-start
  ramp (~100–200 ms) on direction changes.
- **Stall / end-stop detection** is the only travel-limit mechanism: read
  `MTR_ISENSE` (1.0 A/V); if current exceeds a threshold (~1.5× free-running tune
  current, tuned empirically) for > ~150 ms, treat it as a mechanical end-stop:
  BRAKE immediately. PARK drives DOWN to that stall; the sweep reverses off a stall.
- There is **no absolute position** — the sweep works on the SWR gradient, not
  coordinates. Always **BRAKE** (not COAST) to hold the antenna at the found dip.
- Never dwell against a stall (heat / driver fault) — back off and BRAKE.

---

## 10. Tuning algorithm (SWR sweep)

1. Confirm forward power present (carrier on — §6/§7).
2. **Coarse sweep:** move one direction at moderate duty, sampling SWR; if SWR
   rises steadily (or a stall end-stop is hit), reverse. Remember the lowest SWR and
   roughly where it was (by time/step count since the last reversal).
3. **Fine search:** creep back toward the minimum at low duty and hill-climb
   (step, measure, reverse a step if worse) until SWR < target (default 1.3:1) or
   the step size bottoms out.
4. **BRAKE** at the minimum.
- **Time-box** the keyed search (§15) and abort cleanly on any button/jog press or
  loss of carrier — always unkey + restore radio power on exit (§7).

---

## 11. Persistent storage (NVS)

Minimal — **no band memory**. Use `Preferences`/NVS for:
- `radio`: `brand`, `proto`, `baud`, `civ_addr`, `detected` flag (cached so boot
  skips re-detection).
- `cal`: detector calibration coefficients, SWR target (default 1.3), stall-current
  threshold.

Keep writes infrequent (NVS wear) — only on a successful detect or calibration.

---

## 12. UI

### 12.1 Screens
- **Idle/Main:** big **SWR** (bargraph + numeric), frequency (if a radio is read),
  detected radio brand, and status (READY / TUNING / PARKED / NO RADIO).
- **Tuning:** live SWR while sweeping + an abort hint.
- **Park:** "PARKING…" then "PARKED".

### 12.2 Controls recap
- **TUNE** = start an auto tune. **PARK** = retract antenna to the bottom stop.
- **Jog rocker** = manual up/down (motor runs only while held), live SWR shown.
- **TUNE+PARK held at power-up** = enter calibration / re-scan radio (or use the
  debug console). No encoder, no menus, no memory.

---

## 13. Boot sequence

1. Init NVS, I2C/OLED (splash), UARTs (UART1 inverted for CI-V), ADC, LEDC, ISRs.
2. Load cal + radio + memories from NVS.
3. If no cached radio → run detection (§7) with an on-screen "Detecting radio…".
4. Read mode switch; enter that mode's idle state. Motor stays stopped until
   commanded. Show main screen.

---

## 14. Safety & fault handling

- **Motor:** enforce end-stops; stall-current cutoff; always BRAKE to stop; ramp
  duty; refuse motion if `MTR_ISENSE` reads implausibly high at rest (driver fault).
- **No-carrier guard:** never run a seek without detected forward power.
- **Watchdog:** feed the hardware WDT; ensure the motor is stopped in any fault/
  reset path (motor must not latch on across a crash — default both IN pins low).
- **GPIO12** must remain an input (boot strap); never drive it at reset.
- Brown-out: rely on ESP32 BOD; on under-voltage, stop the motor.

---

## 15. Tunable constants (surface these as named defines)

PWM freq (20 kHz), PWM max duty, soft-start ms, stall current (A) & debounce ms,
SWR target (1.3), seek step size & timeout (30 s), ADC averaging (32–64), button
debounce (20 ms), CAT/CI-V timeouts & baud lists, memory slot granularity.

---

## 16. Milestones / acceptance criteria

1. **Bring-up:** OLED splash; buttons/encoder/rocker read correctly; mode switch
   resolves 3 positions; debug console on UART0.
2. **Motor:** jog up/down with ramp; stall detection trips on end-stop; position
   counter increments; homing works.
3. **SWR:** Vfwd/Vrev read; SWR computed and displayed; calibration routine stores
   coefficients; "no RF" handled.
4. **SEMI:** null-seek reliably finds the SWR minimum on the bench (signal
   generator + adjustable mismatch) within the timeout.
5. **Radio:** auto-detect identifies Icom (CI-V), Kenwood (`ID;`), and a Yaesu rig;
   frequency read works; result cached in NVS.
6. **AUTO:** frequency change triggers recall + fine-trim; positions persist across
   power cycles.
7. **Robustness:** no motor runaway on faults; WDT clean; NVS writes bounded.

---

## 17. Verify against hardware before/while coding

- **CI-V invert polarity** on GPIO13/14 (scope; flip invert flags if needed).
- **MODE_SW levels** (§12.3) — exact divider taps.
- **Hall pulse** electrical level/threshold on GPIO36 and pulses-per-revolution.
- **Detector transfer curve** for the BAT46 detectors (calibration).
- **Motor stall current** of the specific antenna (set the threshold empirically).
- Pin map above is from the netlist and is authoritative; cross-check once on the
  first assembled board.
