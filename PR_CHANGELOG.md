# PR Changelog

## Summary

This update revises the hardware power stage, removes the unused external SWR jack,
refreshes generated board and fab artifacts, and aligns the firmware, documentation,
and enclosure previews with the current mobile-installation design.

## Hardware

- Replaced the adjustable U1 MP1584 module with the fixed-output Murata OKI-78SR-3.3/1.5-W36-C.
- Added a new custom SIP footprint for the Murata regulator.
- Removed the external SWR jack footprint and related board wiring.
- Tightened the U1 placement cluster for a cleaner input-protection-to-regulator layout.
- Softened the T1 toroid silkscreen and moved C7 away from the toroid outline for readability.

## Firmware

- Added power-on self test screens and serial diagnostics.
- Added OLED status improvements: PARK state and TUNED flash sequence.
- Added two live diagnostics pages toggled by a TUNE+PARK hold.
- Added optional Tarheel sensor feedback handling with pulse-based position tracking after PARK homing.

## Mechanical and enclosure

- Updated enclosure previews to reflect the current board revision.
- Removed the external SWR side-wall feature from the enclosure model and docs.
- Kept the GX16-4 antenna connector strategy and service-open render views.

## Documentation

- Reworked the top-level README into a real project overview.
- Updated assembly and sourcing docs for:
  - Murata regulator usage
  - no external SWR jack
  - direct-solder, strain-relieved in-vehicle internal wiring
  - future locking-connector guidance for a board respin
- Updated the BOM and routing notes to match the current board.

## Generated artifacts

- Regenerated schematic, PCB, netlist, DSN, BOM, renders, PDFs, Gerbers, and fab ZIP.
- Removed the obsolete BUCK_MP1584 custom footprint from the tracked KiCad library.
- Added the new REG_OKI78SR custom footprint.

## Validation

- PlatformIO firmware build completed successfully.
- KiCad regeneration completed successfully.
- Gerbers and `fab/tuner_gerbers.zip` were regenerated.
