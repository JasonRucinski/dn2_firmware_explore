"""Does a build play the same notes at the same times as stock? One row per build.

    python scripts/emu_seqplay_sweep.py BUILD.syx [BUILD.syx ...] [--stock STOCK.syx]

Runs `emu_seqplay.play` on the stock image and on each build with the same trigs (two tracks,
one step shared) and compares what reached the DSP, event by event: the time since the first
note-on, note-on or note-off, voices and note numbers. Kind, voices and notes must match
exactly; the time may differ by up to --tolerance instructions, because the capture lands
wherever the ColdFire was when the frame went out and a build with different code shifts that
by a few instructions (a frame is about 88,000 apart). A mod that leaves the sequencer alone
must match inside that. Exit status is the number of builds that differ.
"""

from __future__ import annotations

import argparse
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

import emu_seqplay as P                                              # noqa: E402

STOCK = ROOT / "00_Resources/00_Firmware/Digitone_II_OS1.11_dist/Digitone_II_OS1.11.syx"
TRACKS = {1: [1, 5, 9, 13], 2: [1, 7]}


def first_difference(a: list[tuple], b: list[tuple], tolerance: int = 0) -> str | None:
    """None when the lists agree; else the first event that does not."""
    if len(a) != len(b):
        return f"{len(b)} events against stock's {len(a)}"
    for i, (x, y) in enumerate(zip(a, b)):
        if x[1:] != y[1:] or abs(x[0] - y[0]) > tolerance:
            return f"event {i}: {y} against stock's {x}"
    return None


def worst_offset(a: list[tuple], b: list[tuple]) -> int:
    return max((abs(x[0] - y[0]) for x, y in zip(a, b)), default=0)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("builds", nargs="+", type=pathlib.Path)
    ap.add_argument("--stock", type=pathlib.Path, default=STOCK)
    ap.add_argument("--run", default="700M")
    ap.add_argument("--tolerance", type=int, default=1000,
                    help="instructions a time may differ by (default 1000)")
    a = ap.parse_args()
    base = P.signature(P.play(a.stock, TRACKS, a.run))
    ons = sum(1 for e in base if e[1] == "on")
    print(f"stock: {len(base)} events, {ons} note-ons")
    differing = 0
    for build in a.builds:
        try:
            mine = P.signature(P.play(build, TRACKS, a.run))
        except RuntimeError as error:
            print(f"{build.name:55} FAULT {error}")
            differing += 1
            continue
        why = first_difference(base, mine, a.tolerance)
        differing += why is not None
        verdict = (f"same as stock (times within {worst_offset(base, mine)} instructions)"
                   if why is None else "DIFFERS: " + why)
        print(f"{build.name:55} {verdict}")
    return differing


if __name__ == "__main__":
    raise SystemExit(main())
