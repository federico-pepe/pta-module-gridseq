# GridSeq — User Manual

GridSeq is a multitrack step sequencer for Ableton Push 2/3 running as a
[push-tethered-app](https://github.com/federico-pepe/push-tethered-app)
module. This manual explains what every button, pad, and encoder does.
Grid layout is Live-style: **columns are tracks**, **rows are steps**.

## Quick orientation

```
Rows (top→bottom):  step 1 … step 8     (top row = step 1, earliest)
Cols (left→right):  track 1 … track 8   (the currently visible window)
```

- A **lit pad** = that step is on for that column's track, in the
  track's own color.
- The **brightest** pad in a column = the playhead — whichever step is
  about to play or just played for that track. It travels **top to
  bottom** as steps advance. Every track can run its own speed (time
  division), so different columns' playheads move at different rates —
  that's expected, not a bug.
- There is no header/status bar — GridSeq has none. What the area above
  the pads shows depends on the mode (this is the important part — read
  "Track mode vs Main mode" below); everything else (BPM, sync,
  playing/stopped, mute/solo, division) is read off the LEDs instead —
  see "Button LED legend" below and the Tempo popup under "Tempo".
- The **bottom strip**, one label per column, always names the track
  ("Track 1", "Track 2" …) directly above each of the 8 buttons below
  the screen — this never changes meaning, in either mode. Every
  track has its own color, shared by its pad LEDs and its bottom label —
  drawn only from the hardware's "Vivid" palette row (bright, distinct
  hues; no muddy/dark entries), cycled across tracks. The **selected**
  track's label is a solid filled block in that color; every other
  track's label is just colored text on black; none are filled while
  Main mode is active.
- Each parameter's **value** is drawn noticeably larger than its label
  (2x, standard font) and without a repeated abbreviation (the label
  above it already says "Velocity", "Gate", etc. — the value below it is
  just the number). With no pad held, it's the **range** across every
  step in that column ("40..100", or a single number if every step
  agrees). **Hold a step pad** and it narrows to that one step's exact
  value instead — release the pad and it goes back to showing the
  range. This applies to every per-step parameter (velocity, gate,
  repeat, probability, offset, pitch).

## Track mode vs Main mode

GridSeq has exactly one specific track selected, or **Main mode** active
— never both. This changes what the 8 encoders and the area above the
pads mean:

**Track mode (a specific track selected — the default):**
- The 8 columns are **parameters** of that one track: column 1 =
  Velocity, column 2 = Gate, column 3 = Repeat, column 4 = Probability,
  column 5 = Offset, column 6 = Pitch (shows note names like "C#3" here
  instead of a plain semitone number — see "Pitch and scale" below),
  column 7 = **MIDI Channel**: the track's MIDI
  output channel (1-16, independent per track), column 8 = **Mod**: renders as a small colored button —
  same height as the old header row, with a "**>**" hinting there's
  another page behind it — not a label+value pair, since there's no
  single number worth showing for a whole mod lane. **Tap the "Screen
  top" button directly above this column** to jump straight into that
  track's mod-lane editor (see "Mod lane" below); turning the encoder
  itself still does nothing. Encoder *N* always edits column *N*'s
  parameter for the selected track.
- All 8 parameters are visible and editable at once — no paging.

**Main mode (press "Select (main)"):**
- The 8 columns are **tracks** again (like the pad grid always is), but
  all showing the *same* parameter — encoder *N* edits the *N*th visible
  track's value of that one parameter. Turn the **jog wheel** to change
  *which* parameter all 8 columns show and edit (velocity, gate, repeat,
  probability, offset, pitch, MIDI channel, mod) — it cycles the same
  list Track mode's 8 columns are fixed to, stopping at either end
  (Velocity, Mod) rather than wrapping around. Mod still renders as a
  button here, one per visible track, in that track's color, and the
  "Screen top N" button above any column opens *that* track's mod lane
  directly, whichever parameter Main mode currently happens to show.
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

Pitch, Offset, Repeat, and MIDI Channel are deliberately **less
sensitive** than the rest — a real, deliberate turn is needed per step
change, not just any small wiggle of the encoder. Velocity, Gate, and
Probability stay at full sensitivity (every encoder message moves them),
since fast fine adjustment matters more there than for a 12-note pitch
range or a 1-16 channel count.

## Pitch and scale

Every track works the same way — there's no separate "drum" mode.
Every active step triggers `root + pitch offset`, quantized to the
track's scale. The pitch offset is set per step via the "Pitch" encoder
page (column 6 in Track mode) — there's no on-grid piano roll in v1;
hold the step pad and turn the Pitch encoder to hear it move. The
offset can reach any of the 128 MIDI notes regardless of root — clamped
only at the very ends (note 0 or 127), never silently narrowed to a
band around the root; see "Toggling and editing steps" above for its
(deliberately reduced) sensitivity. Leave the default `chromatic` scale
active and this behaves
exactly like picking any note directly (e.g. for selecting a drum-kit
voice by note number) — quantization only kicks in once you switch to
a non-`chromatic` scale.

