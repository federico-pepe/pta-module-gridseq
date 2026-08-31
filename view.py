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
INAUDIBLE_STEP = 118  # "gray_mid" — an on step for a track that won't actually
                       # sound right now (explicitly muted, or muted-by-solo
                       # because some other track is soloed) — same grey used
                       # for the bottom-strip label in this state, so pads and
                       # the track label agree at a glance.

# Button LED indices — separate from pad LEDs because button-white is a
# different palette entry than pad-white (see docs/protocol/led-output.md
# and hardware-reference.md: pad white = 120, button white = 122).
BTN_OFF = 0
BTN_DIM = 118      # "gray_mid" — visibly lit but low-intensity, for "inactive"
BTN_FULL = 122     # "lgray"/"white_btn" — full button-white, for "active"
BTN_GREEN = 11     # Play, while the transport is running
MOD_LANE_OPEN = 127  # "pure_red" — the open mod lane's Screen top button, signaling "click to exit"

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
    "Octave Up": 55,
    "Octave Down": 54,
    "Page Left": 62,
    "Page Right": 63,
    "D-Pad up": 46,
    "D-Pad down": 47,
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
    # Screen top N opens the mod-lane overlay for the Nth visible track
    # (Engine.open_mod_lane) — sits directly above that track's column,
    # including its Mod status-button in Track/Main mode.
    "Screen top 1": 102, "Screen top 2": 103, "Screen top 3": 104, "Screen top 4": 105,
    "Screen top 5": 106, "Screen top 6": 107, "Screen top 7": 108, "Screen top 8": 109,
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

    out["Octave Up"] = BTN_FULL if held.get("Octave Up") else BTN_DIM
    out["Octave Down"] = BTN_FULL if held.get("Octave Down") else BTN_DIM

    out["Page Left"] = BTN_FULL if held.get("Page Left") else (BTN_DIM if e.track_page > 0 else BTN_OFF)
    out["Page Right"] = BTN_FULL if held.get("Page Right") else (
        BTN_DIM if e.track_page + 8 < len(e.tracks) else BTN_OFF)

    t = e.selected()
    if e.mod_lane_active:
        # D-Pad moves the mod-lane cursor instead of paging/length — LEDs
        # reflect room to move the cursor up/down.
        out["D-Pad up"] = BTN_FULL if held.get("D-Pad up") else (
            BTN_DIM if e.mod_cursor > 0 else BTN_OFF)
        out["D-Pad down"] = BTN_FULL if held.get("D-Pad down") else (
            BTN_DIM if e.mod_cursor < eng.MAX_STEPS - 1 else BTN_OFF)
    elif e.mods.get("shift"):
        # Shift + D-Pad grows/shrinks length instead of paging — LEDs
        # reflect room to shrink/grow, not room to page.
        out["D-Pad up"] = BTN_FULL if held.get("D-Pad up") else (
            BTN_DIM if (t and t["length"] > eng.DEFAULT_STEPS) else BTN_OFF)
        out["D-Pad down"] = BTN_FULL if held.get("D-Pad down") else (
            BTN_DIM if (t and t["length"] < eng.MAX_STEPS) else BTN_OFF)
    else:
        out["D-Pad up"] = BTN_FULL if held.get("D-Pad up") else (
            BTN_DIM if (t and t["step_page"] > 0) else BTN_OFF)
        out["D-Pad down"] = BTN_FULL if held.get("D-Pad down") else (
            BTN_DIM if (t and (t["step_page"] + 1) * 8 < t["length"]) else BTN_OFF)

    out["Undo"] = BTN_FULL if state.undo_snapshot is not None else BTN_DIM
    out["Duplicate"] = BTN_FULL if held.get("Duplicate") else (
        BTN_DIM if len(e.tracks) < eng.MAX_TRACKS else BTN_OFF)

    for name in ("Mute", "Solo", "Repeat", "Accent", "Shift"):
        out[name] = BTN_FULL if e.mods.get(name.lower()) else BTN_DIM

    # Scale is a toggle (Scale mode), not a held modifier — full while
    # active, off (not just dim) while unavailable (Main mode / mod lane
    # open, neither of which has a single selected track to apply to).
    if e.scale_mode_active:
        out["Scale"] = BTN_FULL
    elif e.main_selected or e.mod_lane_active:
        out["Scale"] = BTN_OFF
    else:
        out["Scale"] = BTN_DIM

    # While mod-lane mode is active, the Scene buttons set the selected
    # track's mod division instead of its note division — pulse the one
    # that matches mod_div instead of div.
    selected_div = (t["mod_div"] if e.mod_lane_active else t["div"]) if t else None
    for div_name in eng.DIVISIONS:
        out[div_name] = _pulsing_div_color() if div_name == selected_div else BTN_DIM

    out["Select (main)"] = BTN_FULL if e.main_selected else BTN_DIM

    # Screen top N: off by default — these buttons only ever do one
    # thing (open a Mod button's track's lane), so they only light when
    # there's actually a Mod button on screen for them to sit above,
    # using that Mod button's own track color rather than a generic
    # dim/full (mirrors the Screen-bottom row's "off = no track owns
    # this" choice rather than Select (main)'s toggle-style dim/full).
    # Whichever one's mod lane is currently *open* overrides to bright
    # red instead, signaling "click to exit" — same button, different
    # job once you're inside the overlay it opens.
    for col in range(8):
        name = "Screen top %d" % (col + 1)
        idx, ct = e.track_at(col)
        if e.mod_lane_active:
            out[name] = MOD_LANE_OPEN if idx == e.selected_track else BTN_OFF
        elif e.scale_mode_active:
            out[name] = BTN_OFF
        elif e.main_selected:
            shows_mod = ct is not None and eng.ENCODER_PARAMS[e.current_param] == "mod lane"
            out[name] = ct["color"] if shows_mod else BTN_OFF
        else:
            out[name] = t["color"] if (col == 7 and t is not None) else BTN_OFF

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


