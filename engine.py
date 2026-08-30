"""engine.py — GridSeq's sequencer model: tracks, steps, timing, trigger logic.

No I/O here. Everything that touches stdin/stdout lives in run.py; everything
that touches display pixels lives in view.py. This module only knows how to
advance time and decide what to play.

Design note (see the plan this module was built from): unlike
push-tethered-app's modules/seq.go, which has one shared step index for a
single lane set, every Track here can run its own time division, so each
track keeps its own step position instead of one global counter.
"""

import time

MAX_TRACKS = 16          # 2 pages of 8 columns; enough headroom without overbuilding
DEFAULT_TRACK_COUNT = 8
DEFAULT_STEPS = 8
MAX_STEPS = 64
MIN_BPM, MAX_BPM, DEFAULT_BPM = 40, 240, 120
TICKS_PER_QUARTER = 24   # MIDI clock standard, independent of tempo
EXTERNAL_CLOCK_TIMEOUT = 2.0  # seconds; matches seq.go's externalClockTimeout

# Push's 8 "Scene 1/4".."Scene 1/32t" buttons, in beats-per-step, used
# directly as the time-division picker for the selected track.
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

SCALES = {
    "chromatic": list(range(12)),
    "major": [0, 2, 4, 5, 7, 9, 11],
    "minor": [0, 2, 3, 5, 7, 8, 10],
    "dorian": [0, 2, 3, 5, 7, 9, 10],
    "pentatonic_major": [0, 2, 4, 7, 9],
    "pentatonic_minor": [0, 3, 5, 7, 10],
}
SCALE_NAMES = list(SCALES.keys())

# Encoder parameter pages, cycled by tapping any encoder. "pan" and "mod" are
# v2/v3 stubs: shown, but an encoder turn on those pages does nothing yet
# (per-track CC modulation lanes land in v2 — see the plan).
PARAM_PAGES = ["velocity", "gate", "repeat", "probability", "offset", "pitch", "pan (v2)", "mod (v2)"]

# Palette indices (core/push3.Palette, see palette.json) used for track colors,
# cycled across DEFAULT_TRACK_COUNT+ tracks.
TRACK_COLORS = [11, 79, 61, 30, 100, 49, 90, 39, 69, 23, 10, 34, 77, 0, 120, 56]


def new_step():
    return {
        "on": False,
        "vel": 100,
        "gate": 50,       # percent of step duration
        "repeat": 1,       # ratchet count, 1 = no ratchet
        "prob": 100,       # percent chance to fire
        "offset": 0,       # micro-timing, -45..+45 percent of step duration
        "accent": False,
        "note": 0,         # semitone offset from track root, melodic tracks only
    }


def new_track(index):
    return {
        "name": "Track %d" % (index + 1),
        "kind": "drum",
        "channel": 1,
        "base_note": 36 + index,   # spreads default drum notes across the low range
        "root": 60,
        "scale": "chromatic",
        "div": DEFAULT_DIV,
        "muted": False,
        "solo": False,
        "length": DEFAULT_STEPS,
        "steps": [new_step() for _ in range(DEFAULT_STEPS)],
        "color": TRACK_COLORS[index % len(TRACK_COLORS)],
        "step_page": 0,     # which 8-step window is being viewed/edited
        # runtime-only fields below; harmless to persist, ignored on load if stale
        "_pos": 0.0,        # wall-clock track beat position at last resync
        "_current_step": -1,
        "_ext_acc": 0,      # external-clock tick accumulator for this track
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
        self.param_page = 0             # index into PARAM_PAGES

        self.last_ext_clock = None
        self.ext_synced_before = False

        self.mods = {
            "select": False, "mute": False, "solo": False,
            "note": False, "scale": False, "repeat": False, "accent": False,
            "shift": False,
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

    def toggle_kind(self, track_idx):
        if track_idx is None:
            return
        t = self.tracks[track_idx]
        t["kind"] = "melodic" if t["kind"] == "drum" else "drum"

    def cycle_scale(self, track_idx, forward=True):
        if track_idx is None:
            return
        t = self.tracks[track_idx]
        if t["kind"] != "melodic":
            return
        i = SCALE_NAMES.index(t["scale"]) if t["scale"] in SCALE_NAMES else 0
        i = (i + (1 if forward else -1)) % len(SCALE_NAMES)
        t["scale"] = SCALE_NAMES[i]

    def nudge_param(self, track_idx, step_idx, param, delta):
        """Edits one step's param if step_idx is given (a pad is held),
        otherwise nudges the track's default and rescales existing steps
        by the same relative amount — the OXI "global knob" feel."""
        t = self.tracks[track_idx]
        if step_idx is not None and 0 <= step_idx < t["length"]:
            self._nudge_step_param(t["steps"][step_idx], param, delta)
            return
        for step in t["steps"]:
            self._nudge_step_param(step, param, delta)

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
            step["note"] = max(-24, min(24, step["note"] + (1 if delta > 0 else -1 if delta < 0 else 0)))
        # "pan (v2)" / "mod (v2)": intentionally no-op, stub pages only

    # -- octave / transpose -----------------------------------------------------

    def transpose_all_melodic(self, semitones):
        for t in self.tracks:
            if t["kind"] == "melodic":
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
        elif first_byte == 0xFA:    # Start
            self.play_start = now
            self.playing = True
            for t in self.tracks:
                t["_current_step"] = -1
                t["_ext_acc"] = 0
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
            # External clock path already advances steps in
            # on_external_clock_byte; re-anchor so we don't jump on drop-out.
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

    def _advance_step(self, track_idx, now):
        t = self.tracks[track_idx]
        t["_current_step"] = (t["_current_step"] + 1) % t["length"]
        self._trigger_step(track_idx, t["_current_step"], now)

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

        note = t["base_note"] if t["kind"] == "drum" else self._scale_note(t, step["note"])
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

    def _scale_note(self, t, semitone_offset):
        # v1 keeps pitch entry simple: a step's "note" is a plain semitone
        # offset from the track root. "scale" is stored and shown, but does
        # not quantize yet — scale-aware quantization is a v2 refinement,
        # tracked so it doesn't block a working melodic track today.
        return max(0, min(127, t["root"] + semitone_offset))

    def _schedule_note(self, track_idx, note, vel, fire_at, off_at):
        t = self.tracks[track_idx]
        ch = t["channel"]
        # fire immediately if due now-ish (draw-driven, no real scheduler thread);
        # ratchet repeats beyond the first one fire on later ticks via pending list
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
