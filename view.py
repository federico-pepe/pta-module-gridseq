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
INAUDIBLE_STEP = 118  # "gray_mid" — an on step for a track that does not
                       # actually sound right now (explicitly muted, or
                       # muted by solo because some other track is
                       # soloed). Same grey as the bottom-strip label in
                       # this state, so pads and the track label agree at
                       # a glance.

# Button LED indices — separate from pad LEDs because button-white is a
# different palette entry than pad-white (see docs/protocol/led-output.md
# and hardware-reference.md: pad white = 120, button white = 122).
BTN_OFF = 0
BTN_DIM = 118      # "gray_mid" — visibly lit but low-intensity, for "inactive"
BTN_FULL = 122     # "lgray"/"white_btn" — full button-white, for "active"
BTN_GREEN = 126     # Play, while the transport is running

# The active time-division button pulses between these two — vivid bright
# green and fully off — rather than a single static color, so it's
# unmistakable which division is running (there's no real analog
# brightness/PWM for button LEDs, just a fixed palette, so a blink between
# two entries is the closest thing to "pulsing").
DIV_ACTIVE_HI = 126  # "green_vivid"
DIV_ACTIVE_LO = 0   # off/black
PULSE_HZ = 1.0


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
    "D-Pad center": 91,
    "Jog press": 94,
    "Undo": 119,
    "Add": 32,
    "Save": 82,
    "Set": 80,
    "Delete": 118,
    "Mute": 60,
    "Solo": 61,
    "Scale": 58,
    "Clip View": 113,
    "Repeat": 56,
    "Accent": 57,
    "Shift": 49,
    "Note": 50,
    "Scene 1/4": 36, "Scene 1/4t": 37,
    "Scene 1/8": 38, "Scene 1/8t": 39,
    "Scene 1/16": 40, "Scene 1/16t": 41,
    "Scene 1/32": 42, "Scene 1/32t": 43,
    "Screen bottom 1": 20, "Screen bottom 2": 21, "Screen bottom 3": 22, "Screen bottom 4": 23,
    "Screen bottom 5": 24, "Screen bottom 6": 25, "Screen bottom 7": 26, "Screen bottom 8": 27,
    "Select (main)": 28,
    # Screen top 1-8 (CC 102-109) are currently unmapped — their old job
    # (opening the mod lane) is gone, no replacement assigned yet. See
    # plans/2026-09-02-mod-track-redesign.md's "Open" section.
}