def _mod_bucket_index(value):
    """Highest bucket index whose value is <= the given value — how far
    up the bar-graph column gets filled for that mod value."""
    idx = 0
    for i, b in enumerate(eng.MOD_BUCKETS):
        if b <= value:
            idx = i
    return idx


def mod_lane_pad_colors(state):
    """8x8 grid for the mod-lane bar-graph overlay: column = the visible
    track's mod lane, rows 0..k lit (k = the cursor step's value's
    bucket) in that track's color — a filled bar, tallest = loudest.
    Columns whose track has no step at the current cursor (mod_length <=
    cursor) are left entirely off."""
    grid = [[OFF for _ in range(8)] for _ in range(8)]
    e = state.engine
    for col in range(8):
        idx, t = e.track_at(col)
        if t is None or not (0 <= e.mod_cursor < t["mod_length"]):
            continue
        value = t["mod_steps"][e.mod_cursor]
        top = _mod_bucket_index(value)
        for row in range(top + 1):
            grid[row][col] = t["color"]
    return grid


def pad_colors(state):
    """Returns an 8x8 list-of-lists of palette indices, row 0 = bottom
    (matches push3.PadCoord), col 0 = left — one entry per physical pad.
    Row 7 (top) is the earliest step in the page, row 0 (bottom) the
    latest, so the playhead reads top-to-bottom — see handle_pad's
    matching (7 - row) in run.py."""
    e = state.engine
    if e.mod_lane_active:
        return mod_lane_pad_colors(state)
    grid = [[OFF for _ in range(8)] for _ in range(8)]
    for col in range(8):
        idx, t = e.track_at(col)
        if t is None:
            continue
        page_base = t["step_page"] * 8
        for row in range(8):
            step_idx = page_base + (7 - row)
            if step_idx >= t["length"]:
                continue
            step = t["steps"][step_idx]
            is_playhead = (t["_current_step"] == step_idx)
            if is_playhead and step["on"]:
                grid[row][col] = PLAYHEAD_ON
            elif is_playhead:
                grid[row][col] = DIM
            elif step["on"]:
                grid[row][col] = t["color"] if e.track_audible(t) else INAUDIBLE_STEP
            else:
                grid[row][col] = OFF
    return grid


