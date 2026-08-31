#!/usr/bin/env python3
"""run.py — GridSeq protocol loop.

Same envelope shape as every process module in this app (see
push-tethered-app/examples/modules/hello-py's run.py docstring for the full
wire format). This file only does I/O + event dispatch; the sequencer model
lives in engine.py, the screen/pad-color rendering in view.py.

Outgoing calls come in two shapes (see docs/architecture/process-modules.md's
method table): pure notifications (set_pad, set_button, log — no id, no
reply expected) and requests (send_cc, send_note, note_off, store_get,
store_set — carry an id, host replies on its own line later). This module
never blocks waiting for a reply; incoming response lines are matched
against a small pending-request table and applied whenever they arrive.

Pad and button LEDs are relit once per "draw" call (diffed against the last
frame, so an unchanged grid/button set costs nothing) rather than after
every individual handler — draw is called continuously (30-60fps) by the
host, so this is at most one frame of latency and it means every state
change, wherever it happens, is guaranteed to reach the LEDs without having
to remember to call relight_* at every call site.
"""

import base64
import copy
import json
import sys
import time

import engine as eng
import view

# Persistence is temporarily disabled: every module start begins from a
# fresh default pattern, and nothing is written to the host's store on
# close. The store_get/store_set call sites are kept intact (just
# unreached) so re-enabling this later is a one-line flip, not a rewrite.
PERSIST_ENABLED = False


def send(obj):
    sys.stdout.write(json.dumps(obj) + "\n")
    sys.stdout.flush()  # not optional — see hello-py's docstring


def respond(id_, result):
    if id_ is None:
        return
    send({"id": id_, "result": result})


def respond_error(id_, message):
    send({"id": id_, "error": message})


def notify(method, params):
    send({"method": method, "params": params})


def pad_note(col, row):
    """Mirrors core/push3.PadNote: note 36 is bottom-left, ascending
    left-to-right then bottom-to-top."""
    return 36 + row * 8 + col


class State:
    def __init__(self):
        self.engine = eng.Engine(send_note=self.send_note, note_off=self.note_off, send_cc=self.send_cc, log=self.log)
        self.undo_snapshot = None
        self.last_pad_colors = None
        self.last_button_colors = None
        self.button_held = {}  # button name -> currently pressed, for momentary LED feedback
        self.popup_title = None    # generic transient popup — see show_popup
        self.popup_body = None
        self.popup_until = 0.0     # time.monotonic() deadline; popup shows while now < this
        self._next_id = 1000
        self._pending = {}  # request id -> tag string, for responses we care about

    POPUP_DURATION = 1.5  # seconds a popup stays up after show_popup

    def show_popup(self, title, body=None):
        """A transient on-screen popup for a button/knob whose effect
        isn't otherwise visible (BPM after a Tempo turn, a track's kind
        after Note toggles it, ...). `title` is the small top line,
        `body` (optional) the bigger line below it — see view._popup_ops."""
        self.popup_title = title
        self.popup_body = body
        self.popup_until = time.monotonic() + State.POPUP_DURATION

    def request(self, method, params, tag=None):
        self._next_id += 1
        rid = self._next_id
        if tag:
            self._pending[rid] = tag
        send({"id": rid, "method": method, "params": params})
        return rid

    # host calls, wired into the engine so engine.py stays I/O-free
    def send_note(self, ch, note, vel):
        self.request("send_note", {"ch": ch, "note": note, "vel": vel})

    def note_off(self, ch, note):
        self.request("note_off", {"ch": ch, "note": note})

    def send_cc(self, ch, cc, val):
        self.request("send_cc", {"ch": ch, "cc": cc, "val": val})

    def log(self, message):
        notify("log", {"message": message})


def relight_grid(state):
    """Full redraw of the 8x8 pad LEDs — same "redraw, don't diff" choice
    beatcount-py makes, for the same reason: correctness over message count,
    and 64 notifications is cheap. Diffed against the last frame so a
    steady-state grid costs nothing."""
    grid = view.pad_colors(state)
    if grid == state.last_pad_colors:
        return
    state.last_pad_colors = copy.deepcopy(grid)
    for row in range(8):
        for col in range(8):
            notify("set_pad", {"note": pad_note(col, row), "colour": grid[row][col]})


