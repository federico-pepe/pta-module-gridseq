"""view.py — builds GridSeq's screen (draw ops) and physical pad LED colors.

Op shapes mirror internal/module's Go types exactly (the ABI), same as every
other process module in this app — see hello-py's draw() for the rationale.
No image op: not available over the process-loader IPC.
"""

import json
import os

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


def _track_summary_line(t, selected):
    marker = ">" if selected else " "
    mute = "M" if t["muted"] else " "
    solo = "S" if t["solo"] else " "
    kind = "melo" if t["kind"] == "melodic" else "drum"
    div = t["div"].replace("Scene ", "")
    return "%s%-8.8s %s%s %-4s %-6s" % (marker, t["name"], mute, solo, kind, div)


def _param_value_line(t, param_name):
    if not t["steps"]:
        return "-"
    if param_name == "velocity":
        vals = [s["vel"] for s in t["steps"]]
    elif param_name == "gate":
        vals = [s["gate"] for s in t["steps"]]
    elif param_name == "repeat":
        vals = [s["repeat"] for s in t["steps"]]
    elif param_name == "probability":
        vals = [s["prob"] for s in t["steps"]]
    elif param_name == "offset":
        vals = [s["offset"] for s in t["steps"]]
    elif param_name == "pitch":
        vals = [s["note"] for s in t["steps"]]
    else:
        return "n/a"
    lo, hi = min(vals), max(vals)
    return "%d..%d" % (lo, hi) if lo != hi else str(lo)


def draw(state):
    e = state.engine
    black = color("off")
    white = color("white")
    gray = color("gray_green")

    ops = [
        {"kind": "rect", "params": {"x": 0, "y": 0, "w": 960, "h": 160, "c": black}},
        {"kind": "header", "params": {"y": 0, "w": 960, "h": 18, "s": "GridSeq"}},
    ]

    param_name = eng.PARAM_PAGES[e.param_page]
    col_w = 960 // 8
    for col in range(8):
        idx, t = e.track_at(col)
        x = col * col_w + 4
        if t is None:
            ops.append({"kind": "text", "params": {"x": x, "baseline": 34, "s": "--", "c": gray}})
            continue
        selected = (idx == e.selected_track)
        line1 = _track_summary_line(t, selected)
        line2 = "%s: %s" % (param_name.split(" ")[0][:4], _param_value_line(t, param_name))
        c = white if selected else gray
        ops.append({"kind": "text", "params": {"x": x, "baseline": 34, "s": line1, "c": c}})
        ops.append({"kind": "text", "params": {"x": x, "baseline": 50, "s": line2, "c": c}})

    bpm = e.doc["pattern"]["bpm"]
    sync = "ext" if e.is_externally_synced() else "int"
    play_state = "playing" if e.playing else "stopped"
    status = "BPM %d (%s)  %s  page trk %d-%d  param %d/%d:%s" % (
        bpm, sync, play_state,
        e.track_page + 1, e.track_page + 8,
        e.param_page + 1, len(eng.PARAM_PAGES), param_name,
    )
    ops.append({"kind": "statusbar", "params": {"y": 142, "w": 960, "h": 18, "s": status, "is_error": False}})

    return {"ops": ops, "failed": 0}
