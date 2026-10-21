"""A Bloom sound: its controls in their own units, and the glide they define.

The record words each control is stored as are milestone B2's work (the borrowed
WaveTone records, `docs/bloom-machine.md`, "Forty knobs"). Here every control is
in the unit a player thinks in: rates in Hz or note lengths, times in seconds or
bars, depths as fractions.

**B0 covers** pages 1 and 2 (minus SYNC and XMOD, see `osc`), ANCH and MODE from
page 3, DUCK and LINK from page 5. **Not yet:** SWNG, PAN, PDEP, PULSE 2, the
Bloom filter (page 4), STAK, VEL and TIME = note length.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from . import clock
from .pulse import Glide

ANCHORS = ("trig", "bar", "play")


@dataclass(frozen=True)
class Sound:
    # page 1, OSC
    wav1: float = 0.0              # 0 saw, 0.5 pulse, 1 triangle
    pw1: float = 0.5
    wav2: float = 0.0
    detune: float = 0.12           # osc 2, in semitones from osc 1
    mix: float = 0.5               # 0 osc 1 only, 1 osc 2 only
    sub: float = 0.3               # a sine an octave below osc 1
    # page 2, PULSE
    sync: bool = False             # rates as note lengths, TIME in bars
    start: float | str = 12.0      # Hz, or a note length with sync
    end: float | str = 1.0
    time: float = 8.0              # seconds, or bars with sync
    curve: str = "exp"
    fdep: float = 45.0             # FREQ knob steps at full swing, signed
    vdep: float = 0.0              # 0..1, the chop
    shap: float = 0.0              # 0 triangle, 0.5 pump, 1 square
    tilt: float = 0.0              # -1..+1
    # page 3, MOTION
    anchor: str = "trig"
    anchor_bars: int = 1           # with anchor "bar": the glide restarts every N bars
    mode: str = "smooth"
    # page 5, PLAY
    duck_source: int | None = None # a track number, or none
    damt: float = 0.0
    drel: float = 0.15             # seconds
    link: int | None = None        # follow this track's PULSE settings
    # the stock pages, for the preview only (the instrument's own filter and amp)
    freq: float = 50.0             # 0..127
    reso: float = 0.7              # 0..1

    def __post_init__(self):
        if self.anchor not in ANCHORS:
            raise ValueError(f"ANCH is one of {ANCHORS}, not {self.anchor!r}")
        if self.anchor_bars < 1:
            raise ValueError("ANCH bars must be at least 1")
        self.glide()               # checks the rates, TIME, CURV and MODE

    def glide(self) -> Glide:
        """The glide in PULSE's own units: beats with SYNC, seconds without."""
        def r(x):
            if isinstance(x, str):
                if not self.sync:
                    raise ValueError(f"a note length ({x}) needs SYNC on")
                return clock.note_rate(x)
            return float(x)
        t = self.time * 4.0 if self.sync else self.time
        return Glide(r(self.start), r(self.end), t, self.curve, self.mode)


PULSE_FIELDS = ("sync", "start", "end", "time", "curve", "fdep", "vdep", "shap", "tilt",
                "anchor", "anchor_bars", "mode")


def linked(sound: Sound, tracks: dict[int, Sound]) -> Sound:
    """LINK: a sound whose PULSE settings are track `sound.link`'s, the rest its own.

    Only one hop: a linked track's own LINK is not followed, so links cannot loop.
    """
    if sound.link is None:
        return sound
    if sound.link not in tracks:
        raise ValueError(f"LINK names track {sound.link}, which has no Bloom sound")
    src = tracks[sound.link]
    return replace(sound, **{f: getattr(src, f) for f in PULSE_FIELDS})
