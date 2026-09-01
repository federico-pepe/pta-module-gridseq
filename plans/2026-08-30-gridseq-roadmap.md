# GridSeq roadmap

**Status:** living plan — updated as v1/v2/v3 progress, not a one-time
design doc. When a phase's contract settles, its user-facing rules get
folded into [MANUAL.md](../MANUAL.md) and [README.md](../README.md);
this file stays as the reasoning trail (why, what was considered and
rejected) rather than being deleted.

## Context

GridSeq is an OXI ONE MKII–inspired step sequencer built as a
push-tethered-app process module — not a port, a new design for Push's
actual hardware (8x8 pad grid, 8 encoders, no CV/gate, no analog clock).
It started from a single architecture plan (core engine + v1/v2/v3
staging) and has since gone through several rounds of hands-on hardware
feedback that changed the control scheme materially from that first
draft. This file captures where it's landed and what's still open, so a
future session (or a fresh Claude Code instance) doesn't have to
re-derive the reasoning from the commit history alone.

## What shipped

**v1 — core sequencer.** Columns = tracks (Live-style), rows = steps.
Per-step velocity/gate/repeat(ratchet)/probability/micro-timing-offset/
accent. Drum or melodic per-track kind (removed later — see "Drum/
melodic removed" near the end of this section). Per-track time division (the 8
"Scene 1/4"…"1/32t" buttons, a direct literal fit no knob-turn needed).
Multitrack beyond 8 via `Duplicate` (grows the track list) + `Page Left/
Right` (scrolls the visible 8-column window). External MIDI clock sync
with automatic fallback to internal BPM. Single-pattern persistence via
the host's `store_get`/`store_set`, versioned (`{"version":1,...}`) from
the start so a v3 schema change is additive, not a migration.

**Control-scheme redesign (post-v1, hardware-driven).** The very first
cut had 8 encoders mapped one-per-visible-*track*, with a "current
parameter" cycled by tapping an encoder. Hands-on use showed this made
comparing/tuning one track's several parameters clumsy (had to cycle
through pages) and made "which encoder does what" ambiguous. Landed on
two explicit, mutually exclusive modes instead:

- **Track mode** (a specific track selected, the default): the 8
  columns are **parameters** of that one track — column *N* = a fixed
  parameter, always. Encoder *N* edits it. All 8 live at once, no
  paging.
- **Main mode** (`Select (main)`, CC28 — chosen because it's the
  existing, already-mapped "Select (main)" button, not a new binding):
  the 8 columns are **tracks** again, all showing the *same* parameter.
  The jog wheel scrolls *which* parameter that is. Encoder *N* edits the
  *N*th visible track's value of it.
- The jog wheel **only** does this parameter-scrolling, and **only** in
  Main mode — an earlier iteration had it scroll track selection, which
  the user explicitly rejected once Screen-bottom buttons took over
  direct track selection (jog-for-tracks became redundant and confusing
  next to two other track-selection paths).
- Holding a step pad + turning any encoder always overrides to edit
  that exact step, in either mode, using whichever parameter the mode
  currently resolves to.

**Visual language.** Every track has one color, shared by its pad LEDs,
its bottom-strip label, and its column text. *(Superseded — `TRACK_COLORS`
started as the hardware "Vivid" row `[1, 9, 10, 13, 17, 21, 22, 25, 26]`
with yellow excluded, but is now a larger, hand-picked-on-hardware list
that includes yellow — the division pulse below moved to green instead.
New tracks also no longer walk that list 1-by-1: they stride through it
by `TRACK_COLOR_STEP` so neighboring tracks don't land on adjacent,
visually-similar entries. A Shift + Screen-bottom color-picker overlay
lets a track's color be set by hand from the pad grid. See `engine.py`'s
`TRACK_COLORS`/`TRACK_COLOR_STEP`/`color_picker_grid` and CLAUDE.md's
Colors section for the current state.)* Screen-bottom buttons are black
by default,
lighting only for the selected track, in that track's color — deliberate
"black = no track owns this" instead of a generic dim-gray for every
populated-but-unselected slot. The active time-division button pulses
between vivid green (10) and off (0) rather than a static color — real
analog LED brightness doesn't exist for buttons (fixed palette only), so
blinking between two entries is the practical stand-in for "pulsing."
Parameter values render at 2x via `Text`'s integer `scale` field — a
`styledtext`-based 1.5x was tried and explicitly rejected in favor of
staying on the standard bitmap font.

**v2 "simple" mod slice (superseded by the full mod lane below).**
Encoder column 8 ("Mod") was originally a per-step 0-127 value sent as
`send_cc(channel, mod_cc=1, value)` once when the *note* step triggered
— not an independent lane, riding the note lane's own length/division.
Replaced outright once the real mod lane shipped (see below); kept here
so the history isn't lost, not because any of it is still true. Column 7
("Pan") stays a reserved no-op.

