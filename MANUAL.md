# GridSeq — User Manual

GridSeq is a multitrack step sequencer for Ableton Push 2/3. It runs as
a [push-tethered-app](https://github.com/federico-pepe/push-tethered-app)
module.

This manual explains the function of every button, pad, and encoder. The
grid layout follows the style of Ableton Live: columns are tracks, and
rows are steps.

## Quick orientation

```
Rows (top→bottom):  step 1 … step 8     (top row = step 1, earliest)
Cols (left→right):  track 1 … track 8   (the currently visible window)
```

- A **lit pad** means that step is on, for the track of that column, in
  the track's own color.
- The **brightest** pad in a column is the playhead. It marks the step
  about to play, or the step that just played, for that track. The
  playhead travels **top to bottom** as steps advance. Each track can
  run at its own speed (time division). As a result, the playheads of
  different columns can move at different rates. This is expected
  behavior, not a bug.
- GridSeq has no header or status bar. The content shown above the pads
  depends on the mode. See "Track mode vs Main mode" below for the
  details. Read every other value from the LEDs instead: BPM, clock
  sync, play/stop state, mute/solo, and time division. See "Button LED
  legend" below, and the Tempo popup under "Tempo".
- The **bottom strip** has one label per column. It always names the
  track ("Track 1", "Track 2" …), directly above the matching button
  below the screen. This does not change meaning in either mode. Each
  track has its own color, shared by its pad LEDs and its bottom label.
  GridSeq draws these colors from a hand-picked, hardware-tested list
  (`TRACK_COLORS` in `engine.py`), cycled across tracks with a stride so
  neighboring tracks do not get similar hues. The **selected** track's
  label is a solid filled block in that color. Every other track's label
  is colored text on black. No label is filled while Main mode is
  active.
- Each parameter's **value** shows noticeably larger than its label (2x,
  the standard font), with no repeated abbreviation. The label above it
  already names the parameter ("Velocity", "Gate", and so on), so the
  value below it is just the number. With no pad held, the value shows
  the **range** across every step in that column, for example "40..100",
  or a single number if every step agrees. **Hold a step pad** to narrow
  the value to that one step's exact number. Release the pad to return
  to the range view. This applies to every per-step parameter: velocity,
  gate, repeat, probability, offset, and pitch.

## Track mode vs Main mode

GridSeq has exactly one specific track selected, or **Main mode**
active, never both. This changes the meaning of the 8 encoders and the
area above the pads.

**Track mode (a specific track selected, the default):**
- The 8 columns are **parameters** of that one track: column 1 =
  Velocity, column 2 = Gate, column 3 = Repeat, column 4 = Probability,
  column 5 = Offset, column 6 = Pitch. Pitch shows note names, for
  example "C#3", instead of a plain semitone number. See "Pitch and
  scale" below. Column 7 = **MIDI Channel**, the MIDI output channel of
  the track (1-16, independent per track). Column 8 = **Mod**. Mod
  renders as a small colored button, the same height as the old header
  row, with a "**>**" mark that hints at another page behind it. Mod has
  no single label/value pair, because no one number can show the state
  of a whole mod lane.
- **Tap the "Screen top" button directly above the Mod column** to jump
  straight into the mod-lane editor for that track. See "Mod lane"
  below. Turning the encoder itself still does nothing. Encoder *N*
  always edits the parameter of column *N*, for the selected track.
- All 8 parameters show and edit at once. There is no paging.

**Main mode (press "Select (main)"):**
- The 8 columns are **tracks** again, the same as the pad grid always
  shows. But now all 8 columns show the *same* parameter. Encoder *N*
  edits the value of that one parameter, for the *N*th visible track.
- Turn the **jog wheel** to change *which* parameter all 8 columns show
  and edit: velocity, gate, repeat, probability, offset, pitch, MIDI
  channel, or mod. The jog wheel cycles the same list that Track mode's
  8 columns are fixed to. It stops at either end (Velocity, Mod) instead
  of wrapping around.
- Mod still renders as a button here, one per visible track, in that
  track's color. The "Screen top N" button above any column opens the
  mod lane of *that* track directly, no matter which parameter Main mode
  currently shows.
- Use Main mode to compare or adjust the same parameter across every
  track at a glance, for example to balance every track's velocity
  against the others.

The jog wheel does **only** this parameter-scrolling, and **only** in
Main mode. It never changes which track is selected.

## Selecting a track

Press one of the **8 buttons below the screen** ("Screen bottom 1"–"8"),
under the "Track N" label of the track you want. Each button selects the
track in its column, and leaves Main mode if it was active.

