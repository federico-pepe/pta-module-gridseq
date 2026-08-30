# GridSeq

An OXI ONE MKII–inspired multitrack step sequencer, built as a
[push-tethered-app](https://github.com/federico-pepe/push-tethered-app)
process module for Ableton Push 2/3 in tethered mode. Not a port — a new
design built around Push's actual hardware (8x8 pad grid, 8 encoders, no
CV/gate, no analog clock) and its own literally-named buttons
(`Scene 1/4`…`Scene 1/32t` as a direct time-division picker, `Page Left`/
`Right`, `Mute`/`Solo`/`Select`, `Note`, `Scale`, `Repeat`, `Accent`).

## Grid layout

Live-style: **columns = tracks**, **rows = steps** of the currently viewed
step-page (row 0 = bottom = earliest step). `Page Left`/`Page Right` scroll
the 8-track column window; `D-Pad left`/`right` scroll the step-page window
for the selected track, so a track's pattern can run longer than 8 steps.

Full control mapping, data model, and the v2 (per-track CC modulation
lanes) / v3 (pattern chain) roadmap are documented in the design plan this
module was built from.

## Install

```bash
go run ./cmd/pushapp -install /path/to/pta-module-gridseq
go run ./cmd/pushapp -module gridseq
```

Requires `python3` on PATH (stdlib only, no pip install).

## Manual

Full control mapping, LED legend, and known v1 limitations:
[MANUAL.md](MANUAL.md).

## Status

v1 (this repo, current state): step on/off, per-step velocity/gate/
repeat(ratchet)/probability/micro-timing-offset/accent, drum or melodic
per-track kind, per-track time division, multitrack (>8 via column
paging), external MIDI clock sync, single-pattern persistence.

v2/v3 (planned): per-track CC modulation lane, pattern-slot chaining.