The Pitch column's on-screen value shows the resolved note **name**
("C3", "C#3", "D3"...), using Ableton Live's own octave numbering (MIDI
60 = C3, not the more common "C4" scientific-pitch convention — chosen
to agree with Live since this is a Push module) — what you'd actually
read off a piano roll — since a plain semitone-offset number means
nothing without knowing the root and scale it resolves through. Full
range is C-2 to G8.

**Octave Up / Octave Down** transpose the root of *every track* by an
octave — this is global, not per-track.

**Press "Scale"** to enter **Scale mode** — only works with a specific
track selected (not Main mode, not while the mod lane overlay is open;
the button LED goes fully off, not just dim, when it can't be entered).
While active, only two columns mean anything: column 1 = **Key**
(turn to step the selected track's root through the 12 semitones,
keeping its octave — "C3" becomes "C#3", not some other octave's "C"),
column 2 = **Scale** (turn to cycle the scale name). Both encoders are
deliberately less sensitive than the others here — small wiggles don't
change anything, a real turn is needed per step — and neither one
wraps: reach the first or last item (B for Key, `pentatonic_minor` for
Scale, in the order they cycle) and turning further the same way does
nothing; reverse direction to come back. The other 6 columns go blank
rather than show stale Track-mode parameters underneath, and every
other encoder is inert. **Press "Scale" again** to leave — whatever
Key/Scale you landed on is already in effect (there was no separate
"apply" step; every turn edits live, same as everywhere else in
GridSeq).

Scale quantizes at **playback** time only — a step's pitch encoder
still stores a plain semitone offset from root, and switching scales
never rewrites that stored offset, only which absolute note it resolves
to when the step fires (each offset snaps to its nearest degree in the
current scale; `chromatic` applies no quantization at all). That makes
trying a different scale on an existing pattern non-destructive: switch
back to `chromatic` and every step plays exactly the raw offset you
originally set.

## Repeat and Accent shortcuts

- **Repeat** (hold) + tap a step: quick-toggles that step's ratchet count
  between 1 (off) and 4, without touching the "repeat" encoder. (The
  encoder still works normally for finer control, e.g. 2, 3, 5+ repeats.)
- **Accent** (hold) + tap a step: toggles a fixed velocity/gate boost on
  that step, independent of whatever the velocity value is.

## Mute / Solo

**Mute** (hold) + tap the track's **Screen-bottom** button = mute that
track. **Solo** (hold) + tap a Screen-bottom button = solo it (silencing
every non-soloed track). Both are per-track toggles, reflected by the
`Mute`/`Solo` button LED (dim = off, full = on) while held — tapping a
*pad* while either is held does **not** mute/solo; it just toggles that
step normally, the same as with no modifier held.

A track that won't actually sound right now (explicitly muted, or
silenced because some other track is soloed) turns **grey**: its pad
steps that are on show grey instead of the track's color, and its
bottom-strip label turns grey too (instead of its track color, or the
color-filled block if it's the selected track). This reflects
`Engine.track_audible()` exactly — it's not two separate mute/solo
visual states, one shared "won't sound" look covers both causes.

Muting/soloing is purely a GridSeq-side gate: a muted/silenced track
simply never sends its notes or mod CCs (`Engine.track_audible()` is
checked at trigger time in `_trigger_step`/`_trigger_mod_step`) — there's
no MIDI "mute message"; this is the only way to mute/solo MIDI output
from here.

## Track color picker

**Shift** (hold) + tap a track's **Screen-bottom** button: selects that
track and borrows the whole pad grid for a color picker — every pad goes
dark except the outer **border** ring, which lights up with GridSeq's 26
track colors, one per border pad, starting at the pad just left of
bottom-center and running clockwise around the edge (2 border pads at
the end of the loop are left dark — there are 28 border pads and only 26
colors). Tap any lit border pad to assign that color to the selected
track immediately — its pad steps, Screen-bottom button, and Screen-top
Mod button all switch to it right away, and you can tap a different
border pad to change your mind before letting go. Release **Shift** to
exit and get the normal step grid back; nothing else (mute/solo, step
editing, encoders) is reachable while the picker is open.

## Tempo

Turn the **Tempo wheel** (top-right of the encoder row) to change the
global BPM (40-240). A "TEMPO" popup with the current value appears,
centered on screen, while you're turning it, then disappears on its own
about a second and a half after you stop — there's no permanent BPM
readout otherwise, since the header that used to show it is gone. Only
has an effect while running on internal sync — see below.

This is a generic mechanism (`State.show_popup`) — a centered white box,
a small title line, and an optional bigger line below it, sized to fit
whatever text it's showing — for any button whose effect isn't
otherwise visible on screen; Tempo is the only one using it right now.

## Transport

- **Play**: starts/stops the sequencer. White = stopped, **green** =
  playing. (`Stop Clips` is unbound — it did the same thing as Play with
  the sequencer running, so it was removed rather than kept as a
  redundant second stop.)
- If MIDI clock arrives on GridSeq's declared external-MIDI-in port,
  every track locks to that clock instead of its internal BPM — there's
  no on-screen int/ext indicator any more (that lived in the now-removed
  header), only the timing itself changing. It falls back to internal
  timing automatically if
  the external clock stops for more than 2 seconds.

## Time division

The 8 buttons above the pads labeled **Scene 1/4, 1/4t, 1/8, 1/8t, 1/16,
1/16t, 1/32, 1/32t** set the *selected track's* speed directly — press
one, that track now advances at that rate. The currently active one for
the selected track **pulses vivid green, on and off** (impossible to
miss); the rest sit dim.

## Mod lane

Every track has an independent **mod lane**: its own length, its own time
division, and its own per-step 0-127 value — fully decoupled from the note
lane (different length, different speed, its own steps). Whenever a mod
step's value is above 0, it fires `send_cc(channel, mod_cc, value)` on its
own schedule, whether or not the note lane is even playing anything at
that moment.

The "Screen top N" row is off by default, and only ever lights above an
actual Mod button, in that track's own color — off everywhere else,
same "off = nothing here" convention the Screen-bottom row uses. **In
Main mode**, that's every column once the jog wheel is scrolled to Mod
(one Mod button per visible track); pressing any of them opens that
track's mod-lane editor. **In Track mode**, only "Screen top 8" ever
lights (it's the one actually sitting above the single Mod button
there); pressing it opens the *selected* track's lane.

Once the editor is open, it works the same way regardless of which mode
opened it: the currently-open track's own Screen top button turns
**bright red** — that's the one to press to close it — while pressing
any *other* lit-up one jumps straight to that track's lane instead of
closing first. While the editor is open, GridSeq's grid, D-Pad, and
Scene buttons all change meaning:

- **The pad grid** is borrowed: column *N* is the *N*th visible track's
  mod lane (same track-per-column layout as always), and the column
  becomes a **bar graph** — tapping a row sets that track's mod value at
  the current cursor step to one of 8 buckets (0, 18, 36, 54, 73, 91, 109,
  127; bottom row = lowest, top row = highest), and the pads redraw with
  rows 0 through that bucket lit in the track's color, tallest = loudest.
  A track whose mod lane is shorter than the current cursor step shows an
  entirely dark column — nothing to edit there.
- **D-Pad up / D-Pad down** move a single shared **cursor** through mod
  steps one at a time (not by pages) — each column's label is prefixed
  "S*N*" (e.g. "S3 1/16") for the current cursor step *N*, since there's
  no header left to show it once. The D-Pad LEDs reflect whether there's
  room to move further up/down (dim) or not (off).
- **The Scene buttons** (`1/4`…`1/32t`) set the *selected* track's mod
  division instead of its note division — the active one pulses the same
  way the note-division picker does.
- Track mode, Main mode, the 8 encoders, and the jog wheel are all
  irrelevant while mod-lane mode is active — it's a third mode, exclusive
  of the other two, that takes over the same surface.

Mod lane length isn't adjustable from the surface yet in v1 — every track
starts with an 8-step mod lane at the same default division as its note
lane (both changeable independently once you're editing).

## Growing beyond 8 tracks — and why Page Left/Right looked broken

**Page Left / Page Right** scroll the visible 8-track window sideways.
Early on these could look like they did nothing, because they let you
page into a *window with no tracks in it yet* — GridSeq starts with
exactly 8 tracks, so page 2 was empty and looked identical to page 1
being "stuck."

Fixed: Page Right is now a no-op (and its LED goes fully **off**, not
just dim) once you're on the last page that actually has a track in it.
To get a 9th track (and somewhere for Page Right to go), press
**Add** — it appends a new track, copied from the currently
selected one (kind, channel, division, root, scale, length, and all its
steps). Keep pressing Add to grow further, up to 16 tracks total.
Page Left/Right's LEDs tell you at a glance whether there's anywhere to
page to: dim = yes, off = no, full white = held.

## Stepping through a long pattern — D-Pad up/down

**D-Pad up / D-Pad down** scroll the *step*-page window (which 8 steps
of the selected track's pattern you're editing/viewing) — independent of
which tracks are visible. A track's pattern can be up to 64 steps long.
Up scrolls to earlier steps, down to later ones — matching the rows'
own top-to-bottom, earliest-to-latest layout (see "Quick orientation"),
so the D-Pad moves the same direction the pads and the playhead already
read. (D-Pad left/right are unused for this — GridSeq's step timeline
reads vertically, not horizontally.)

**Shift (hold) + D-Pad up / D-Pad down** shrinks/grows the *selected*
track's length by 8 steps (one page) — down to a floor of 8, up to a
ceiling of 64. Growing appends fresh (off) steps; shrinking truncates the
tail, so shrinking then growing back does not restore what was there.
D-Pad's LEDs switch meaning while Shift is held: dim = room to
shrink/grow, off = at the floor/ceiling.

**Clip View** (a plain toggle, top-right of the encoder row) opens a
dedicated Length view for fine control: the screen's top-left label/value
switches to "Length" and the selected track's step count, and encoder 1
edits it one step at a time — down to a floor of **1**, not 8, so a track
can be shorter than a full D-Pad page (the other 7 encoders go blank
while this is open). Same throttled-turn feel as Key/Scale in Scale
mode — a deliberate turn is needed per step change, not just any small
wiggle. Exclusive with Scale mode (opening either closes the other) and
unavailable in Main mode or with the mod lane open, same gating as Scale
mode. New tracks/patterns still default to 8 steps; only this knob (or
Shift + D-Pad) changes that afterward.

## Undo

**Undo** reverses the last step/param/mute/solo/division/kind/Add
edit — one level only, not a deep history. Its LED is lit full white
whenever there's something to undo, dim when there isn't, so you can see
at a glance whether pressing it will do anything.

## Resetting a parameter to its default

**Delete (hold) + touch a screen encoder** (a light touch, not a turn or
a click — same capacitive sensor that already fires on every normal
turn, see "Mod lane" for why that matters) snaps that encoder's current
parameter back to its default value: 100 for Velocity, 50 for Gate, 1
for Repeat, 100 for Probability, 0 for Offset, 0 (root note) for Pitch,
1 for MIDI Channel. With a step pad held, only that step resets; with
nothing held, every step on the track resets. Has no effect on Mod (a
status page, not an editable value here) or while Scale mode or the mod
lane overlay is active.

## Saving and loading sequences

**Save** writes the current pattern to a file, under the name it was
last saved or loaded as. The very first Save of a session (nothing
loaded yet) auto-names it "Sequence 1", "Sequence 2", … — there's no
text entry on this hardware to name it by hand. A "SAVED &lt;name&gt;"
popup confirms.

**Set** opens a full-screen list of every saved sequence, "New" always
first. Scroll with the jog wheel or D-Pad up/down (D-Pad up = earlier
in the list, matching every other D-Pad-scrolling context in this
manual). **Jog press or D-Pad center** confirms the highlighted entry:
picking "New" resets to a fresh default 8-track pattern; picking a
saved name loads it. Either way the pattern you were on is **not**
auto-saved first — Save it beforehand if you want to keep it. Pressing
**Set** again with nothing else pressed just closes the list without
changing anything. While the list is open, the pad grid, the other 7
encoders, and Tempo are all inert — same "one overlay owns everything"
exclusivity as the mod-lane overlay.

Sequence files live in this module's own `sequences/` folder as plain
JSON, one per sequence — a separate mechanism from the host's
`store_get`/`store_set` single-pattern slot described below (which stays
disabled either way).

## Button LED legend

| State | Meaning |
|---|---|
| **Off (black)** | No function here right now (Page Right at the last page; every "Screen bottom" button except the selected track's, or all of them in Main mode) |
| **Dim white** | Has a function, currently inactive/available |
| **Full white** | Active: held down, toggled on, or "currently in effect" (selected track's division, Undo when something is undoable, Main mode on) |
| **Track color** | The selected track's own "Screen bottom" button — matches its pad LEDs and on-screen label. Off entirely while Main mode is active. Also every "Screen top" button that currently sits above an actual Mod button, in that track's color — off everywhere else on that row. |
| **Green** | Play, while the sequencer is running |
| **Pulsing green/off** | The selected track's active time-division button |
| **Bright red** | The mod lane's open track, on its "Screen top" button — press it to close the overlay |

## Persistence

**Currently disabled.** GridSeq always starts from a fresh default
pattern and does not save on close — every session starts blank. The
save/load machinery (`store_get`/`store_set`) is still in the code,
just not called (`run.py`'s `PERSIST_ENABLED = False`); flipping that
one flag re-enables the original behavior (pattern saved automatically
on close, reloaded automatically on the next start).

## Not in v1 yet

- A real visualization for the Mod column's status page (currently a
  plain colored button — undecided how to show a whole lane's worth of
  values in that space)
- Mod-lane length control from the surface (fixed at 8 steps for now,
  same as note-lane length was before its own control shipped)
- Per-track mod CC number (fixed to CC1 for every track)
- Pattern slots / song chaining (v3)

See the project README for the full v1→v3 roadmap.