_PARAM_FIELD = {
    "velocity": "vel", "gate": "gate", "repeat": "repeat",
    "probability": "prob", "offset": "offset", "pitch": "note",
    "mod": "mod",
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

PARAM_LABEL_BASELINE = 16  # top of screen — replaces the removed header row
PARAM_VALUE_BASELINE = 46  # same 30px label-to-value gap the old header-relative layout used

VALUE_SCALE = 2  # Text's "scale" is an integer block-multiplier (nearest-neighbor,
                 # same bitmap font), not a point size — 2x is the closest whole
                 # step up from the label's 1x while staying on the standard font.

_PARAM_LABEL_OVERRIDES = {"channel": "MIDI Channel", "mod lane": "Mod"}


def _param_label(param_name):
    if param_name in _PARAM_LABEL_OVERRIDES:
        return _PARAM_LABEL_OVERRIDES[param_name]
    return param_name.split(" ")[0].capitalize()  # "velocity" -> "Velocity"


def _value_op(x, baseline, s, c):
    """The bigger value text under each parameter label — still the
    standard bitmap font (Text), just at 2x via its "scale" field, not
    StyledText's separate antialiased face."""
    return {"kind": "text", "params": {"x": x, "baseline": baseline, "s": s, "c": c, "scale": VALUE_SCALE}}


def _held_step(e):
    """(track_idx, step_idx) of the currently-held pad, translated
    through the same row inversion as everywhere else (row 7 = earliest
    step) — or (None, None) if no pad is held, or the held pad is past
    its track's length. Centralized here so draw()'s value display and
    run.py's edit dispatch can't drift apart on what "the held step" means."""
    if e.held_pad is None:
        return None, None
    col, row = e.held_pad
    idx, t = e.track_at(col)
    if t is None:
        return None, None
    step_idx = t["step_page"] * 8 + (7 - row)
    if step_idx >= t["length"]:
        return None, None
    return idx, step_idx


def _param_display_value(t, param_name, held_step=None):
    """"channel" is a track-level scalar, not aggregated over steps like
    _PARAM_FIELD's entries — show it directly, held pad or not (there's
    no step for it to narrow down to). For every per-step parameter: with
    a pad held, show that exact step's value (a single number is easy to
    read and reason about); with nothing held, fall back to the
    lo..hi range across every step (a compressed "shape" preview) — this
    is the same "range narrows to an exact value while editing" pattern
    _pitch_display_value uses for note names. Callers must special-case
    "mod lane" themselves (see _mod_button_ops) rather than routing it
    here, since it renders as a button, not a label+value pair."""
    if param_name == "channel":
        return str(t["channel"])
    if param_name not in _PARAM_FIELD:
        return "n/a"
    if held_step is not None:
        return str(t["steps"][held_step][_PARAM_FIELD[param_name]])
    return _param_value(t, param_name)


NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]


def _note_name(midi_note):
    midi_note = max(0, min(127, midi_note))
    # MIDI 60 = C3 — Ableton Live's own octave numbering (not the more
    # common scientific-pitch-notation "MIDI 60 = C4"), since GridSeq is
    # a Push module and Live is what these note names need to agree
    # with. Full range is C-2 (MIDI 0) to G8 (MIDI 127).
    octave = midi_note // 12 - 2
    return "%s%d" % (NOTE_NAMES[midi_note % 12], octave)


def _pitch_display_value(e, t, held_step=None):
    """The Pitch column shows the resolved absolute pitch as a note name
    ("C#3") instead of the raw semitone-offset number — a name is what's
    actually meaningful to read off, since the same offset means a
    different note depending on root/scale."""
    if held_step is not None:
        return _note_name(e.resolve_note(t, t["steps"][held_step]["note"]))
    if not t["steps"]:
        return "-"
    notes = [e.resolve_note(t, s["note"]) for s in t["steps"]]
    lo, hi = min(notes), max(notes)
    return _note_name(lo) if lo == hi else "%s..%s" % (_note_name(lo), _note_name(hi))


CHAR_W = 7  # basicfont.Face7x13's fixed glyph advance at scale 1 (see internal/renderframe);
            # width at scale N is CHAR_W * N — used to center text without real font metrics.

MOD_BUTTON_Y, MOD_BUTTON_H = 0, 18  # same footprint the removed header row used to occupy — no taller


