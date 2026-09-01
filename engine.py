"""engine.py — GridSeq's sequencer model: tracks, steps, timing, trigger logic.

No I/O here. run.py handles stdin/stdout. view.py handles the display.
This module only advances time and decides what to play.

Design note: push-tethered-app's modules/seq.go uses one shared step
index for all lanes. Here, each Track runs its own time division and
keeps its own step position.
"""

import time

MAX_TRACKS = 16          # 2 pages of 8 columns
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

# The 8 parameters, in encoder order. "Encoder index N" means:
#   - A track is selected (main_selected False): encoder N always edits
#     ENCODER_PARAMS[N] of that track. Fixed 1:1 mapping, all 8
#     parameters live at once, no paging.
#   - Main mode (main_selected True): all 8 encoders edit the *same*
#     parameter, ENCODER_PARAMS[current_param], one encoder per track
#     (encoder N -> the Nth visible track). The jog wheel picks which
#     parameter all 8 show, by scrolling current_param.
# "channel" is track-level, not per-step (see set_channel). With no pad
# held, turning it changes the track's MIDI channel. A held pad has
# nothing to target, so it does nothing there (see NOOP_PARAMS in
# run.py's held-pad branch). "mod lane" is a status page only: it shows
# the track's mod-lane division. Actual mod-lane editing happens in the
# grid overlay (mod_lane_active below), not via this encoder. Turning it
# does nothing, held pad or not.
ENCODER_PARAMS = ["velocity", "gate", "repeat", "probability", "offset", "pitch", "channel", "mod lane"]
NOOP_PARAMS = ("mod lane",)

# Bucket values (0-127) for the mod-lane bar-graph editor's 8 rows. Row 0
# (bottom, same convention as the note grid) is the lowest bucket, row 7
# the highest.
MOD_BUCKETS = [round(i * 127 / 7) for i in range(8)]

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
        "channel": 1,
        "root": 60,
        "scale": "chromatic",
        "mod_cc": 1,        # CC1 = mod wheel. Fixed, not yet per-track configurable.
        "div": DEFAULT_DIV,
        "muted": False,
        "solo": False,
        "length": DEFAULT_STEPS,
        "steps": [new_step() for _ in range(DEFAULT_STEPS)],
        "color": TRACK_COLORS[(index * TRACK_COLOR_STEP) % len(TRACK_COLORS)],
        "step_page": 0,     # which 8-step window is being viewed/edited
        # The mod lane: fully independent of the note lane — own length,
        # own division, own step values (0-127 each), edited via the
        # mod-lane grid overlay (Engine.mod_lane_active), not per-step
        # note editing. Fires send_cc(channel, mod_cc, value) on its own
        # schedule whenever a step's value is > 0.
        "mod_length": DEFAULT_STEPS,
        "mod_div": DEFAULT_DIV,
        "mod_steps": [0 for _ in range(DEFAULT_STEPS)],
        # Runtime-only fields below. Harmless to persist, ignored on load if stale.
        "_pos": 0.0,        # wall-clock track beat position at last resync
        "_current_step": -1,
        "_ext_acc": 0,      # external-clock tick accumulator for this track
        "_mod_current_step": -1,
        "_mod_ext_acc": 0,  # external-clock tick accumulator for the mod lane
    }


