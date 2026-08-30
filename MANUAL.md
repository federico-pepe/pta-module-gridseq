# GridSeq — User Manual

GridSeq is a multitrack step sequencer for Ableton Push 2/3 running as a
[push-tethered-app](https://github.com/federico-pepe/push-tethered-app)
module. This manual explains what every button, pad, and encoder does.
Grid layout is Live-style: **columns are tracks**, **rows are steps**.

## Quick orientation

```
Rows (top→bottom):  step 8 … step 1     (bottom row = step 1, earliest)
Cols (left→right):  track 1 … track 8   (the currently visible window)
```

- A **lit pad** = that step is on for that column's track, in the
  track's own color.
- The **brightest** pad in a column = the playhead — whichever step is
  about to play or just played for that track. Every track can run its
  own speed (time division), so different columns' playheads move at
  different rates — that's expected, not a bug.
- The **top bar** (header) shows: BPM, internal/external sync,
  playing/stopped, which 8-track window you're looking at (and how many
  tracks exist total), and — on the right — either the selected track's
  kind/division/mute/solo flags, or "MAIN - <Parameter>" in Main mode.
- **What the area above the pads shows depends on the mode** (this is the
  important part — read "Track mode vs Main mode" below).
- The **bottom strip**, one label per column, always names the track
  ("Track 1", "Track 2" …) directly above each of the 8 buttons below the
  screen — this never changes meaning, in either mode. Every track has
  its own color, shared by its pad LEDs and its bottom label — drawn only
  from the hardware's "Vivid" palette row (bright, distinct hues; no
  muddy/dark entries), cycled across tracks. The **selected** track's
  label is a solid filled block in that color; every other track's label
  is just colored text on black; none are filled while Main mode is
  active.
- Each parameter's **value** is drawn noticeably larger than its label
  (2x, standard font) and without a repeated abbreviation (the label
  above it already says "Velocity", "Gate", etc. — the value below it is
  just the number).

## Track mode vs Main mode

GridSeq has exactly one specific track selected, or **Main mode** active
— never both. This changes what the 8 encoders and the area above the
pads mean:

**Track mode (a specific track selected — the default):**
- The 8 columns are **parameters** of that one track: column 1 =
  Velocity, column 2 = Gate, column 3 = Repeat, column 4 = Probability,
  column 5 = Offset, column 6 = Pitch, columns 7-8 = Pan/Mod (v2, not
  implemented yet). Encoder *N* always edits column *N*'s parameter for
  the selected track.
- All 8 parameters are visible and editable at once — no paging.

**Main mode (press "Select (main)"):**
- The 8 columns are **tracks** again (like the pad grid always is), but
  all showing the *same* parameter — encoder *N* edits the *N*th visible
  track's value of that one parameter. Turn the **jog wheel** to change
  *which* parameter all 8 columns show and edit (velocity, gate, repeat,
  probability, offset, pitch, pan, mod) — it cycles the same list Track
  mode's 8 columns are fixed to.
- This is for comparing/adjusting the same parameter across every track
  at a glance — e.g. balance every track's velocity against each other.

The jog wheel **only** does this parameter-scrolling, and **only** in
Main mode. It never changes which track is selected.

## Selecting a track

Press one of the **8 buttons below the screen** ("Screen bottom 1"–"8"),
right under the "Track N" label you want. Each one selects the track in
that column and leaves Main mode if it was active. Those buttons are
**black by default** — only the selected track's button lights, in that
track's own color. If you've paged sideways (see below), "Screen bottom
3" means "the 3rd track currently visible," not literally track #3.

## Main mode

Press **Select (main)** (the button just above the "1/32t" time-division
button) to toggle Main mode on or off directly — see "Track mode vs Main
mode" above for what changes. The **Select (main)** button itself lights
dim when off, full white when on, so you can always tell which mode
you're in. Selecting a specific track (a Screen-bottom button) always
turns Main mode back off.

## Toggling and editing steps

- **Tap a pad**: toggles that step on/off for that column's track — this
  always means a track, in both modes; the pad grid never becomes a
  parameter grid.
- **Hold a pad + turn any encoder**: edits *that one step's* value,
  overriding everything else — which parameter depends on the mode
  (the encoder's fixed column in Track mode, or the jog-selected
  parameter in Main mode), but it always targets the exact step under
  the held pad, on that pad's own track.
- **Turn an encoder with no pad held**: edits the track *default* for
  that parameter instead, rescaling every existing step by the same
  relative amount (turn velocity up a bit, every step's velocity nudges
  up a bit — the "global knob" feel).

## Track kind: drum vs melodic

Press **Note** to flip the *selected* track between:
- **drum** (default) — every active step triggers the track's fixed
  note (`base_note`).
- **melodic** — every active step triggers `root + pitch offset`, where
  the pitch offset is set per step via the "pitch" encoder page. There's
  no on-grid piano roll in v1 — hold the step pad and turn the pitch
  encoder to hear it move.

