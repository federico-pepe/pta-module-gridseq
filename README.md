# GridSeq

An OXI ONE MKII–inspired multitrack step sequencer, built as a
[push-tethered-app](https://github.com/federico-pepe/push-tethered-app)
process module for Ableton Push 2/3 in tethered mode. Not a port — a new
design built around Push's actual hardware (8x8 pad grid, 8 encoders, no
CV/gate, no analog clock) and its own literally-named buttons
(`Scene 1/4`…`Scene 1/32t` as a direct time-division picker, `Page Left`/
`Right`, `Mute`/`Solo`/`Select`, `Scale`, `Repeat`, `Accent`).

## Grid layout

Live-style: **columns = tracks**, **rows = steps** of the currently viewed
step-page (row 7/top = earliest step, playhead travels top-to-bottom).
`Page Left`/`Page Right` scroll the 8-track column window; `D-Pad up`/
`down` scroll the step-page window for the selected track, so a track's
pattern can run longer than 8 steps.

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
probability/micro-timing-offset/accent/pitch, per-track time division,
multitrack (>8 via column paging), Track mode
(8 columns = 8 parameters of the selected track) vs Main mode (8 columns
= 8 tracks sharing one jog-selected parameter), external MIDI clock
sync, single-pattern persistence.

Per-track pattern length control (shipped): `Shift` + `D-Pad up`/`down`
shrinks/grows the selected track's length by 8 steps (8..64).

v2.5 mod lane (shipped): every track has an independent mod lane — own
length, own division, own per-step 0-127 value, decoupled from the note
lane — replacing the earlier "mod rides the note step" v2 slice. Any
`Screen top N` button opens a bar-graph grid overlay for editing the
Nth visible track's lane directly; see [MANUAL.md](MANUAL.md#mod-lane).

Scale quantization (shipped): playback-time only — a step's pitch stays a
plain semitone offset from root, quantized to the nearest degree of the
track's scale only when it fires, so switching scales never rewrites
stored data.

