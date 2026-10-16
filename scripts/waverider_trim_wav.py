"""TRIM turned fast while a note holds, before and after 0.1.2's slew, as one WAV.

    python scripts/waverider_trim_wav.py [--out out/waverider/trim_slew.wav]

dnfw.waverider.live (bit-exact to the shipped section 7 in the runner, scripts/sharc_waverider_m5.py's
`trim_jump`): osc 1 alone on the baked table 0 at POS 64, LEV 100, a C3 held from block 0. TRIM, as the
frame carries it: held at the default, turned up fast to 0 dB, down to -15 dB, back to the default
(a word step of 0x400 every 8 blocks, as an encoder burst), then a jump to 0 dB and back (a p-lock).
The first half is 0.1.1 (the factor jumps), the second 0.1.2 (the factor slews 0.1 dB a block).
"""

from __future__ import annotations

import argparse
import math
import pathlib
import struct
import sys
import wave

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from dnfw.waverider import dsp, live  # noqa: E402

BLOCK, RATE = 32, 48000


def trim_words() -> list[int]:
    words = [live.TRIM_DEFAULT_WORD] * 750
    for target, step in ((0x7F00, 0x400), (0, -0x400), (live.TRIM_DEFAULT_WORD, 0x400)):
        w = words[-1]
        while w != target:
            w = max(0, min(0x7F00, w + step)) if abs(target - w) > abs(step) else target
            words += [w] * 8
        words += [w] * 750
    words += [0x7F00] * 750 + [live.TRIM_DEFAULT_WORD] * 750
    return words


def render(words: list[int], slew: bool) -> list[float]:
    osc1 = (0x4000, 0, 0x4000, 0x6400, 0x3200, live.MPOS_NONE, 0, 0, 0, 0x7F00)
    blocks = [(48.0, osc1, (0, 0, 0x4000, 0), (0, b == 0, live.PRST_OFF, 0, 0, 0)) for b in range(len(words))]
    keep = live.trim_slew
    if not slew:
        live.trim_slew = lambda last, target, note_on: target
    try:
        return live.render_two(dsp.tables(), blocks, BLOCK, trims=words)
    finally:
        live.trim_slew = keep


def largest_step_db(words: list[int], slew: bool) -> float:
    f, worst = 0.0, 0.0
    for b, w in enumerate(words):
        g = live.trim_slew(f, live.trim_factor(w), b == 0) if slew else live.trim_factor(w)
        if f:
            worst = max(worst, abs(20 * math.log10(g / f)))
        f = g
    return worst


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=pathlib.Path, default=ROOT / "out/waverider/trim_slew.wav")
    a = ap.parse_args()
    words = trim_words()
    before, after = render(words, False), render(words, True)
    gap = [0.0] * (RATE // 2)
    samples = before + gap + after
    a.out.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(a.out), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(b"".join(struct.pack("<h", max(-32767, min(32767, round(x * 32767)))) for x in samples))
    print(f"wrote {a.out}: {len(samples) / RATE:.1f} s, 0.1.1 then 0.1.2 after {len(gap) / RATE} s of silence; "
          f"the level's largest jump between two blocks: {largest_step_db(words, False):.2f} dB (0.1.1), "
          f"{largest_step_db(words, True):.2f} dB (0.1.2)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