**Octave Up / Octave Down** transpose the root of *every melodic track*
by an octave — this is global, not per-track.

**Scale** (hold) + turn any encoder cycles the selected track's scale
name (shown in the header's track line). In v1 this is a label only — it
doesn't quantize pitch yet; that's a planned refinement.

## Repeat and Accent shortcuts

- **Repeat** (hold) + tap a step: quick-toggles that step's ratchet count
  between 1 (off) and 4, without touching the "repeat" encoder. (The
  encoder still works normally for finer control, e.g. 2, 3, 5+ repeats.)
- **Accent** (hold) + tap a step: toggles a fixed velocity/gate boost on
  that step, independent of whatever the velocity value is.

## Mute / Solo

**Mute** (hold) + tap a column = mute that track. **Solo** (hold) + tap a
column = solo it (muting every non-soloed track). Both are per-track
toggles, reflected by the LED (dim = off, full = on) — no visual change
on the grid itself besides playback going silent.

## Tempo

Turn the **Tempo wheel** (top-right of the encoder row) to change the
global BPM (40-240), shown live in the header. Only has an effect while
running on internal sync — see below.

## Transport

- **Play**: starts/stops the sequencer. White = stopped, **green** =
  playing.
- **Stop Clips**: hard stop (same as pressing Play while running, kept
  as a separate dedicated stop).
- If MIDI clock arrives on GridSeq's declared external-MIDI-in port, the
  header switches to "(ext)" and every track locks to that clock instead
  of its internal BPM. It falls back to internal timing automatically if
  the external clock stops for more than 2 seconds.

## Time division

The 8 buttons above the pads labeled **Scene 1/4, 1/4t, 1/8, 1/8t, 1/16,
1/16t, 1/32, 1/32t** set the *selected track's* speed directly — press
one, that track now advances at that rate. The currently active one for
the selected track **pulses vivid green, on and off** (impossible to
miss); the rest sit dim.

## Growing beyond 8 tracks — and why Page Left/Right looked broken

**Page Left / Page Right** scroll the visible 8-track window sideways.
Early on these could look like they did nothing, because they let you
page into a *window with no tracks in it yet* — GridSeq starts with
exactly 8 tracks, so page 2 was empty and looked identical to page 1
being "stuck."

Fixed: Page Right is now a no-op (and its LED goes fully **off**, not
just dim) once you're on the last page that actually has a track in it.
To get a 9th track (and somewhere for Page Right to go), press
**Duplicate** — it appends a new track, copied from the currently
selected one (kind, channel, division, root, scale, length, and all its
steps). Keep pressing Duplicate to grow further, up to 16 tracks total.
Page Left/Right's LEDs tell you at a glance whether there's anywhere to
page to: dim = yes, off = no, full white = held.

## Stepping through a long pattern — D-Pad left/right

**D-Pad left / D-Pad right** scroll the *step*-page window (which 8 steps
of the selected track's pattern you're editing/viewing) — independent of
which tracks are visible. A track's pattern can be up to 64 steps long.

**Known v1 limitation:** every track starts at exactly 8 steps, and there
is no control yet to lengthen a track's pattern past 8 — so D-Pad
left/right will look inactive (LED off) on every fresh track, for the
same reason Page Right used to: there's nowhere to go yet. Per-track
length control is a near-term addition, not implemented in this version.
The persisted data model already supports up to 64 steps per track
(`length`/`steps`), so this will not require a data migration when added.

## Undo

**Undo** reverses the last step/param/mute/solo/division/kind/Duplicate
edit — one level only, not a deep history. Its LED is lit full white
whenever there's something to undo, dim when there isn't, so you can see
at a glance whether pressing it will do anything.

## Button LED legend

| State | Meaning |
|---|---|
| **Off (black)** | No function here right now (Page Right at the last page; every "Screen bottom" button except the selected track's, or all of them in Main mode) |
| **Dim white** | Has a function, currently inactive/available |
| **Full white** | Active: held down, toggled on, or "currently in effect" (selected track's division, Undo when something is undoable, Main mode on) |
| **Track color** | The selected track's own "Screen bottom" button — matches its pad LEDs and on-screen label. Off entirely while Main mode is active. |
| **Green** | Play, while the sequencer is running |
| **Pulsing green/off** | The selected track's active time-division button |

## Persistence

The current pattern (all tracks, all steps, BPM) is saved automatically
when the module closes (switching to another module, or quitting
`pushapp`), and reloaded automatically the next time GridSeq starts.

## Not in v1 yet

- Scale quantization (Scale is a label today, not a pitch filter)
- Per-track pattern length control beyond the default 8 steps
- Per-track CC modulation lanes ("pan (v2)"/"mod (v2)" encoder pages)
- Pattern slots / song chaining (v3)

See the project README for the full v1→v3 roadmap.