def _mod_button_ops(x, col_w, c):
    """The "Mod" column's status page (Track/Main mode only — not the
    mod-lane editor overlay itself) renders as a colored button tile
    instead of a label+value pair: there's no single meaningful value to
    show (a whole lane's worth of steps), and "n/a" was just noise. How
    to actually visualize the lane here is still undecided — this is a
    placeholder that at least doesn't waste the space or lie. The ">"
    hints there's another page of settings behind it (the mod-lane
    overlay, opened via the "Screen top N" button above this column)."""
    black = color("off")
    baseline = MOD_BUTTON_Y + 14
    return [
        {"kind": "rect", "params": {"x": x + 4, "y": MOD_BUTTON_Y, "w": col_w - 8, "h": MOD_BUTTON_H, "c": c}},
        {"kind": "text", "params": {"x": x + 10, "baseline": baseline, "s": "Mod", "c": black}},
        {"kind": "text", "params": {"x": x + col_w - 16, "baseline": baseline, "s": ">", "c": black}},
    ]


def draw(state):
    e = state.engine
    black = color("off")
    gray = color("gray_green")

    ops = [
        {"kind": "rect", "params": {"x": 0, "y": 0, "w": 960, "h": 160, "c": black}},
    ]

    col_w = 960 // 8

    # No header row (removed — took up space for status text that's
    # mostly redundant with what the LEDs already show). What the 8
    # encoders control now occupies the very top of the screen instead:
    # parameter name above, a bigger value below — same two-row shape in
    # all three modes, just with different per-column meaning.
    if e.scale_mode_active:
        # Scale mode: only columns 1 (Key) and 2 (Scale) mean anything —
        # both track-level, for the selected track — the other 6 are
        # deliberately blank rather than showing stale/irrelevant
        # parameters from Track mode underneath.
        t = e.selected()
        if t is not None:
            c = color_by_index(t["color"])
            key_name = NOTE_NAMES[t["root"] % 12]
            ops.append({"kind": "text", "params": {"x": 4, "baseline": PARAM_LABEL_BASELINE, "s": "Key", "c": c}})
            ops.append(_value_op(4, PARAM_VALUE_BASELINE, key_name, c))
            scale_name = t["scale"].replace("_", " ").title()
            ops.append({"kind": "text", "params": {"x": col_w + 4, "baseline": PARAM_LABEL_BASELINE, "s": "Scale", "c": c}})
            ops.append(_value_op(col_w + 4, PARAM_VALUE_BASELINE, scale_name, c))
    elif e.mod_lane_active:
        # Mod-lane mode: columns = tracks' mod lanes (same as always),
        # label = that track's own mod division (independent per track),
        # value = its mod value at the shared cursor step — "-" if that
        # track's lane doesn't reach the cursor yet.
        for col in range(8):
            idx, t = e.track_at(col)
            x = col * col_w
            if t is None:
                continue
            c = color_by_index(t["color"])
            label = "S%d %s" % (e.mod_cursor + 1, t["mod_div"].replace("Scene ", ""))
            value = str(t["mod_steps"][e.mod_cursor]) if e.mod_cursor < t["mod_length"] else "-"
            ops.append({"kind": "text", "params": {"x": x + 4, "baseline": PARAM_LABEL_BASELINE, "s": label, "c": c}})
            ops.append(_value_op(x + 4, PARAM_VALUE_BASELINE, value, c))
    elif e.main_selected:
        # Columns = tracks, every one showing the *same* parameter
        # (eng.current_param, picked by the jog wheel) — so all 8 values
        # are directly comparable, and the label is the same in every
        # column (there's only one parameter active).
        param_name = eng.ENCODER_PARAMS[e.current_param]
        label = _param_label(param_name)
        held_idx, held_step = _held_step(e)
        for col in range(8):
            idx, t = e.track_at(col)
            x = col * col_w
            if t is None:
                continue
            c = color_by_index(t["color"])
            if param_name == "mod lane":
                ops.extend(_mod_button_ops(x, col_w, c))
                continue
            this_held_step = held_step if idx == held_idx else None
            if param_name == "pitch":
                value = _pitch_display_value(e, t, this_held_step)
            else:
                value = _param_display_value(t, param_name, this_held_step)
            ops.append({"kind": "text", "params": {"x": x + 4, "baseline": PARAM_LABEL_BASELINE, "s": label, "c": c}})
            ops.append(_value_op(x + 4, PARAM_VALUE_BASELINE, value, c))
    else:
        # Columns = parameters, all for the one selected track (item 2):
        # column 1 = velocity (encoder 1's param), column 2 = gate, etc.
        t = e.selected()
        held_idx, held_step = _held_step(e)
        this_held_step = held_step if held_idx == e.selected_track else None
        for col in range(8):
            param_name = eng.ENCODER_PARAMS[col]
            x = col * col_w
            c = color_by_index(t["color"]) if t is not None else gray
            if param_name == "mod lane":
                ops.extend(_mod_button_ops(x, col_w, c))
                continue
            label = _param_label(param_name)
            if t is None:
                value = "n/a"
            elif param_name == "pitch":
                value = _pitch_display_value(e, t, this_held_step)
            else:
                value = _param_display_value(t, param_name, this_held_step)
            ops.append({"kind": "text", "params": {"x": x + 4, "baseline": PARAM_LABEL_BASELINE, "s": label, "c": c}})
            ops.append(_value_op(x + 4, PARAM_VALUE_BASELINE, value, c))

    # Bottom strip: always tracks, regardless of the mode above — it
    # labels the physical "Screen bottom" buttons and pad-grid columns,
    # which never change meaning. The selected track's label is a filled,
    # colored block (a highlighted tab); every other track's is colored
    # text on black; none are highlighted while Main mode is active (see
    # item 1: those buttons are black unless selected). A track that
    # won't actually sound right now
    # (muted, or muted-by-solo) greys out here too, matching its pads —
    # "muted" isn't just a pad-level fact, it should read at a glance
    # from the label too.
    for col in range(8):
        idx, t = e.track_at(col)
        x = col * col_w
        if t is None:
            continue
        selected = (idx == e.selected_track) and not e.main_selected
        c = color_by_index(t["color"]) if e.track_audible(t) else color("gray_mid")
        label = t["name"]
        if selected:
            ops.append({"kind": "rect", "params": {"x": x, "y": LABEL_Y, "w": col_w, "h": LABEL_H, "c": c}})
            ops.append({"kind": "text", "params": {"x": x + 4, "baseline": LABEL_Y + 15, "s": label, "c": black}})
        else:
            ops.append({"kind": "text", "params": {"x": x + 4, "baseline": LABEL_Y + 15, "s": label, "c": c}})

    # Transient popup: appears over everything else for a couple seconds
    # after State.show_popup was last called (Tempo turn, Scale cycling,
    # ...), then goes away on its own — the one place this kind of
    # otherwise-invisible feedback shows up now that the header's gone.
    if state.popup_title is not None and time.monotonic() < state.popup_until:
        ops.extend(_popup_ops(state.popup_title, state.popup_body))

    return {"ops": ops, "failed": 0}