def default_pattern():
    return {
        "bpm": DEFAULT_BPM,
        "tracks": [new_track(i) for i in range(DEFAULT_TRACK_COUNT)],
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

        self.held_pad = None            # (col, row) of the currently-held pad, or None
        self.main_selected = False      # True: the 8 columns are tracks, all showing one shared parameter
        self.current_param = 0          # index into ENCODER_PARAMS. Only meaningful in Main mode, set by the jog wheel.

        self.mod_lane_active = False    # True: grid is borrowed for the mod-lane bar-graph editor
        self.mod_cursor = 0             # which mod-lane step index the bar graph is showing/editing

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

            mod_length = max(1, min(MAX_STEPS, int(t.get("mod_length", DEFAULT_STEPS))))
            t["mod_length"] = mod_length
            mod_steps = saved.get("mod_steps") or []
            filled_mod = []
            for j in range(mod_length):
                v = mod_steps[j] if j < len(mod_steps) and isinstance(mod_steps[j], (int, float)) else 0
                filled_mod.append(max(0, min(127, int(v))))
            t["mod_steps"] = filled_mod

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

    def track_at(self, col):
        idx = self.track_page + col
        if 0 <= idx < len(self.tracks):
            return idx, self.tracks[idx]
        return None, None

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

    def mod_step_duration(self, track, bpm):
        beats_per_step = DIVISIONS.get(track["mod_div"], DIVISIONS[DEFAULT_DIV])
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
            t["_mod_current_step"] = -1
            t["_mod_ext_acc"] = 0

    def stop(self):
        self.playing = False
        self._release_all_pending(time.monotonic())
        for t in self.tracks:
            t["_current_step"] = -1
            t["_mod_current_step"] = -1

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

    # -- mod lane -----------------------------------------------------

    def open_mod_lane(self, track_idx):
        """Wired to every "Screen top N" button. Selects that column's
        track and opens the mod-lane overlay for it. A second press on
        the button for the *same*, already-open track closes the overlay
        (a plain toggle). Pressing a different track's button while the
        overlay is open jumps straight to that track, instead of closing
        first. Closing only happens by pressing the button of the track
        that is currently open."""
        if self.mod_lane_active and self.selected_track == track_idx:
            self.mod_lane_active = False
        else:
            self.select_track(track_idx)
            self.mod_lane_active = True
            self.scale_mode_active = False  # exclusive with the mod lane overlay
            self.length_view_active = False  # same

    def move_mod_cursor(self, delta):
        self.mod_cursor = max(0, min(MAX_STEPS - 1, self.mod_cursor + delta))

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

    def set_mod_division(self, track_idx, div_name):
        if track_idx is None:
            return
        t = self.tracks[track_idx]
        if div_name in DIVISIONS:
            t["mod_div"] = div_name

    def set_mod_value(self, track_idx, row):
        """Tapping row `row` (0=bottom..7=top) in a mod-lane column sets
        that track's mod value at the current cursor step to that row's
        bucket. No-op if the cursor is past that track's own mod_length."""
        t = self.tracks[track_idx]
        if not (0 <= self.mod_cursor < t["mod_length"]):
            return
        if 0 <= row < len(MOD_BUCKETS):
            t["mod_steps"][self.mod_cursor] = MOD_BUCKETS[row]

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
        self.held_pad = None
        self.main_selected = False
        self.mod_lane_active = False
        self.scale_mode_active = False
        self.length_view_active = False
        self.current_param = 0

    def add_track(self, duplicate_from=None):
        """Appends a new track (up to MAX_TRACKS) — the only way a track
        count grows past DEFAULT_TRACK_COUNT, wired to the "Duplicate"
        button. Without this, Page Left/Right had nowhere to page *to*,
        which is why paging looked broken before this existed."""
        if len(self.tracks) >= MAX_TRACKS:
            return False
        idx = len(self.tracks)
        t = new_track(idx)
        if duplicate_from is not None and 0 <= duplicate_from < len(self.tracks):
            src = self.tracks[duplicate_from]
            t["channel"] = src["channel"]
            t["div"] = src["div"]
            t["root"] = src["root"]
            t["scale"] = src["scale"]
            t["length"] = src["length"]
            t["steps"] = [dict(s) for s in src["steps"]]
            t["mod_length"] = src["mod_length"]
            t["mod_div"] = src["mod_div"]
            t["mod_steps"] = list(src["mod_steps"])
        self.tracks.append(t)
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
        mode (many tracks) or while the mod lane overlay (a different
        track-scoped overlay) is open. Turning it off works in any mode,
        the same as the mod lane's own toggle-closes-if-already-open
        behavior."""
        if not self.scale_mode_active and (self.main_selected or self.mod_lane_active):
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
        if not self.length_view_active and (self.main_selected or self.mod_lane_active):
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
        if track_idx is None or param in NOOP_PARAMS:
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
        # "channel" (track-level, see set_channel) and "mod lane"
        # (status-only) never reach here: run.py routes them elsewhere or
        # no-ops them before calling nudge_param.

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

                t["_mod_ext_acc"] += 1
                mod_beats_per_step = DIVISIONS.get(t["mod_div"], DIVISIONS[DEFAULT_DIV])
                mod_ticks_per_step = max(1, round(TICKS_PER_QUARTER * mod_beats_per_step))
                if t["_mod_ext_acc"] >= mod_ticks_per_step:
                    t["_mod_ext_acc"] = 0
                    self._advance_mod_step(idx)
        elif first_byte == 0xFA:    # Start
            self.play_start = now
            self.playing = True
            for t in self.tracks:
                t["_current_step"] = -1
                t["_ext_acc"] = 0
                t["_mod_current_step"] = -1
                t["_mod_ext_acc"] = 0
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

            mod_dur = self.mod_step_duration(t, bpm)
            mod_idx = int(elapsed / mod_dur) % t["mod_length"]
            if mod_idx != t["_mod_current_step"]:
                t["_mod_current_step"] = mod_idx
                self._trigger_mod_step(idx, mod_idx)

    def _advance_step(self, track_idx, now):
        t = self.tracks[track_idx]
        t["_current_step"] = (t["_current_step"] + 1) % t["length"]
        self._trigger_step(track_idx, t["_current_step"], now)

    def _advance_mod_step(self, track_idx):
        t = self.tracks[track_idx]
        t["_mod_current_step"] = (t["_mod_current_step"] + 1) % t["mod_length"]
        self._trigger_mod_step(track_idx, t["_mod_current_step"])

    def _trigger_mod_step(self, track_idx, step_idx):
        t = self.tracks[track_idx]
        if not self.track_audible(t):
            return
        value = t["mod_steps"][step_idx]
        if value > 0:
            self._send_cc(t["channel"], t["mod_cc"], value)

    def _trigger_step(self, track_idx, step_idx, now):
        t = self.tracks[track_idx]
        if not self.track_audible(t):
            return
        step = t["steps"][step_idx]
        if not step["on"]:
            return

        bpm = self.doc["pattern"]["bpm"]
        step_dur = self.step_duration(t, bpm)

        import random
        if random.randint(1, 100) > step["prob"]:
            return

        note = self.resolve_note(t, step["note"])
        vel = step["vel"] + (20 if step["accent"] else 0)
        vel = max(1, min(127, vel))
        gate_frac = step["gate"] / 100.0
        offset_frac = step["offset"] / 100.0
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
