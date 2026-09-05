"""engine.py — GridSeq's sequencer model: tracks, steps, timing, trigger logic.

No I/O here. run.py handles stdin/stdout. view.py handles the display.
This module only advances time and decides what to play.

Design note: push-tethered-app's modules/seq.go uses one shared step
index for all lanes. Here, each Track runs its own time division and
keeps its own step position.
"""

import math
import time

MAX_TRACKS = 32          # 2 pages of 8 columns
DEFAULT_TRACK_COUNT = 8
DEFAULT_STEPS = 8
MAX_STEPS = 64
MIN_BPM, MAX_BPM, DEFAULT_BPM = 40, 240, 120
TICKS_PER_QUARTER = 24   # MIDI clock standard, independent of tempo
EXTERNAL_CLOCK_TIMEOUT = 2.0  # seconds. Matches seq.go's externalClockTimeout.

# Push's 8 "Scene 1/4".."Scene 1/32t" buttons, in beats per step. This
# is the time-division picker for the selected track.
DIVISIONS = {
    "Scene 1/4": 1.0,
    "Scene 1/4t": 2.0 / 3.0,
    "Scene 1/8": 0.5,
    "Scene 1/8t": 1.0 / 3.0,
    "Scene 1/16": 0.25,
    "Scene 1/16t": 1.0 / 6.0,
    "Scene 1/32": 0.125,
    "Scene 1/32t": 1.0 / 12.0,
}
DEFAULT_DIV = "Scene 1/16"

# Semitone offsets from root (0-11). _quantize_to_scale quantizes to
# these (nearest pitch class). Order here is the cycle order for
# Engine.cycle_scale (the Scale knob): diatonic modes first, then
# symmetric scales, pentatonic/blues, then the melodic-minor family. Not
# alphabetical, so the knob groups related sounds together.
SCALES = {
    "chromatic": list(range(12)),
    "major": [0, 2, 4, 5, 7, 9, 11],
    "minor": [0, 2, 3, 5, 7, 8, 10],
    "dorian": [0, 2, 3, 5, 7, 9, 10],
    "mixolydian": [0, 2, 4, 5, 7, 9, 10],
    "lydian": [0, 2, 4, 6, 7, 9, 11],
    "phrygian": [0, 1, 3, 5, 7, 8, 10],
    "locrian": [0, 1, 3, 5, 6, 8, 10],
    "whole_tone": [0, 2, 4, 6, 8, 10],
    "half_whole_dim": [0, 1, 3, 4, 6, 7, 9, 10],
    "whole_half_dim": [0, 2, 3, 5, 6, 8, 9, 11],
    "minor_blues": [0, 3, 5, 6, 7, 10],
    "minor_pentatonic": [0, 3, 5, 7, 10],
    "major_pentatonic": [0, 2, 4, 7, 9],
    "harmonic_minor": [0, 2, 3, 5, 7, 8, 11],
    "harmonic_major": [0, 2, 4, 5, 7, 8, 11],
    "dorian_sharp4": [0, 2, 3, 6, 7, 9, 10],
    "phrygian_dominant": [0, 1, 4, 5, 7, 8, 10],
    "melodic_minor": [0, 2, 3, 5, 7, 9, 11],
    "lydian_augmented": [0, 2, 4, 6, 8, 9, 11],
    "lydian_dominant": [0, 2, 4, 6, 7, 9, 10],
    "super_locrian": [0, 1, 3, 4, 6, 8, 10],
}
SCALE_NAMES = list(SCALES.keys())

# Display overrides for scale names whose title-cased, underscore-split
# form reads wrong, for example "Dorian Sharp4" instead of "Dorian #4".
# Anything not listed here falls back to that generic transform (see
# view.py's scale-name display in draw()).
SCALE_LABELS = {
    "half_whole_dim": "Half-Whole Dim",
    "whole_half_dim": "Whole-Half Dim",
    "dorian_sharp4": "Dorian #4",
}

# The 7 MIDI-track parameters, in encoder order (encoders 1-7 — encoder 8
# is unused on a MIDI track, see plans/2026-09-02-mod-track-redesign.md).
# "Encoder index N" means:
#   - A track is selected (main_selected False): encoder N always edits
#     ENCODER_PARAMS[N] of that track. Fixed 1:1 mapping, all 7
#     parameters live at once, no paging.
#   - Main mode (main_selected True): all visible encoders edit the
#     *same* parameter, ENCODER_PARAMS[current_param], one encoder per
#     track (encoder N -> the Nth visible track). The jog wheel picks
#     which parameter all columns show, by scrolling current_param.
# "channel" is track-level, not per-step (see set_channel). With no pad
# held, turning it changes the track's MIDI channel. A held pad has
# nothing to target, so it does nothing there.
ENCODER_PARAMS = ["velocity", "gate", "repeat", "probability", "offset", "pitch", "channel"]

# A Mod track's 8 encoder columns are fixed slots, not named params from
# a list like ENCODER_PARAMS — columns 3/4's meaning depends on
# mod_dest_type. See Engine.nudge_mod_column and view._mod_track_column
# for the one place each column's meaning is defined:
#   0 mode, 1 amount, 2 dest type,
#   3 CC (external) / dest track (internal),
#   4 MIDI channel (external) / dest param (internal),
#   5 LFO shape (no-op in seq mode), 6-7 reserved for future
#   retrigger/offset/phase.
MOD_MODES = ("seq", "lfo")
MOD_DEST_TYPES = ("external", "internal")
MOD_LFO_SHAPES = ("triangle", "sine", "saw", "square")
MOD_DEST_PARAMS = ["velocity", "gate", "probability", "offset", "pitch"]  # MIDI-track destinations
MOD_DEST_PARAMS_MOD = ["amount"]  # Mod-track destinations — just Amount for now
MOD_COMBINE_MODES = ("offset_additive",)  # only mode that ships; see plan's "Open"
TRACK_KINDS = ("midi", "mod")

# Valid range for each parameter a Mod track can offset internally —
# used to clamp the combined (base + mod) value the same way a step's
# own value is already clamped in _nudge_step_param.
MOD_PARAM_RANGE = {
    "velocity": (1, 127), "gate": (2, 99), "probability": (0, 100),
    "offset": (-45, 45), "pitch": (-127, 127), "amount": (0, 100),
}

# Palette indices (core/push3.Palette, see palette.json) for track
# colors, cycled across DEFAULT_TRACK_COUNT+ tracks. Hand-picked on real
# Push hardware for what reads clearly and stays distinct on the small
# pad LEDs. Do not reorder or regenerate this list without re-testing on
# hardware. Yellow (7) is included on purpose: the active-time-division
# pulse (DIV_ACTIVE_HI/LO in view.py) moved to green, so yellow no longer
# needs to stay reserved.
TRACK_COLORS = [1, 2, 3, 4, 6, 5, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 26, 25]

