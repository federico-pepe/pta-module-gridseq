# CLAUDE.md

Guidance for Claude Code in this repository.

> **Doc sync rule:** Update this file, `README.md`, and `MANUAL.md` when a
> change matters to a future reader — new control-scheme behavior, a
> changed button/encoder mapping, a new persisted field, a resolved or
> newly found limitation. Put the update in the same commit as the code
> change. Skip it for pure refactors with no user-visible effect.
>
> **Plans live in `plans/`**, one file per plan, named
> `YYYY-MM-DD-name-of-the-plan.md` — same convention as
> `push-tethered-app`'s own `plans/` directory. A plan holds intent,
> rationale, and open decisions; it stays as a reasoning trail even
> after its settled parts get folded into `README.md`/`MANUAL.md`. Don't
> delete a plan file once a phase ships — update its "what shipped" /
> "open" split instead.

## Project

GridSeq is a step sequencer module for `push-tethered-app` (a
cross-platform host that owns an Ableton Push 2/3 in tethered mode). It
is a **process-loaded module**: an independent Python program the host
spawns and talks to over newline-delimited JSON on stdin/stdout — not
Go code living inside the host's repo. This repo has no dependency on
`push-tethered-app` beyond that protocol; it is developed and versioned
separately, installed into a user's `pushapp` via
`pushapp -install /path/to/this/repo`.

Design intent: not a port of anything, a sequencer built for Push's
actual hardware (8x8 pad grid, 8 encoders, jog wheel, no CV/gate, no
analog clock) — see [plans/2026-08-30-gridseq-roadmap.md](plans/2026-08-30-gridseq-roadmap.md)
for the full reasoning trail, what shipped, and what's still open.

## Read this first

- [MANUAL.md](MANUAL.md) — end-user control mapping: every button/pad/
  encoder, the button-LED legend, Track mode vs Main mode
- [README.md](README.md) — install steps, shipped-vs-planned summary
- [plans/](plans/) — design history and open decisions, newest-dated
  file per topic is authoritative for "what's still undecided"

## Layout

```
manifest.json   module id/version/exec, needs_midi_out, needs_midi_in
run.py          protocol loop: reads stdin, dispatches events, writes responses/notifications
engine.py       the sequencer model (Track/Step/Pattern, timing, trigger logic) — no I/O
view.py         builds each frame's screen ops + pad/button LED colors — no I/O
palette.json    generated file, DO NOT hand-edit — see "Colors" below
plans/          design plans, see the doc-sync rule above
```

`run.py` is the only file that touches stdin/stdout. `engine.py` is the
only file with sequencer state and timing logic — it takes plain
callbacks (`send_note`, `note_off`, `send_cc`, `log`) from `run.py` so it
never imports `json`/`sys` itself. `view.py` reads `engine.py`'s state
and returns plain dicts (op lists, color maps); it never mutates engine
state. Keep this split when adding features — it's what makes the
protocol loop, the sequencer logic, and the rendering independently
testable.

## The wire protocol (what `run.py` implements)

Full spec: `push-tethered-app`'s
`docs/architecture/process-modules.md` and
`docs/guides/writing-a-process-module.md` (that repo is the protocol's
source of truth; this repo does not vendor a copy — check there if the
shape of an op or event ever looks wrong).

Quick facts that have bitten this repo before:
- **Flush stdout after every write.** Python buffers stdout when it's a
  pipe; skipping the flush makes the host hang on the first `draw`.
- Outgoing calls are either **notifications** (`set_pad`, `set_button`,
  `log` — no `id`, no reply) or **requests** (`send_cc`, `send_note`,
  `note_off`, `store_get`, `store_set` — carry an `id`, host replies on
  its own line later, asynchronously). Never block waiting for a reply;
  match responses by `id` in the main loop instead (see `run.py`'s
  `handle_response`).
- `set_button`'s wire field is named `"brightness"` (a legacy name — the
  value is a palette **index**, same mechanism as `set_pad`'s
  `"colour"`, not an actual brightness/PWM value).
- `ExternalMIDI`/`external_midi` data arrives as **base64**, not a
  number array (`base64.b64decode(data["raw"])`) — this is how Go's
  `encoding/json` encodes a `[]byte` field.
- No `image` op is available over this IPC. Every other op
  (`rect`/`text`/`header`/`statusbar`/etc.) mirrors the host's Go
  `internal/module.Frame` methods field-for-field.