**Full mod lane (v2.5).** Every track now has an independent mod lane:
its own `mod_length`, `mod_div`, and `mod_steps` (0-127 each), fully
decoupled from the note lane's length/division/steps — the originally
planned shape, not the v2 "rides the note step" stopgap above, which it
replaces (a step's old `mod` field is gone; nothing reads it anymore).
Firing is symmetric with the note lane: its own wall-clock and
external-clock advance path (`Engine.mod_step_duration`,
`_advance_mod_step`, `_trigger_mod_step`, `_mod_current_step`/
`_mod_ext_acc` per track), sending `send_cc(channel, mod_cc, value)`
whenever a mod step's value is > 0, independent of whether the note
lane is even playing anything at that instant.

Editing needed the pad grid, so it borrows it via an exclusive third
mode (`Engine.mod_lane_active`), alongside Track/Main mode:
- **Toggle**: `Screen top 8` (CC109) — a plain press/release toggle, not
  a hold. This button sits directly above the Mod column and was
  entirely unmanaged before (GridSeq only ever used the "Screen bottom"
  row). It was chosen only after ruling out touching/pressing encoder 8
  itself: Push's screen encoders have no click, only a capacitive touch
  event, and that touch fires on every normal turn (turning encoder 8
  to edit something else already touches it) — so a touch-based toggle
  on the encoder would collide with unrelated interaction. No such
  collision exists for a dedicated button.
- **Editing**: column *N* = the *N*th visible track's mod lane (keeps
  the pad grid's normal columns-are-tracks convention, per explicit
  user preference over "columns become steps"). Row = a bar-graph
  bucket (`MOD_BUCKETS`, 8 evenly-spaced values 0-127) for a single
  shared **cursor step** (`Engine.mod_cursor`) rather than a step page —
  since editing is "one step, all tracks at once," not "one track, many
  steps." `D-Pad left/right` move the cursor by 1 while the mode is
  active (a third meaning added to the same buttons Shift+D-Pad already
  reassigns for track length).
- **Mod division**: the Scene buttons (`1/4`…`1/32t`) set the selected
  track's `mod_div` instead of `div` while the mode is active, reusing
  the existing division-picker buttons rather than adding new ones.
- Track/Main mode, the 8 encoders, and the jog wheel are all inert while
  mod-lane mode is active (`handle_encoder` returns early) — column 8's
  Track/Main-mode page is now a status-only display of the selected
  track's `mod_div`, not an editable value; actual editing only happens
  through the overlay.

Deliberately **not built in this pass**: mod-lane length control from
the surface (`mod_length` is fixed at 8, exactly where note length
started before its own control shipped — same natural follow-up), and a
per-track `mod_cc` (still hardcoded to CC1 for every track, as before).

**Per-track step-length control.** `Shift` (the mod button, previously
declared in `engine.py`'s `mods` dict and wired in `run.py` but with no
gesture attached to it) + `D-Pad left`/`D-Pad right` shrinks/grows the
*selected* track's length by 8 steps (one D-Pad page) — floor 8, ceiling
`MAX_STEPS` (64). Chose 8-step increments over 1-step because D-Pad
paging is already in units of 8, so growth always lands exactly on a new
full page (no partial last page to special-case in the view). Growing
appends fresh `new_step()`s; shrinking truncates the tail (data loss on
the dropped steps, same as `load()`'s existing clamp-to-length
behavior) rather than hiding-and-restoring, since a hide/restore model
would need its own persisted "shadow" step list for no clear benefit at
v1 scope. `Engine.set_length()` also re-clamps `step_page` down if the
new length no longer has a page that far out. The D-Pad LEDs
(`view.button_colors`) switch meaning while `Shift` is held — dim/off
reflects room to shrink/grow instead of room to page — mirroring how
Page Left/Right's LEDs already signal "room to page."

**Scale quantization.** Landed at **trigger time only**, not on entry:
`Engine._scale_note` computes `root + offset` same as always, then
`Engine._quantize_to_scale` snaps that to the nearest pitch class in
`SCALES[scale]` (already existed, just wasn't consulted before) —
`chromatic` is special-cased to skip quantization entirely, since its
interval table is all 12 semitones and would be a no-op anyway. Chose
trigger-time over entry-time because it needed zero control-surface or
schema changes (the pitch encoder still edits a plain semitone offset,
exactly as before) and makes scale switching non-destructive — the
stored per-step offset never changes, only which absolute note it
resolves to, so flipping back to `chromatic` always recovers the exact
original offsets. Tie-breaking (a pitch class equidistant from two scale
degrees) resolves to whichever degree comes first in `SCALES[name]`'s
list order, i.e. the lower one — deterministic, not spelled out
anywhere on the surface, but not expected to matter in practice.

**UI pass: header removal, playhead direction, transient BPM, persistence
toggle.** Four small hardware-driven requests landed together:

- The header row (`{"kind":"header",...}`) is gone entirely — user
  feedback was that it mostly duplicated what the LEDs already show
  (BPM/sync/playing state aren't shown anywhere else now; mute/solo,
  division, and mode are still readable from LEDs alone) and cost screen
  space. Parameter names/values (what used to sit below the header) moved
  up to occupy the vacated top of the screen (`PARAM_LABEL_BASELINE`=16,
  `PARAM_VALUE_BASELINE`=46 in `view.py`, replacing the old 40/68). Track
  kind (`DRM`/`MEL`), previously only in the header's Track-mode status
  line, moved into the bottom-strip label (`"Track 1 (DRM)"`) so it isn't
  lost. Two readouts genuinely have nowhere to go now and aren't shown
  anywhere: the selected track's **scale name**, and external/internal
  **sync** status — both are silent regressions worth revisiting if they
  turn out to matter in practice, not fixed here since neither was asked
  for. The mod lane's cursor position (previously in the header's
  "MOD LANE - step N/L") was **not** left silent — it moved into each
  column's label prefix (`"S3 1/16"`) since losing cursor feedback
  entirely would have broken that mode's usability, not just its polish.
