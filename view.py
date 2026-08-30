"""view.py — builds GridSeq's screen (draw ops) and physical pad LED colors.

Op shapes mirror internal/module's Go types exactly (the ABI), same as every
other process module in this app — see hello-py's draw() for the rationale.
No image op: not available over the process-loader IPC.
"""

import json
import os
import time

import engine as eng

with open(os.path.join(os.path.dirname(__file__), "palette.json")) as _f:
    PALETTE = json.load(_f)


def color(name):
    e = PALETTE["byName"][name]
    return {"R": e["r"], "G": e["g"], "B": e["b"], "A": e["a"]}


def color_by_index(idx):
    e = PALETTE["byIndex"][idx]
    return {"R": e["r"], "G": e["g"], "B": e["b"], "A": e["a"]}


# Palette indices (for set_pad, which wants a raw index, not RGBA)
OFF = 0
DIM = 79        # aquamarine-ish dim marker, used for "playhead only, step empty"
PLAYHEAD_ON = 120  # bright white — playhead currently on an active step

# Button LED indices — separate from pad LEDs because button-white is a
# different palette entry than pad-white (see docs/protocol/led-output.md
# and hardware-reference.md: pad white = 120, button white = 122).
BTN_OFF = 0
BTN_DIM = 118      # "gray_mid" — visibly lit but low-intensity, for "inactive"
BTN_FULL = 122     # "lgray"/"white_btn" — full button-white, for "active"
BTN_GREEN = 11     # Play, while the transport is running

# The active time-division button pulses between these two — vivid bright
# green and fully off — rather than a single static color, so it's
# unmistakable which division is running (there's no real analog
# brightness/PWM for button LEDs, just a fixed palette, so a blink between
# two entries is the closest thing to "pulsing").
DIV_ACTIVE_HI = 10  # "green_vivid"
DIV_ACTIVE_LO = 0   # off/black
PULSE_HZ = 2.0


def _pulsing_div_color():
    phase = int(time.time() * PULSE_HZ * 2) % 2
    return DIV_ACTIVE_HI if phase == 0 else DIV_ACTIVE_LO

# CC per named button GridSeq lights, confirmed against
# internal/pushmap/buttons.go. Only buttons with a function attached are
# listed here — this is exactly the set the module lights, matching the
# rule "light every button that does something, leave the rest dark."
BUTTON_CC = {
    "Play": 85,
    "Stop Clips": 29,
    "Note": 50,
    "Octave Up": 55,
    "Octave Down": 54,
    "Page Left": 62,
    "Page Right": 63,
    "D-Pad left": 44,
    "D-Pad right": 45,
    "Undo": 119,
    "Duplicate": 88,
    "Mute": 60,
    "Solo": 61,
    "Scale": 58,
    "Repeat": 56,
    "Accent": 57,
    "Shift": 49,
    "Scene 1/4": 36, "Scene 1/4t": 37,
    "Scene 1/8": 38, "Scene 1/8t": 39,
    "Scene 1/16": 40, "Scene 1/16t": 41,
    "Scene 1/32": 42, "Scene 1/32t": 43,
    "Screen bottom 1": 20, "Screen bottom 2": 21, "Screen bottom 3": 22, "Screen bottom 4": 23,
    "Screen bottom 5": 24, "Screen bottom 6": 25, "Screen bottom 7": 26, "Screen bottom 8": 27,
    "Select (main)": 28,
}


