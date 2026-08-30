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

v1 (shipped): step on/off, per-step velocity/gate/repeat(ratchet)/
probability/micro-timing-offset/accent, drum or melodic per-track kind,
per-track time division, multitrack (>8 via column paging), Track mode
(8 columns = 8 parameters of the selected track) vs Main mode (8 columns
= 8 tracks sharing one jog-selected parameter), external MIDI clock
sync, single-pattern persistence.

v2 "simple" slice (shipped): a step's mod amount (encoder 8) sent as a
fixed MIDI CC (CC1, mod wheel) whenever that step triggers — locked to
the note lane's own length/division, not an independent lane.

v2.5/v3 candidates (not built):
- **Full mod lane** — the originally-planned decoupled lane: its own
  length/division and per-track CC number, edited via a dedicated
  grid-editing overlay (hold a button, pads become a bar-graph column
  editor, like OXI's mod lanes) instead of riding the note steps. Needs
  its own UI design pass since the 8x8 grid has no spare surface for a
  second independent lane without borrowing the pad grid temporarily.
- Scale quantization (Scale is currently a label, not a pitch filter)
- Per-track pattern length control beyond the default 8 steps
- Pattern slots / song chaining (v3, per the original plan)