These buttons are **black by default**. Only the button of the selected
track lights up, in that track's own color. If you have paged sideways
(see below), "Screen bottom 3" means "the 3rd track currently visible",
not literally track #3.

## Main mode

Press **Select (main)** (the button just above the "1/32t" time-division
button) to toggle Main mode on or off. See "Track mode vs Main mode"
above for what changes.

The **Select (main)** button lights dim when off, and full white when
on, so you can always tell which mode you are in. Selecting a specific
track (a Screen-bottom button) always turns Main mode back off.

## Toggling and editing steps

- **Tap a pad**: toggles that step on or off, for the track of that
  column. This always means a track, in both modes. The pad grid never
  becomes a parameter grid.
- **Hold a pad, then turn any encoder**: edits *that one step's* value,
  and overrides everything else. Which parameter this edits depends on
  the mode: the encoder's fixed column in Track mode, or the
  jog-selected parameter in Main mode. Either way, the edit always
  targets the exact step under the held pad, on that pad's own track.
- **Turn an encoder with no pad held**: edits the track's *default*
  value for that parameter instead. This rescales every existing step by
  the same relative amount. For example, turn velocity up a little, and
  every step's velocity moves up a little too. This is the "global knob"
  feel.

Pitch, Offset, Repeat, and MIDI Channel are **less sensitive** than the
rest, by design. Each of these needs a real, deliberate turn per step
change, not just a small wiggle of the encoder. Velocity, Gate, and
Probability stay at full sensitivity: every encoder message moves them.
Fast, fine adjustment matters more for these than for a 12-note pitch
range or a 1-16 channel count.

## Pitch and scale

Every track works the same way. There is no separate "drum" mode. Each
active step triggers `root + pitch offset`, quantized to the scale of
the track.

Set the pitch offset per step with the "Pitch" encoder, column 6 in
Track mode. There is no on-grid piano roll in v1. Hold the step pad and
turn the Pitch encoder to hear the note move.

The offset can reach any of the 128 MIDI notes, from any root note. It
clamps only at the very ends, note 0 or note 127. It never narrows to a
band around the root. See "Toggling and editing steps" above for its
reduced sensitivity.

Leave the default `chromatic` scale active, and pitch editing behaves
exactly like picking any note directly, for example to select a
drum-kit voice by note number. Quantization starts only when you switch
to a scale other than `chromatic`.

The on-screen value of the Pitch column shows the resolved note
**name**, for example "C3", "C#3", or "D3". This uses the octave
numbering of Ableton Live: MIDI note 60 is "C3", not the more common
"C4" of scientific pitch notation. GridSeq matches Live's numbering,
because this is a Push module for Live. This name is what you read off a
piano roll. A plain semitone-offset number tells you nothing, without
the root note and scale it resolves through. The full range is C-2 to
G8.

**Octave Up** and **Octave Down** transpose the root note of *every
track* by one octave. This is a global control, not a per-track one.

**Press "Scale"** to enter **Scale mode**. This mode works only with a
specific track selected, not in Main mode and not while the mod lane
overlay is open. The button LED goes fully off, not just dim, when Scale
mode is not available.

While Scale mode is active, only two columns mean anything:
- Column 1 = **Key**. Turn it to step the root note of the selected
  track through the 12 semitones, within its current octave. For
  example, "C3" becomes "C#3", not the "C" of a different octave.
- Column 2 = **Scale**. Turn it to cycle through the scale names, 22 in
  total: Chromatic, Major, Minor, Dorian, Mixolydian, Lydian, Phrygian,
  Locrian, Whole Tone, Half-Whole Dim, Whole-Half Dim, Minor Blues,
  Minor Pentatonic, Major Pentatonic, Harmonic Minor, Harmonic Major,
  Dorian #4, Phrygian Dominant, Melodic Minor, Lydian Augmented, Lydian
  Dominant, and Super Locrian. This is the cycle order: the diatonic
  modes first, then the symmetric scales, then pentatonic and blues,
  then the melodic-minor family.

Both Key and Scale are less sensitive than the other encoders. A small
wiggle changes nothing. A real turn is needed per step. Neither encoder
wraps around: at the first or last item (B for Key, Super Locrian for
Scale), turning further the same way does nothing. Turn the encoder the
other way to come back.

The other 6 columns go blank in Scale mode, instead of showing stale
Track-mode parameters. Every other encoder is inert.

**Press "Scale" again** to leave the mode. The Key and Scale values you
land on are already in effect. There is no separate "apply" step. Every
turn edits live, the same as everywhere else in GridSeq.