def button_colors(state):
    """Returns {button_name: palette_index} for every button GridSeq
    manages. Rules (per the design decision this was built from):
    Play is white when paused, green when playing; every other managed
    button is dim white when inactive, full white when active — "active"
    meaning held for a momentary action, toggled on for a modifier, or
    "currently in effect" for a status indicator (Undo, division picker,
    track-select row)."""
    e = state.engine
    held = state.button_held
    out = {}

    out["Play"] = BTN_GREEN if e.playing else BTN_FULL

    for name in ("Stop Clips", "Note"):
        out[name] = BTN_FULL if held.get(name) else BTN_DIM

    out["Octave Up"] = BTN_FULL if held.get("Octave Up") else BTN_DIM
    out["Octave Down"] = BTN_FULL if held.get("Octave Down") else BTN_DIM

    out["Page Left"] = BTN_FULL if held.get("Page Left") else (BTN_DIM if e.track_page > 0 else BTN_OFF)
    out["Page Right"] = BTN_FULL if held.get("Page Right") else (
        BTN_DIM if e.track_page + 8 < len(e.tracks) else BTN_OFF)

    t = e.selected()
    out["D-Pad left"] = BTN_FULL if held.get("D-Pad left") else (
        BTN_DIM if (t and t["step_page"] > 0) else BTN_OFF)
    out["D-Pad right"] = BTN_FULL if held.get("D-Pad right") else (
        BTN_DIM if (t and (t["step_page"] + 1) * 8 < t["length"]) else BTN_OFF)

    out["Undo"] = BTN_FULL if state.undo_snapshot is not None else BTN_DIM
    out["Duplicate"] = BTN_FULL if held.get("Duplicate") else (
        BTN_DIM if len(e.tracks) < eng.MAX_TRACKS else BTN_OFF)

    for name in ("Mute", "Solo", "Scale", "Repeat", "Accent", "Shift"):
        out[name] = BTN_FULL if e.mods.get(name.lower()) else BTN_DIM

    selected_div = t["div"] if t else None
    for div_name in eng.DIVISIONS:
        out[div_name] = _pulsing_div_color() if div_name == selected_div else BTN_DIM

    out["Select (main)"] = BTN_FULL if e.main_selected else BTN_DIM

    # Screen-bottom buttons are black by default; only the selected track's
    # button lights, in that track's own color. All black while Main is
    # active — no single button should look "the" selection during a
    # broadcast edit.
    for col in range(8):
        name = "Screen bottom %d" % (col + 1)
        idx, ct = e.track_at(col)
        if ct is None or e.main_selected or idx != e.selected_track:
            out[name] = BTN_OFF
        else:
            out[name] = ct["color"]

    return out


def pad_colors(state):
    """Returns an 8x8 list-of-lists of palette indices, row 0 = bottom
    (matches push3.PadCoord), col 0 = left — one entry per physical pad."""
    grid = [[OFF for _ in range(8)] for _ in range(8)]
    e = state.engine
    for col in range(8):
        idx, t = e.track_at(col)
        if t is None:
            continue
        page_base = t["step_page"] * 8
        for row in range(8):
            step_idx = page_base + row
            if step_idx >= t["length"]:
                continue
            step = t["steps"][step_idx]
            is_playhead = (t["_current_step"] == step_idx)
            if is_playhead and step["on"]:
                grid[row][col] = PLAYHEAD_ON
            elif is_playhead:
                grid[row][col] = DIM
            elif step["on"]:
                base = t["color"]
                grid[row][col] = base if not t["muted"] else 61  # dim red-ish when muted
            else:
                grid[row][col] = OFF
    return grid


def _kind_div_flags(t):
    """Mute/solo flags (only present if set — no leading space when they
    aren't) + kind + division, for one track. Used once in the header when
    a specific track is selected — showing it per-column would just be the
    same line repeated 8 times."""
    flags = ("M" if t["muted"] else "") + ("S" if t["solo"] else "")
    prefix = flags + " " if flags else ""
    kind = "Melodic" if t["kind"] == "melodic" else "Drums"
    div = t["div"].replace("Scene ", "")
    return "%s%s  %s" % (prefix, kind, div)


_PARAM_FIELD = {
    "velocity": "vel", "gate": "gate", "repeat": "repeat",
    "probability": "prob", "offset": "offset", "pitch": "note",
}


def _param_value(t, param_name):
    """Just the number(s) — no "Vel"/"Gat"/... prefix. The parameter name
    is already shown on the row above (see draw()), so repeating an
    abbreviation next to the value would just be noise."""
    field = _PARAM_FIELD[param_name]
    if not t["steps"]:
        return "-"
    vals = [s[field] for s in t["steps"]]
    lo, hi = min(vals), max(vals)
    return "%d..%d" % (lo, hi) if lo != hi else str(lo)


LABEL_Y, LABEL_H = 140, 20  # bottom strip, sits directly above the 8 "Screen bottom" buttons

VALUE_SCALE = 2  # Text's "scale" is an integer block-multiplier (nearest-neighbor,
                 # same bitmap font), not a point size — 2x is the closest whole
                 # step up from the label's 1x while staying on the standard font.