# New tracks step through TRACK_COLORS by this stride, not 1-by-1.
# Adjacent entries in the hand-picked list can be close hues (for
# example indices 0-3 are all red/orange). A straight walk gives
# neighboring *tracks* similar colors too. 3 is coprime with
# len(TRACK_COLORS) (26 = 2*13), so the walk still visits all 26 colors
# before it repeats. Every track up to MAX_TRACKS (16) gets a color no
# other track has.
TRACK_COLOR_STEP = 3

# Mod tracks default to plain white (palette "white", the same index
# pad LEDs use for bright-white — see palette.json), not a TRACK_COLORS
# entry — keeps them visually distinct from MIDI tracks at a glance.
# Still changeable via the color picker like any other track.
MOD_TRACK_DEFAULT_COLOR = 120

DEFAULT_MOD_TRACK_COUNT = 8

# The color-picker overlay (Shift + Screen-bottom, see Engine.enter_color_
# picker) paints TRACK_COLORS around the grid's border pads, one color per
# pad, starting at pad note 38 (row 0/bottom, col 2 — see run.py's
# pad_note) and walking clockwise: left along the bottom edge, up the left
# edge, right along the top edge, down the right edge, back along the
# bottom to one pad short of the start. (row, col) tuples, row 0 = bottom
# per pad_note's own convention. 28 border pads, 26 TRACK_COLORS — the
# last 2 pads in the walk are left unlit.
COLOR_PICKER_BORDER = [
    (0, 2), (0, 1), (0, 0),
    (1, 0), (2, 0), (3, 0), (4, 0), (5, 0), (6, 0), (7, 0),
    (7, 1), (7, 2), (7, 3), (7, 4), (7, 5), (7, 6), (7, 7),
    (6, 7), (5, 7), (4, 7), (3, 7), (2, 7), (1, 7), (0, 7),
    (0, 6), (0, 5), (0, 4), (0, 3),
]


def color_picker_grid():
    """Maps each border pad's (row, col) to the TRACK_COLORS entry it
    offers in the color-picker overlay. Shared by view.py (drawing the
    overlay) and run.py (hit-testing a pad press against it)."""
    return {pos: TRACK_COLORS[i] for i, pos in enumerate(COLOR_PICKER_BORDER) if i < len(TRACK_COLORS)}


def new_step():
    return {
        "on": False,
        "vel": 100,
        "gate": 50,       # percent of step duration
        "repeat": 1,       # ratchet count, 1 = no ratchet
        "prob": 100,       # percent chance to fire
        "offset": 0,       # micro-timing, -45..+45 percent of step duration
        "accent": False,
        "note": 0,         # semitone offset from track root
    }


def new_track(index):
    return {
        "name": "Track %d" % (index + 1),
        "kind": "midi",     # "midi" or "mod" — see TRACK_KINDS
        "channel": 1,
        "root": 60,
        "scale": "chromatic",
        "div": DEFAULT_DIV,
        "muted": False,
        "solo": False,
        "length": DEFAULT_STEPS,
        "steps": [new_step() for _ in range(DEFAULT_STEPS)],
        "color": TRACK_COLORS[(index * TRACK_COLOR_STEP) % len(TRACK_COLORS)],
        "step_page": 0,     # which 8-step window is being viewed/edited
        # Mod-track-only fields below. Present but inert on a "midi" track,
        # same as "root"/"scale" being inert on a "mod" track — one dict
        # shape for both kinds keeps load()/to_doc()/add_track generic.
        "mod_mode": "seq",           # "seq": plays its own step grid as a value lane.
                                      # "lfo": free-runs a waveform, steps just retrigger it.
        "mod_amount": 100,           # 0-100 depth applied to the raw output
        "mod_dest_type": "external",  # "external": sends a MIDI CC. "internal": offsets
                                       # another track's parameter.
        "mod_cc": 1,                 # external dest: which CC to send, on this track's channel
        "mod_dest_track": None,      # internal dest: target track index
        "mod_dest_param": MOD_DEST_PARAMS[0],  # internal dest: which parameter to offset
        "mod_lfo_shape": "triangle",
        "mod_combine": "offset_additive",  # only mode that ships — see MOD_COMBINE_MODES
        # Runtime-only fields below. Harmless to persist, ignored on load if stale.
        "_pos": 0.0,        # wall-clock track beat position at last resync
        "_current_step": -1,
        "_ext_acc": 0,      # external-clock tick accumulator for this track
        "_mod_seq_value": 0,   # "seq" mode: last value written by an "on" step, held until the next one
        "_lfo_anchor": 0.0,    # "lfo" mode: time.monotonic() at the last phase reset (retrigger or play start)
        "_mod_last_sent": None,  # external dest: last CC value actually sent, to avoid resending unchanged values
    }


def default_pattern():
    tracks = [new_track(i) for i in range(DEFAULT_TRACK_COUNT)]
    for i in range(DEFAULT_MOD_TRACK_COUNT):
        t = new_track(DEFAULT_TRACK_COUNT + i)
        t["kind"] = "mod"
        t["name"] = "MOD %d" % (i + 1)
        t["color"] = MOD_TRACK_DEFAULT_COLOR
        tracks.append(t)
    return {
        "bpm": DEFAULT_BPM,
        "tracks": tracks,
    }


def default_doc():
    # Wrapped with a version so a v3 schema change is an additive branch,
    # not a breaking migration. See the plan's "Schema note for v1".
    return {"version": 1, "pattern": default_pattern()}