def button_colors(state):
    """Returns {button_name: palette_index} for every button GridSeq
    manages. Rules (per the design decision this was built from): Play is
    white when paused, and green when playing. Every other managed
    button is dim white when inactive, and full white when active.
    "Active" means held for a momentary action, toggled on for a
    modifier, or "currently in effect" for a status indicator (Undo,
    division picker, track-select row)."""
    e = state.engine
    held = state.button_held
    out = {}

    out["Play"] = BTN_GREEN if e.playing else BTN_FULL

    out["Octave Up"] = BTN_FULL if held.get("Octave Up") else BTN_DIM
    out["Octave Down"] = BTN_FULL if held.get("Octave Down") else BTN_DIM

    out["Page Left"] = BTN_FULL if held.get("Page Left") else (BTN_DIM if e.track_page > 0 else BTN_OFF)
    out["Page Right"] = BTN_FULL if held.get("Page Right") else (
        BTN_DIM if e.track_page + 8 < len(e.visible_track_indices()) else BTN_OFF)

    t = e.selected()
    if state.sequence_browser_active:
        # D-Pad (and the jog wheel — see handle_encoder) scroll the
        # sequence list instead of paging/length while the Set-button
        # browser is open — LEDs reflect room to scroll, same pattern as
        # every other D-Pad-repurposing mode below.
        items_len = 1 + len(state.sequence_names)
        out["D-Pad up"] = BTN_FULL if held.get("D-Pad up") else (
            BTN_DIM if state.sequence_cursor > 0 else BTN_OFF)
        out["D-Pad down"] = BTN_FULL if held.get("D-Pad down") else (
            BTN_DIM if state.sequence_cursor < items_len - 1 else BTN_OFF)
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
    out["Add"] = BTN_FULL if held.get("Add") else (
        BTN_DIM if len(e.tracks) < eng.MAX_TRACKS else BTN_OFF)

    out["Save"] = BTN_FULL if held.get("Save") else BTN_DIM
    out["Set"] = BTN_FULL if state.sequence_browser_active else BTN_DIM
    out["D-Pad center"] = BTN_FULL if held.get("D-Pad center") else (
        BTN_DIM if state.sequence_browser_active else BTN_OFF)
    out["Jog press"] = BTN_FULL if held.get("Jog press") else (
        BTN_DIM if state.sequence_browser_active else BTN_OFF)

    for name in ("Mute", "Solo", "Repeat", "Accent", "Shift", "Delete"):
        out[name] = BTN_FULL if e.mods.get(name.lower()) else BTN_DIM

    # Scale is a toggle (Scale mode), not a held modifier — full while
    # active, off (not just dim) while unavailable (Main mode, or a
    # selected Mod track — no pitch concept to apply it to).
    if e.scale_mode_active:
        out["Scale"] = BTN_FULL
    elif e.main_selected or (t is not None and t["kind"] == "mod"):
        out["Scale"] = BTN_OFF
    else:
        out["Scale"] = BTN_DIM

    # Clip View is a toggle (Length view), same shape as Scale above —
    # full while active, off while unavailable, dim otherwise. Available
    # for a selected Mod track too: it has its own length/step grid.
    if e.length_view_active:
        out["Clip View"] = BTN_FULL
    elif e.main_selected:
        out["Clip View"] = BTN_OFF
    else:
        out["Clip View"] = BTN_DIM

    selected_div = t["div"] if t else None
    for div_name in eng.DIVISIONS:
        out[div_name] = _pulsing_div_color() if div_name == selected_div else BTN_DIM

    out["Select (main)"] = BTN_FULL if e.main_selected else BTN_DIM

    # Note is a toggle (view_kind), same full/dim shape as Select (main) —
    # always available, never off.
    out["Note"] = BTN_FULL if e.view_kind == "mod" else BTN_DIM

    # Screen-bottom buttons are black by default. Only the selected
    # track's button lights, in that track's own color. All black while
    # Main is active: no single button must look like "the" selection
    # during a broadcast edit.
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
    (matches push3.PadCoord), col 0 = left — one entry per physical pad.
    Row 7 (top) is the earliest step in the page, row 0 (bottom) the
    latest, so the playhead reads top-to-bottom — see handle_pad's
    matching (7 - row) in run.py."""
    e = state.engine
    if state.sequence_browser_active:
        # Grid has no meaning while the Set-button browser has the
        # screen — same "borrow the whole surface" exclusivity as the
        # color-picker overlay, just with nothing for pads to do at all.
        return [[OFF for _ in range(8)] for _ in range(8)]
    if e.color_picker_active:
        return color_picker_pad_colors(state)
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


def color_picker_pad_colors(state):
    """The color-picker border overlay (Shift + Screen-bottom): whole grid
    dark except the border pads, each lit with one TRACK_COLORS entry — see
    eng.color_picker_grid for the border walk and (row, col) mapping."""
    grid = [[OFF for _ in range(8)] for _ in range(8)]
    for (row, col), color in eng.color_picker_grid().items():
        grid[row][col] = color
    return grid


_PARAM_FIELD = {
    "velocity": "vel", "gate": "gate", "repeat": "repeat",
    "probability": "prob", "offset": "offset", "pitch": "note",
}


def _param_value(t, param_name):
    """Just the number(s), with no "Vel"/"Gat"/... prefix. The parameter
    name is already shown on the row above (see draw()), so an
    abbreviation next to the value only adds noise."""
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

_PARAM_LABEL_OVERRIDES = {"channel": "MIDI Channel"}


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
    step). Returns (None, None) if no pad is held, or the held pad is
    past its track's length. Centralized here so draw()'s value display
    and run.py's edit dispatch cannot drift apart on what "the held
    step" means."""
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
    _PARAM_FIELD's entries. Show it directly, held pad or not, because
    there is no step for it to narrow down to. For every per-step
    parameter: with a pad held, show that exact step's value (a single
    number is easy to read). With nothing held, fall back to the lo..hi
    range across every step (a compressed "shape" preview). This is the
    same "range narrows to an exact value while editing" pattern
    _pitch_display_value uses for note names. Mod tracks never call this
    — see _mod_track_column instead, a completely different column
    layout."""
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


CHAR_W = 7  # basicfont.Face7x13's fixed glyph advance at scale 1 (see internal/renderframe).
            # Width at scale N is CHAR_W * N. Used to center text with no real font metrics.

def _mod_dest_track_label(e, t):
    idx = t["mod_dest_track"]
    if idx is None or not (0 <= idx < len(e.tracks)):
        return "-"
    return e.tracks[idx]["name"]


def _mod_track_column(e, t, col):
    """One of a Mod track's 8 fixed encoder columns — see engine.py's
    comment above MOD_MODES for the layout. Columns 3/4 change meaning
    with mod_dest_type; column 5 is blank in "seq" mode (no waveform to
    pick a shape for)."""
    if col == 0:
        return "Mode", t["mod_mode"].upper()
    if col == 1:
        return "Amount", str(t["mod_amount"])
    if col == 2:
        return "Dest", "EXT" if t["mod_dest_type"] == "external" else "INT"
    if col == 3:
        if t["mod_dest_type"] == "external":
            return "CC", str(t["mod_cc"])
        return "Trk", _mod_dest_track_label(e, t)
    if col == 4:
        if t["mod_dest_type"] == "external":
            return "MIDI Channel", str(t["channel"])
        return "Param", t["mod_dest_param"].capitalize()
    if col == 5:
        return "Shape", t["mod_lfo_shape"].upper() if t["mod_mode"] == "lfo" else "-"
    return "-", ""


SEQ_LIST_X = 20
SEQ_LIST_Y = 30
SEQ_LIST_ROW_H = 20
SEQ_LIST_VISIBLE = 6  # rows shown at once. The list scrolls to keep the cursor in view.
SEQ_LIST_W = 400


def _sequence_browser_ops(state):
    """Full-screen takeover for the Set-button sequence browser: "New"
    first, then every saved sequence name, cursor highlighted as a
    filled bar (same look popups use for their box) — see
    State.sequence_browser_active in run.py for how the list is scrolled
    (D-Pad up/down, jog wheel) and confirmed (Jog press / D-Pad center)."""
    black = color("off")
    white = color("white")
    items = ["New"] + state.sequence_names
    cursor = max(0, min(len(items) - 1, state.sequence_cursor))
    ops = [{"kind": "rect", "params": {"x": 0, "y": 0, "w": 960, "h": 160, "c": black}}]
    ops.append({"kind": "text", "params": {"x": SEQ_LIST_X, "baseline": PARAM_LABEL_BASELINE, "s": "SET: SEQUENCES", "c": white}})
    start = max(0, min(cursor - SEQ_LIST_VISIBLE // 2, max(0, len(items) - SEQ_LIST_VISIBLE)))
    for i in range(start, min(len(items), start + SEQ_LIST_VISIBLE)):
        y = SEQ_LIST_Y + (i - start) * SEQ_LIST_ROW_H
        label = items[i]
        if i == cursor:
            ops.append({"kind": "rect", "params": {"x": SEQ_LIST_X, "y": y, "w": SEQ_LIST_W, "h": SEQ_LIST_ROW_H, "c": white}})
            ops.append({"kind": "text", "params": {"x": SEQ_LIST_X + 8, "baseline": y + 15, "s": label, "c": black}})
        else:
            ops.append({"kind": "text", "params": {"x": SEQ_LIST_X + 8, "baseline": y + 15, "s": label, "c": white}})
    return ops


def draw(state):
    e = state.engine
    black = color("off")
    gray = color("gray_green")

    if state.sequence_browser_active:
        ops = _sequence_browser_ops(state)
        if state.popup_title is not None and time.monotonic() < state.popup_until:
            ops.extend(_popup_ops(state.popup_title, state.popup_body))
        return {"ops": ops, "failed": 0}

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
            scale_name = eng.SCALE_LABELS.get(t["scale"]) or t["scale"].replace("_", " ").title()
            ops.append({"kind": "text", "params": {"x": col_w + 4, "baseline": PARAM_LABEL_BASELINE, "s": "Scale", "c": c}})
            ops.append(_value_op(col_w + 4, PARAM_VALUE_BASELINE, scale_name, c))
    elif e.length_view_active:
        # Length view (Clip View button): only column 1 means anything —
        # the selected track's Length, in 1-step increments — the other 7
        # deliberately blank, same shape as Scale mode above.
        t = e.selected()
        if t is not None:
            c = color_by_index(t["color"])
            ops.append({"kind": "text", "params": {"x": 4, "baseline": PARAM_LABEL_BASELINE, "s": "Length", "c": c}})
            ops.append(_value_op(4, PARAM_VALUE_BASELINE, str(t["length"]), c))
    elif e.main_selected:
        # Columns = tracks (view_kind-filtered), every one showing the
        # *same* parameter/column — so all values are directly
        # comparable, and the label is the same in every column. Which
        # cursor (current_param vs current_param_mod) and which column
        # meaning depends on view_kind, since Mod and MIDI tracks never
        # appear together in Main mode.
        held_idx, held_step = _held_step(e)
        if e.view_kind == "mod":
            for col in range(8):
                idx, t = e.track_at(col)
                x = col * col_w
                if t is None:
                    continue
                c = color_by_index(t["color"])
                label, value = _mod_track_column(e, t, e.current_param_mod)
                ops.append({"kind": "text", "params": {"x": x + 4, "baseline": PARAM_LABEL_BASELINE, "s": label, "c": c}})
                ops.append(_value_op(x + 4, PARAM_VALUE_BASELINE, value, c))
        else:
            param_name = eng.ENCODER_PARAMS[e.current_param]
            label = _param_label(param_name)
            for col in range(8):
                idx, t = e.track_at(col)
                x = col * col_w
                if t is None:
                    continue
                c = color_by_index(t["color"])
                this_held_step = held_step if idx == held_idx else None
                if param_name == "pitch":
                    value = _pitch_display_value(e, t, this_held_step)
                else:
                    value = _param_display_value(t, param_name, this_held_step)
                ops.append({"kind": "text", "params": {"x": x + 4, "baseline": PARAM_LABEL_BASELINE, "s": label, "c": c}})
                ops.append(_value_op(x + 4, PARAM_VALUE_BASELINE, value, c))
    elif e.selected() is not None and e.selected()["kind"] == "mod":
        # Columns = the selected Mod track's own 8 fixed columns (mode,
        # amount, dest, ...) — see _mod_track_column.
        t = e.selected()
        c = color_by_index(t["color"])
        for col in range(8):
            x = col * col_w
            label, value = _mod_track_column(e, t, col)
            ops.append({"kind": "text", "params": {"x": x + 4, "baseline": PARAM_LABEL_BASELINE, "s": label, "c": c}})
            ops.append(_value_op(x + 4, PARAM_VALUE_BASELINE, value, c))
    else:
        # Columns = parameters, all for the one selected track (item 2):
        # column 1 = velocity (encoder 1's param), column 2 = gate, etc.
        t = e.selected()
        held_idx, held_step = _held_step(e)
        this_held_step = held_step if held_idx == e.selected_track else None
        for col in range(8):
            param_name = eng.ENCODER_PARAMS[col] if col < len(eng.ENCODER_PARAMS) else None
            x = col * col_w
            c = color_by_index(t["color"]) if t is not None else gray
            if param_name is None:
                continue  # encoder 8 is unused on a MIDI track
            label = _param_label(param_name)
            if t is None:
                value = "n/a"
            elif param_name == "pitch":
                value = _pitch_display_value(e, t, this_held_step)
            else:
                value = _param_display_value(t, param_name, this_held_step)
            ops.append({"kind": "text", "params": {"x": x + 4, "baseline": PARAM_LABEL_BASELINE, "s": label, "c": c}})
            ops.append(_value_op(x + 4, PARAM_VALUE_BASELINE, value, c))

    # Bottom strip: always tracks, regardless of the mode above. It
    # labels the physical "Screen bottom" buttons and pad-grid columns,
    # which never change meaning. The selected track's label is a
    # filled, colored block (a highlighted tab). Every other track's
    # label is colored text on black. No label is highlighted while Main
    # mode is active (see item 1: those buttons are black unless
    # selected). A track that does not actually sound right now (muted,
    # or muted by solo) greys out here too, matching its pads. "Muted" is
    # not just a pad-level fact. It must read at a glance from the label
    # too.
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
    (optional) bigger below it. Reused for every "button did something
    that is not otherwise visible" case (see State.show_popup), not just
    the Tempo readout it started as. Box width fits the widest line,
    because a one-word title ("TEMPO") and a multi-word body ("Melodic
    Sequencer") need very different widths. Centering both text and box
    uses CHAR_W, because there is no real font-metrics API to query."""
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