def _param_label(param_name):
    return param_name.split(" ")[0].capitalize()  # "velocity" -> "Velocity", "pan (v2)" -> "Pan"


def _value_op(x, baseline, s, c):
    """The bigger value text under each parameter label — still the
    standard bitmap font (Text), just at 2x via its "scale" field, not
    StyledText's separate antialiased face."""
    return {"kind": "text", "params": {"x": x, "baseline": baseline, "s": s, "c": c, "scale": VALUE_SCALE}}


def draw(state):
    e = state.engine
    black = color("off")
    gray = color("gray_green")

    bpm = e.doc["pattern"]["bpm"]
    sync = "ext" if e.is_externally_synced() else "int"
    play_state = "playing" if e.playing else "stopped"

    if e.main_selected:
        mode_str = "MAIN - %s" % _param_label(eng.ENCODER_PARAMS[e.current_param])
    else:
        sel = e.selected()
        mode_str = _kind_div_flags(sel) if sel is not None else ""

    header = "GridSeq   BPM %d (%s)   %s   tracks %d-%d/%d   %s" % (
        bpm, sync, play_state,
        e.track_page + 1, min(e.track_page + 8, len(e.tracks)), len(e.tracks),
        mode_str,
    )

    ops = [
        {"kind": "rect", "params": {"x": 0, "y": 0, "w": 960, "h": 160, "c": black}},
        {"kind": "header", "params": {"y": 0, "w": 960, "h": 18, "s": header}},
    ]

    col_w = 960 // 8

    # Upper area: what the 8 encoders show/control right now. Both modes
    # use the same two-row shape — parameter name above, a bigger value
    # below — just with different meanings per column (item 1 & 2).
    if e.main_selected:
        # Columns = tracks, every one showing the *same* parameter
        # (eng.current_param, picked by the jog wheel) — so all 8 values
        # are directly comparable, and the label is the same in every
        # column (there's only one parameter active).
        param_name = eng.ENCODER_PARAMS[e.current_param]
        label = _param_label(param_name)
        for col in range(8):
            idx, t = e.track_at(col)
            x = col * col_w
            if t is None:
                continue
            c = color_by_index(t["color"])
            value = _param_value(t, param_name) if param_name in _PARAM_FIELD else "n/a"
            ops.append({"kind": "text", "params": {"x": x + 4, "baseline": 40, "s": label, "c": c}})
            ops.append(_value_op(x + 4, 68, value, c))
    else:
        # Columns = parameters, all for the one selected track (item 2):
        # column 1 = velocity (encoder 1's param), column 2 = gate, etc.
        t = e.selected()
        for col in range(8):
            param_name = eng.ENCODER_PARAMS[col]
            x = col * col_w
            label = _param_label(param_name)
            c = color_by_index(t["color"]) if t is not None else gray
            value = (_param_value(t, param_name) if (t is not None and param_name in _PARAM_FIELD)
                     else "n/a")
            ops.append({"kind": "text", "params": {"x": x + 4, "baseline": 40, "s": label, "c": c}})
            ops.append(_value_op(x + 4, 68, value, c))

    # Bottom strip: always tracks, regardless of the mode above — it
    # labels the physical "Screen bottom" buttons and pad-grid columns,
    # which never change meaning. The selected track's label is a filled,
    # colored block (a highlighted tab); every other track's is colored
    # text on black; none are highlighted while Main mode is active (see
    # item 1: those buttons are black unless selected).
    for col in range(8):
        idx, t = e.track_at(col)
        x = col * col_w
        if t is None:
            continue
        selected = (idx == e.selected_track) and not e.main_selected
        c = color_by_index(t["color"])
        label = t["name"]
        if selected:
            ops.append({"kind": "rect", "params": {"x": x, "y": LABEL_Y, "w": col_w, "h": LABEL_H, "c": c}})
            ops.append({"kind": "text", "params": {"x": x + 4, "baseline": LABEL_Y + 15, "s": label, "c": black}})
        else:
            ops.append({"kind": "text", "params": {"x": x + 4, "baseline": LABEL_Y + 15, "s": label, "c": c}})

    return {"ops": ops, "failed": 0}