- `Text`'s `"scale"` is an **integer** block-multiplier (1x, 2x, 3x…),
  not a point size. For a font-size change that isn't a whole multiple,
  the real answer here was "don't" — `styledtext` (arbitrary point size,
  a different antialiased face) was tried and explicitly rejected in
  favor of staying on the one standard bitmap font. Don't reintroduce
  `styledtext` for value/label text without checking
  `plans/2026-08-30-gridseq-roadmap.md`'s "considered and rejected"
  section first.

## Colors

`palette.json` is generated from `push-tethered-app`'s
`core/push3.Palette` via `go run ./cmd/genpalette` (run from *that*
repo, then copy the output into this repo's root — see that repo's
`docs/guides/writing-a-process-module.md#colors`). It resolves every
0-127 hardware index to `{index, name, r, g, b, a}`, both `byName` and
`byIndex`. Regenerate only if that repo's `core/push3.Palette` itself
changes (rare, it's a fixed SysEx-sourced table) — this file is checked
in, not rebuilt on every run.

- **Pad and button LEDs** (`set_pad`/`set_button`) want a raw palette
  **index** (0-127), never RGB.
- **Screen ops** (`text`, `rect`, `header`, …) want the resolved
  `{"R","G","B","A"}` dict — look it up via `view.color(name)` or
  `view.color_by_index(idx)`, never hand-copy an RGB literal.
- Track colors (`TRACK_COLORS` in `engine.py`) are a hand-picked list,
  not a mechanical palette-row slice — chosen and ordered from real
  Push hardware tests for what reads clearly and stays distinct on the
  small pad LEDs. Don't reorder or regenerate that list without
  re-testing on hardware. Yellow (index 7) is included: the pulsing
  active-time-division indicator (`DIV_ACTIVE_HI`/`DIV_ACTIVE_LO` in
  `view.py`) uses green, not yellow, so there's no clash to avoid.
- New tracks walk `TRACK_COLORS` with a stride (`TRACK_COLOR_STEP`, see
  `engine.py`) instead of `index % len(...)`, so adjacent *tracks* don't
  get adjacent (often visually similar) list entries. Keep the stride
  coprime with `len(TRACK_COLORS)` if either changes, so every track up
  to `MAX_TRACKS` still gets a color no other track has.
- The color-picker overlay (`Engine.enter_color_picker`, Shift +
  Screen-bottom) paints `TRACK_COLORS` straight, in list order, around
  the grid's border pads (`COLOR_PICKER_BORDER`/`color_picker_grid` in
  `engine.py`) — unrelated to the stride above, since a human is picking
  visually here rather than needing adjacent-track separation.

## Testing without hardware

There is no Push-hardware-free simulator in this repo (unlike
`push-tethered-app`'s Go-only `cmd/screensim`) — a process module's
protocol loop is trivial to drive directly instead. The pattern used
throughout this repo's history, and the one to reach for first:

```python
import json, subprocess, time
p = subprocess.Popen(["python3", "run.py"], stdin=subprocess.PIPE,
                      stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                      text=True, bufsize=1)
def send(o): p.stdin.write(json.dumps(o) + "\n"); p.stdin.flush()
# ... send {"id":1,"method":"init","params":{}}, then read exactly two
# lines (the init response, then the store_get request run.py always
# sends right after — in that fixed order, since respond() runs before
# the follow-up request) ...
```

Notes from experience:
- `init`'s response and its follow-up `store_get` request are two
  separate lines, always in that order — read both explicitly rather
  than looping "until id==1 matches," which returns after the first
  line and leaves the second unread.
- A `draw` request always gets a response, but any number of
  `set_pad`/`set_button`/`send_cc`/`log` notifications may arrive
  *before* it in the same batch (both LED relights are diffed against
  the previous frame, so they're silent when nothing changed) — drain
  and collect lines until you see the matching `id`, don't assume the
  very next line is the response.
- An open-ended `while True: readline()` with no per-call timeout can
  hang the test itself if a line never arrives (e.g. waiting on a
  notification that a diff suppressed). Bound every read with a
  wall-clock timeout.
- No shell `timeout` command on macOS by default — bound Python loops
  with `time.time()` deadlines instead of relying on it.

## Install / run (against a local `push-tethered-app` checkout)

```bash
go run ./cmd/pushapp -install /path/to/this/repo
go run ./cmd/pushapp -module gridseq
```

Requires `python3` on PATH, stdlib only (no pip install). Real hardware
testing needs Live closed (or Push's User Mode engaged) per
`push-tethered-app`'s own hardware safety rules — this repo has no
special additional hardware precautions beyond what that repo's
`CLAUDE.md` already documents for any module.