- **Playhead direction**: row 7 (physical top) is now the earliest step
  in a page, row 0 (bottom) the latest, inverted from v1's row-0-is-
  earliest — so the playhead reads top-to-bottom. This is purely a
  `run.py`/`view.py` display-and-input convention (`step_idx = page_base
  + (7 - row)` in both `handle_pad` and `pad_colors`); `engine.py`'s
  timing/trigger logic is untouched, since it only ever deals in logical
  step indices, never physical rows. The mod lane's bar-graph rows are
  unaffected on purpose — those rows are value buckets, not a step
  sequence, so "top to bottom" has no meaning there.
- **Transient BPM popup**: turning the Tempo wheel now shows a "TEMPO
  <value>" popup (`view.py`'s `TEMPO_DISPLAY_SECS` = 1.5s) that fades on
  its own — the only place BPM is visible now that the header's gone.
  Tracked via `State.last_tempo_change` (`time.monotonic()`, set in
  `run.py`'s `handle_encoder`), checked against the same clock in
  `view.draw`.
- **Persistence disabled**: `run.py`'s `PERSIST_ENABLED = False` skips
  both the `init`-time `store_get` and the `close`-time `store_set` (via
  an early return in `save_pattern`) — every session now starts from
  `engine.default_doc()`. Explicitly requested as temporary ("start
  fresh for now, don't remove the mechanism") — the call sites, and
  `Engine.load`/`to_doc`, are untouched, so re-enabling is flipping one
  constant back to `True`, not restoring deleted code.

**Controls pass: Channel replaces Pan, Mod-as-button, Stop Clips removed,
Mute/Solo regestured.** Four more small hardware-driven requests:

- **Pan → Channel.** Pan (column 7) was a permanent no-op with no
  concrete plan to ever implement it in this cycle; replaced outright
  with each track's MIDI output **channel** (1-16), via a new
  `Engine.set_channel(track_idx, delta)`. Channel is track-level, not
  per-step, unlike every other encoder-column parameter — so it's routed
  around `Engine.nudge_param`/`_nudge_step_param` entirely (those only
  know how to touch per-step step-dict fields or track-wide rescale-all-
  steps, neither of which fits a single scalar). `run.py`'s
  `handle_encoder` special-cases `param_name == "channel"` in both
  no-pad-held branches (Main mode and Track mode) to call `set_channel`
  directly, and explicitly excludes it in the held-pad branch (there's
  no per-step channel concept to target — same "inert while a pad's
  held" treatment `NOOP_PARAMS` gives "mod lane", just not lumped into
  that tuple since channel *is* live outside that one branch).
- **Mod-as-button.** The Mod column's status page (Track/Main mode, not
  the mod-lane editor overlay) used to show "n/a" as its value — there's
  no single number that represents a whole lane's worth of steps.
  Replaced with a plain colored rect + "Mod" label (`view._mod_button_ops`)
  instead of showing a fake/empty value. Still no real answer for
  visualizing the lane's actual content on this status page — deliberately
  deferred, tracked in "Open" below.
- **Stop Clips removed.** It duplicated `Play`'s stop behavior exactly
  (`e.stop()` either way) with no distinct function, so it's unbound:
  removed from `view.BUTTON_CC` (LED goes dark/unmanaged) and from
  `run.py`'s dispatch. `Engine.stop()` itself is untouched — `Play`
  still calls it via `toggle_play()`.
- **Mute/Solo regestured.** Previously: hold `Mute`/`Solo` + tap a *pad*
  in the track's column. In practice this was easy to reach for the
  wrong combination (`Mute`/`Solo` + the track's **Screen-bottom**
  button, not a pad) since Screen-bottom is already "the track" in every
  other gesture (selection). Switched to match: `handle_pad` no longer
  checks `e.mods["mute"]`/`["solo"]` at all (a pad tap while either is
  held now just toggles the step, same as with no modifier), and
  `handle_button`'s `SCREEN_BOTTOM` dispatch checks the mute/solo mods
  first, falling through to `select_track` only when neither is held.
  Paired with a visual cue: any track `Engine.track_audible()` says
  won't sound right now (explicitly muted, or silenced by another
  track's solo) renders **grey** — `view.INAUDIBLE_STEP` (palette 118,
  "gray_mid") for its on pad steps, `color("gray_mid")` for its
  bottom-strip label — instead of the old muted-only "dim red-ish"
  pad color (palette 61) that didn't cover the solo case and didn't
  touch the label at all. Reusing `track_audible()` (already the
  trigger-time gate in `_trigger_step`/`_trigger_mod_step`) means the
  grey-out is exactly "won't make sound," not a second hand-maintained
  condition that could drift from the real mute/solo logic.

