"""DUCK: a built-in sidechain. Bloom dips each time a source track triggers.

On the DSP the source's trigs come from the frame: the note-trigger mask at offset
34 and each voice row's owner track at `0xa5a + 2r` (`docs/bloom-machine.md`,
"DUCK"). Here they are a list of times.

The gain is `1 - DAMT * env`. `env` rises to 1 over ATTACK seconds (so the dip
never clicks) and falls back with time constant DREL. A new trig restarts it from
where it is, so fast trigs never jump.

This module is pure: numbers in, numbers out.
"""

from __future__ import annotations

import bisect
import math

ATTACK = 0.001                     # 1 ms: fast enough to read as instant, slow enough not to click


def _after(level: float, since: float, release: float) -> float:
    """The envelope `since` seconds after a trig that found it at `level`."""
    if since < ATTACK:
        return level + (1.0 - level) * since / ATTACK
    return math.exp(-(since - ATTACK) / max(release, 1e-4))


class Duck:
    """One source track's trigs, with the level each one found, worked out once."""

    def __init__(self, trigs: list[float], release: float) -> None:
        self.trigs = sorted(trigs)
        self.release = release
        self.found = []
        level, prev = 0.0, None
        for t in self.trigs:
            if prev is not None:
                level = _after(level, t - prev, release)
            self.found.append(level)
            prev = t

    def envelope(self, t: float) -> float:
        """The duck envelope 0..1 at `t` seconds."""
        i = bisect.bisect_right(self.trigs, t) - 1
        if i < 0:
            return 0.0
        return _after(self.found[i], t - self.trigs[i], self.release)

    def gain(self, t: float, amount: float) -> float:
        """DAMT 0..1: 0 no duck, 1 down to silence on the trig."""
        return 1.0 - min(max(amount, 0.0), 1.0) * self.envelope(t)
