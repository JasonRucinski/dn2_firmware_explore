"""One Bloom track rendered: the oscillators, PULSE on the cutoff and the chop, DUCK.

What the DSP will compute, and in the same split (`docs/bloom-machine.md`):

- **per sample**, inside Bloom's own render: the oscillators, the chop
  (`1 - VDEP x (1 - m')`, m' = PULSE mapped to 0..1) and DUCK's gain;
- **per 32-sample block**, in Bloom's setup arm: the stock filter's cutoff, FREQ +
  FDEP x m, from PULSE's value at the block's first sample. That is what milestone
  B1 must show the stock filter follows.

The output is `Render.dry`, the machine's own signal before the stock filter, which
is what the DSP gate compares bit for bit (once B3 fixes the float32 order of
operations), and `Render.cutoff`, the FREQ knob value per block.

**`Render.preview` is for listening only.** It runs the dry signal through a
stand-in for the stock filter: a two-pole TPT state-variable low-pass, with FREQ
mapped 20 Hz .. 20 kHz and a fixed amp gate. It is **not** Elektron's filter and
says nothing about how the instrument will sound beyond the shape of the motion.

This module is pure: numbers in, numbers out.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from . import clock, pulse
from .duck import Duck
from .osc import RATE, Oscillator, hz
from .sound import Sound

BLOCK = 32                          # samples per DSP block: 1,500 blocks a second at 48 kHz
VOICE_GAIN = 0.2
GATE_RAMP = 0.005                   # the preview's amp gate: 5 ms on and off


@dataclass
class Render:
    dry: list[float] = field(default_factory=list)
    cutoff: list[float] = field(default_factory=list)       # FREQ knob, per block
    pulse: list[float] = field(default_factory=list)        # PULSE m, per block
    preview: list[float] = field(default_factory=list)


def anchor_time(sound: Sound, seconds: float, trig_start: float, bpm: float) -> float:
    """`t` for PULSE: time since the glide's anchor, in its own unit."""
    spb = clock.seconds_per_beat(bpm)
    if sound.anchor == "play":
        since = seconds
    elif sound.anchor == "trig":
        since = seconds - trig_start
    else:
        span = sound.anchor_bars * 4 * spb
        since = seconds - math.floor(seconds / span + 1e-12) * span
    return since / spb if sound.sync else since


def chop(m: float, depth: float) -> float:
    return 1.0 - min(max(depth, 0.0), 1.0) * (1.0 - (m + 1.0) / 2.0)


def knob_hz(knob: float) -> float:
    """The preview filter's map: FREQ 0..127 -> 20 Hz .. 20 kHz, exponentially."""
    return 20.0 * 1000.0 ** (min(max(knob, 0.0), 127.0) / 127.0)


class _Svf:
    """The preview's stand-in filter: a TPT state-variable low-pass, per block coefficients."""

    def __init__(self) -> None:
        self.ic1 = self.ic2 = 0.0
        self.g = self.k = self.a1 = self.a2 = self.a3 = 0.0

    def set(self, fc: float, reso: float, rate: float) -> None:
        self.g = math.tan(math.pi * min(fc, 0.45 * rate) / rate)
        self.k = 2.0 - 1.9 * min(max(reso, 0.0), 1.0)
        self.a1 = 1.0 / (1.0 + self.g * (self.g + self.k))
        self.a2 = self.g * self.a1
        self.a3 = self.g * self.a2

    def lp(self, x: float) -> float:
        v3 = x - self.ic2
        v1 = self.a1 * self.ic1 + self.a2 * v3
        v2 = self.ic2 + self.a2 * self.ic1 + self.a3 * v3
        self.ic1, self.ic2 = 2 * v1 - self.ic1, 2 * v2 - self.ic2
        return v2


def render(sound: Sound, events, seconds: float, bpm: float = 120.0,
           kicks: list[float] | None = None, rate: float = RATE,
           preview: bool = True) -> Render:
    """Render `seconds` of one track playing `events`: (start s, length s, notes)."""
    g = sound.glide()
    out = Render()
    duck = Duck(kicks or [], sound.drel) if sound.duck_source is not None else None
    svf = _Svf()
    voices = []                                     # (start, end, osc1, osc2, sub, f1, f2, fs)
    pending = sorted(events)
    n = int(seconds * rate)
    m = 0.0
    for i in range(n):
        t = i / rate
        while pending and pending[0][0] <= t:
            start, length, notes = pending.pop(0)
            for note in notes:
                voices.append((start, start + length, Oscillator(), Oscillator(), Oscillator(),
                               hz(note), hz(note + sound.detune), hz(note - 12)))
        trig = max((v[0] for v in voices if v[0] <= t), default=0.0)
        if i % BLOCK == 0:
            ta = anchor_time(sound, t, trig, bpm)
            m = pulse.value(g, ta, sound.shap)
            fdep = pulse.tilted_depth(sound.fdep, sound.tilt, g, ta)
            out.pulse.append(m)
            out.cutoff.append(min(max(sound.freq + fdep * m, 0.0), 127.0))
            svf.set(knob_hz(out.cutoff[-1]), sound.reso, rate)
        ta = anchor_time(sound, t, trig, bpm)
        ms = pulse.value(g, ta, sound.shap)
        level = chop(ms, pulse.tilted_depth(sound.vdep, sound.tilt, g, ta))
        if duck is not None:
            level *= duck.gain(t, sound.damt)
        y = 0.0
        alive = []
        for v in voices:
            start, end, o1, o2, sb, f1, f2, fs = v
            if t >= end + GATE_RAMP:              # finished only once its release has ended:
                continue                          # at its first sample a voice's gate is 0 too
            alive.append(v)
            gate = min(1.0, (t - start) / GATE_RAMP, max(0.0, (end - t) / GATE_RAMP + 1.0))
            a = o1.next(f1, sound.wav1, sound.pw1, rate)
            b = o2.next(f2, sound.wav2, 0.5, rate)
            s = math.sin(2 * math.pi * sb.p)
            sb.next(fs, 0.0, 0.5, rate)
            y += gate * ((1 - sound.mix) * a + sound.mix * b + sound.sub * s)
        voices = alive
        y *= VOICE_GAIN * level
        out.dry.append(y)
        if preview:
            out.preview.append(svf.lp(y))
    return out