**Controls pass 2: drum pitch, MIDI Channel label, Mod button sizing,
Screen top N → open mod lane, generic popup mechanism, and a held-pad
row-inversion bugfix.** Six items, one of them a real regression found
while implementing another:

- **Pitch in drum mode.** `_skip_pitch` (a v1 deliberate restriction —
  pitch only meant something for melodic tracks) is gone; `_trigger_step`
  now computes a drum note as `base_note + step["note"]`, clamped 0-127,
  **unquantized** — deliberately not routed through `_scale_note`, since
  a drum kit's notes each select a different sound, not a scale degree.
  This was asked for directly ("why can't I turn pitch in drum mode").
- **Held-pad row-inversion bug (found, not asked for).** While testing
  the drum-pitch fix, holding a pad and turning Pitch changed the *wrong*
  step's offset. Root cause: the previous session's playhead-direction
  change (`step_idx = page_base + (7 - row)`) landed in `handle_pad` and
  `pad_colors`, but `handle_encoder`'s held-pad branch still computed
  `held_step = page_base + hrow` — raw, uninverted. Every held-pad
  encoder edit (velocity, gate, repeat, probability, offset, pitch) had
  been landing on the mirror-image step since that change shipped, not
  just pitch — the user hit it via pitch first, but the fix
  (`held_step = page_base + (7 - hrow)`) applies to the whole path, not
  a pitch-specific patch. Worth remembering: a display convention that's
  encoded in more than one call site needs every call site checked when
  it changes, not just the obvious ones (pad tap and pad color were
  obvious; the held-pad encoder path wasn't touched by that commit and
  nothing caught it until manual testing here).
- **"Channel" → "MIDI Channel"** on screen only — `_PARAM_LABEL_OVERRIDES`
  in `view.py` maps the internal `ENCODER_PARAMS` name to its display
  label, since `_param_label`'s generic `split(" ")[0].capitalize()`
  can't produce a two-word label from a one-word internal name.
- **Mod button sizing.** `MOD_BUTTON_Y, MOD_BUTTON_H` changed from
  `4, 54` to `0, 18` — the exact footprint the removed header row used
  to occupy, "no taller" being the explicit ask. Added a "`>`" glyph at
  the button's right edge signaling there's another page (the mod-lane
  overlay) behind it.
- **Screen top N → open, not just toggle.** `Engine.open_mod_lane
  (track_idx)` replaces the old `toggle_mod_lane()` (deleted, no longer
  called from anywhere): selects that column's track and opens its mod
  lane, closing only on a second press for the *same* track (pressing a
  different track's Screen top button while the overlay's open jumps
  straight there instead of closing first). All 8 `Screen top N` buttons
  are wired now (`SCREEN_TOP` dict in `run.py`, mirroring `SCREEN_BOTTOM`)
  — previously only 8 was, and it only ever acted on whatever track
  happened to already be selected, not the column the button sits above.
  A side effect worth noting: `open_mod_lane` calls `select_track`,
  which always clears `main_selected` — so opening a mod lane from Main
  mode and later closing it lands back in Track mode, not Main mode.
  Not fixed, since it matches the existing "selecting a specific track
  always leaves Main mode" invariant everywhere else.
- **Generic popup mechanism.** `State.show_popup(title, body=None)`
  (`run.py`) replaces the Tempo-specific `last_tempo_change` field with
  `popup_title`/`popup_body`/`popup_until`; `view._popup_ops` renders a
  white box sized to fit whichever line is wider (title at `CHAR_W=7`px/
  char, body at `CHAR_W * VALUE_SCALE`), both lines centered using that
  same fixed-width math — `internal/renderframe`'s `basicfont.Face7x13`
  is confirmed monospace at 7px/glyph advance (scaled by the `Text` op's
  integer `scale`), so this centers exactly, not approximately, with no
  real font-metrics API needed. `Note` now calls `show_popup` with the
  track's name and its new kind, as a second example of the mechanism
  beyond Tempo — the explicit ask was "reusable for any button whose
  effect isn't visible," not "add it everywhere," so no other buttons
  got one in this pass.

**Pitch display pass: held-step exact value, note names for melodic.**
Two related on-screen-value asks, both about the same underlying
complaint — the lo..hi range shown for a parameter column is a fine
"shape at a glance" summary, but useless for figuring out the exact
value you're about to dial in while holding a pad.

