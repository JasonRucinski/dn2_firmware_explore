"""Bloom's oscillators: PolyBLEP saw and pulse, a triangle, and the WAV morph.

PolyBLEP subtracts a two-sample polynomial step at each discontinuity, which
removes most of the aliasing a naive saw or pulse has, at every pitch, with no
tables. The triangle has no step, only a corner, so it is left naive: its
harmonics fall at 1/n^2 and its aliasing is far below the saw's.

**Not in B0, on purpose:** hard sync (SYNC) and osc 2 into osc 1 (XMOD). A sync
reset is a step too, and needs its own BLEP to stay clean; it is its own
milestone, B4 (`docs/bloom-machine.md`).

This module is pure: numbers in, numbers out.
"""

from __future__ import annotations

RATE = 48000.0


def poly_blep(t: float, dt: float) -> float:
    """The correction for a unit step at phase 0, at phase `t`, with step `dt`."""
    if t < dt:
        t /= dt
        return t + t - t * t - 1.0
    if t > 1.0 - dt:
        t = (t - 1.0) / dt
        return t * t + t + t + 1.0
    return 0.0


def saw(p: float, dt: float) -> float:
    return 2.0 * p - 1.0 - poly_blep(p, dt)


def pulse(p: float, dt: float, width: float) -> float:
    w = min(max(width, 0.02), 0.98)
    y = 1.0 if p < w else -1.0
    return y + poly_blep(p, dt) - poly_blep((p - w) % 1.0, dt)


def triangle(p: float) -> float:
    return 1.0 - 4.0 * abs(p - 0.5)


def morph(p: float, dt: float, wav: float, width: float) -> float:
    """WAV 0..1: saw (0) -> pulse (0.5) -> triangle (1)."""
    wav = min(max(wav, 0.0), 1.0)
    if wav <= 0.5:
        w = wav * 2
        return (1 - w) * saw(p, dt) + w * pulse(p, dt, width)
    w = (wav - 0.5) * 2
    return (1 - w) * pulse(p, dt, width) + w * triangle(p)


def hz(note: float, a4: float = 440.0) -> float:
    return a4 * 2.0 ** ((note - 69.0) / 12.0)


class Oscillator:
    """A phase in 0..1 and the morph. The phase starts at 0 on a note (PRST On)."""

    def __init__(self) -> None:
        self.p = 0.0

    def next(self, freq: float, wav: float, width: float, rate: float = RATE) -> float:
        dt = min(freq / rate, 0.5)
        y = morph(self.p, dt, wav, width)
        self.p += dt
        if self.p >= 1.0:
            self.p -= 1.0
        return y
