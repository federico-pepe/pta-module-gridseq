#!/usr/bin/env python3
"""run.py — GridSeq protocol loop.

Same envelope shape as every process module in this app (see
push-tethered-app/examples/modules/hello-py's run.py docstring for the
full wire format). This file only does I/O and event dispatch. The
sequencer model lives in engine.py. The screen and pad-color rendering
lives in view.py.

Outgoing calls come in two shapes (see
docs/architecture/process-modules.md's method table): pure notifications
(set_pad, set_button, log, with no id and no reply expected) and
requests (send_cc, send_note, note_off, store_get, store_set, which
carry an id and get a host reply on a later line). This module never
blocks while it waits for a reply. Incoming response lines are matched
against a small pending-request table, and applied whenever they arrive.

Pad and button LEDs relight once per "draw" call, diffed against the
last frame so an unchanged grid or button set costs nothing, instead of
relighting after every individual handler. The host calls draw
continuously (30-60fps), so this is at most one frame of latency. It
also guarantees that every state change, wherever it happens, reaches
the LEDs, with no need to remember to call relight_* at every call site.
"""

import base64
import copy
import json
import os
import re
import sys
import time

import engine as eng
import view

# Saved sequences (Save/Set buttons) are plain JSON files in this directory,
# one per sequence, named after the sequence — a separate mechanism from the
# host's store_get/store_set (single-doc, currently disabled via
# PERSIST_ENABLED below), since Save/Set is explicitly about naming and
# switching between several sequences, not a single "the pattern" slot.
SEQUENCES_DIR = os.path.join(os.path.dirname(__file__), "sequences")

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
        self.popup_until = 0.0     # time.monotonic() deadline. Popup shows while now < this.

        self.active_sequence_name = None    # name Save writes to. None means never saved this session.
        self.sequence_browser_active = False  # True: Set-button overlay owns the screen/grid/D-Pad/jog
        self.sequence_names = []            # cached listing, refreshed each time the browser opens
        self.sequence_cursor = 0            # index into ["New"] + sequence_names

        self._next_id = 1000
        self._pending = {}  # request id -> tag string, for responses we care about

    POPUP_DURATION = 1.5  # seconds a popup stays up after show_popup

    def show_popup(self, title, body=None):
        """A transient on-screen popup for a button or knob whose effect
        is not otherwise visible (BPM after a Tempo turn, a track's kind
        after Note toggles it, and so on). `title` is the small top
        line. `body` (optional) is the bigger line below it. See
        view._popup_ops."""
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
    """Full redraw of the 8x8 pad LEDs, the same "redraw, do not diff"
    choice beatcount-py makes, for the same reason: correctness over
    message count, and 64 notifications is cheap. Diffed against the
    last frame, so a steady-state grid costs nothing."""
    grid = view.pad_colors(state)
    if grid == state.last_pad_colors:
        return
    state.last_pad_colors = copy.deepcopy(grid)
    for row in range(8):
        for col in range(8):
            notify("set_pad", {"note": pad_note(col, row), "colour": grid[row][col]})


def relight_buttons(state):
    """Full redraw of every managed button LED, the same diffed-redraw
    choice as relight_grid. Wire field is "brightness" (see
    docs/architecture/process-modules.md's method table). The value is a
    palette index, the same mechanism as set_pad's "colour"."""
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
    if state.sequence_browser_active:
        return  # grid is inert while the Set-button browser owns the screen
    col, row = data.get("col"), data.get("row")
    pressed = data.get("pressed")

    if not pressed:
        if e.held_pad == (col, row):
            e.held_pad = None
        return

    if e.color_picker_active:
        color = eng.color_picker_grid().get((row, col))
        if color is not None:
            snapshot_for_undo(state)
            e.set_track_color(color)
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
        # (The "repeat" encoder already exists, as encoder 3, so holding
        # Repeat no longer needs to bypass anything. This gives the
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
        "Shift": "shift", "Delete": "delete",
    }.get(name)
    if mod_key:
        e.mods[mod_key] = bool(pressed)
        if mod_key == "shift" and not pressed and e.color_picker_active:
            e.exit_color_picker()
        return

    if not pressed:
        return  # everything below fires on press only

    if name == "Play":
        e.toggle_play()
    elif name == "Scale":
        e.toggle_scale_mode()
    elif name == "Clip View":
        e.toggle_length_view()
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
        if state.sequence_browser_active:
            state.sequence_cursor = max(0, state.sequence_cursor - 1)
        elif e.mod_lane_active:
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
        if state.sequence_browser_active:
            items_len = 1 + len(state.sequence_names)
            state.sequence_cursor = min(items_len - 1, state.sequence_cursor + 1)
        elif e.mod_lane_active:
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
    elif name == "Add":
        snapshot_for_undo(state)
        e.add_track(duplicate_from=e.selected_track)
    elif name == "Save":
        if state.active_sequence_name is None:
            state.active_sequence_name = next_sequence_name()
        save_sequence(state, state.active_sequence_name)
        state.show_popup("SAVED", state.active_sequence_name)
    elif name == "Set":
        # Plain toggle — a second press with nothing else pressed in
        # between just closes the browser without applying any selection
        # (Jog press / D-Pad center is what commits — see below).
        if state.sequence_browser_active:
            state.sequence_browser_active = False
        else:
            state.sequence_browser_active = True
            state.sequence_names = list_sequences()
            state.sequence_cursor = 0
    elif name in ("Jog press", "D-Pad center") and state.sequence_browser_active:
        confirm_sequence_selection(state)
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
        # Entry-time gating only. Opening from Track mode works only via
        # column 8 (the one Mod status button actually on screen there,
        # see view.draw's Track-mode loop), because columns 1-7 map to
        # nothing in that mode. In Main mode, and once the overlay is
        # already open, every column maps to "that column's track". The
        # overlay itself does not remember which mode opened it, so
        # closing or switching works the same way regardless: press the
        # currently-open track's own button to close it, or any other to
        # jump straight there. See Engine.open_mod_lane and its LED in
        # view.button_colors, which highlights whichever button closes
        # the overlay.
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
        elif e.mods["shift"]:
            e.enter_color_picker(track_idx)
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

    if state.sequence_browser_active:
        # Every encoder (including Tempo) is inert here except the jog
        # wheel, which scrolls the list — same "borrow everything, one
        # exception" shape as mod-lane mode borrowing the grid/D-Pad.
        if name == "Jog wheel turn" and delta:
            items_len = 1 + len(state.sequence_names)
            step = 1 if delta > 0 else -1
            state.sequence_cursor = max(0, min(items_len - 1, state.sequence_cursor + step))
        return

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

    if e.length_view_active:
        # Length view is exclusive. Only encoder 1 does anything: the
        # selected track's Length, throttled like Key/Scale (see
        # nudge_length), so a small wiggle does not jump several steps.
        if delta and idx == 0:
            e.nudge_length(e.selected_track, delta)
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
        return  # volume/jog-press not used in v1. Nothing to do with a zero delta.

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