Scale quantizes at **playback** time only. A step's pitch encoder still
stores a plain semitone offset from the root note. Switching scales
never rewrites that stored offset. It changes only the absolute note the
offset resolves to when the step fires. Each offset snaps to its nearest
degree in the current scale. `chromatic` applies no quantization at all.

This makes a scale change non-destructive on an existing pattern.
Switch back to `chromatic`, and every step plays exactly the raw offset
you originally set.

## Repeat and Accent shortcuts

- **Repeat** (hold), then tap a step: this quick-toggles the ratchet
  count of that step, between 1 (off) and 4, with no change to the
  "repeat" encoder. The encoder still works normally, for finer control,
  for example 2, 3, or 5+ repeats.
- **Accent** (hold), then tap a step: this toggles a fixed velocity and
  gate boost on that step, independent of the step's own velocity value.

## Mute / Solo

Hold **Mute**, then tap a track's **Screen-bottom** button, to mute that
track. Hold **Solo**, then tap a Screen-bottom button, to solo it. Solo
silences every other, non-soloed track.

Both mute and solo are per-track toggles. The `Mute`/`Solo` button LED
shows dim for off and full for on, while held. If you tap a *pad* while
either button is held, the tap does **not** mute or solo. It just
toggles that step, the same as with no modifier held.

A track that does not actually sound right now, because of a mute or
because another track is soloed, turns **grey**. Its pad steps that are
on show grey instead of the track's color, and its bottom-strip label
turns grey too, instead of the track's color or its filled block if it
is the selected track. This display follows `Engine.track_audible()`
exactly. There are not two separate mute/solo visual states. One shared
"will not sound" look covers both causes.

Mute and solo are a GridSeq-side gate only. A muted or silenced track
never sends its notes or mod CCs. `Engine.track_audible()` runs at
trigger time, in `_trigger_step` and `_trigger_mod_step`. There is no
MIDI "mute message" involved. This is the only way to mute or solo MIDI
output from GridSeq.

## Track color picker

Hold **Shift**, then tap a track's **Screen-bottom** button. This
selects that track, and borrows the whole pad grid for a color picker.
Every pad goes dark, except the outer **border** ring. The border pads
light up with the 26 track colors of GridSeq, one color per pad. The
sequence starts at the pad just left of bottom-center, and runs
clockwise around the edge. The border has 28 pads and GridSeq has 26
colors, so 2 border pads at the end of the loop stay dark.

Tap any lit border pad to set that color on the selected track,
immediately. Its pad steps, its Screen-bottom button, and its Screen-top
Mod button all switch to the new color at once. You can tap a different
border pad to change your choice, before you release Shift.

Release **Shift** to exit the picker and return to the normal step grid.
No other control (mute/solo, step editing, encoders) works while the
picker is open.

## Tempo

Turn the **Tempo wheel** (top-right of the encoder row) to change the
global BPM, from 40 to 240. A "TEMPO" popup, with the current value,
shows centered on screen while you turn the wheel. It closes on its own,
about a second and a half after you stop. There is no permanent BPM
readout otherwise, because GridSeq no longer has a header to show it in.
The Tempo wheel has an effect only while GridSeq runs on internal sync.
See "Transport" below.

This popup is a generic mechanism, `State.show_popup`: a centered white
box, with a small title line and an optional larger line below it,
sized to fit its text. Any button whose effect is not otherwise visible
on screen can use this mechanism. Tempo is the only one that uses it
today.

## Transport

- **Play**: starts or stops the sequencer. White means stopped, and
  **green** means playing. `Stop Clips` has no function now, because it
  did the same thing as Play while the sequencer ran. GridSeq removed it
  instead of keeping a redundant second stop control.
- If MIDI clock arrives on the declared external-MIDI-in port of
  GridSeq, every track locks to that clock instead of its internal BPM.
  There is no on-screen int/ext indicator any more, because that display
  lived in the now-removed header. Only the timing itself changes. If
  the external clock stops for more than 2 seconds, GridSeq falls back
  to internal timing automatically.

## Time division

The 8 buttons above the pads, labeled **Scene 1/4, 1/4t, 1/8, 1/8t,
1/16, 1/16t, 1/32, 1/32t**, set the speed of the *selected track*
directly. Press one, and that track advances at that rate from then on.
The button for the selected track's active division **pulses vivid
green, on and off**, so it is impossible to miss. The rest stay dim.

## Mod lane

