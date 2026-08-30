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

import engine as eng
import view


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
        self._next_id = 1000
        self._pending = {}  # request id -> tag string, for responses we care about

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
    step_idx = t["step_page"] * 8 + row

    if e.mods["mute"]:
        snapshot_for_undo(state)
        t["muted"] = not t["muted"]
        return
    if e.mods["solo"]:
        snapshot_for_undo(state)
        t["solo"] = not t["solo"]
        return
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
        "Scale": "scale", "Repeat": "repeat", "Accent": "accent",
        "Shift": "shift",
    }.get(name)
    if mod_key:
        e.mods[mod_key] = bool(pressed)
        return

    if not pressed:
        return  # everything below fires on press only

    if name == "Play":
        e.toggle_play()
    elif name == "Stop Clips":
        e.stop()
    elif name == "Note":
        snapshot_for_undo(state)
        e.toggle_kind(e.selected_track)
    elif name == "Octave Up":
        e.transpose_all_melodic(12)
    elif name == "Octave Down":
        e.transpose_all_melodic(-12)
    elif name == "Page Left":
        e.track_page = max(0, e.track_page - 8)
    elif name == "Page Right":
        if e.track_page + 8 < len(e.tracks):
            e.track_page += 8
    elif name == "D-Pad left":
        t = e.selected()
        if t and t["step_page"] > 0:
            t["step_page"] -= 1
    elif name == "D-Pad right":
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
        e.set_division(e.selected_track, name)
    elif name == "Select (main)":
        e.toggle_main()
    elif name in SCREEN_BOTTOM:
        col = SCREEN_BOTTOM[name]
        track_idx, t = e.track_at(col)
        if t is not None:
            e.select_track(track_idx)


def _skip_pitch(param_name, t):
    return param_name == "pitch" and t["kind"] != "melodic"


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
        return

    if name == "Jog wheel turn":
        # Only scrolls anything in Main mode: which parameter all 8
        # columns show and edit. Never touches track selection.
        if delta and e.main_selected:
            step = 1 if delta > 0 else -1
            e.current_param = (e.current_param + step) % len(eng.ENCODER_PARAMS)
        return

    if idx is None or idx < 0 or delta == 0:
        return  # volume/jog-press not used in v1; nothing to do with a zero delta

    if e.mods["scale"]:
        e.cycle_scale(e.selected_track, forward=(delta > 0))
        return

    if e.held_pad is not None:
        hcol, hrow = e.held_pad
        h_track_idx, h_t = e.track_at(hcol)
        if h_t is not None:
            param_name = eng.ENCODER_PARAMS[e.current_param if e.main_selected else idx]
            if param_name not in ("pan (v2)", "mod (v2)") and not _skip_pitch(param_name, h_t):
                held_step = h_t["step_page"] * 8 + hrow
                e.nudge_param(h_track_idx, held_step, param_name, delta)
        return

    if e.main_selected:
        track_idx, t = e.track_at(idx)
        if t is None:
            return
        param_name = eng.ENCODER_PARAMS[e.current_param]
        if param_name in ("pan (v2)", "mod (v2)") or _skip_pitch(param_name, t):
            return
        e.nudge_param(track_idx, None, param_name, delta)
        return

    t = e.selected()
    if t is None:
        return
    param_name = eng.ENCODER_PARAMS[idx]
    if param_name in ("pan (v2)", "mod (v2)") or _skip_pitch(param_name, t):
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