_ENCODER_TOUCH_RE = re.compile(r"^Encoder (\d) touch$")


def handle_touch(state, data):
    """Hold Delete, then touch a screen encoder (not turn it. A bare
    touch fires on every normal turn too, see the mod-lane toggle's own
    note on why touch-as-trigger needs a modifier). This resets that
    encoder's current parameter to its default. Same param-resolution
    split as handle_encoder's no-pad-held branches. Main mode uses
    current_param, shared across all 8. Track mode uses
    ENCODER_PARAMS[idx], fixed per encoder. A held pad narrows the reset
    to just that one step, the same as a normal edit."""
    e = state.engine
    if not data.get("touched") or not e.mods.get("delete"):
        return
    if state.sequence_browser_active or e.scale_mode_active or e.mod_lane_active or e.length_view_active:
        return
    m = _ENCODER_TOUCH_RE.match(data.get("name") or "")
    if not m:
        return
    idx = int(m.group(1)) - 1

    if e.held_pad is not None:
        hcol, hrow = e.held_pad
        h_track_idx, h_t = e.track_at(hcol)
        if h_t is None:
            return
        param_name = eng.ENCODER_PARAMS[e.current_param if e.main_selected else idx]
        if param_name in eng.NOOP_PARAMS or param_name == "channel":
            return
        snapshot_for_undo(state)
        held_step = h_t["step_page"] * 8 + (7 - hrow)
        e.reset_param(h_track_idx, held_step, param_name)
        return

    if e.main_selected:
        track_idx, t = e.track_at(idx)
        if t is None:
            return
        param_name = eng.ENCODER_PARAMS[e.current_param]
        if param_name in eng.NOOP_PARAMS:
            return
        snapshot_for_undo(state)
        e.reset_param(track_idx, None, param_name)
        return

    t = e.selected()
    if t is None:
        return
    param_name = eng.ENCODER_PARAMS[idx]
    if param_name in eng.NOOP_PARAMS:
        return
    snapshot_for_undo(state)
    e.reset_param(e.selected_track, None, param_name)


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


def list_sequences():
    if not os.path.isdir(SEQUENCES_DIR):
        return []
    return sorted(f[:-5] for f in os.listdir(SEQUENCES_DIR) if f.endswith(".json"))


def save_sequence(state, name):
    os.makedirs(SEQUENCES_DIR, exist_ok=True)
    path = os.path.join(SEQUENCES_DIR, name + ".json")
    with open(path, "w") as f:
        json.dump(state.engine.to_doc(), f)


def load_sequence_doc(name):
    path = os.path.join(SEQUENCES_DIR, name + ".json")
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def next_sequence_name():
    """First unused "Sequence N" — Save's auto-name for a pattern that's
    never been saved or loaded this session (active_sequence_name is
    None), since there's no text entry on this hardware to name it by
    hand."""
    existing = set(list_sequences())
    n = 1
    while ("Sequence %d" % n) in existing:
        n += 1
    return "Sequence %d" % n


def confirm_sequence_selection(state):
    """Jog press / D-Pad center while the Set-button browser is open:
    commits whatever's highlighted — "New" resets to a fresh pattern,
    anything else loads that saved sequence — and closes the browser."""
    items = ["New"] + state.sequence_names
    idx = state.sequence_cursor
    if 0 <= idx < len(items):
        choice = items[idx]
        if choice == "New":
            state.engine.enter_sequence(None)
            state.active_sequence_name = None
            state.show_popup("NEW", "Sequence")
        else:
            doc = load_sequence_doc(choice)
            if doc is not None:
                state.engine.enter_sequence(doc)
                state.active_sequence_name = choice
                state.show_popup("LOADED", choice)
    state.sequence_browser_active = False
    state.last_pad_colors = None


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
            elif kind == "touch":
                handle_touch(state, data)
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
