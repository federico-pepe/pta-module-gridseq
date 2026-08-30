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
accent. Drum or melodic per-track kind. Per-track time division (the 8
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

**Visual language.** Every track has one color from the hardware's
"Vivid" palette row only (`docs/push3-led-colors.md` upstream in
ableton-push-hack — indices `[1, 9, 10, 13, 17, 21, 22, 25, 26]`, yellow
excluded on purpose, see below) shared by its pad LEDs, its bottom-strip
label, and its column text. Screen-bottom buttons are black by default,
lighting only for the selected track, in that track's color — deliberate
"black = no track owns this" instead of a generic dim-gray for every
populated-but-unselected slot. The active time-division button pulses
between vivid green (10) and off (0) rather than a static color — real
analog LED brightness doesn't exist for buttons (fixed palette only), so
blinking between two entries is the practical stand-in for "pulsing."
Parameter values render at 2x via `Text`'s integer `scale` field — a
`styledtext`-based 1.5x was tried and explicitly rejected in favor of
staying on the standard bitmap font.

**v2 "simple" mod slice.** Encoder column 8 ("Mod") is a real per-step
0-127 value, sent as `send_cc(channel, mod_cc=1, value)` once when that
step triggers. This is deliberately **not** the originally-planned
independent mod lane — see "Open: full mod lane" below for why and what
a real one would need. Column 7 ("Pan") stays a reserved no-op.

## Open / not built

**Full mod lane (v2.5/v3 candidate).** The original plan called for a
decoupled lane: its own length and time division, independent of the
note steps, with a dedicated grid-editing overlay (hold a button, pads
become a bar-graph column editor — OXI's approach). Deferred because the
8x8 grid has no spare surface for a second independent lane without
borrowing the pad grid temporarily, and that borrowing needs its own
interaction design (what does holding a step pad mean while the grid is
in "mod-lane edit" mode? does Track/Main mode still apply?) rather than
slotting into the existing parameter model the way "Mod rides the note
step" did. Needs a design pass before implementation, not just an
engine change — candidate follow-up: prototype the overlay concept in
isolation (maybe as a scratch scene, similar to how `cmd/screensim`
lets push-tethered-app iterate on a widget without hardware) before
wiring it into GridSeq's event handling.

**Scale quantization.** `scale` is stored and shown per melodic track
but doesn't quantize pitch input yet — `pitch` is a plain semitone
offset from root. Real quantization needs an interval table per scale
(GridSeq doesn't have one yet) and a decision on where quantization
happens (as steps are entered vs. only at trigger time).

**Per-track step-length control.** Every track is fixed at 8 steps in
v1; the data model already supports up to 64 (`length`/`steps` fields),
and `D-Pad left/right` already scroll a step-page window — but there's
no control yet to actually lengthen a track past 8, so that D-Pad
scrolling has nowhere to go on a fresh track. Needs a control surface
decision (which button/gesture sets length) before it's wired up.

**Pattern slots / song chaining (v3).** Multiple saved pattern slots
and a simple chain (next-slot-on-repeat-count, OXI-Arranger-lite) per
the original plan. Deferred until the above are settled, since it's the
biggest remaining schema change (`Store` grows from one `Pattern` to
`{slots, chain}`) and should land once, not iteratively.

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
