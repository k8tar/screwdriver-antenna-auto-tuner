# Screwdriver Antenna Auto Tuner

An ESP32-based automatic controller for motorized HF screwdriver antennas.

This repository contains the firmware, generated KiCad design files, enclosure
model, sourcing notes, build documentation, renders, and fabrication outputs for
an in-vehicle automatic antenna tuner with:

- ESP32 control logic
- OLED status display
- motor drive with current-based stall detection
- SWR measurement using an onboard directional coupler
- detachable radio and antenna harnesses
- Tarheel-style sensor support via the 4-wire antenna connector

## Current revision highlights

- single-mode auto-tuner firmware with TUNE, PARK, and jog controls
- power-stage revision to the Murata OKI-78SR fixed 3.3 V regulator
- external SWR jack removed from the PCB revision
- updated enclosure previews and board renders
- regenerated Gerber package in `fab/tuner_gerbers.zip`

## Repository layout

- `firmware/` — PlatformIO firmware, simulation wiring, and firmware spec
- `hardware/` — assembly guide, BOM, sourcing, routing notes, enclosure model
- `hardware/kicad/` — generated KiCad schematic, PCB, netlist, DSN, footprints
- `renders/` — board and enclosure images plus schematic and PCB PDFs
- `fab/` — generated Gerbers and fabrication ZIP package
- `scripts/` — source-of-truth generators for schematic, PCB, BOM, and fab outputs

## Build and generation

Firmware build:

```bash
cd firmware
pio run
```

Hardware regeneration from the repo root:

```bash
python3 scripts/gen_footprints.py
python3 scripts/gen_schematic.py
flatpak run --command=kicad-cli org.kicad.KiCad sch export netlist -o hardware/kicad/tuner.net hardware/kicad/tuner.kicad_sch
flatpak run --command=python3 org.kicad.KiCad scripts/gen_pcb.py
flatpak run --command=python3 org.kicad.KiCad scripts/export_dsn.py
python3 scripts/gen_bom.py
python3 scripts/gen_gerbers.py
```

## Primary documentation

- `firmware/FIRMWARE_SPEC.md`
- `firmware/src/README.md`
- `hardware/ASSEMBLY.md`
- `hardware/SOURCING.md`
- `hardware/RADIO_CONNECTOR.md`
- `hardware/enclosure/README.md`

## Notes

- The generated KiCad files in `hardware/kicad/` are derived artifacts; the
	Python scripts in `scripts/` are the source of truth.
- For vehicle use, internal board wiring should be direct-soldered and strain
	relieved rather than using loose jumper leads.