class Engine:
    def __init__(self, send_note, note_off, send_cc, log):
        self._send_note = send_note
        self._note_off = note_off
        self._send_cc = send_cc
        self._log = log

        self.doc = default_doc()
        self.playing = False
        self.play_start = None          # time.monotonic() anchor
        self.pending_offs = []          # list of (due_time, channel, note)

        self.track_page = 0             # which 8-column track window is visible
        self.selected_track = 0
        self.view_kind = "midi"         # "midi" or "mod" — which kind of track the columns/paging/select browse.
                                         # Toggled by the Note button. See visible_track_indices/track_at.

        self.held_pad = None            # (col, row) of the currently-held pad, or None
        self.main_selected = False      # True: the 8 columns are tracks, all showing one shared parameter
        self.current_param = 0          # index into ENCODER_PARAMS (view_kind "midi"). Set by the jog wheel in Main mode.
        self.current_param_mod = 0      # same, but the 0-7 Mod-track column index (view_kind "mod")

        self._mod_mode_accum = 0
        self._mod_dest_type_accum = 0
        self._mod_lfo_shape_accum = 0
        self._mod_dest_track_accum = 0
        self._mod_dest_param_accum = 0

        self.color_picker_active = False  # True: grid is borrowed for the color-picker border overlay
        self.color_picker_track = None    # track index the picked color will be assigned to

        self.scale_mode_active = False  # True: encoders 1/2 are Key/Scale for the selected track, the rest blank
        self._key_accum = 0             # accumulated raw encoder delta not yet enough to step Key once
        self._scale_accum = 0           # same, for Scale
        self._channel_accum = 0         # same, for MIDI Channel
        self._param_accum = {}          # same, per THROTTLED_PARAMS name — see nudge_param

        self.length_view_active = False  # True: encoder 1 is the selected track's Length, the rest blank
        self._length_accum = 0           # same accumulated-turn technique, for Length

        self.last_ext_clock = None
        self.ext_synced_before = False

        self.mods = {
            "mute": False, "solo": False,
            "repeat": False, "accent": False,
            "shift": False, "delete": False,
        }

    # -- persistence -----------------------------------------------------

    def load(self, doc):
        if not doc:
            return
        if doc.get("version") != 1:
            return  # unknown/future schema: keep defaults rather than guess
        pattern = doc.get("pattern")
        if not pattern:
            return
        self.doc["pattern"]["bpm"] = pattern.get("bpm", DEFAULT_BPM)
        saved_tracks = pattern.get("tracks") or []
        tracks = []
        for i, saved in enumerate(saved_tracks[:MAX_TRACKS]):
            t = new_track(i)
            t.update({k: v for k, v in saved.items() if k in t and not k.startswith("_")})
            length = max(1, min(MAX_STEPS, int(t.get("length", DEFAULT_STEPS))))
            t["length"] = length
            steps = saved.get("steps") or []
            filled = []
            for j in range(length):
                s = new_step()
                if j < len(steps) and isinstance(steps[j], dict):
                    s.update({k: v for k, v in steps[j].items() if k in s})
                filled.append(s)
            t["steps"] = filled

            if t["kind"] not in TRACK_KINDS:
                t["kind"] = "midi"
            if t["mod_mode"] not in MOD_MODES:
                t["mod_mode"] = "seq"
            if t["mod_dest_type"] not in MOD_DEST_TYPES:
                t["mod_dest_type"] = "external"
            if t["mod_lfo_shape"] not in MOD_LFO_SHAPES:
                t["mod_lfo_shape"] = "triangle"
            if t["mod_combine"] not in MOD_COMBINE_MODES:
                t["mod_combine"] = "offset_additive"
            if t["mod_dest_param"] not in MOD_DEST_PARAMS and t["mod_dest_param"] not in MOD_DEST_PARAMS_MOD:
                t["mod_dest_param"] = MOD_DEST_PARAMS[0]
            if not isinstance(t["mod_dest_track"], int) or t["mod_dest_track"] == i or \
                    not (0 <= t["mod_dest_track"] < MAX_TRACKS):
                t["mod_dest_track"] = None
            t["mod_amount"] = max(0, min(100, int(t.get("mod_amount", 100))))
            t["mod_cc"] = max(0, min(127, int(t.get("mod_cc", 1))))

            tracks.append(t)
        if tracks:
            self.doc["pattern"]["tracks"] = tracks

    def to_doc(self):
        # Strip runtime-only fields before persisting.
        pattern = self.doc["pattern"]
        clean_tracks = []
        for t in pattern["tracks"]:
            ct = {k: v for k, v in t.items() if not k.startswith("_")}
            clean_tracks.append(ct)
        return {"version": 1, "pattern": {"bpm": pattern["bpm"], "tracks": clean_tracks}}

    # -- track helpers -----------------------------------------------------

    @property
    def tracks(self):
        return self.doc["pattern"]["tracks"]

    def visible_track_indices(self):
        """Absolute track indices whose kind matches view_kind, in order —
        what the 8 grid columns / Screen-bottom row / Page Left-Right
        actually browse. See track_at."""
        return [i for i, t in enumerate(self.tracks) if t["kind"] == self.view_kind]

    def _tracks_of_kind(self, kind):
        return [i for i, t in enumerate(self.tracks) if t["kind"] == kind]

    def track_at(self, col):
        visible = self.visible_track_indices()
        pos = self.track_page + col
        if 0 <= pos < len(visible):
            idx = visible[pos]
            return idx, self.tracks[idx]
        return None, None

    def toggle_view_kind(self):
        """Wired to the Note button (CC50): flips which kind of track the
        columns/paging/select browse. Resets navigation the same way
        enter_sequence does, because the old selection/page can point
        past the new kind's visible tracks."""
        self.view_kind = "mod" if self.view_kind == "midi" else "midi"
        self.track_page = 0
        self.main_selected = False
        self.scale_mode_active = False
        self.length_view_active = False
        visible = self.visible_track_indices()
        self.selected_track = visible[0] if visible else 0

    def selected(self):
        if 0 <= self.selected_track < len(self.tracks):
            return self.tracks[self.selected_track]
        return None

    def toggle_main(self):
        self.main_selected = not self.main_selected
        if self.main_selected:
            self.scale_mode_active = False  # exclusive with Scale mode, which requires a specific track selected
            self.length_view_active = False  # same, for Clip View's Length overlay

    def select_track(self, track_idx):
        """Picking a specific track (Screen-bottom button or the jog wheel)
        always leaves Main mode — Main is reached only via its own
        "Select (main)" button."""
        self.selected_track = track_idx
        self.main_selected = False

    def any_solo(self):
        return any(t["solo"] for t in self.tracks)

    def track_audible(self, t):
        if t["muted"]:
            return False
        if self.any_solo() and not t["solo"]:
            return False
        return True

    def step_duration(self, track, bpm):
        beats_per_step = DIVISIONS.get(track["div"], DIVISIONS[DEFAULT_DIV])
        return (60.0 / max(1, bpm)) * beats_per_step

    # -- transport -----------------------------------------------------

    def toggle_play(self):
        if self.playing:
            self.stop()
        else:
            self.start()

    def start(self):
        self.playing = True
        self.play_start = time.monotonic()
        for t in self.tracks:
            t["_current_step"] = -1
            t["_ext_acc"] = 0
            t["_mod_seq_value"] = 0
            t["_lfo_anchor"] = self.play_start
            t["_mod_last_sent"] = None

    def stop(self):
        self.playing = False
        self._release_all_pending(time.monotonic())
        for t in self.tracks:
            t["_current_step"] = -1

    # -- pad / step editing -----------------------------------------------------

    def toggle_step(self, track_idx, step_idx):
        t = self.tracks[track_idx]
        if 0 <= step_idx < t["length"]:
            t["steps"][step_idx]["on"] = not t["steps"][step_idx]["on"]

    def toggle_accent(self, track_idx, step_idx):
        t = self.tracks[track_idx]
        if 0 <= step_idx < t["length"]:
            t["steps"][step_idx]["accent"] = not t["steps"][step_idx]["accent"]

    def set_division(self, track_idx, div_name):
        if track_idx is None:
            return
        t = self.tracks[track_idx]
        if div_name in DIVISIONS:
            t["div"] = div_name

    def set_length(self, track_idx, new_length, floor=DEFAULT_STEPS):
        """Grows or shrinks the track's step count. Growing appends fresh
        steps. Shrinking truncates the tail (this loses data, same as
        load()'s existing clamp-to-length behavior). `floor` defaults to
        DEFAULT_STEPS (8), for Shift + D-Pad up/down, which moves in
        whole 8-step pages and must not leave a page with nothing to land
        on. nudge_length (the Clip View length knob, 1-step resolution)
        passes floor=1 instead, because a track can be as short as one
        step."""
        if track_idx is None:
            return
        t = self.tracks[track_idx]
        new_length = max(floor, min(MAX_STEPS, new_length))
        if new_length == t["length"]:
            return
        if new_length > t["length"]:
            t["steps"].extend(new_step() for _ in range(new_length - t["length"]))
        else:
            t["steps"] = t["steps"][:new_length]
        t["length"] = new_length
        last_page = (new_length - 1) // 8
        if t["step_page"] > last_page:
            t["step_page"] = last_page

    # -- mod track params -----------------------------------------------------

    def nudge_mod_step_value(self, track_idx, step_idx, delta):
        """Held-pad editing on a "seq"-mode Mod track's own grid: the
        Amount column (column 1) edits that one step's stored value
        instead of the track's overall mod_amount depth — same shape as
        a MIDI track's velocity column, just 0-127 rather than 1-127
        since a Mod step can validly hold zero."""
        t = self.tracks[track_idx]
        if 0 <= step_idx < t["length"]:
            t["steps"][step_idx]["vel"] = max(0, min(127, t["steps"][step_idx]["vel"] + delta))

    def nudge_mod_amount(self, track_idx, delta):
        t = self.tracks[track_idx]
        t["mod_amount"] = max(0, min(100, t["mod_amount"] + delta))

    def nudge_mod_cc(self, track_idx, delta):
        t = self.tracks[track_idx]
        t["mod_cc"] = max(0, min(127, t["mod_cc"] + delta))

    def cycle_mod_mode(self, track_idx, forward=True):
        # Clamps, does not wrap — same "stop at the ends" choice as
        # cycle_scale/cycle_key, so turning past SEQ or LFO does nothing
        # instead of jumping to the other end.
        t = self.tracks[track_idx]
        i = MOD_MODES.index(t["mod_mode"])
        i = max(0, min(len(MOD_MODES) - 1, i + (1 if forward else -1)))
        t["mod_mode"] = MOD_MODES[i]

    def nudge_mod_mode(self, track_idx, delta):
        self._mod_mode_accum += delta
        while self._mod_mode_accum >= self.KNOB_ACCUM_THRESHOLD:
            self.cycle_mod_mode(track_idx, True)
            self._mod_mode_accum -= self.KNOB_ACCUM_THRESHOLD
        while self._mod_mode_accum <= -self.KNOB_ACCUM_THRESHOLD:
            self.cycle_mod_mode(track_idx, False)
            self._mod_mode_accum += self.KNOB_ACCUM_THRESHOLD

    def cycle_mod_dest_type(self, track_idx, forward=True):
        # Clamps, does not wrap — see cycle_mod_mode.
        t = self.tracks[track_idx]
        i = MOD_DEST_TYPES.index(t["mod_dest_type"])
        i = max(0, min(len(MOD_DEST_TYPES) - 1, i + (1 if forward else -1)))
        t["mod_dest_type"] = MOD_DEST_TYPES[i]

    def nudge_mod_dest_type(self, track_idx, delta):
        self._mod_dest_type_accum += delta
        while self._mod_dest_type_accum >= self.KNOB_ACCUM_THRESHOLD:
            self.cycle_mod_dest_type(track_idx, True)
            self._mod_dest_type_accum -= self.KNOB_ACCUM_THRESHOLD
        while self._mod_dest_type_accum <= -self.KNOB_ACCUM_THRESHOLD:
            self.cycle_mod_dest_type(track_idx, False)
            self._mod_dest_type_accum += self.KNOB_ACCUM_THRESHOLD

    def cycle_mod_lfo_shape(self, track_idx, forward=True):
        t = self.tracks[track_idx]
        i = MOD_LFO_SHAPES.index(t["mod_lfo_shape"])
        t["mod_lfo_shape"] = MOD_LFO_SHAPES[(i + (1 if forward else -1)) % len(MOD_LFO_SHAPES)]

    def nudge_mod_lfo_shape(self, track_idx, delta):
        self._mod_lfo_shape_accum += delta
        while self._mod_lfo_shape_accum >= self.KNOB_ACCUM_THRESHOLD:
            self.cycle_mod_lfo_shape(track_idx, True)
            self._mod_lfo_shape_accum -= self.KNOB_ACCUM_THRESHOLD
        while self._mod_lfo_shape_accum <= -self.KNOB_ACCUM_THRESHOLD:
            self.cycle_mod_lfo_shape(track_idx, False)
            self._mod_lfo_shape_accum += self.KNOB_ACCUM_THRESHOLD

    def cycle_mod_dest_track(self, track_idx, forward=True):
        """Cycles mod_dest_track among every *other* track — MIDI or Mod.
        A Mod track can modulate another Mod track (for example, one
        LFO's rate-of-change driving another's Amount), just not itself.
        Resets mod_dest_param if it doesn't apply to the new
        destination's kind (see _mod_dest_param_options)."""
        t = self.tracks[track_idx]
        candidates = [i for i in range(len(self.tracks)) if i != track_idx]
        if not candidates:
            t["mod_dest_track"] = None
            return
        cur = t["mod_dest_track"]
        i = candidates.index(cur) if cur in candidates else (-1 if forward else len(candidates))
        i = max(0, min(len(candidates) - 1, i + (1 if forward else -1)))
        t["mod_dest_track"] = candidates[i]
        options = self._mod_dest_param_options(track_idx)
        if t["mod_dest_param"] not in options:
            t["mod_dest_param"] = options[0]

    def nudge_mod_dest_track(self, track_idx, delta):
        self._mod_dest_track_accum += delta
        while self._mod_dest_track_accum >= self.KNOB_ACCUM_THRESHOLD:
            self.cycle_mod_dest_track(track_idx, True)
            self._mod_dest_track_accum -= self.KNOB_ACCUM_THRESHOLD
        while self._mod_dest_track_accum <= -self.KNOB_ACCUM_THRESHOLD:
            self.cycle_mod_dest_track(track_idx, False)
            self._mod_dest_track_accum += self.KNOB_ACCUM_THRESHOLD

    def _mod_dest_param_options(self, track_idx):
        """Which param list applies depends on the destination track's
        kind — a Mod track has no velocity/gate/pitch to offset, only
        its own Amount."""
        t = self.tracks[track_idx]
        dest = t["mod_dest_track"]
        if dest is not None and 0 <= dest < len(self.tracks) and self.tracks[dest]["kind"] == "mod":
            return MOD_DEST_PARAMS_MOD
        return MOD_DEST_PARAMS

    def cycle_mod_dest_param(self, track_idx, forward=True):
        t = self.tracks[track_idx]
        options = self._mod_dest_param_options(track_idx)
        i = options.index(t["mod_dest_param"]) if t["mod_dest_param"] in options else 0
        i = max(0, min(len(options) - 1, i + (1 if forward else -1)))
        t["mod_dest_param"] = options[i]

    def nudge_mod_dest_param(self, track_idx, delta):
        self._mod_dest_param_accum += delta
        while self._mod_dest_param_accum >= self.KNOB_ACCUM_THRESHOLD:
            self.cycle_mod_dest_param(track_idx, True)
            self._mod_dest_param_accum -= self.KNOB_ACCUM_THRESHOLD
        while self._mod_dest_param_accum <= -self.KNOB_ACCUM_THRESHOLD:
            self.cycle_mod_dest_param(track_idx, False)
            self._mod_dest_param_accum += self.KNOB_ACCUM_THRESHOLD

    def nudge_mod_column(self, track_idx, col, delta):
        """Dispatches one of a Mod track's 8 Track-mode encoder columns —
        see MOD_MODES's comment above ENCODER_PARAMS for the fixed column
        layout. Columns 6-7 are reserved (no-op) for now."""
        t = self.tracks[track_idx]
        if col == 0:
            self.nudge_mod_mode(track_idx, delta)
        elif col == 1:
            self.nudge_mod_amount(track_idx, delta)
        elif col == 2:
            self.nudge_mod_dest_type(track_idx, delta)
        elif col == 3:
            if t["mod_dest_type"] == "external":
                self.nudge_mod_cc(track_idx, delta)
            else:
                self.nudge_mod_dest_track(track_idx, delta)
        elif col == 4:
            if t["mod_dest_type"] == "external":
                self.nudge_channel(track_idx, delta)
            else:
                self.nudge_mod_dest_param(track_idx, delta)
        elif col == 5:
            self.nudge_mod_lfo_shape(track_idx, delta)

    # -- color picker -----------------------------------------------------

    def enter_color_picker(self, track_idx):
        """Wired to Shift + Screen-bottom N: selects that track (same as a
        plain Screen-bottom press) and borrows the grid for the
        color-picker border overlay (see color_picker_grid). Exited only
        by releasing Shift — see run.py's Shift handling."""
        self.select_track(track_idx)
        self.color_picker_active = True
        self.color_picker_track = track_idx

    def exit_color_picker(self):
        self.color_picker_active = False
        self.color_picker_track = None

    def set_track_color(self, color_idx):
        if self.color_picker_track is None:
            return
        if 0 <= self.color_picker_track < len(self.tracks):
            self.tracks[self.color_picker_track]["color"] = color_idx

    def set_channel(self, track_idx, delta):
        """Track-level, not per-step — one MIDI channel (1-16) per whole
        track, stepped by 1 per call regardless of delta magnitude. Call
        via nudge_channel from encoder input (not directly) so a whole
        accumulated turn is needed per step, not just a nonzero delta."""
        if track_idx is None:
            return
        t = self.tracks[track_idx]
        step = 1 if delta > 0 else -1 if delta < 0 else 0
        t["channel"] = max(1, min(16, t["channel"] + step))

    def nudge_channel(self, track_idx, delta):
        self._channel_accum += delta
        while self._channel_accum >= self.KNOB_ACCUM_THRESHOLD:
            self.set_channel(track_idx, 1)
            self._channel_accum -= self.KNOB_ACCUM_THRESHOLD
        while self._channel_accum <= -self.KNOB_ACCUM_THRESHOLD:
            self.set_channel(track_idx, -1)
            self._channel_accum += self.KNOB_ACCUM_THRESHOLD

    def enter_sequence(self, doc):
        """Swaps in a whole different sequence. Wired to the Set-button
        browser's confirm gesture. `doc=None` means "New" (a fresh
        default pattern). Otherwise `doc` is a saved sequence's file
        contents, run through the normal `load()` clamping. Unlike
        `load()` alone, this also resets navigation and overlay state
        (track_page, selected_track, which mode or overlay was open),
        because loading a different pattern can leave any of those
        pointing past the new pattern's edges, or in a mode that no
        longer makes sense. It also stops playback first, so the old
        pattern's notes do not hang."""
        self.stop()
        self.doc = default_doc()
        if doc is not None:
            self.load(doc)
        self.track_page = 0
        self.selected_track = 0
        self.view_kind = "midi"
        self.held_pad = None
        self.main_selected = False
        self.scale_mode_active = False
        self.length_view_active = False
        self.current_param = 0
        self.current_param_mod = 0

    def add_track(self, duplicate_from=None):
        """Appends a new track (up to MAX_TRACKS) — the only way a track
        count grows past DEFAULT_TRACK_COUNT, wired to the "Duplicate"
        button. Without this, Page Left/Right had nowhere to page *to*,
        which is why paging looked broken before this existed."""
        if len(self.tracks) >= MAX_TRACKS:
            return False
        idx = len(self.tracks)
        t = new_track(idx)
        t["kind"] = self.view_kind
        if t["kind"] == "mod":
            t["name"] = "MOD %d" % (len(self._tracks_of_kind("mod")) + 1)
            t["color"] = MOD_TRACK_DEFAULT_COLOR
        if duplicate_from is not None and 0 <= duplicate_from < len(self.tracks) and \
                self.tracks[duplicate_from]["kind"] == self.view_kind:
            src = self.tracks[duplicate_from]
            t["channel"] = src["channel"]
            t["div"] = src["div"]
            t["root"] = src["root"]
            t["scale"] = src["scale"]
            t["length"] = src["length"]
            t["steps"] = [dict(s) for s in src["steps"]]
            if t["kind"] == "mod":
                t["mod_mode"] = src["mod_mode"]
                t["mod_amount"] = src["mod_amount"]
                t["mod_dest_type"] = src["mod_dest_type"]
                t["mod_cc"] = src["mod_cc"]
                t["mod_dest_track"] = src["mod_dest_track"]
                t["mod_dest_param"] = src["mod_dest_param"]
                t["mod_lfo_shape"] = src["mod_lfo_shape"]
                t["mod_combine"] = src["mod_combine"]
        self.tracks.append(t)
        return True

    def remove_track(self, track_idx):
        """Wired to Delete (hold) + a track's Screen-bottom button — works
        on either kind of track. Refuses to remove the last track left in
        the whole pool (not just the last of one kind — an empty Mod view
        is fine, an entirely empty pool is not). Every other Mod track's
        mod_dest_track is reindexed to follow the shift, or cleared if it
        pointed at the removed track."""
        if track_idx is None or not (0 <= track_idx < len(self.tracks)):
            return False
        if len(self.tracks) <= 1:
            return False
        del self.tracks[track_idx]
        for t in self.tracks:
            dest = t["mod_dest_track"]
            if dest is None:
                continue
            if dest == track_idx:
                t["mod_dest_track"] = None
            elif dest > track_idx:
                t["mod_dest_track"] = dest - 1
        if self.selected_track > track_idx:
            self.selected_track -= 1
        elif self.selected_track >= len(self.tracks):
            self.selected_track = len(self.tracks) - 1
        self.track_page = 0
        self.held_pad = None
        visible = self.visible_track_indices()
        if self.selected_track not in visible:
            self.selected_track = visible[0] if visible else 0
        return True

    def cycle_scale(self, track_idx, forward=True):
        # Clamps, does not wrap. At either end of SCALE_NAMES, it just
        # stops. Turning further the same way does nothing. Only
        # reversing direction moves it again (cycle_key does the same).
        if track_idx is None:
            return
        t = self.tracks[track_idx]
        i = SCALE_NAMES.index(t["scale"]) if t["scale"] in SCALE_NAMES else 0
        i = max(0, min(len(SCALE_NAMES) - 1, i + (1 if forward else -1)))
        t["scale"] = SCALE_NAMES[i]

    def cycle_key(self, track_idx, forward=True):
        """Steps the track's root by one pitch class (semitone) within
        its current octave — e.g. root=61 (C#4) forward becomes 62 (D4).
        Clamps at B/C (11/0), same as cycle_scale, even though a pitch
        class is circular in music theory (B -> C is a completely normal
        move) — explicitly requested as "the knobs" without carving Key
        out, and clamping here is harmless: Octave Up/Down already
        covers moving to a different octave's C. Octave itself never
        moves here, only via Octave Up/Down (global, all tracks)."""
        if track_idx is None:
            return
        t = self.tracks[track_idx]
        octave_part, pitch_class = divmod(t["root"], 12)
        pitch_class = max(0, min(11, pitch_class + (1 if forward else -1)))
        t["root"] = max(0, min(127, octave_part * 12 + pitch_class))

    # Accumulated *raw* encoder delta (not detents) needed before Key/Scale
    # actually steps once. Push's relative encoders can send a nonzero
    # delta on every small wiggle, and stepping a 12-item/6-item list on
    # every single one of those felt too twitchy — this makes a
    # deliberate turn amount required per step instead of 1 tick = 1 step.
    KNOB_ACCUM_THRESHOLD = 4

    def nudge_key(self, track_idx, delta):
        self._key_accum += delta
        while self._key_accum >= self.KNOB_ACCUM_THRESHOLD:
            self.cycle_key(track_idx, forward=True)
            self._key_accum -= self.KNOB_ACCUM_THRESHOLD
        while self._key_accum <= -self.KNOB_ACCUM_THRESHOLD:
            self.cycle_key(track_idx, forward=False)
            self._key_accum += self.KNOB_ACCUM_THRESHOLD

    def nudge_scale(self, track_idx, delta):
        self._scale_accum += delta
        while self._scale_accum >= self.KNOB_ACCUM_THRESHOLD:
            self.cycle_scale(track_idx, forward=True)
            self._scale_accum -= self.KNOB_ACCUM_THRESHOLD
        while self._scale_accum <= -self.KNOB_ACCUM_THRESHOLD:
            self.cycle_scale(track_idx, forward=False)
            self._scale_accum += self.KNOB_ACCUM_THRESHOLD

    def toggle_scale_mode(self):
        """Wired to the "Scale" button (a plain toggle now, not a hold).
        Enterable only with a specific track selected. Scale mode shows
        Key/Scale for *the* selected track, which means nothing in Main
        mode (many tracks) or for a Mod track (no pitch concept)."""
        selected = self.selected()
        if not self.scale_mode_active and (self.main_selected or (selected and selected["kind"] == "mod")):
            return
        self.scale_mode_active = not self.scale_mode_active
        if self.scale_mode_active:
            # Fresh accumulators on entry. A partial turn left over from
            # several sessions ago must not bias the very next tick.
            self._key_accum = 0
            self._scale_accum = 0
            self.length_view_active = False  # exclusive with Clip View's Length overlay

    def toggle_length_view(self):
        """Wired to the "Clip View" button (CC113, a plain toggle like
        Scale). Only encoder 1 does anything while active — the selected
        track's Length, in 1-step increments (unlike Shift + D-Pad
        up/down's 8-step pages) — same "needs a specific track selected"
        gating as Scale mode, and exclusive with it for the same reason:
        both use the top-of-screen label/value row for something other
        than Track mode's normal 8-parameter row."""
        if not self.length_view_active and self.main_selected:
            return
        self.length_view_active = not self.length_view_active
        if self.length_view_active:
            self._length_accum = 0
            self.scale_mode_active = False

    def nudge_length(self, track_idx, delta):
        self._length_accum += delta
        while self._length_accum >= self.KNOB_ACCUM_THRESHOLD:
            t = self.tracks[track_idx] if track_idx is not None and 0 <= track_idx < len(self.tracks) else None
            if t is not None:
                self.set_length(track_idx, t["length"] + 1, floor=1)
            self._length_accum -= self.KNOB_ACCUM_THRESHOLD
        while self._length_accum <= -self.KNOB_ACCUM_THRESHOLD:
            t = self.tracks[track_idx] if track_idx is not None and 0 <= track_idx < len(self.tracks) else None
            if t is not None:
                self.set_length(track_idx, t["length"] - 1, floor=1)
            self._length_accum += self.KNOB_ACCUM_THRESHOLD

    # Params where an accumulated turn is required per step, same
    # technique (and threshold) as nudge_key/nudge_scale. A plain
    # per-message delta felt too twitchy for these specifically.
    # Velocity/gate/probability are deliberately left at full,
    # per-message sensitivity. They are 0-100/1-127-range continuous
    # values, where fast, fine adjustment is the point.
    THROTTLED_PARAMS = ("pitch", "offset", "repeat")

    def nudge_param(self, track_idx, step_idx, param, delta):
        """Edits one step's param if step_idx is given (a pad is held),
        otherwise nudges the track's default and rescales existing steps
        by the same relative amount — the OXI "global knob" feel."""
        if param in self.THROTTLED_PARAMS:
            accum = self._param_accum.get(param, 0) + delta
            step_delta = 0
            while accum >= self.KNOB_ACCUM_THRESHOLD:
                step_delta += 1
                accum -= self.KNOB_ACCUM_THRESHOLD
            while accum <= -self.KNOB_ACCUM_THRESHOLD:
                step_delta -= 1
                accum += self.KNOB_ACCUM_THRESHOLD
            self._param_accum[param] = accum
            if step_delta == 0:
                return
            delta = step_delta

        t = self.tracks[track_idx]
        if step_idx is not None and 0 <= step_idx < t["length"]:
            self._nudge_step_param(t["steps"][step_idx], param, delta)
            return
        for step in t["steps"]:
            self._nudge_step_param(step, param, delta)

    # param name -> new_step() field, for reset_param below. Same mapping
    # view.py's _PARAM_FIELD uses for display, duplicated here rather than
    # imported since engine.py never imports view.py (the reverse is true).
    _RESET_FIELD = {
        "velocity": "vel", "gate": "gate", "repeat": "repeat",
        "probability": "prob", "offset": "offset", "pitch": "note",
    }

    def reset_param(self, track_idx, step_idx, param):
        """Snaps one param back to new_step()'s (or, for "channel",
        new_track()'s) default value — wired to Delete (hold) + touch an
        encoder. Same step_idx=None-means-every-step convention as
        nudge_param: a held pad targets just that step, nothing held
        resets every step on the track."""
        if track_idx is None:
            return
        t = self.tracks[track_idx]
        if param == "channel":
            t["channel"] = new_track(0)["channel"]
            return
        field = self._RESET_FIELD.get(param)
        if field is None:
            return
        default_value = new_step()[field]
        if step_idx is not None and 0 <= step_idx < t["length"]:
            t["steps"][step_idx][field] = default_value
            return
        for step in t["steps"]:
            step[field] = default_value

    @staticmethod
    def _nudge_step_param(step, param, delta):
        if param == "velocity":
            step["vel"] = max(1, min(127, step["vel"] + delta))
        elif param == "gate":
            step["gate"] = max(2, min(99, step["gate"] + delta))
        elif param == "repeat":
            step["repeat"] = max(1, min(8, step["repeat"] + (1 if delta > 0 else -1 if delta < 0 else 0)))
        elif param == "probability":
            step["prob"] = max(0, min(100, step["prob"] + delta))
        elif param == "offset":
            step["offset"] = max(-45, min(45, step["offset"] + delta))
        elif param == "pitch":
            # +/-127 covers every reachable absolute note (0-127) from any
            # root (0-127) — the old +/-24 clamp made notes below ~C2/above
            # ~C6 unreachable whenever root sat near the middle of its own
            # range. delta arrives pre-throttled (see THROTTLED_PARAMS) but
            # not sign-reduced like "repeat" — a fast turn can still move
            # several units in one call, just not on every tiny wiggle.
            step["note"] = max(-127, min(127, step["note"] + delta))
        # "channel" (track-level, see set_channel) never reaches here:
        # run.py routes it elsewhere before calling nudge_param.

    # -- octave / transpose -----------------------------------------------------

    def transpose_all(self, semitones):
        for t in self.tracks:
            t["root"] = max(0, min(127, t["root"] + semitones))

    # -- timing / trigger -----------------------------------------------------

    def is_externally_synced(self):
        if self.last_ext_clock is None:
            return False
        return (time.monotonic() - self.last_ext_clock) < EXTERNAL_CLOCK_TIMEOUT

    def on_external_clock_byte(self, first_byte):
        now = time.monotonic()
        if first_byte == 0xF8:      # Timing Clock
            self.last_ext_clock = now
            if not self.ext_synced_before:
                self.ext_synced_before = True
            for idx, t in enumerate(self.tracks):
                t["_ext_acc"] += 1
                beats_per_step = DIVISIONS.get(t["div"], DIVISIONS[DEFAULT_DIV])
                ticks_per_step = max(1, round(TICKS_PER_QUARTER * beats_per_step))
                if t["_ext_acc"] >= ticks_per_step:
                    t["_ext_acc"] = 0
                    self._advance_step(idx, now)
                if t["kind"] == "mod" and t["mod_mode"] == "lfo" and t["mod_dest_type"] == "external":
                    self._emit_mod_output(idx, now)
        elif first_byte == 0xFA:    # Start
            self.play_start = now
            self.playing = True
            for t in self.tracks:
                t["_current_step"] = -1
                t["_ext_acc"] = 0
                t["_mod_seq_value"] = 0
                t["_lfo_anchor"] = now
                t["_mod_last_sent"] = None
        elif first_byte == 0xFB:    # Continue
            self.playing = True
        elif first_byte == 0xFC:    # Stop
            self.stop()

    def tick(self, now=None):
        """Called every draw. Advances wall-clock-driven tracks (used only
        while not externally synced) and releases any pending note-offs."""
        now = now if now is not None else time.monotonic()
        self._release_due(now)

        synced = self.is_externally_synced()
        if synced:
            # The external clock path already advances steps in
            # on_external_clock_byte. Re-anchor so playback does not
            # jump on drop-out.
            self.play_start = now
            for t in self.tracks:
                t["_pos"] = 0.0
            return

        if self.ext_synced_before:
            self.ext_synced_before = False

        if not self.playing or self.play_start is None:
            return

        bpm = self.doc["pattern"]["bpm"]
        elapsed = now - self.play_start
        for idx, t in enumerate(self.tracks):
            step_dur = self.step_duration(t, bpm)
            step_idx = int(elapsed / step_dur) % t["length"]
            if step_idx != t["_current_step"]:
                t["_current_step"] = step_idx
                self._trigger_step(idx, step_idx, now)
            if t["kind"] == "mod" and t["mod_mode"] == "lfo" and t["mod_dest_type"] == "external":
                self._emit_mod_output(idx, now)

    def _advance_step(self, track_idx, now):
        t = self.tracks[track_idx]
        t["_current_step"] = (t["_current_step"] + 1) % t["length"]
        self._trigger_step(track_idx, t["_current_step"], now)

    # -- mod track output -----------------------------------------------------

    def _mod_output_raw(self, track_idx, now):
        """This Mod track's current output value, 0-127, before mod_amount
        scaling — the raw sequenced value ("seq" mode) or the raw
        waveform sample ("lfo" mode). Read both by _emit_mod_output (the
        push path, external dest) and by _apply_mod (the pull path,
        internal dest)."""
        t = self.tracks[track_idx]
        if t["mod_mode"] == "lfo":
            bpm = self.doc["pattern"]["bpm"]
            period = max(0.01, self.step_duration(t, bpm))
            phase = ((now - t["_lfo_anchor"]) / period) % 1.0
            return round(self._lfo_waveform(t["mod_lfo_shape"], phase) * 127)
        return t["_mod_seq_value"]

    @staticmethod
    def _lfo_waveform(shape, phase):
        """phase is 0..1 (one full cycle). Returns 0..1."""
        if shape == "sine":
            return (math.sin(phase * 2 * math.pi) + 1) / 2
        if shape == "saw":
            return phase
        if shape == "square":
            return 1.0 if phase < 0.5 else 0.0
        return 1.0 - abs(phase * 2 - 1)  # triangle

    def _effective_mod_amount(self, track_idx, now):
        """This track's own mod_amount (0-100), possibly offset by
        another Mod track targeting its Amount internally. Deliberately
        does not recurse further than this one level — _apply_mod's own
        loop always uses a modulator's raw mod_amount, never this — so a
        mutual amount<->amount routing between two Mod tracks cannot
        loop forever."""
        t = self.tracks[track_idx]
        return self._apply_mod(track_idx, "amount", t["mod_amount"], now)

    def _emit_mod_output(self, track_idx, now):
        """Sends the current output as a CC, if this track's dest is
        external and the scaled value actually changed since the last
        send — a "seq" track only changes on its own "on" steps, but an
        "lfo" track is called every tick, and re-sending an unchanged CC
        every frame would flood the host for nothing."""
        t = self.tracks[track_idx]
        if t["mod_dest_type"] != "external":
            return
        raw = self._mod_output_raw(track_idx, now)
        amount = self._effective_mod_amount(track_idx, now)
        scaled = max(0, min(127, round(raw * (amount / 100.0))))
        if scaled == t["_mod_last_sent"]:
            return
        t["_mod_last_sent"] = scaled
        self._send_cc(t["channel"], t["mod_cc"], scaled)

    def _trigger_mod_track_step(self, track_idx, step, now):
        """Unlike a MIDI track, this runs on *every* step, on or off —
        an "off" step needs to actively zero the seq output, not just be
        skipped, or the last "on" step's value would keep applying
        forever (see plans/2026-09-02-mod-track-redesign.md's
        follow-up)."""
        t = self.tracks[track_idx]
        if t["mod_mode"] == "lfo":
            if step["on"]:
                t["_lfo_anchor"] = now  # retrigger: restart the waveform's phase here
        else:
            t["_mod_seq_value"] = step["vel"] if step["on"] else 0
        self._emit_mod_output(track_idx, now)

    def _apply_mod(self, dest_track_idx, param_name, base_value, now):
        """Offsets base_value by every audible internal-dest Mod track
        routed at (dest_track_idx, param_name), scaled by each one's
        mod_amount, then clamps to that parameter's valid range. Two Mod
        tracks routed to the same track+param simply sum. A plain linear
        scan over self.tracks — fine at MAX_TRACKS=16, no registry
        needed."""
        total = base_value
        for idx, t in enumerate(self.tracks):
            if t["kind"] != "mod" or not self.track_audible(t):
                continue
            if t["mod_dest_type"] != "internal" or t["mod_dest_track"] != dest_track_idx:
                continue
            if t["mod_dest_param"] != param_name:
                continue
            raw = self._mod_output_raw(idx, now)
            # Uses the modulator's raw mod_amount, not _effective_mod_amount —
            # keeps this non-recursive, so two Mod tracks routing Amount at
            # each other can never loop forever.
            total += raw * (t["mod_amount"] / 100.0)  # mod_combine == "offset_additive", the only mode so far
        lo_hi = MOD_PARAM_RANGE.get(param_name)
        if lo_hi:
            total = max(lo_hi[0], min(lo_hi[1], total))
        return total

    def _trigger_step(self, track_idx, step_idx, now):
        t = self.tracks[track_idx]
        if not self.track_audible(t):
            return
        step = t["steps"][step_idx]

        if t["kind"] == "mod":
            # Runs on every step, on or off — see _trigger_mod_track_step.
            self._trigger_mod_track_step(track_idx, step, now)
            return

        if not step["on"]:
            return

        bpm = self.doc["pattern"]["bpm"]
        step_dur = self.step_duration(t, bpm)

        prob = self._apply_mod(track_idx, "probability", step["prob"], now)
        import random
        if random.randint(1, 100) > prob:
            return

        note_offset = self._apply_mod(track_idx, "pitch", step["note"], now)
        note = self.resolve_note(t, round(note_offset))
        vel = self._apply_mod(track_idx, "velocity", step["vel"], now) + (20 if step["accent"] else 0)
        vel = max(1, min(127, round(vel)))
        gate_frac = self._apply_mod(track_idx, "gate", step["gate"], now) / 100.0
        offset_frac = self._apply_mod(track_idx, "offset", step["offset"], now) / 100.0
        repeats = max(1, step["repeat"])

        for r in range(repeats):
            slot = step_dur / repeats
            fire_at = now + offset_frac * step_dur + r * slot
            off_at = fire_at + gate_frac * slot
            self._schedule_note(track_idx, note, vel, fire_at, off_at)

    def resolve_note(self, t, semitone_offset):
        """The absolute MIDI note a step's stored pitch offset resolves
        to for track t: root + offset, quantized to the track's scale
        (a no-op for the default "chromatic" scale). Public (not
        underscore-prefixed) because view.py calls it too, for the
        on-screen note-name display, so the trigger path and the screen
        always agree on what a given offset means.

        A step's "note" stays a plain semitone offset from root — editing
        never quantizes, only this (playback) does. That keeps switching
        a track's scale non-destructive: the stored offsets never
        change, only which absolute pitch they resolve to."""
        note = t["root"] + semitone_offset
        note = self._quantize_to_scale(note, t["scale"])
        return max(0, min(127, note))

    @staticmethod
    def _quantize_to_scale(note, scale_name):
        intervals = SCALES.get(scale_name)
        if not intervals or scale_name == "chromatic":
            return note
        octave_base, pitch_class = divmod(note, 12)
        nearest = min(intervals, key=lambda i: abs(i - pitch_class))
        return octave_base * 12 + nearest

    def _schedule_note(self, track_idx, note, vel, fire_at, off_at):
        t = self.tracks[track_idx]
        ch = t["channel"]
        # Fires immediately if due now-ish (draw-driven, no real scheduler
        # thread). Ratchet repeats beyond the first one fire on later
        # ticks, via the pending list.
        if fire_at <= time.monotonic() + 0.001:
            self._send_note(ch, note, vel)
            self.pending_offs.append((off_at, ch, note))
        else:
            self.pending_offs.append((fire_at, ch, -note - 1))  # negative-1 sentinel = "note on due"
            self.pending_offs.append((off_at, ch, note))

    def _release_due(self, now):
        remaining = []
        for due, ch, note in self.pending_offs:
            if due > now:
                remaining.append((due, ch, note))
                continue
            if note < 0:
                real_note = -note - 1
                self._send_note(ch, real_note, 100)
            else:
                self._note_off(ch, note)
        self.pending_offs = remaining

    def _release_all_pending(self, now):
        for due, ch, note in self.pending_offs:
            if note >= 0:
                self._note_off(ch, note)
        self.pending_offs = []