- **Exact value while held.** `view._held_step(e)` computes
  `(track_idx, step_idx)` for the currently-held pad through the same
  row inversion as `handle_pad`/`handle_encoder` (`page_base + (7 -
  row)`) — centralized here so a fourth call site can't drift from the
  other three the way `handle_encoder`'s held-pad branch already did
  once this session. `_param_display_value` now takes an optional
  `held_step`: given one, it indexes that exact step's field instead of
  calling `_param_value`'s lo..hi aggregation. Applies to every
  per-step parameter (velocity, gate, repeat, probability, offset,
  pitch) in both Track mode (one `held_step` shared across all 8
  columns, since they're all the same track) and Main mode (only the
  column whose track matches the held pad's track narrows — the other
  7 keep showing their own ranges).
- **Note names for melodic pitch.** `Engine._trigger_step`'s inline
  drum/melodic note branch was pulled out into a new public
  `Engine.resolve_note(t, offset)` — public specifically so `view.py`
  could call the exact same resolution the trigger path uses, rather
  than reimplementing scale quantization a second time and risking the
  two disagreeing. `view._note_name(midi_note)` converts to scientific
  pitch notation (`octave = midi // 12 - 1`, so MIDI 60 = C4). Scoped to
  **melodic only**, per the explicit ask: a drum track's Pitch column
  still shows the raw offset number, since there each value selects a
  kit voice, not a scale degree — a note name would misrepresent what
  the value does, not clarify it. The range case (no pad held) resolves
  every step through `resolve_note` first, then takes the *note-name*
  lo..hi ("C4..E4") rather than the raw-offset lo..hi, so range and
  held-exact stay on the same footing (both show what will actually
  play, never the internal offset number, for melodic tracks).

**Follow-up fixes: Scale popup, Screen top N mode-scoping, pitch range.**
Three small corrections, one of them undoing part of what the controls
pass above had just shipped:

- **Scale popup.** `handle_encoder`'s `e.mods["scale"]` branch now calls
  `state.show_popup(t["name"], t["scale"].replace("_", " ").title())`
  after `cycle_scale` — but only when the track is actually melodic
  (`cycle_scale` itself no-ops on drum tracks, so popping up a scale
  name that has zero effect would be misleading, not informative).