UI pass (shipped): the header row is gone — parameter names/values moved
to the top of the screen where the header used to be, BPM only appears
as a transient popup while the Tempo wheel is turning, and the playhead
now travels top-to-bottom instead of bottom-to-top. **Persistence is
currently disabled** (`run.py`'s `PERSIST_ENABLED = False`) — every
session starts from a fresh pattern; the save/load code is intact behind
that flag for when it's turned back on.

Controls pass (shipped): Pan (encoder column 7) is gone, replaced by
**Channel** — each track's MIDI output channel (1-16), independently
settable. The Mod column's status page no longer shows "n/a"; it renders
as a plain colored button instead (how to actually visualize a mod lane
there is still undecided). `Stop Clips` is unbound (Play already toggles
stop). **Mute/Solo now gesture on the Screen-bottom (track-select)
buttons**, not on pads (`Mute`/`Solo` held + tap the track's own
Screen-bottom button) — pad taps while either is held just toggle the
step normally now. A track that won't actually sound (muted, or
silenced by another track's solo) turns grey — both its pad steps and
its bottom-strip label — driven by the same `Engine.track_audible()`
check already used at trigger time, not a separate visual flag.

Controls pass 2 (shipped): pitch became a real per-step control (this
found and fixed a real bug in the process: a held-pad encoder edit was
landing on the wrong step entirely, because the playhead-direction row
inversion from the UI pass never reached `handle_encoder`'s held-pad
path). "Channel" now reads "MIDI Channel" on screen. The Mod status
button is now exactly the old header's height (not taller) with a
"`>`" hinting there's another page behind it, and `Screen top N` opens
that column's track's mod lane directly (later scoped further — see
below). The Tempo popup text is centered, and popups are now a reusable
mechanism (`State.show_popup`).

Pitch display pass (shipped): every per-step parameter column (velocity,
gate, repeat, probability, offset, pitch) shows the lo..hi range across
all steps normally, and narrows to that one step's exact value while a
pad is held — reading a range to figure out what value you're about to
set was the actual complaint. The Pitch column shows the resolved note
name ("C#3", Ableton Live's octave numbering) instead of a raw semitone
offset, using the same `Engine.resolve_note` the trigger path already
used internally (now public, so the screen and playback can't disagree).

Follow-up fixes (shipped): **Screen top
N** is scoped by mode now — Main mode still opens any column's track's
mod lane, but Track mode only responds to **Screen top 8** (the one
actually above a Mod button there; the other 7 columns are other
parameters, not other tracks, so 1-7 do nothing rather than opening an
unrelated track's lane). **Pitch range**: a step's offset can now reach
any of the 128 MIDI notes from any root (`+/-127`, not the old `+/-24`
which made notes outside roughly C2-C6 unreachable) — and moves by the
encoder's raw delta instead of one semitone per tick, so the wider range
stays practical to sweep.

More follow-up fixes (shipped): note names were shifted down an octave
— MIDI 60 is now "C3" (Ableton Live's own convention) instead of the
scientific-pitch-notation "C4" the first pass used, since Live is what
these names need to agree with. Step-page scrolling (D-Pad) and its
Shift-held length variant moved from `D-Pad left`/`right` to `D-Pad
up`/`down` — GridSeq's step timeline reads top-to-bottom, so up/down
matches it and left/right (now unbound for this) didn't.

Drum/melodic removed (shipped): every track works the same way now —
`root + pitch offset`, quantized to the track's scale — instead of a
per-track "kind" toggling between an unquantized `base_note + offset`
(drum) and a quantized `root + offset` (melodic). Now that pitch can
reach any of the 128 notes and the default `chromatic` scale applies no
quantization, the two behaviors had converged to "the same thing, with
extra bookkeeping" — the `Note` button, its kind-toggle popup, and the
`(DRM)`/`(MEL)` bottom-strip suffix are all gone. Picking a specific
drum-kit voice by note number still works exactly as before, as long as
the track's scale is left at `chromatic` (the default) — quantization
only changes anything once a non-`chromatic` scale is chosen.

Scale mode (shipped): `Scale` is now a toggle, not a hold — press it to
enter a dedicated mode where only two columns show anything (Key, Scale,
both for the selected track), the other 6 go blank, and every other
encoder is inert; press `Scale` again to leave. Replaces the old
hold-`Scale`-and-turn-any-encoder gesture. Only enterable with a
specific track selected — not from Main mode, and not while the mod
lane overlay is open — since both apply to more than one track at once
and Scale mode is inherently single-track.

Scale mode tuning (shipped): the Key/Scale encoders now require an
accumulated turn (`Engine.KNOB_ACCUM_THRESHOLD = 4`) before actually
stepping once, instead of every single relative-encoder tick moving the
value — plain 1-tick-per-step felt too twitchy for a 12-item/6-item
list. Both also clamp at their list ends now instead of wrapping (reach
`pentatonic_minor` or B and it just stops there until you reverse).

More encoder tuning (shipped): the Main mode jog wheel now clamps at
either end of its parameter list too, instead of wrapping. Pitch,
Offset, Repeat, and MIDI Channel got the same accumulated-turn treatment
Key/Scale did — Velocity, Gate, and Probability deliberately kept full
per-message sensitivity. The "Screen top N" row (mod-lane access) is
now off by default and only lights above an actual on-screen Mod
button, in that track's color, instead of a blanket dim/full for every
column regardless of whether it means anything there; whichever track's
mod lane is currently open shows bright red instead, on the button that
actually closes it — which required fixing a real inconsistency in the
dispatch (see the plan file: previously, once the overlay was open, only
`Screen top 8` could ever close it, regardless of which track's lane
was open or which button opened it).

v3 candidates (not built):
- Mod-lane length control from the surface, and a per-track mod CC number
  (both currently fixed)
- Pattern slots / song chaining (v3, per the original plan)
