"""Which bytes of the ColdFire's frame to the DSP move when Waverider's TRIM turns, a pattern playing?

    python scripts/emu_trim_frames.py BUILD.syx [--out out/trim_frames]

Three panel_drive runs from reset (digikit-wt-forced's panel driver, SSI0 paced, the whole
2,688-byte frame kept at every send to the DSP, 0x400cf7be). Track 1 is made a Waverider track
in MACHINE SEL, a trig is entered on steps 1, 5, 9 and 13, SYN page 4 is shown and the pattern
plays. Mid-play one knob turns up and back down, its push held:
- `none`: no knob (the frames' own movement: counters, notes on and off);
- `trim`: knob D, TRIM (record 262, WaveTone's FINE);
- `dclk`: knob C, DCLK (record 254), the control: a page 4 knob that changes only its slot.

For each run it prints the frame offsets that changed between two sends and that `none` never
changed, and voice 0..3's note words (offset 2 + 2v, semitones x 256) at every change.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import struct
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
PANEL = pathlib.Path("D:/01_Code/Z_Personal/digikit-wt-forced/out/target/release/examples/panel_drive.exe")
EXCHANGE, FRAME = "0x400cf7be", 2688
NO, RECORD, PLAY, STOP, TRIG1 = 12, 19, 20, 21, 25
KNOBS = {"none": None, "trim": 4, "dclk": 3}


def steps(knob: int | None) -> list[str]:
    s = ["wait:1500M", f"tap:{NO}", "wait:60M"]
    s += ["press:17", "tap:2", "release:17", "wait:60M"]                  # MACHINE SEL
    s += [x for _ in range(4) for x in ("tap:14", "wait:20M")]             # down to WAVERIDER
    s += ["tap:10", "wait:100M", "tap:2", "wait:60M"]
    s += [f"tap:{RECORD}"] + [f"tap:{TRIG1 + t - 1}" for t in (1, 5, 9, 13)] + [f"tap:{RECORD}", "wait:30M"]
    s += [x for _ in range(3) for x in ("tap:2", "wait:30M")] + ["frame:page4"]
    s += ["wait:50M", f"tap:{PLAY}", "wait:150M"]
    if knob is not None:
        push = 40 + knob
        turn = [x for _ in range(8) for x in (f"turn:{knob}:10", "wait:15M")]
        down = [x for _ in range(8) for x in (f"turn:{knob}:-10", "wait:15M")]
        s += [f"press:{push}"] + turn + ["frame:turned"] + down + [f"release:{push}"]
    else:
        s += ["wait:240M"]
    return s + ["wait:150M", f"tap:{STOP}", "wait:20M"]


def run(image: pathlib.Path, knob: int | None, out: pathlib.Path) -> list[bytes]:
    out.mkdir(parents=True, exist_ok=True)
    cmd = [str(PANEL), str(image), "--ssi-hz", "96000", "--out", str(out),
           "--capture", f"{EXCHANGE}:1:{FRAME}", "--steps", ",".join(steps(knob))]
    done = subprocess.run(cmd, capture_output=True, text=True, timeout=3000)
    if not done.stdout.strip():
        sys.exit(f"no output: {done.stderr[-300:]}")
    result = json.loads(done.stdout.strip().splitlines()[-1])
    print(f"  outcome {result['outcome']}, {len(result['captures'])} sends", flush=True)
    return [bytes.fromhex(c["hex"]) for c in result["captures"] if len(c["hex"]) == 2 * FRAME]


def moved(frames: list[bytes]) -> set[int]:
    return {i for a, b in zip(frames, frames[1:]) for i in range(FRAME) if a[i] != b[i]}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("image", type=pathlib.Path)
    ap.add_argument("--out", type=pathlib.Path, default=ROOT / "out/trim_frames")
    a = ap.parse_args()
    frames = {}
    for name, knob in KNOBS.items():
        print(name, flush=True)
        frames[name] = run(a.image.resolve(), knob, a.out / name)
    base = moved(frames["none"])
    for name in ("trim", "dclk"):
        extra = sorted(moved(frames[name]) - base)
        print(f"{name}: offsets that moved and never move in 'none': {[hex(i) for i in extra]}")
        last = None
        for n, f in enumerate(frames[name]):
            notes = struct.unpack_from(">4H", f, 2)
            if notes != last:
                print(f"  send {n}: notes {[f'{x / 256:.4f}' for x in notes]}")
                last = notes
    return 0


if __name__ == "__main__":
    sys.exit(main())