def relight_buttons(state):
    """Full redraw of every managed button LED, same diffed-redraw choice as
    relight_grid. Wire field is "brightness" (see
    docs/architecture/process-modules.md's method table); the value is a
    palette index, same mechanism as set_pad's "colour"."""
    colors = view.button_colors(state)
    if colors == state.last_button_colors:
        return
    state.last_button_colors = dict(colors)
    for name, idx in colors.items():
        cc = view.BUTTON_CC.get(name)
        if cc is not None:
            notify("set_button", {"cc": cc, "brightness": idx})


def snapshot_for_undo(state):
    state.undo_snapshot = copy.deepcopy(state.engine.to_doc())


def handle_pad(state, data):
    e = state.engine
    col, row = data.get("col"), data.get("row")
    pressed = data.get("pressed")

    if not pressed:
        if e.held_pad == (col, row):
            e.held_pad = None
        return

    track_idx, t = e.track_at(col)
    if t is None:
        return

    if e.mod_lane_active:
        # Grid is borrowed: column = track's mod lane, row = value bucket
        # at the current cursor step.
        snapshot_for_undo(state)
        e.set_mod_value(track_idx, row)
        return

    # Row 7 (physical top) is the earliest step in the page, row 0
    # (physical bottom) the latest — so the playhead visibly travels
    # top-to-bottom as steps advance, not bottom-to-top.
    step_idx = t["step_page"] * 8 + (7 - row)

    # Mute/Solo + tap live on the Screen-bottom (track-select) buttons,
    # not here — see handle_button — so a pad tap while either is held
    # still just toggles the step, same as normal.
    if e.mods["accent"]:
        snapshot_for_undo(state)
        e.toggle_accent(track_idx, step_idx)
        return
    if e.mods["repeat"]:
        # Quick ratchet toggle, Accent's counterpart: 1 <-> 4 repeats.
        # (The "repeat" encoder already exists — encoder 3 — so holding
        # Repeat no longer needs to bypass anything; this gives the
        # button its own one-tap job instead.)
        snapshot_for_undo(state)
        if 0 <= step_idx < t["length"]:
            step = t["steps"][step_idx]
            step["repeat"] = 1 if step["repeat"] > 1 else 4
        return

    if step_idx < t["length"]:
        snapshot_for_undo(state)
        e.toggle_step(track_idx, step_idx)

    e.held_pad = (col, row)


SCREEN_BOTTOM = {"Screen bottom %d" % n: n - 1 for n in range(1, 9)}
SCREEN_TOP = {"Screen top %d" % n: n - 1 for n in range(1, 9)}


