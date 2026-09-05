# Mod Track redesign

## Status

Shipped (this file's own commit). Supersedes the old per-track "mod lane"
bolt-on described in `2026-08-30-gridseq-roadmap.md`.

## Context

The old mod lane was a second, hidden step lane bolted onto every track:
own length/division/step array, edited through a grid overlay, always
tied to that track's own MIDI channel, and always sending CC1. It had no
per-track CC choice, no way to modulate a sequencer parameter directly
(only outboard gear via CC), and needing to "open" a lane before editing
it added a mode most people forgot how to reach.

Rethought as: Tracks generate MIDI, Mod Tracks generate modulation. Both
are the same step-sequencer object — own column, own grid, own
length/division — GridSeq just plays one kind's steps as notes and the
other kind's steps as a modulation source. A Mod Track's output goes
either external (a MIDI CC, freely chosen) or internal (offsets a
chosen parameter on a chosen MIDI track, live, every time that track's
step fires).

## What shipped

- `Track.kind`: `"midi"` or `"mod"`. Both live in the same 16-slot pool
  (`MAX_TRACKS`). A track is structurally the same dict either way —
  `kind` just changes how `_trigger_step` and the UI interpret it.
- `Engine.view_kind` (`"midi"`/`"mod"`): a global browsing filter, not a
  per-track flag. The 8 grid columns, Screen-bottom track-select, and
  Page Left/Right all show only tracks whose `kind` matches
  `view_kind` — `Engine.track_at`/`visible_track_indices` do the
  filtering, so every existing call site got this for free. The new
  **Note button (CC 50)** toggles it (`Engine.toggle_view_kind`).
  Pressing Add while in Mod view creates a Mod track; while in Track
  view, a MIDI track.
- Mod Track fields (`new_track`): `mod_mode` (`"seq"`/`"lfo"`),
  `mod_amount` (0-127 depth), `mod_dest_type` (`"external"`/
  `"internal"`), `mod_cc` (now genuinely per-track, fixing the old
  hardcoded CC1), `mod_dest_track`/`mod_dest_param` (internal routing),
  `mod_lfo_shape` (`"triangle"`/`"sine"`/`"saw"`/`"square"`),
  `mod_combine` (`"offset_additive"` — the only mode that ships, kept as
  an explicit field/dispatch point so a future mode is a new value, not
  a rewrite).
- **Seq mode**: plays its own grid like a note track, but a step's `on`
  writes `vel` (0-127) as the new held output value instead of firing a
  note; `off` steps hold the previous value.
- **LFO mode**: free-runs a waveform (shape-selectable) at a rate tied
  to the track's own `div` (the existing Scene-button picker — no new
  "Rate" control needed, `div` already means "how often does this
  track's clock tick"). A step's `on` retriggers (resets) the LFO phase
  at that grid position; `off` steps do nothing.
- **External** output: sends `send_cc(channel, mod_cc, value)`. LFO
  tracks stream continuously (once per tick, only when the value
  actually changed, to avoid flooding identical CCs). Seq tracks send on
  each `on` step, same as before.
- **Internal** routing: a MIDI track's step-trigger reads any Mod
  track(s) targeting (its index, that parameter) and adds their scaled
  output as an offset, clamped to the parameter's valid range, before
  the step's own probability roll / note-on. Multiple Mod tracks routed
  to the same track+param sum.
- Destination picking is **inline**, not a separate overlay: two of the
  Mod-track page's own 8 encoder columns are "dest track" / "dest
  param" (or "CC" / "channel" when `mod_dest_type` is external) — no
  new overlay-entry gesture to learn, consistent with "a Mod track's
  page behaves like Track mode already does."
- Removed entirely: `mod_cc`/`mod_length`/`mod_div`/`mod_steps` fields,
  the mod-lane grid overlay (`mod_lane_active`, `mod_cursor`,
  `open_mod_lane`, `set_mod_value`, `set_mod_division`,
  `mod_lane_pad_colors`), the "Mod" status tile in `ENCODER_PARAMS`, and
  the Screen-top-button mod-lane-open wiring. Screen top buttons are
  unmapped/dark for now (see Open, below).
- `ENCODER_PARAMS` (MIDI tracks) drops to 7 entries (no replacement for
  the freed 8th slot yet — the 8th encoder is simply inert on a MIDI
  track).

## Migration

Old saved docs have `mod_cc`/`mod_length`/`mod_div`/`mod_steps` on every
track and no `kind` field. `load()`'s generic key-filter update
(`new_track(i)` then `t.update({k:v for k,v in saved.items() if k in
t...})`) makes this automatically safe: `kind` isn't in the old saved
dict, so it keeps `new_track`'s default (`"midi"`); the four stale
`mod_*` keys aren't in the new `new_track()` shape, so they're silently
dropped. No explicit migration code needed. (`sequences/` is empty in
this repo today, so this is a reasoned guarantee, not something tested
against real fixtures.)

## Follow-up tuning (shipped same day)

- A fresh pattern starts with 8 MIDI tracks **and** 8 Mod tracks, not 0.
  New Mod tracks (default or via Add) get a white default color
  (`MOD_TRACK_DEFAULT_COLOR`) and name themselves "MOD 1", "MOD 2", ...
- Mode and Dest columns clamp at either end instead of wrapping —
  matches Key/Scale's existing "stop at the ends" convention.
- Amount is 0-100, not 0-127 (`MOD_PARAM_RANGE["amount"]`, `nudge_mod_amount`).
- Internal destination can target any other track, MIDI or Mod
  (`cycle_mod_dest_track`) — a Mod track cannot target itself. Which
  param list applies depends on the destination's kind
  (`_mod_dest_param_options`): `MOD_DEST_PARAMS` for a MIDI dest,
  `MOD_DEST_PARAMS_MOD` (currently just `"amount"`) for a Mod dest.
  `_effective_mod_amount` applies this one level deep (for a track's own
  external CC output) without recursing, so a mutual Amount<->Amount
  routing between two Mod tracks cannot loop forever.

## Bug fix (shipped same day)

`_trigger_step` early-returned on an "off" step before even checking
`t["kind"]`, so a Mod track in "seq" mode never got a chance to zero its
held value on an "off" step — once any "on" step fired, that value kept
applying to an internal destination forever, since off steps were
skipped entirely rather than actively zeroing `_mod_seq_value`. Fixed by
moving the `kind == "mod"` branch in `_trigger_step` before the
`step["on"]` check, and making `_trigger_mod_track_step` run on every
step (on or off) — "seq" mode now sets `_mod_seq_value` to the step's
`vel` on an "on" step and to `0` on an "off" step, so an unmodulated
destination reads as fully unmodulated the instant the mod step turns
off, not "still holding the last value someone set."

## Delete + track button (shipped same day)

`Engine.remove_track(track_idx)` deletes a track (MIDI or Mod), wired to
Delete (hold) + a Screen-bottom button in `run.py`. Refuses to remove
the last track in the whole pool. Every other Mod track's
`mod_dest_track` is reindexed to follow the shift, or cleared to `None`
if it pointed at the removed track.

## Open

- Freed 8th `ENCODER_PARAMS` slot on MIDI tracks: shipped blank. No
  obvious per-step MIDI parameter was missing before mod lane's removal.
- Screen top buttons: dark for now. Their only past job (opening the
  mod lane) is gone; no replacement job assigned yet.
- Retrigger / offset / phase for Mod tracks: explicitly deferred, per
  the original request. `mod_combine` and the reserved (no-op) 7th/8th
  Mod-track encoder columns leave room to add them without a rework.
- Delete+touch reset-to-default doesn't yet cover Mod-track params
  (only MIDI ENCODER_PARAMS are wired to `reset_param`) — low priority,
  add if it's missed in practice.