Each track has an independent **mod lane**: its own length, its own
time division, and its own per-step value from 0 to 127. The mod lane is
fully decoupled from the note lane, with a different length, a different
speed, and its own steps. Whenever a mod step's value is above 0, it
fires `send_cc(channel, mod_cc, value)` on its own schedule, whether or
not the note lane is playing anything at that moment.

The "Screen top N" row is off by default. It lights up only above an
actual Mod button, in that track's own color, and stays off everywhere
else. This is the same "off means nothing here" convention that the
Screen-bottom row uses.

**In Main mode**, every column can show this once the jog wheel scrolls
to Mod (one Mod button per visible track). Press any of them to open the
mod-lane editor for that track. **In Track mode**, only "Screen top 8"
ever lights, because it is the one button that sits above the single Mod
button there. Press it to open the *selected* track's lane.

Once the editor is open, it works the same way regardless of which mode
opened it. The Screen top button of the currently open track turns
**bright red**. Press that same button to close the editor. Press any
*other* lit button to jump straight to that track's lane, instead of
closing first.

While the mod-lane editor is open, the grid, D-Pad, and Scene buttons of
GridSeq all change meaning:

- **The pad grid** is borrowed. Column *N* becomes the mod lane of the
  *N*th visible track, the same track-per-column layout as always. Each
  column becomes a **bar graph**. Tap a row to set that track's mod
  value, at the current cursor step, to one of 8 buckets: 0, 18, 36, 54,
  73, 91, 109, or 127. The bottom row is the lowest bucket, and the top
  row is the highest. The pads then redraw with rows 0 through that
  bucket lit, in the track's color, so a taller bar means a louder
  value. A track whose mod lane is shorter than the current cursor step
  shows an entirely dark column, with nothing to edit there.
- **D-Pad up** and **D-Pad down** move a single, shared **cursor**
  through the mod steps, one step at a time, not by pages. Each column's
  label carries the prefix "S*N*" (for example "S3 1/16"), for the
  current cursor step *N*, because there is no header left to show it
  elsewhere. The D-Pad LEDs show whether there is room to move further
  up or down (dim) or not (off).
- **The Scene buttons** (`1/4` to `1/32t`) set the mod division of the
  *selected* track, instead of its note division. The active one pulses
  the same way the note-division picker does.
- Track mode, Main mode, the 8 encoders, and the jog wheel all do
  nothing while mod-lane mode is active. Mod-lane mode is a third mode,
  exclusive of the other two, and it takes over the same surface.

Mod lane length has no surface control yet, in v1. Every track starts
with an 8-step mod lane, at the same default division as its note lane.
You can change each one independently, once you are editing it.

## Growing beyond 8 tracks — and why Page Left/Right looked broken

**Page Left** and **Page Right** scroll the visible 8-track window
sideways.

Early on, these buttons often looked like they did nothing. The reason:
they let you page into a *window with no tracks in it yet*. GridSeq
starts with exactly 8 tracks, so page 2 was empty, and looked identical
to page 1 being "stuck".

This is now fixed. Page Right does nothing, and its LED goes fully
**off**, not just dim, once you reach the last page that actually has a
track in it. To get a 9th track, and somewhere for Page Right to go,
press **Add**. `Add` appends a new track, copied from the currently
selected one: its kind, channel, division, root, scale, length, and all
its steps. Keep pressing Add to grow further, up to 16 tracks total.

The LEDs of Page Left and Page Right show, at a glance, whether there is
anywhere to page to: dim means yes, off means no, and full white means
the button is held.

## Stepping through a long pattern — D-Pad up/down

**D-Pad up** and **D-Pad down** scroll the *step*-page window: which 8
steps of the selected track's pattern you edit or view. This is
independent of which tracks are visible. A track's pattern can run up to
64 steps long.

Up scrolls to earlier steps, and down scrolls to later ones. This
matches the top-to-bottom, earliest-to-latest layout of the rows (see
"Quick orientation"), so the D-Pad moves in the same direction as the
pads and the playhead already do. D-Pad left and right have no function
here, because the step timeline of GridSeq reads vertically, not
horizontally.

Hold **Shift**, then press **D-Pad up** or **D-Pad down**, to shrink or
grow the length of the *selected* track by 8 steps (one page), down to a
floor of 8 and up to a ceiling of 64. Growing appends fresh, off steps.
Shrinking truncates the tail, so a shrink followed by a grow does not
restore what was there before. The D-Pad LEDs switch meaning while Shift
is held: dim means room to shrink or grow, and off means you are at the
floor or the ceiling.