POPUP_Y, POPUP_H = 8, 80
POPUP_PAD = 20  # horizontal padding either side of the widest line


def _popup_ops(title, body):
    """A centered white popup box: `title` on a small top line, `body`
    (optional) bigger below it — reused for every "button did something
    that isn't otherwise visible" case (see State.show_popup), not just
    the Tempo readout it started as. Box width fits the widest line
    since a one-word title ("TEMPO") and a multi-word body ("Melodic
    Sequencer") need very different widths; centering both text and box
    uses CHAR_W since there's no real font-metrics API to query."""
    black = color("off")
    title_w = CHAR_W * len(title)
    body_w = CHAR_W * VALUE_SCALE * len(body) if body else 0
    box_w = min(920, max(title_w, body_w) + POPUP_PAD * 2)
    box_x = (960 - box_w) // 2
    ops = [{"kind": "rect", "params": {"x": box_x, "y": POPUP_Y, "w": box_w, "h": POPUP_H, "c": color("white")}}]
    ops.append({"kind": "text", "params": {
        "x": box_x + (box_w - title_w) // 2, "baseline": POPUP_Y + 22, "s": title, "c": black,
    }})
    if body:
        ops.append(_value_op(box_x + (box_w - body_w) // 2, POPUP_Y + 62, body, black))
    return ops
