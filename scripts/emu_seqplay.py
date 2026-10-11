"""Play the sequencer in the emulator and list the notes it sends the DSP.

    python scripts/emu_seqplay.py BUILD.syx [--trigs 1,5,9,13] [--run 700M] [--ssi-hz 96000]

Boots BUILD from reset with SSI0 paced (the audio-frame interrupt, and with it the forced
interrupts that tick the sequencer, run: digikit finding 04, "The internal step clock"),
enters the trigs on track 1 with RECORD and the trig keys, presses PLAY and captures every
frame sent to the DSP. Prints each note-on and note-off with its time, and checks that the
note-ons keep to the trigs' spacing.

The step period is read from the run, not assumed: 120 BPM is 16.5 M instructions a step at
the 132 MHz the SSI lane paces against. Needs a panel_drive with `service_forced` (digikit
#65) and a literal `--capture` length (digikit branch feat/capture-literal-len).
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from dnfw import seqframes as SF                                    # noqa: E402

PANEL_CANDIDATES = (
    ROOT.parent / "digikit-wt-forced/out/target/release/examples/panel_drive.exe",
    ROOT.parent / "digikit-rust/out/native/target-host/release/examples/panel_drive.exe",
)
EXCHANGE = "0x400cf7be"      # the audio ISR's send/receive to the DSP; argument 1 is the frame
NO, RECORD, PLAY, STOP, TRIG1 = 12, 19, 20, 21, 25


def panel_drive() -> pathlib.Path:
    chosen = os.environ.get("PANEL_DRIVE")
    for path in ([pathlib.Path(chosen)] if chosen else []) + list(PANEL_CANDIDATES):
        if path.exists():
            return path
    raise SystemExit("panel_drive.exe not found; set PANEL_DRIVE")


def script(trigs: list[int], run: str) -> list[str]:
    taps = [f"tap:{TRIG1 + t - 1}" for t in trigs]
    return (["wait:1500M", f"tap:{NO}", "wait:60M", f"tap:{RECORD}"] + taps
            + [f"tap:{RECORD}", "wait:50M", f"tap:{PLAY}", f"wait:{run}", f"tap:{STOP}",
               "wait:20M"])


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("build", type=pathlib.Path)
    ap.add_argument("--trigs", default="1,5,9,13", help="steps of track 1, 1-based, ascending")
    ap.add_argument("--run", default="700M", help="instructions to play for")
    ap.add_argument("--ssi-hz", default="96000")
    ap.add_argument("--json", type=pathlib.Path, help="keep panel_drive's output here")
    a = ap.parse_args()
    trigs = [int(t) for t in a.trigs.split(",")]

    cmd = [str(panel_drive()), str(a.build), "--ssi-hz", a.ssi_hz,
           "--capture", f"{EXCHANGE}:1:48", "--steps", ",".join(script(trigs, a.run))]
    done = subprocess.run(cmd, capture_output=True, text=True, timeout=1500)
    if not done.stdout.strip():
        print(done.stderr[-600:])
        return 2
    result = json.loads(done.stdout)
    if a.json:
        a.json.write_text(done.stdout)
    if result["outcome"] != "done":
        print("fault:", result["fault"])
        return 2

    found = SF.events(result["captures"])
    ons = SF.note_ons(found)
    if not ons:
        print("no note-on reached the DSP")
        return 1
    t0 = ons[0].icount
    print(f"{len(ons)} note-ons, {len(found) - len(ons)} note-offs")
    for e in found:
        print(f"  {SF.seconds(e.icount - t0):7.3f} s  {e.kind:3}  voices {list(e.voices)}")

    spacing = SF.gaps(found)
    # trigs repeat every 16 steps: the gaps between them, then the wrap to the first
    steps = [b - a_ for a_, b in zip(trigs, trigs[1:])] + [16 - trigs[-1] + trigs[0]]
    expected = [steps[i % len(steps)] for i in range(len(spacing))]
    per_step = [g / s for g, s in zip(spacing, expected)]
    if per_step:
        mean = sum(per_step) / len(per_step)
        worst = max(abs(p - mean) / mean for p in per_step)
        print(f"step period {mean / 1e6:.2f} M instructions = {SF.bpm(mean):.1f} BPM; "
              f"worst gap off by {worst * 100:.2f}%")
        return 0 if worst < 0.02 else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
