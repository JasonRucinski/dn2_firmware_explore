"""What Bloom's type-7 render loop computes (milestone B3a): the contract the SHARC code
is held to, bit for bit, in float32 and in the loop's own order of operations.

B0's `osc` is the musical model, in float64. This is the same PolyBLEP saw written
the way the DSP will compute it, with two tables instead of a division per sample:

- **DT[k]**, k = 0..128, the phase step at MIDI note k: 440 * 2^((k-69)/12) / 48000,
  as float32;
- **INV[k]** = 1 / DT[k], as float32 (the BLEP's `t / dt` becomes `t * inv`);
- for a note n (float semitones, note + TUN1, clamped to 0..127): k = trunc(n),
  fr = n - k, dt = DT[k] + fr * (DT[k+1] - DT[k]), and inv the same over INV. The
  interpolated inverse is not exactly 1/dt; it is what the loop uses, so it is what
  the reference uses. Linear between semitones, it is within 0.2 % of 1/dt.

Per sample, with p the phase in [0, 1), carried per track from block to block:

    y = 2p - 1                       the naive saw
    if p < dt:      u = p * inv;          y -= u + u - u*u - 1
    elif p > 1-dt:  u = (p - 1) * inv;    y -= u*u + u + u + 1
    out = y * GAIN
    p = p + dt;  if p >= 1: p = p - 1

Every operation is rounded to float32 in that order (`_f`). GAIN is 0.5, so a
Bloom track sits near a stock synth's level before the stock chain's own -20 dB.

This module is pure: numbers in, numbers out.
"""

from __future__ import annotations

import struct

RATE = 48000.0
NOTES = 129
GAIN = 0.5


def _f(x: float) -> float:
    return struct.unpack("<f", struct.pack("<f", x))[0]


def dt_table() -> list[float]:
    return [_f(440.0 * 2.0 ** ((k - 69) / 12.0) / RATE) for k in range(NOTES)]


def inv_table() -> list[float]:
    return [_f(1.0 / d) for d in dt_table()]


def note_from_frame(note: float, tun1_word: int) -> float:
    """The loop's pitch: the engine's note cell plus TUN1 (frame word / 256 - 64),
    clamped to 0..127, as Waverider M6 reads it. A non-finite or negative note is 0."""
    if note != note or note < 0 or note in (float("inf"),):
        note = 0.0
    n = _f(_f(note) + _f(_f(tun1_word / 256.0) - 64.0))
    return min(max(n, 0.0), 127.0)


def step(note: float) -> tuple[float, float]:
    """(dt, inv) for a clamped note, interpolated as the loop does."""
    dt, inv = dt_table(), inv_table()
    k = int(note)
    k = min(k, NOTES - 2)
    fr = _f(note - k)
    d = _f(dt[k] + _f(fr * _f(dt[k + 1] - dt[k])))
    i = _f(inv[k] + _f(fr * _f(inv[k + 1] - inv[k])))
    return d, i


def render_block(p: float, dt: float, inv: float, n: int = 32) -> tuple[list[float], float]:
    """N samples of the saw from phase P -> (samples, the phase after them)."""
    out = []
    one = 1.0
    for _ in range(n):
        y = _f(_f(p + p) - one)
        if p < dt:
            u = _f(p * inv)
            y = _f(y - _f(_f(_f(u + u) - _f(u * u)) - one))
        elif p > _f(one - dt):
            u = _f(_f(p - one) * inv)
            y = _f(y - _f(_f(_f(_f(u * u) + u) + u) + one))
        out.append(_f(y * GAIN))
        p = _f(p + dt)
        if p >= one:
            p = _f(p - one)
    return out, p


def render(note: float, tun1_word: int, blocks: int, p: float = 0.0) -> list[float]:
    """BLOCKS blocks of one held note, the phase carried, as the loop renders it."""
    dt, inv = step(note_from_frame(note, tun1_word))
    out = []
    for _ in range(blocks):
        b, p = render_block(p, dt, inv)
        out += b
    return out


# -- B3b: PULSE on FREQ ---------------------------------------------------------------------
#
# What Bloom's pre-unpack hook computes (pulse.asm): once a block, before the stock unpack
# reads the received frame, for every track whose machine in that frame is 7, a triangle
# whose rate glides from PULSE_START_HZ to PULSE_END_HZ over PULSE_TIME_S (exponential,
# restarted by the track's trig) is added to the frame's FREQ word. B1b showed the stock
# filter follows such a rewrite exactly as it follows the ColdFire's own value, one block
# late. v0 fixes the Innerbloom gesture; its controls come with the pages (B4).
#
# Per track, per block, in float32 and in this order:
#
#     if page word != last written:  base = page word      (a value from the ColdFire)
#     if trig:                       step = STEP0, phase = 0, n = 0
#     if step == 0:                  word = base           (never triggered: no pulse)
#     else:
#         m    = 1 - |phase - 0.5| * 4                      -1 .. +1, the triangle
#         word = clamp(base + trunc(m * DEPTH), 0, FREQ_MAX)
#         phase = phase + step;  if phase >= 1: phase = phase - 1
#         if n < BLOCKS:  n = n + 1;  step = STEP1 if n == BLOCKS else step * RATIO
#     last = word
#
# "base" makes the rewrite idempotent: the ring can hand the unpack a page this hook has
# already rewritten, and the pulse must then ride on the ColdFire's value, not its own.

PULSE_START_HZ = 12.0
PULSE_END_HZ = 1.0
PULSE_TIME_S = 8.0
PULSE_BLOCK = 32
PULSE_BLOCKS = round(PULSE_TIME_S * RATE / PULSE_BLOCK)              # 12000
PULSE_STEP0 = _f(PULSE_START_HZ * PULSE_BLOCK / RATE)
PULSE_STEP1 = _f(PULSE_END_HZ * PULSE_BLOCK / RATE)
PULSE_RATIO = _f((PULSE_END_HZ / PULSE_START_HZ) ** (1.0 / PULSE_BLOCKS))
PULSE_DEPTH = 8192.0                  # 32 FREQ steps either way (a step is 256 in the word)
FREQ_MAX = 0x7F00


class PulseState:
    """One track's pulse, as pulse.asm keeps it (32 bytes a track, zeros at boot)."""

    __slots__ = ("step", "phase", "n", "base", "last")

    def __init__(self):
        self.step, self.phase, self.n, self.base, self.last = 0.0, 0.0, 0, 0, 0


def pulse_block(s: PulseState, page_word: int, trig: bool) -> int:
    """One block of one track: the FREQ word to write, given the page's word and the trig."""
    if page_word != s.last:
        s.base = page_word
    if trig:
        s.step, s.phase, s.n = PULSE_STEP0, 0.0, 0
    if s.step == 0.0:
        word = s.base
    else:
        m = _f(1.0 - _f(abs(_f(s.phase - 0.5)) * 4.0))
        word = min(max(s.base + int(_f(m * PULSE_DEPTH)), 0), FREQ_MAX)
        s.phase = _f(s.phase + s.step)
        if s.phase >= 1.0:
            s.phase = _f(s.phase - 1.0)
        if s.n < PULSE_BLOCKS:
            s.n += 1
            s.step = PULSE_STEP1 if s.n == PULSE_BLOCKS else _f(s.step * PULSE_RATIO)
    s.last = word
    return word
