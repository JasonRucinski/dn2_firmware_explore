"""The factory sounds (`docs/bloom-machine.md`, "Factory sounds"), each with a
demonstration pattern. Each is also an acceptance target: what it should sound like
is written beside it, before anything is built.

Vowel Bloom is not here yet: it needs the Bloom filter (milestone B6).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .sound import Sound

CHORDS = ((58, 62, 65, 69), (60, 64, 67, 69), (57, 60, 64, 67), (50, 57, 60, 65))
"""Bb maj7, C6, Am7, Dm(add11): the progression from the programming story."""


@dataclass(frozen=True)
class Demo:
    sound: Sound
    listen_for: str
    bpm: float = 150.0
    bars: int = 4
    held: bool = False             # one chord held throughout, or a chord per bar
    kick: bool = False             # a kick on every beat, as DUCK's source

    def events(self) -> list[tuple[float, float, tuple[int, ...]]]:
        """(start seconds, length seconds, notes) for the pattern."""
        bar = 4 * 60.0 / self.bpm
        if self.held:
            return [(0.0, self.bars * bar, CHORDS[0])]
        return [(i * bar, bar, CHORDS[i % len(CHORDS)]) for i in range(self.bars)]

    def kicks(self) -> list[float]:
        beat = 60.0 / self.bpm
        return [i * beat for i in range(self.bars * 4)] if self.kick else []

    @property
    def seconds(self) -> float:
        return self.bars * 4 * 60.0 / self.bpm


PRESETS = {
    "innerbloom": Demo(
        Sound(),
        "one held chord: the filter flutters about 12 times a second, then slows smoothly "
        "to one pulse a second by 8 s",
        bpm=120.0, bars=5, held=True),
    "future-chop": Demo(
        Sound(sync=True, start="1/8T", end="1/8T", time=0.0, shap=1.0, vdep=0.85, fdep=12.0,
              freq=70.0, reso=0.4, duck_source=9, damt=0.6, drel=0.12),
        "a chord per bar chopped in steady eighth-note triplets, ducking under a kick on "
        "every beat", kick=True),
    "riser": Demo(
        Sound(sync=True, start="1/4", end="1/64", time=4.0, mode="land", tilt=0.8,
              vdep=0.6, fdep=50.0, freq=45.0),
        "one held chord over 4 bars: quarter-note pulses that speed up to a buzz and stop "
        "exactly on the bar line after the last", held=True),
    "breathing-pad": Demo(
        Sound(sync=True, start="1/16", end="1/2", time=2.0, mode="land", anchor="bar",
              anchor_bars=2, shap=0.5, vdep=0.4, fdep=35.0),
        "a chord per bar, but the slowdown runs every 2 bars whatever the chords do: each "
        "chord change continues the pulse instead of restarting it"),
    "step-roll": Demo(
        Sound(sync=True, start="1/4", end="1/32", time=1.0, mode="step", shap=1.0,
              vdep=0.9, fdep=20.0),
        "a chord per bar rolling quarters, eighths, sixteenths, thirty-seconds, a beat "
        "each, every edge on the grid"),
}


def get(name: str) -> Demo:
    try:
        return PRESETS[name]
    except KeyError:
        raise ValueError(f"no Bloom preset {name!r}; one of {', '.join(PRESETS)}") from None
