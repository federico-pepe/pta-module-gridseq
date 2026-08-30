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
    and 64 notifications is cheap."""
    grid = view.pad_colors(state)
    if grid == state.last_pad_colors:
        return
    state.last_pad_colors = copy.deepcopy(grid)
    for row in range(8):
        for col in range(8):
            notify("set_pad", {"note": pad_note(col, row), "colour": grid[row][col]})


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

    if e.mods["select"]:
        e.selected_track = track_idx
        return
    if e.mods["mute"]:
        snapshot_for_undo(state)
        t["muted"] = not t["muted"]
        relight_grid(state)
        return
    if e.mods["solo"]:
        snapshot_for_undo(state)
        t["solo"] = not t["solo"]
        relight_grid(state)
        return
    if e.mods["accent"]:
        snapshot_for_undo(state)
        e.toggle_accent(track_idx, step_idx)
        relight_grid(state)
        return

    if step_idx < t["length"]:
        snapshot_for_undo(state)
        e.toggle_step(track_idx, step_idx)
        relight_grid(state)

    e.held_pad = (col, row)


def handle_button(state, data):
    e = state.engine
    name = data.get("name") or ""
    pressed = data.get("pressed")

    # momentary modifiers: track pressed/released, act on the combined
    # pad/encoder gesture, not on the button press itself
    mod_key = {
        "Select": "select", "Mute": "mute", "Solo": "solo",
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
        relight_grid(state)
    elif name == "Octave Up":
        e.transpose_all_melodic(12)
    elif name == "Octave Down":
        e.transpose_all_melodic(-12)
    elif name == "Page Left":
        e.track_page = max(0, e.track_page - 8)
        relight_grid(state)
    elif name == "Page Right":
        if e.track_page + 8 < eng.MAX_TRACKS:
            e.track_page += 8
            relight_grid(state)
    elif name == "D-Pad left":
        t = e.selected()
        if t and t["step_page"] > 0:
            t["step_page"] -= 1
            relight_grid(state)
    elif name == "D-Pad right":
        t = e.selected()
        if t and (t["step_page"] + 1) * 8 < t["length"]:
            t["step_page"] += 1
            relight_grid(state)
    elif name == "Undo":
        if state.undo_snapshot is not None:
            e.load(state.undo_snapshot)
            state.undo_snapshot = None
            relight_grid(state)
    elif name in eng.DIVISIONS:
        snapshot_for_undo(state)
        e.set_division(e.selected_track, name)


def handle_encoder(state, data):
    e = state.engine
    idx = data.get("index")
    delta = data.get("delta") or 0

    if idx is None or idx < 0 or delta == 0:
        return  # volume/tempo/jog not used in v1; nothing to do with a zero delta

    if e.mods["scale"]:
        e.cycle_scale(e.selected_track, forward=(delta > 0))
        return

    track_idx, t = e.track_at(idx)
    if t is None:
        track_idx = e.selected_track
        t = e.tracks[track_idx] if 0 <= track_idx < len(e.tracks) else None
    if t is None:
        return

    held_step = None
    if e.held_pad is not None:
        hcol, hrow = e.held_pad
        h_track_idx, h_t = e.track_at(hcol)
        if h_track_idx == track_idx and h_t is not None:
            held_step = h_t["step_page"] * 8 + hrow

    if e.mods["repeat"]:
        e.nudge_param(track_idx, held_step, "repeat", delta)
        return

    param_name = eng.PARAM_PAGES[e.param_page]
    if param_name in ("pan (v2)", "mod (v2)"):
        return  # stub pages, no-op by design — see the plan's v2 section
    if param_name == "pitch" and t["kind"] != "melodic":
        return

    e.nudge_param(track_idx, held_step, param_name, delta)


def handle_touch(state, data):
    # Encoders 1-8 touch = notes 0-7 (see docs/protocol/midi-input.md).
    # Tapping an encoder cycles the active parameter page.
    note = data.get("note")
    touched = data.get("touched")
    if touched and note is not None and 0 <= note <= 7:
        e = state.engine
        e.param_page = (e.param_page + 1) % len(eng.PARAM_PAGES)


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
        state.last_pad_colors = None  # force a relight on the next tick
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
            elif kind == "touch":
                handle_touch(state, data)
            elif kind == "external_midi":
                handle_external_midi(state, data)
                relight_grid(state)
        elif method == "draw":
            state.engine.tick()
            relight_grid(state)
            respond(id_, view.draw(state))
        elif method == "close":
            state.engine.stop()
            save_pattern(state)
            for row in range(8):
                for col in range(8):
                    notify("set_pad", {"note": pad_note(col, row), "colour": 0})
            respond(id_, {})
            break
        elif id_ is not None:
            respond_error(id_, "unknown method %r" % method)


if __name__ == "__main__":
    main()