def handle_button(state, data):
    e = state.engine
    name = data.get("name") or ""
    pressed = data.get("pressed")

    if name in view.BUTTON_CC:
        state.button_held[name] = bool(pressed)

    # momentary modifiers: track pressed/released, act on the combined
    # pad/encoder gesture, not on the button press itself
    mod_key = {
        "Mute": "mute", "Solo": "solo",
        "Repeat": "repeat", "Accent": "accent",
        "Shift": "shift",
    }.get(name)
    if mod_key:
        e.mods[mod_key] = bool(pressed)
        return

    if not pressed:
        return  # everything below fires on press only

    if name == "Play":
        e.toggle_play()
    elif name == "Scale":
        e.toggle_scale_mode()
    elif name == "Octave Up":
        e.transpose_all(12)
    elif name == "Octave Down":
        e.transpose_all(-12)
    elif name == "Page Left":
        e.track_page = max(0, e.track_page - 8)
    elif name == "Page Right":
        if e.track_page + 8 < len(e.tracks):
            e.track_page += 8
    elif name == "D-Pad up":
        # Up = backward in time (earlier steps) — rows scroll top-to-
        # bottom as steps advance, so "up" naturally means "earlier",
        # matching the playhead's own direction. Left/right are unused
        # for this now (moved off them since time reads vertically here,
        # not horizontally).
        if e.mod_lane_active:
            e.move_mod_cursor(-1)
        elif e.mods["shift"]:
            snapshot_for_undo(state)
            t = e.selected()
            if t:
                e.set_length(e.selected_track, t["length"] - 8)
        else:
            t = e.selected()
            if t and t["step_page"] > 0:
                t["step_page"] -= 1
    elif name == "D-Pad down":
        if e.mod_lane_active:
            e.move_mod_cursor(1)
        elif e.mods["shift"]:
            snapshot_for_undo(state)
            t = e.selected()
            if t:
                e.set_length(e.selected_track, t["length"] + 8)
        else:
            t = e.selected()
            if t and (t["step_page"] + 1) * 8 < t["length"]:
                t["step_page"] += 1
    elif name == "Duplicate":
        snapshot_for_undo(state)
        e.add_track(duplicate_from=e.selected_track)
    elif name == "Undo":
        if state.undo_snapshot is not None:
            e.load(state.undo_snapshot)
            state.undo_snapshot = None
    elif name in eng.DIVISIONS:
        snapshot_for_undo(state)
        if e.mod_lane_active:
            e.set_mod_division(e.selected_track, name)
        else:
            e.set_division(e.selected_track, name)
    elif name == "Select (main)":
        e.toggle_main()
    elif name in SCREEN_TOP:
        # Entry-time gating only: opening from Track mode only works via
        # column 8 (the one Mod status button actually on screen there —
        # see view.draw's Track-mode loop), since 1-7 don't map to
        # anything in that mode. Main mode, and once the overlay is
        # already open, every column maps to "that column's track" —
        # the overlay itself doesn't remember which mode opened it, so
        # closing/switching has to work the same way regardless (press
        # the currently-open track's own button to close it, any other
        # to jump straight there — see Engine.open_mod_lane and its LED
        # in view.button_colors, which highlights whichever one closes).
        col = SCREEN_TOP[name]
        if e.mod_lane_active or e.main_selected:
            track_idx, t = e.track_at(col)
            if t is not None:
                e.open_mod_lane(track_idx)
        elif col == 7:
            e.open_mod_lane(e.selected_track)
    elif name in SCREEN_BOTTOM:
        col = SCREEN_BOTTOM[name]
        track_idx, t = e.track_at(col)
        if t is None:
            pass
        elif e.mods["mute"]:
            snapshot_for_undo(state)
            t["muted"] = not t["muted"]
        elif e.mods["solo"]:
            snapshot_for_undo(state)
            t["solo"] = not t["solo"]
        else:
            e.select_track(track_idx)


