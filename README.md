# GridSeq

GridSeq is a multitrack step sequencer. The design takes inspiration from
the OXI ONE MKII.

GridSeq runs as a
[push-tethered-app](https://github.com/federico-pepe/push-tethered-app)
process module, for Ableton Push 2/3 in tethered mode. GridSeq is not a
port of the OXI ONE MKII. It is a new design for the actual hardware of
Push: an 8x8 pad grid, 8 encoders, no CV/gate, and no analog clock.
GridSeq also uses the literally-named buttons of Push: `Scene 1/4` to
`Scene 1/32t` as a direct time-division picker, and `Page Left`/`Right`,
`Mute`/`Solo`/`Select`, `Scale`, `Repeat`, `Accent`.

## Grid layout

The grid layout follows the same style as Ableton Live: columns are
tracks, and rows are steps of the current step-page. Row 7 (the top row)
is the earliest step. The playhead moves from top to bottom.

`Page Left` and `Page Right` scroll the column window of 8 tracks.
`D-Pad up` and `D-Pad down` scroll the step-page window for the selected
track. As a result, a track's pattern can run longer than 8 steps.

The design plan for this module documents the full control mapping, the
data model, and the roadmap for v2 (per-track CC modulation lanes) and
v3 (pattern chain).

## Install

```bash
go run ./cmd/pushapp -install /path/to/pta-module-gridseq
go run ./cmd/pushapp -module gridseq
```

GridSeq needs `python3` on the PATH. It uses only the Python standard
library, so no `pip install` step is necessary.

## Manual

[MANUAL.md](MANUAL.md) gives the full control mapping, the LED legend,
and the known limits of v1.

## Status

v1 (shipped). The v1 release added:
- Step on/off, and per-step velocity, gate, repeat (ratchet),
  probability, micro-timing offset, accent, and pitch.
- A time division per track.
- Support for more than 8 tracks, through column paging.
- Track mode: 8 columns show the 8 parameters of the selected track.
- Main mode: 8 columns show 8 tracks, and share one parameter picked by
  the jog wheel.
- Sync to an external MIDI clock.
- Persistence for a single pattern.

Per-track pattern length control (shipped). `Shift` + `D-Pad up`/`down`
changes the length of the selected track by 8 steps, from 8 to 64.

v2.5 mod lane (shipped). Each track now has its own mod lane, separate
from the note lane. Each mod lane has its own length, its own division,
and its own per-step value from 0 to 127. This replaces the earlier v2
design, where the mod value rode on the note step.

Any `Screen top N` button opens a bar-graph grid overlay. Use it to edit
the mod lane of the Nth visible track directly. See
[MANUAL.md](MANUAL.md#mod-lane).

Scale quantization (shipped). Quantization happens only at playback
time. A step's pitch stays stored as a plain semitone offset from the
root note. GridSeq quantizes the offset to the nearest degree of the
track's scale only when the step fires. As a result, a change of scale
never rewrites the stored data.

UI pass (shipped). GridSeq removed the header row. Parameter names and
values now show at the top of the screen, in the space the header used
to fill. The BPM value now shows only in a transient popup, while you
turn the Tempo wheel. The playhead now moves from top to bottom, not
from bottom to top.

**Persistence is currently off** (`run.py`'s `PERSIST_ENABLED = False`).
Each session starts from a fresh pattern. The save and load code stays
in place behind this flag, for when persistence turns back on.

Controls pass (shipped). GridSeq removed Pan (encoder column 7) and
added **Channel** instead: the MIDI output channel of each track, from 1
to 16, set independently per track. The status page of the Mod column no
longer shows "n/a". It now shows a plain colored button. How to show a
mod lane there is still an open question. `Stop Clips` has no function
now, because `Play` already toggles stop.

`Mute` and `Solo` now work on the Screen-bottom (track-select) buttons,
not on pads. Hold `Mute` or `Solo`, then tap the Screen-bottom button of
a track. While you hold either button, a pad tap still just toggles the
step, with no change to mute or solo.

A track that does not sound (muted, or silenced by the solo of another
track) turns grey. This applies to both its pad steps and its
bottom-strip label. The same `Engine.track_audible()` check drives this
display, and drives the trigger logic, so there is no separate visual
flag.

Controls pass 3 (shipped). `Add` (CC32) now replaces `Duplicate` (CC88)
as the button that appends a new track, copied from the selected one.
The behavior is the same, on the correctly-named physical button.

`Save` (CC82) and `Set` (CC80) give the pattern its own named,
file-based save and load. This is independent of the
`store_get`/`store_set` single-pattern slot, which stays off. `Save`
writes the current pattern to `sequences/<name>.json`. The first save
names the file "Sequence N" automatically. `Set` opens a full-screen
list of every saved sequence, plus "New". Scroll the list with the jog
wheel or `D-Pad up`/`down`. Confirm your choice with `Jog press` or
`D-Pad center`.

Hold `Delete`, then touch a screen encoder, to reset the current
parameter of that encoder to its default value. This resets just one
step if a pad is held, or the whole track if not. See
[MANUAL.md](MANUAL.md#saving-and-loading-sequences) for the full
behavior of both `Save` and `Set`.

Track color picker (shipped). Hold `Shift`, then press the Screen-bottom
button of a track. This opens a color-picker overlay on the pad grid.
The border pads light up with the 26 track colors of GridSeq. Tap one to
set it as the color of the selected track. Release `Shift` to close the
overlay.

New tracks now also pick a color from `TRACK_COLORS` with a stride, not
in list order. As a result, neighboring tracks do not default to similar
colors. See [MANUAL.md](MANUAL.md#track-color-picker).

Length view (shipped). `Clip View` (CC113) toggles a dedicated Length
view. In this view, encoder 1 edits the step count of the selected
track, one step at a time, down to a floor of 1. `Shift` + `D-Pad
up`/`down` still moves in pages of 8 steps, with a floor of 8, for fast
changes. New tracks and patterns still default to 8 steps. See
[MANUAL.md](MANUAL.md#stepping-through-a-long-pattern--d-pad-updown).

Controls pass 2 (shipped). Pitch became a real per-step control. This
work found and fixed a bug: a held-pad encoder edit landed on the wrong
step. The playhead-direction row inversion from the UI pass had never
reached the held-pad path of `handle_encoder`.

"Channel" now reads "MIDI Channel" on screen. The Mod status button is
now the same height as the old header, not taller, with a "`>`" mark
that hints at another page behind it. `Screen top N` now opens the mod
lane of that column's track directly. A later pass scoped this further
(see below). The Tempo popup text is now centered. Popups are now a
reusable mechanism, `State.show_popup`.

Pitch display pass (shipped). Each per-step parameter column (velocity,
gate, repeat, probability, offset, pitch) normally shows the low-high
range across all steps. While you hold a pad, the column narrows to the
exact value of that one step. The complaint that led to this change: a
range gave no way to know the value you were about to set.

The Pitch column now shows the resolved note name, for example "C#3",
with the octave numbering of Ableton Live. It no longer shows a raw
semitone offset. This uses the same `Engine.resolve_note` function that
the trigger path already used. The function is now public, so the
screen and playback always agree.

Follow-up fixes (shipped). `Screen top N` now depends on the mode. In
Main mode, it still opens the mod lane of any column's track. In Track
mode, it responds only to `Screen top 8`, the button above the actual
Mod button. In Track mode, columns 1 to 7 are other parameters, not
other tracks, so they do nothing instead of opening an unrelated track's
lane.

Pitch range: a step's offset can now reach any of the 128 MIDI notes,
from any root note. The range is now +/-127, not the old +/-24, which
made notes outside about C2-C6 unreachable. The offset now moves by the
raw delta of the encoder, not by one semitone per tick, so the wider
range stays practical to sweep.

More follow-up fixes (shipped). Note names shifted down an octave. MIDI
note 60 is now "C3", the convention of Ableton Live. The first pass used
"C4", from scientific pitch notation. GridSeq names notes to agree with
Live.

Step-page scrolling (`D-Pad`), and its `Shift`-held length variant,
moved from `D-Pad left`/`right` to `D-Pad up`/`down`. The step timeline
of GridSeq reads top-to-bottom, so up/down matches it. Left/right did
not match, and now has no function here.

Drum/melodic removed (shipped). Every track now works the same way:
`root + pitch offset`, quantized to the scale of the track. This
replaces the old per-track "kind" setting, which toggled between an
unquantized `base_note + offset` (drum) and a quantized `root + offset`
(melodic).

Pitch can now reach any of the 128 notes, and the default `chromatic`
scale applies no quantization. As a result, the two old behaviors had
become the same, with extra bookkeeping. GridSeq removed the `Note`
button, its kind-toggle popup, and the `(DRM)`/`(MEL)` suffix on the
bottom strip.

Picking a specific drum-kit voice by note number still works as before,
if the scale of the track stays at `chromatic` (the default).
Quantization changes the result only when you pick a scale other than
`chromatic`.

Scale mode (shipped). `Scale` is now a toggle, not a held button. Press
it to enter a dedicated mode. In this mode, only two columns show
anything: Key and Scale, both for the selected track. The other 6
columns stay blank, and every other encoder does nothing. Press `Scale`
again to leave the mode. This replaces the old gesture of holding
`Scale` and turning any encoder.

You can enter Scale mode only with a specific track selected, not from
Main mode and not while the mod lane overlay is open. Both of those
apply to more than one track at once, and Scale mode always applies to a
single track.

Scale mode tuning (shipped). The Key and Scale encoders now need an
accumulated turn (`Engine.KNOB_ACCUM_THRESHOLD = 4`) before they step
once. Before this change, every relative-encoder tick moved the value,
which felt too sensitive for a 12-item or 22-item list.

Both encoders now clamp at the ends of their list, instead of wrapping
around. At `super_locrian` or at B, the encoder stops. Turn the encoder
the other way to move again.

Scale library (shipped). The scale library grew from 6 scales to 22
(`engine.py`'s `SCALES`):
- The 7 diatonic modes.
- The two octatonic (diminished) scales.
- Whole tone, and minor blues.
- Both pentatonic scales.
- Harmonic minor and harmonic major.
- The melodic-minor family: melodic minor, dorian #4, phrygian
  dominant, lydian augmented, lydian dominant, and super locrian.

The cycle order of the Scale encoder groups related scales together, not
in alphabetical order.

A few display names (`SCALE_LABELS` in `engine.py`) override the generic
display rule, which turns underscores into title case. For example,
GridSeq shows "Dorian #4", not "Dorian Sharp4", and "Half-Whole
Dim"/"Whole-Half Dim", not "Half Whole Dim"/"Whole Half Dim".

More encoder tuning (shipped). The jog wheel of Main mode now also
clamps at each end of its parameter list, instead of wrapping.

Pitch, Offset, Repeat, and MIDI Channel now use the same accumulated-turn
treatment as Key and Scale. Velocity, Gate, and Probability keep full
per-message sensitivity, by design.

The `Screen top N` row (mod-lane access) is now off by default. It
lights up only above an actual on-screen Mod button, in the color of
that track. Before this change, every column showed a blanket dim or
full light, with no regard to whether it meant anything there.

The track whose mod lane is open now shows bright red, on the button
that closes it. This fix corrected a real bug in the dispatch logic:
before the fix, once the overlay was open, only `Screen top 8` closed
it, no matter which track's lane was open or which button opened it.
See the plan file for more detail.

v3 candidates (not built):
- A surface control for mod-lane length, and a per-track mod CC number
  (both fixed today)
- Pattern slots, or song chaining (v3, from the original plan)