- **Screen top N, mode-scoped.** The prior pass wired all 8 `Screen top
  N` buttons uniformly via `e.track_at(col)`, which resolves relative to
  `track_page` regardless of mode — harmless in Main mode (where every
  column really is a different track) but wrong in Track mode, where
  the 8 columns are *parameters* of one track, not 8 tracks. Pressing
  Screen top 1-7 there was opening the mod lane for whatever track
  happened to sit in that page column, unrelated to the one actually
  selected and showing on screen — reported as "pressing the buttons on
  top immediately enters the Mod page," which was true but for the
  wrong reason (it worked for *every* button, not just the one actually
  above a Mod button). Fixed by branching on `e.main_selected` in
  `run.py`'s `SCREEN_TOP` dispatch: Main mode keeps the old per-column
  behavior; Track mode only responds to `col == 7` (Screen top 8, the
  one really sitting above the Mod status button in that mode's layout)
  and always targets `e.selected_track` rather than `track_at(col)`.
- **Pitch range.** `_nudge_step_param`'s `"pitch"` clamp was `+/-24`
  around root — fine when root sits near the middle of 0-127, but with
  root anywhere else (via Octave Up/Down or a duplicated track) it made
  a real band of the 128 MIDI notes structurally unreachable, not just
  inconvenient to reach. Widened to `+/-127` (root + offset always
  spans the full 0-127 range from anywhere `root` can be) and switched
  from sign-only stepping (`+/-1` per tick, `"repeat"`'s treatment) to
  raw `delta` (`"velocity"`'s treatment) — a 255-value span at one
  semitone per tick would have made "reach any note" true in principle
  and useless in practice. `resolve_note`'s existing final clamp (0-127)
  is what actually bounds the resolved pitch; the step-level clamp only
  needs to be wide enough to reach every value that clamp allows.

**Note-name octave convention, D-Pad moved to up/down.** Two more
corrections from hands-on use:

- **Octave numbering.** `view._note_name`'s `octave = midi // 12 - 1`
  (scientific pitch notation, MIDI 60 = C4) was internally consistent
  but wrong for this module's actual context: Ableton Live numbers
  octaves its own way, MIDI 60 = C3, one lower than the SPN convention
  — and since GridSeq only exists to sit in front of Live, agreeing
  with Live's numbering matters more than agreeing with the more
  "standard" convention. Reported as "selecting C3 plays a C2" — not a
  display/audio mismatch (both were already computed from the same
  `resolve_note` call, so they could never disagree with each other),
  but a mismatch between GridSeq's chosen convention and the one the
  user was mentally comparing against. Changed to `octave = midi // 12
  - 2`, giving the full range as C-2 (MIDI 0) to G8 (MIDI 127) instead
  of the old C-1 to G9.
- **D-Pad up/down, not left/right.** Every D-Pad binding (step-page
  scrolling, Shift-held length, mod-lane cursor) moved from `D-Pad
  left`/`right` (CC 44/45) to `D-Pad up`/`down` (CC 46/47, confirmed
  against `core/push3.CCDPadUp`/`CCDPadDown`) — rationale: GridSeq's
  rows are the step timeline, read top-to-bottom (row 7 = earliest,
  playhead travels down), so a control that moves through that same
  timeline reads more naturally as up/down than left/right, which was
  really "horizontal" in name only. `D-Pad up` = backward/earlier (old
  `left`'s job: page back, shrink length, move mod cursor back);
  `D-Pad down` = forward/later (old `right`'s job). Applied uniformly
  to all three D-Pad behaviors, not just the one the ask named
  explicitly (page-scrolling and length), since leaving the mod-lane
  cursor on left/right while everything else moved to up/down would
  have made the D-Pad's meaning inconsistent depending on which mode
  was active — the same "a shared convention needs every call site
  updated together" lesson as the held-pad row-inversion bug earlier
  in this file. `D-Pad left`/`right` are simply unbound now, not
  repurposed for anything else.

**Drum/melodic removed.** v1's original design gave each track a
`kind` ("drum" or "melodic") that changed how a step's pitch offset
resolved: drum did `base_note + offset` unquantized (so the offset
picked a different kit voice per step, not a melodic interval); melodic
did `root + offset` quantized to the track's scale. This was a genuine
behavioral fork at the time — but two things this session shipped
independently made it redundant:

1. The pitch-range fix widened the reachable offset to `+/-127` (every
   MIDI note, from any root), so melodic tracks could already reach any
   note a drum track could.
2. `chromatic` (the default scale, and the one every existing track
   already had) applies **zero quantization** — `_quantize_to_scale`
   short-circuits for it. So a melodic track on `chromatic` already
   behaved *exactly* like the old drum path: pick any note, get exactly
   that note, no snapping.

Once both were true, "kind" wasn't gating any actual behavior anymore
for the common case — it only mattered if a track used a non-`chromatic`
scale, at which point "drum" tracks would ignore that scale entirely
(which was itself arguably a footgun: set a scale on a drum track by
mistake, wonder why it does nothing). The user noticed this convergence
directly ("does it make sense to have Drum and Melodic Sequencers?") and
asked to collapse to one always-quantized-by-scale model. Removed:
`t["kind"]`, `t["base_note"]`, `Engine.toggle_kind`, the `Note` button
binding and its kind-toggle popup, `view._kind_abbrev` and the bottom-
strip `(DRM)`/`(MEL)` suffix, and the kind checks in `resolve_note`,
`cycle_scale`, and `transpose_all_melodic` (renamed `transpose_all` — it
now genuinely applies to every track, not just melodic ones, so the
qualifier in the name would have been misleading). `resolve_note` and
the old private `_scale_note` collapsed into one function, since there
was no longer a second branch to keep them separate for. The one real
behavior change: a track using a non-`chromatic` scale for what used to
be drum-voice selection will now have its note choices quantized to
that scale, same as any other track — previously "drum" tracks ignored
scale entirely. Flagged to the user as the one tradeoff before
implementing; not considered a regression since scale defaults to
`chromatic` and nothing sets it otherwise without a deliberate `Scale`
+ encoder turn.

**Scale mode: hold-and-turn replaced with a dedicated toggle mode.**
`Scale` was a momentary modifier (hold + turn *any* encoder to cycle
scale) since v1. Replaced with a toggle: press `Scale` to enter a mode
where encoder 1 is **Key** (`Engine.cycle_key` — steps the selected
track's root by one pitch class, wrapping within its current octave,
new: octave itself never moves here, only Octave Up/Down does that) and
encoder 2 is **Scale** (`cycle_scale`, unchanged); the other 6 columns
render nothing (not stale Track-mode parameters) and every other
encoder no-ops (`handle_encoder`'s `e.scale_mode_active` branch returns
early for everything except `idx` 0/1) — mirrors how `mod_lane_active`
already makes its own overlay exclusive. Press `Scale` again to leave;
edits are live the whole time (no separate "apply," matching every
other control in GridSeq), so there was never anything to commit on
exit.

Gating: `Engine.toggle_scale_mode` refuses to turn **on** while
`main_selected` or `mod_lane_active` (both are "more than one track at
once" states; Scale mode is inherently "the one selected track", the
same reasoning `open_mod_lane`'s Track-mode `col == 7` restriction used)
— explicitly asked for ("Scale should be selectable only when a Track
is already selected"). Turning it **off** is always allowed regardless.
Kept the three overlay-ish modes (`main_selected`, `mod_lane_active`,
`scale_mode_active`) mutually exclusive defensively: `toggle_main` and
`open_mod_lane` both clear `scale_mode_active` when they activate,
rather than leaving it possible to have two of them "on" at once with
no defined visual precedence between them.

The old momentary `"scale"` entry in `Engine.mods` and its `run.py`
`mod_key` mapping are gone — nothing reads a held-Scale state anymore,
so keeping the dict entry around would have been dead state.

**Scale mode tuning: lower sensitivity, clamp instead of wrap.**
Immediate hands-on feedback on the mode above: the Key/Scale encoders
changed value on every relative-encoder message, which on real hardware
can mean every small wiggle (not just a deliberate detent) moves a
12-item or 6-item list — too twitchy. Fixed with a per-encoder
accumulator (`Engine._key_accum`/`_scale_accum`, both runtime-only, not
persisted) rather than just requiring a bigger `|delta|` per message:
`nudge_key`/`nudge_scale` add the raw delta in, then drain it in
`KNOB_ACCUM_THRESHOLD`-sized (4) chunks, calling `cycle_key`/
`cycle_scale` once per chunk — so a slow turn (many small-delta
messages) and a fast turn (fewer, larger-delta messages) both take
roughly the same *total* rotation to produce one step, rather than the
fast turn skipping multiple steps at once or the slow turn stepping on
every message. `toggle_scale_mode` zeroes both accumulators on entry so
a partial turn left over from a previous session (however unlikely
given they're never persisted) can't bias the first tick.

Second ask in the same message: **stop at the ends instead of wrapping**
— `cycle_key`/`cycle_scale` switched from modulo wrap-around to
`max(0, min(last_index, i +/- 1))` clamping. Applied to **both** knobs
even though a pitch class is circular in actual music theory (B -> C is
a completely ordinary move, unlike "the scale after the last scale"
which means nothing) — the ask said "the knobs" without carving Key
out as an exception, and clamping Key costs nothing real since Octave
Up/Down already covers reaching a different octave's C. Worth
remembering if a future session is asked to make Key wrap again: that
would be undoing a deliberate (if debatable) choice to follow the
literal ask over the more "correct" music-theory default, not a bug fix.

**Jog wheel clamp, four more throttled encoders, Screen top LED
rework — and a real dispatch bug found in the process.** Four asks in
one message:

1. **Jog wheel clamps in Main mode.** Same one-line change as Key/Scale
   and now this: `e.current_param = max(0, min(len(ENCODER_PARAMS)-1,
   e.current_param + step))` instead of `% len(...)`. Third and last
   place this "stop at the ends" pattern has landed.
2. **Pitch, Offset, Repeat, MIDI Channel throttled.** Generalized the
   Key/Scale accumulator technique rather than inventing a second one:
   `Engine.THROTTLED_PARAMS = ("pitch", "offset", "repeat")` gates the
   top of `nudge_param` — accumulate delta in `self._param_accum[param]`
   (keyed by param name, shared across whichever track/step is being
   edited, same as Key/Scale's accumulators aren't per-track either),
   drain in `KNOB_ACCUM_THRESHOLD`-sized chunks, and only call
   `_nudge_step_param` with the drained integer step count — zero steps
   drained means an early return, no-op. Channel doesn't route through
   `nudge_param` (it's track-level, not per-step) so it got its own
   `nudge_channel` wrapping the existing `set_channel` the same way
   `nudge_key` wraps `cycle_key`. Velocity/Gate/Probability were
   deliberately left alone — continuous-feeling ranges where fast
   per-message response is the point, unlike a 12-note pitch class or a
   1-16 channel count. `run.py`'s two `e.set_channel(...)` call sites
   became `e.nudge_channel(...)`; `set_channel` itself is unchanged
   (still the "apply exactly one step" primitive, just no longer called
   directly from input handling).
3. **Screen top LEDs: off by default, colored only above a real Mod
   button.** Previously every "Screen top N" button sat at a blanket
   dim/full regardless of whether anything was actually rendered above
   it — in Track mode, that meant 7 of 8 lighting up for buttons that
   do nothing (1-7 only work in Main mode or once the overlay's already
   open). Rewired `view.button_colors` to compute, per mode, whether
   that column currently shows a Mod button at all (Track mode: only
   column 8, using the *selected* track's color, since Track mode's Mod
   button is always for the selected track regardless of which track
   object happens to sit in that page column; Main mode: whichever
   columns have jogged to the "mod lane" parameter, each in its own
   track's color) and only lights when it does — `BTN_OFF` otherwise,
   matching the Screen-bottom row's existing "off = nothing here"
   convention rather than `Select (main)`'s generic dim/full toggle
   look.
4. **The open track's button turns bright red (`MOD_LANE_OPEN`, palette
   127 "pure_red") to signal "click to exit."** Implementing this
   exposed a real bug in the Track-mode-gating dispatch from two
   sessions ago: `SCREEN_TOP` dispatch checked `e.main_selected` to
   decide whether a pressed column maps to "that column's track" or is
   gated to column-8-only — but `select_track` (called by
   `open_mod_lane` on every open) always clears `main_selected`, so the
   instant *any* mod lane opened, `main_selected` became `False` and
   stayed that way for as long as the overlay was open, regardless of
   whether it was opened from Track mode or Main mode. Net effect:
   once open, **only** `Screen top 8` could ever close it — pressing
   the button for the actually-open track (if it wasn't column 8) did
   nothing. Not something the ask surfaced directly, but unavoidable
   once "highlight the button that closes it" needed to be *true*: if
   the highlighted button didn't actually close it, the red LED would
   have been a lie. Fixed by gating on `e.mod_lane_active or
   e.main_selected` instead of `e.main_selected` alone — Track-mode-only
   gating (`col == 7`) now applies exclusively to *entering* the
   overlay from Track mode; once inside, every column behaves
   identically regardless of entry mode (press the open track's button
   to close, any other to jump straight to that track), which is also
   exactly what makes the red-LED-is-the-close-button promise actually
   hold.

**Controls pass 3: Add replaces Duplicate, file-based named sequences
(Save/Set), Delete+touch param reset.** Three more hardware-driven
requests:

- **`Duplicate` (CC88) → `Add` (CC32).** Pure rebind to the correctly-
  named physical button — `Engine.add_track(duplicate_from=...)` and its
  "copy the selected track" behavior are unchanged, only which button
  and which `view.BUTTON_CC`/`handle_button` name reach it.
- **Save/Set named sequences.** A second, independent persistence path
  from the host's `store_get`/`store_set` single-doc slot (which stays
  disabled, `PERSIST_ENABLED = False`): `Save` (CC82) writes
  `Engine.to_doc()` straight to a JSON file in this module's own
  `sequences/` directory (gitignored — user data, not source), named
  after `State.active_sequence_name` (auto-assigned "Sequence N" the
  first time, since there's no text entry on this hardware to name it by
  hand). `Set` (CC80) toggles a full-screen browser overlay
  (`view._sequence_browser_ops`) listing "New" plus every saved name,
  exclusive over the grid/other encoders/Tempo the same way the mod-lane
  overlay is (`State.sequence_browser_active`, checked first in
  `handle_pad`/`handle_encoder`, and in `view.pad_colors`/`draw`). Jog
  wheel or D-Pad up/down scroll `State.sequence_cursor`; **Jog press
  (CC94) or D-Pad center (CC91)** confirm — chosen over a plain pad tap
  or live-apply-while-scrolling specifically because those two already
  exist as unbound momentary buttons and a hardware "click to confirm"
  gesture reads more intentional than a pad tap or a scroll that
  silently discards the current unsaved pattern the instant you scroll
  past it. `Engine.enter_sequence(doc)` (doc=None for "New") resets
  navigation/overlay state too (`track_page`, `selected_track`, which
  mode was open), not just pattern data, and stops playback first so the
  outgoing pattern's notes don't hang. This is deliberately *not* the
  `{slots, chain}` v3 schema change described under "Pattern slots" below
  — it's files-on-disk, switched by a full engine-state swap, with no
  chaining/song-position concept at all; that harder design is still
  open.
- **Delete + touch encoder = reset to default.** `Delete` (CC118, a
  held modifier like `Shift`) + touching (not turning — a bare touch
  already fires on every normal turn, so touch-as-trigger needs a
  modifier held, same reasoning the mod-lane toggle button's own design
  note gives for not using an encoder touch there) a screen encoder
  resets that encoder's current parameter to `new_step()`'s (or
  `new_track()`'s, for Channel) default value, via a new
  `Engine.reset_param`. Wired through the wire protocol's `"touch"`
  event kind (`Touch{Name, Touched}`, e.g. `"Encoder 3 touch"`) — unused
  by GridSeq before this, since nothing needed encoder-touch data on its
  own until a modifier-gated reset needed it. No-ops in Scale mode, the
  mod-lane overlay, and the sequence browser, and for "mod lane" (a
  status page, not an editable value) — same set of "nothing sensible to
  target" exclusions `handle_encoder`'s own branches already use.

## Open / not built

**Mod status page visualization.** The Mod column (Track/Main mode) is
currently just a colored button with no data on it — a placeholder from
the controls pass above, not a real answer. Needs its own design pass
once there's a concrete idea (e.g. a mini bar-graph preview of the mod
lane's current shape, or its `mod_length`/`mod_div` at a glance) — same
"don't build UI blind" lesson the mod-lane editor itself already went
through.

**Pattern slots / song chaining (v3).** A simple chain
(next-slot-on-repeat-count, OXI-Arranger-lite) per the original plan —
still open even though "multiple saved patterns" itself shipped via the
file-based Save/Set sequences above (controls pass 3). Chaining needs
slots live *in the running doc* with song-position state, which the
file-swap approach deliberately doesn't have — still the biggest
remaining schema change (`Store` grows from one `Pattern` to `{slots,
chain}`) and should land once, not iteratively.

## Decisions considered and rejected (so they aren't re-litigated)

- Yellow was the first pulsing-division color choice; user asked for
  vivid green + off instead. Yellow (index 7) stays reserved/excluded
  from the track-color pool so it never gets confused with anything
  division-related in the future.
- `styledtext` (antialiased, arbitrary point size) was used for the
  bigger value text first, to hit an exact 1.5x. Rejected in favor of
  `Text`'s integer `scale` (2x) to keep everything on the one standard
  bitmap font.
- Per-column duplicate "Track N" labels (one repeated per parameter
  column) were removed once the bottom strip took over track
  identification — showing kind/division/mute/solo once (in the header,
  for the selected track) replaced 8x redundant copies.