def handle_encoder(state, data):
    """Two different meanings for "encoder index", chosen by Main mode:

    - Track selected (not Main): encoder N is always ENCODER_PARAMS[N] of
      the selected track — fixed, 1:1, every parameter live at once.
    - Main mode: encoder N is the Nth *visible track*'s value of
      eng.current_param — the one parameter every column currently shows,
      picked by the jog wheel.

    Either way, holding a step pad always overrides to edit just that one
    step — using the mode's own parameter resolution (fixed-per-encoder in
    Track mode, the shared current_param in Main mode).
    """
    e = state.engine
    idx = data.get("index")
    delta = data.get("delta") or 0
    name = data.get("name") or ""

    if name == "Tempo wheel turn":
        if delta:
            bpm = e.doc["pattern"]["bpm"] + delta
            e.doc["pattern"]["bpm"] = max(eng.MIN_BPM, min(eng.MAX_BPM, bpm))
            state.show_popup("TEMPO", str(e.doc["pattern"]["bpm"]))
        return

    if e.scale_mode_active:
        # Scale mode is exclusive: only encoders 1 (Key) and 2 (Scale)
        # do anything, both track-level (no per-step meaning, so a held
        # pad is irrelevant here too — unlike the rest of Track mode).
        if delta:
            if idx == 0:
                e.nudge_key(e.selected_track, delta)
            elif idx == 1:
                e.nudge_scale(e.selected_track, delta)
        return

    if e.mod_lane_active:
        # Mod-lane mode is exclusive: it borrows the grid and D-Pad, and
        # every encoder (including the jog wheel) is irrelevant while
        # it's active — editing happens via pads (set_mod_value) instead.
        return

    if name == "Jog wheel turn":
        # Only scrolls anything in Main mode: which parameter all 8
        # columns show and edit. Never touches track selection. Clamps
        # at either end of ENCODER_PARAMS instead of wrapping — same
        # "stop at the ends" choice Key/Scale made, for the same reason
        # (there's no meaningful "next parameter after Mod").
        if delta and e.main_selected:
            step = 1 if delta > 0 else -1
            e.current_param = max(0, min(len(eng.ENCODER_PARAMS) - 1, e.current_param + step))
        return

    if idx is None or idx < 0 or delta == 0:
        return  # volume/jog-press not used in v1; nothing to do with a zero delta

    if e.held_pad is not None:
        # "channel" is track-level, not per-step — nothing for a held pad
        # to target, so it's inert here even though it's editable with no
        # pad held (below).
        hcol, hrow = e.held_pad
        h_track_idx, h_t = e.track_at(hcol)
        if h_t is not None:
            param_name = eng.ENCODER_PARAMS[e.current_param if e.main_selected else idx]
            if param_name not in eng.NOOP_PARAMS and param_name != "channel":
                # Same row inversion as handle_pad's step_idx and
                # pad_colors: row 7 (top) is the earliest step.
                held_step = h_t["step_page"] * 8 + (7 - hrow)
                e.nudge_param(h_track_idx, held_step, param_name, delta)
        return

    if e.main_selected:
        track_idx, t = e.track_at(idx)
        if t is None:
            return
        param_name = eng.ENCODER_PARAMS[e.current_param]
        if param_name == "channel":
            e.nudge_channel(track_idx, delta)
            return
        if param_name in eng.NOOP_PARAMS:
            return
        e.nudge_param(track_idx, None, param_name, delta)
        return

    t = e.selected()
    if t is None:
        return
    param_name = eng.ENCODER_PARAMS[idx]
    if param_name == "channel":
        e.nudge_channel(e.selected_track, delta)
        return
    if param_name in eng.NOOP_PARAMS:
        return
    e.nudge_param(e.selected_track, None, param_name, delta)


def handle_external_midi(state, data):
    raw = base64.b64decode(data.get("raw", ""))
    if not raw:
        return
    state.engine.on_external_clock_byte(raw[0])


def handle_response(state, env):
    """A line with an id and a result/error but no method: this is the
    host's reply to a request *we* sent (send_note/note_off/send_cc/
    store_get/store_set), not a new request from the host."""
    rid = env.get("id")
    tag = state._pending.pop(rid, None)
    if "error" in env:
        state.log("gridseq: %s failed: %s" % (tag or rid, env["error"]))
        return
    if tag == "store_get":
        result = env.get("result") or {}
        state.engine.load(result.get("doc"))
        state.last_pad_colors = None  # force a relight on the next draw
    # send_note/note_off/send_cc/store_set replies: nothing to do on success


def save_pattern(state):
    if not PERSIST_ENABLED:
        return
    state.request("store_set", {"doc": state.engine.to_doc()})


def main():
    state = State()
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            env = json.loads(line)
        except json.JSONDecodeError:
            continue

        method = env.get("method")
        id_ = env.get("id")
        params = env.get("params") or {}

        if method is None and id_ is not None:
            handle_response(state, env)
            continue

        if method == "init":
            respond(id_, {})
            if PERSIST_ENABLED:
                state.request("store_get", {}, tag="store_get")
        elif method == "handle":
            kind = params.get("kind")
            data = params.get("data") or {}
            if kind == "pad":
                handle_pad(state, data)
            elif kind == "button":
                handle_button(state, data)
            elif kind == "encoder":
                handle_encoder(state, data)
            elif kind == "external_midi":
                handle_external_midi(state, data)
        elif method == "draw":
            state.engine.tick()
            relight_grid(state)
            relight_buttons(state)
            respond(id_, view.draw(state))
        elif method == "close":
            state.engine.stop()
            save_pattern(state)
            for row in range(8):
                for col in range(8):
                    notify("set_pad", {"note": pad_note(col, row), "colour": 0})
            for cc in set(view.BUTTON_CC.values()):
                notify("set_button", {"cc": cc, "brightness": 0})
            respond(id_, {})
            break
        elif id_ is not None:
            respond_error(id_, "unknown method %r" % method)


if __name__ == "__main__":
    main()
