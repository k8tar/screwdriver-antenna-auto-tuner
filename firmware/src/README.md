# ESP32 Screwdriver Tuner Firmware

This firmware implements the updated pure auto-tuner behavior from `firmware/FIRMWARE_SPEC.md`.

Current layout:

- `firmware/platformio.ini`
- `firmware/src/main.cpp`
- `firmware/wokwi.toml`
- `firmware/diagram.json`

## Build and flash

Run commands from the `firmware/` directory:

```bash
pio run
pio run -t upload
pio device monitor
```

## Wokwi simulation

1. Build once:

```bash
pio run
```

2. Open `firmware/diagram.json` in VS Code.
3. Start simulator with `Wokwi: Start Simulator`.

### Sim control mapping

- `TUNE` button -> GPIO32
- `PARK` button -> GPIO33
- `UP` rocker/button -> GPIO22
- `DOWN` rocker/button -> GPIO23
- SWR forward pot -> GPIO34
- SWR reflected pot -> GPIO35
- Motor current sense pot -> GPIO27
- Motor direction LEDs -> GPIO25 / GPIO26
- OLED SSD1306 I2C -> GPIO4 (SDA), GPIO5 (SCL)

### Sim notes

- The simulator does not emulate complete CAT/CI-V radio behavior.
- You can still validate UI, debounce behavior, motor state transitions, stall handling, and SWR search flow.

## Firmware behavior summary

- Single operating model (no AUTO/SEMI/MANUAL mode switch).
- No hall sensor position tracking.
- No memory slot / band memory feature.
- `TUNE`:
  - Attempts low-power keyed carrier via detected radio protocol.
  - Sweeps motor, using SWR trend and stall detection to locate a dip.
  - Returns to best point and finishes with status (`TUNE OK`, `TUNE DONE`, `NO DIP`, etc.).
- `PARK`:
  - Drives downward until stall/end-stop and then stops.
- `UP`/`DOWN`:
  - Manual jog while held.

## Important bring-up checks

1. Verify INA180 + shunt scaling for motor current threshold.
2. Tune stall threshold (`stallA`) for your mechanical system.
3. Validate detector offsets/gains against your coupler hardware.
4. Confirm CAT/CI-V command compatibility with your radio model.

## Notes

- GPIO12 remains input-only in firmware.
- GPIO34/35 are treated as ADC inputs only.