**Clip View** is a plain toggle, top-right of the encoder row. It opens
a dedicated Length view for fine control. In this view, the top-left
label and value on screen switch to "Length" and the step count of the
selected track, and encoder 1 edits that count one step at a time, down
to a floor of **1**, not 8. This lets a track run shorter than a full
D-Pad page. The other 7 encoders go blank while this view is open.

Encoder 1 has the same throttled-turn feel as Key and Scale in Scale
mode: a deliberate turn is needed per step change, not a small wiggle.
Clip View is exclusive with Scale mode, so opening either one closes the
other. Clip View is not available in Main mode, or while the mod lane is
open, the same gating that Scale mode uses.

New tracks and patterns still default to 8 steps. Only this knob, or
Shift + D-Pad, changes the length after that.

## Undo

**Undo** reverses the last step, param, mute, solo, division, kind, or
Add edit. It holds one level only, not a deep history. Its LED lights
full white whenever an undo is available, and dim when it is not, so you
can see at a glance whether pressing it will do anything.

## Resetting a parameter to its default

Hold **Delete**, then touch a screen encoder with a light touch, not a
turn or a click. This uses the same capacitive sensor that already fires
on every normal turn. See "Mod lane" above for why that matters.

This action resets the current parameter of that encoder to its default
value: 100 for Velocity, 50 for Gate, 1 for Repeat, 100 for Probability,
0 for Offset, 0 (the root note) for Pitch, and 1 for MIDI Channel. With a
step pad held, only that step resets. With no pad held, every step on
the track resets.

This action has no effect on Mod, because Mod is a status page here, not
an editable value. It also has no effect while Scale mode or the mod
lane overlay is active.

## Saving and loading sequences

**Save** writes the current pattern to a file, under the name it was
last saved or loaded as. The first Save of a session, with nothing
loaded yet, names the file "Sequence 1", "Sequence 2", and so on,
automatically. This hardware has no text entry to name a file by hand. A
"SAVED &lt;name&gt;" popup confirms the save.

**Set** opens a full-screen list of every saved sequence, with "New"
always first. Scroll the list with the jog wheel, or with D-Pad up/down
(D-Pad up moves to an earlier item in the list, matching every other
D-Pad-scrolling context in this manual).

**Jog press** or **D-Pad center** confirms the highlighted entry.
Picking "New" resets GridSeq to a fresh, default 8-track pattern.
Picking a saved name loads it. Either way, GridSeq does **not**
auto-save the pattern you were on first. Save it yourself beforehand, if
you want to keep it.

Press **Set** again, with nothing else pressed, to close the list with
no change. While the list is open, the pad grid, the other 7 encoders,
and Tempo all do nothing. This is the same "one overlay owns everything"
exclusivity that the mod-lane overlay uses.

Sequence files live in this module's own `sequences/` folder, as plain
JSON, one file per sequence. This is a separate mechanism from the
host's `store_get`/`store_set` single-pattern slot, described below,
which stays off either way.

## Button LED legend

| State | Meaning |
|---|---|
| **Off (black)** | No function here right now (Page Right at the last page, every "Screen bottom" button except the selected track's, or all of them in Main mode) |
| **Dim white** | Has a function, currently inactive or available |
| **Full white** | Active: held down, toggled on, or "currently in effect" (selected track's division, Undo when an undo is available, Main mode on) |
| **Track color** | The selected track's own "Screen bottom" button. This matches its pad LEDs and on-screen label. Off entirely while Main mode is active. Also every "Screen top" button that currently sits above an actual Mod button, in that track's color. Off everywhere else on that row. |
| **Green** | Play, while the sequencer runs |
| **Pulsing green/off** | The active time-division button of the selected track |
| **Bright red** | The open track's "Screen top" button, in the mod lane. Press it to close the overlay. |

## Persistence

**Currently off.** GridSeq always starts from a fresh, default pattern,
and does not save on close. Each session starts blank. The save and
load code (`store_get`/`store_set`) is still in the codebase, just not
called (`run.py`'s `PERSIST_ENABLED = False`). Setting that one flag
back to `True` restores the original behavior: GridSeq saves the pattern
automatically on close, and reloads it automatically on the next start.

## Not in v1 yet

- A real visualization for the status page of the Mod column. Today it
  is a plain colored button. How to show a whole lane's worth of values
  in that space is still an open question.
- A surface control for mod-lane length. It is fixed at 8 steps for now,
  the same way note-lane length was, before its own control shipped.
- A per-track mod CC number. It is fixed to CC1 for every track.
- Pattern slots, or song chaining (v3).

See the project README for the full v1 to v3 roadmap.
