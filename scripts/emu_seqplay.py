"""Play the sequencer in the emulator and list the notes it sends the DSP.

    python scripts/emu_seqplay.py BUILD.syx [--trigs 1,5,9,13] [--track 2:3,11] [--run 700M]

Boots BUILD from reset with SSI0 paced (the audio-frame interrupt, and with it the forced
interrupts that tick the sequencer, run: digikit finding 04, "The internal step clock"),
enters the trigs with RECORD and the trig keys, presses PLAY and captures every frame sent
to the DSP. Prints each note-on (voices and note numbers) and note-off with its time, and
checks that the note-ons keep to the spacing of the trigs' steps.

`--trigs` is track 1's steps; each `--track N:STEPS` adds a track (TRK held, then trig key N).
The note comes from the frame header, one word per voice. Setting a note by hand (hold a
trig, push encoder A, turn) does not take in the emulator yet: every trig plays the default
note, 60.

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
NO, RECORD, PLAY, STOP, TRK, TRIG1 = 12, 19, 20, 21, 16, 25


def panel_drive() -> pathlib.Path:
    chosen = os.environ.get("PANEL_DRIVE")
    for path in ([pathlib.Path(chosen)] if chosen else []) + list(PANEL_CANDIDATES):
        if path.exists():
            return path
    raise SystemExit("panel_drive.exe not found; set PANEL_DRIVE")


def script(tracks: dict[int, list[int]], run: str) -> list[str]:
    entered: list[str] = []
    for track, trigs in sorted(tracks.items()):
        if track != 1 or len(tracks) > 1:
            entered += [f"press:{TRK}", "wait:10M", f"tap:{TRIG1 + track - 1}",
                        f"release:{TRK}", "wait:30M"]
        entered += [f"tap:{RECORD}"] + [f"tap:{TRIG1 + t - 1}" for t in trigs]
        entered += [f"tap:{RECORD}", "wait:30M"]
    return (["wait:1500M", f"tap:{NO}", "wait:60M"] + entered
            + ["wait:50M", f"tap:{PLAY}", f"wait:{run}", f"tap:{STOP}", "wait:20M"])


def play(build: pathlib.Path, tracks: dict[int, list[int]], run: str = "700M",
         ssi_hz: str = "96000", keep: pathlib.Path | None = None) -> list[SF.NoteEvent]:
    """Boot BUILD, play the trigs, and return the note events; raises RuntimeError on a fault."""
    cmd = [str(panel_drive()), str(build), "--ssi-hz", ssi_hz,
           "--capture", f"{EXCHANGE}:1:48", "--steps", ",".join(script(tracks, run))]
    done = subprocess.run(cmd, capture_output=True, text=True, timeout=1500)
    if not done.stdout.strip():
        raise RuntimeError(done.stderr[-300:])
    result = json.loads(done.stdout)
    if keep:
        keep.write_text(done.stdout)
    if result["outcome"] != "done":
        raise RuntimeError(f"fault: {result['fault']}")
    return SF.events(result["captures"])


def parse_tracks(trigs: str, extra: list[str]) -> dict[int, list[int]]:
    tracks = {1: [int(t) for t in trigs.split(",")]}
    for spec in extra:
        number, steps = spec.split(":")
        tracks[int(number)] = [int(t) for t in steps.split(",")]
    return tracks


def signature(found: list[SF.NoteEvent]) -> list[tuple]:
    """What a build did, with times from its first note-on: comparable between builds."""
    ons = SF.note_ons(found)
    t0 = ons[0].icount if ons else 0
    return [(e.icount - t0, e.kind, e.voices, e.notes) for e in found if e.icount >= t0]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("build", type=pathlib.Path)
    ap.add_argument("--trigs", default="1,5,9,13", help="steps of track 1, 1-based, ascending")
    ap.add_argument("--track", action="append", default=[], metavar="N:STEPS",
                    help="another track's steps, e.g. 2:3,11 (repeatable)")
    ap.add_argument("--run", default="700M", help="instructions to play for")
    ap.add_argument("--ssi-hz", default="96000")
    ap.add_argument("--json", type=pathlib.Path, help="keep panel_drive's output here")
    a = ap.parse_args()
    tracks = parse_tracks(a.trigs, a.track)
    try:
        found = play(a.build, tracks, a.run, a.ssi_hz, a.json)
    except RuntimeError as error:
        print(error)
        return 2

    ons = SF.note_ons(found)
    if not ons:
        print("no note-on reached the DSP")
        return 1
    t0 = ons[0].icount
    print(f"{len(ons)} note-ons, {len(found) - len(ons)} note-offs")
    for e in found:
        notes = f"  notes {list(e.notes)}" if e.notes else ""
        print(f"  {SF.seconds(e.icount - t0):7.3f} s  {e.kind:3}  voices {list(e.voices)}{notes}")

    spacing = SF.gaps(found)
    # trigs repeat every 16 steps: the gaps between the steps any track plays on, then the
    # wrap to the first (a step two tracks share is one event: their voices are one mask)
    trigs = sorted({t for steps in tracks.values() for t in steps})
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
