"""PULSE: a modulator whose rate glides, with its phase computed, not accumulated.

`docs/bloom-machine.md`, "PULSE: a function of the song clock". Time `t` runs from
the glide's anchor (a trig, a bar, or PLAY) in PULSE's own unit: beats when SYNC is
on, seconds when it is off. Rates are cycles per unit. Because the phase is a
function of `t` alone, every voice that shares the anchor computes the same value,
so a chord pulses as one, and a change of rate can never restart the phase.

The glide, from rate R0 to R1 over T, then R1 for ever:

    exp  R(t) = R0 * k^(t/T),          phase(t) = R0 * T * (k^(t/T) - 1) / ln k,  k = R1/R0
    lin  R(t) = R0 + (R1 - R0) t/T,    phase(t) = R0 t + (R1 - R0) t^2 / (2T)

Modes:
- **smooth**: the curve as it is;
- **land**: the curve scaled by N*/N, where N is the cycles it completes by T and N*
  that rounded (at least 1), so the last cycle of the glide ends exactly at T: on
  the downbeat when T is whole bars. R1 after T is unscaled, so the cycles after it
  stay on the grid too;
- **step**: a ladder of rates from R0 to R1 by factors of two, T shared evenly
  between the rungs. With SYNC on, note-length rates and whole-beat rungs, every
  rung completes a whole number of cycles, so every edge is on the grid.

This module is pure: numbers in, numbers out.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

CURVES = ("exp", "lin")
MODES = ("smooth", "land", "step")


@dataclass(frozen=True)
class Glide:
    start: float          # R0, cycles per unit
    end: float            # R1
    time: float           # T, in units; 0 means no glide: R1 from the start
    curve: str = "exp"
    mode: str = "smooth"

    def __post_init__(self):
        if self.start <= 0 or self.end <= 0:
            raise ValueError("PULSE rates must be positive")
        if self.time < 0:
            raise ValueError("TIME must not be negative")
        if self.curve not in CURVES:
            raise ValueError(f"CURV is one of {CURVES}, not {self.curve!r}")
        if self.mode not in MODES:
            raise ValueError(f"MODE is one of {MODES}, not {self.mode!r}")


def _raw_phase(g: Glide, t: float) -> float:
    """Cycles completed by `t` <= T, on the unscaled curve."""
    r0, r1, T = g.start, g.end, g.time
    if g.curve == "lin":
        return r0 * t + (r1 - r0) * t * t / (2 * T)
    k = r1 / r0
    if abs(k - 1.0) < 1e-12:
        return r0 * t
    return r0 * T * (k ** (t / T) - 1.0) / math.log(k)


def _rungs(g: Glide) -> list[float]:
    """The step ladder: R0, then x2 (or /2) towards R1, ending on R1."""
    rungs = [g.start]
    up = g.end > g.start
    while (rungs[-1] * 2 <= g.end * (1 + 1e-9)) if up else (rungs[-1] / 2 >= g.end * (1 - 1e-9)):
        rungs.append(rungs[-1] * 2 if up else rungs[-1] / 2)
    if abs(rungs[-1] - g.end) > 1e-9 * g.end:
        rungs.append(g.end)
    return rungs


def glide_cycles(g: Glide) -> float:
    """Cycles the glide completes by T, after the mode is applied."""
    if g.time == 0:
        return 0.0
    if g.mode == "step":
        rungs = _rungs(g)
        return sum(r * g.time / len(rungs) for r in rungs)
    n = _raw_phase(g, g.time)
    return float(max(1, round(n))) if g.mode == "land" else n


def phase(g: Glide, t: float) -> float:
    """Cycles completed `t` units after the anchor (the integer part counts pulses)."""
    if t <= 0:
        return 0.0
    if g.time == 0:
        return g.end * t
    if t >= g.time:
        return glide_cycles(g) + g.end * (t - g.time)
    if g.mode == "step":
        rungs = _rungs(g)
        seg = g.time / len(rungs)
        i = min(int(t / seg), len(rungs) - 1)
        return sum(r * seg for r in rungs[:i]) + rungs[i] * (t - i * seg)
    n = _raw_phase(g, t)
    if g.mode == "land":
        total = _raw_phase(g, g.time)
        return n * glide_cycles(g) / total
    return n


def rate(g: Glide, t: float) -> float:
    """The instantaneous rate at `t`: what the page's header shows."""
    if g.time == 0 or t >= g.time:
        return g.end
    t = max(t, 0.0)
    if g.mode == "step":
        rungs = _rungs(g)
        return rungs[min(int(t / (g.time / len(rungs))), len(rungs) - 1)]
    if g.curve == "lin":
        r = g.start + (g.end - g.start) * t / g.time
    else:
        r = g.start * (g.end / g.start) ** (t / g.time)
    if g.mode == "land":
        r *= glide_cycles(g) / _raw_phase(g, g.time)
    return r


# The shapes, each -1..+1 over one cycle, starting low: at a trig the filter is
# closed and the level is at its dip, so the first pulse opens on the trig.

def _tri(f: float) -> float:
    return 1.0 - 4.0 * abs(f - 0.5)


PUMP_SPEED = 6.0                   # the pump's recovery: e^-6 short of full by the cycle's end


def _pump(f: float) -> float:
    return 1.0 - 2.0 * math.exp(-PUMP_SPEED * f)


SQUARE_SOFTNESS = 6.0              # tanh(6 cos): edges about 1/20 of a cycle wide


def _square(f: float) -> float:
    return -math.tanh(SQUARE_SOFTNESS * math.cos(2 * math.pi * f))


def shape(f: float, shap: float) -> float:
    """SHAP 0..1 morphs triangle (0) -> pump (0.5) -> softened square (1)."""
    f %= 1.0
    shap = min(max(shap, 0.0), 1.0)
    if shap <= 0.5:
        w = shap * 2
        return (1 - w) * _tri(f) + w * _pump(f)
    w = (shap - 0.5) * 2
    return (1 - w) * _pump(f) + w * _square(f)


def tilted_depth(depth: float, tilt: float, g: Glide, t: float) -> float:
    """TILT -1..+1: the depth glides with the rate, by up to +-100 % at the glide's end."""
    u = 1.0 if g.time == 0 else min(max(t / g.time, 0.0), 1.0)
    return depth * max(0.0, 1.0 + min(max(tilt, -1.0), 1.0) * u)


def value(g: Glide, t: float, shap: float) -> float:
    """PULSE's output m, -1..+1, at `t` after the anchor."""
    return shape(phase(g, t), shap)
