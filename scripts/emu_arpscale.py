"""arpscale in the emulator: the arp's step offsets against a reference, stock alongside.

    python scripts/emu_arpscale.py BUILD.syx [--stock STOCK.syx] [--case NAME ...]

Plays the sequencer headless (`scripts/emu_seqplay.py` and digikit's `panel_drive`,
which runs the frame ISR, the step clock and the arp): a C major chord (C4 E4 G4)
on track 1's first trig, arp UP, as `emu_seqplay.py --chord 4,3 --chord-length 60 --arp UP`.
Before PLAY it writes, through `panel_drive`'s `poke` step:

- the sound's sixteen step offsets (`[0x800052a0] + 52 + 1163 x track`, `+358`);
- the toggle (`0x405cd8af`, 1 = on);
- SCALE, ROOT, MODE and the per-track switch in the playback copy of the
  pattern (`L = *0x42c5a9a0`: the header at `L + 0x1dd40`, the track at
  `L + 1701 x track`), whose addresses a first run reads with `peek`;
- the arp's LEN (16 steps) and step mask (all on).

The arp starts its step count again at every trig, so a note's step is its
place in its trig's run of notes.

The runs in `LIVE` play a case from the KEYBOARD page instead of a trig: track
3 selected and its arp UP, TRIG 9, 11 and 13 are held for about 24 arp steps,
with the sequencer stopped or, for one, playing an empty pattern. The keys follow the track's scale and root
(C4 E4 G4 in C major, D4 F4 A4 in D pentatonic minor). A live note's voice
record has no playback copy (`+44` is zero), so this checks the cave's other
way to the scale, and track 3 checks that it finds the right track.

For every case the same pokes go to stock and to BUILD. Stock is the control:
its notes must be the held note plus the offset in semitones, which also yields
the held note of each step (`stock - offset`). BUILD's notes must equal the rule
in `scripts/build_arpscale.py`, computed here in Python from the firmware's own
scale tables, independently of the ColdFire code. A case that keeps stock
behaviour (toggle off, CHROMATIC, CHORD MEMORY) must equal stock exactly.

Needs what `scripts/emu_seqplay.py` needs: a `panel_drive` that delivers the forced
interrupts and takes a literal `--capture` length (digikit #65 and #66; the
`feat/seqplay-chords` branch of angellinares/digikit has both), found through
`PANEL_DRIVE`. Its `poke` and `peek` steps write and read RAM.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import subprocess
import sys
from typing import Literal

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]

import build_arpscale as bs  # noqa: E402
import build_scale_degrees as sd  # noqa: E402
import emu_seqplay as sp  # noqa: E402
from dnfw import seqframes as SF  # noqa: E402
from dnfw.cli.files import read_image  # noqa: E402
from dnfw.firmware.load import load  # noqa: E402

STOCK = ROOT / "00_Resources/00_Firmware/Digitone_II_OS1.11.syx"

PLAYBACK = 0x42C5A9A0          # -> L, the playback copy of the pattern
SOUNDS = 0x800052A0            # -> the live sounds: + 52 + 1163 x track
SOUND_FIRST, SOUND_STRIDE, OFFSETS = 52, 1163, 358
ARP_LEN, ARP_MASK = 355, 356   # the arp's LEN (steps - 1) and its u16 step mask
TRACK = 0
CHORD = [4, 3]                 # C4, then +4 (E4), then +3 (G4)
CHORD_LEN = 60                 # units of the chord's note length: about 14 arp steps a trig
KEYBOARD = 18                  # panel code of [KEYBOARD]
LIVE_KEYS = (33, 35, 37)       # TRIG 9, 11, 13 on the KEYBOARD page: C4 E4 G4 in C major
LIVE_TRACK = 2                 # track 3: not track 1, so a wrong track index shows
LIVE_HOLD = "400M"             # how long the keys are held: about 24 arp steps
STEP = 16.5e6                  # a sixteenth at 120 BPM, in instructions
RUN_GAP = 1.5 * STEP           # a longer gap between note-ons starts the next trig's run
OFFS = [0, 2, 2, -1, 3, -2, 7, -7, 1, 4, -3, 5, 0, -8, 9, -1]

# name -> (toggle, header SCALE, ROOT, MODE, switch, track SCALE, ROOT, MODE, stock expected)
CASES = {
    "ionian-c":        (1, 0, 0, 0, 0x00, None, None, None, False),
    "hirajoshi-a":     (1, 17, 9, 0, 0x00, None, None, None, False),
    "per-track":       (1, 0, 0, 0, 0x07, 7, 2, 0, False),     # header Ionian C, track Pent. Min D
    "chord-memory":    (1, 0, 0, 5, 0x00, None, None, None, True),
    "toggle-off":      (0, 0, 0, 0, 0x00, None, None, None, True),
    "chromatic":       (1, 0xFF, 0, 0, 0x00, None, None, None, True),
}

# How a run plays its chord: a trig on track 1, or held on the KEYBOARD page with the
# sequencer stopped or playing.
Source = Literal["trig", "stopped", "playing"]
LIVE: dict[str, tuple[str, Source]] = {
    "live-ionian-c": ("ionian-c", "stopped"),
    "live-per-track": ("per-track", "stopped"),
    "live-toggle-off": ("toggle-off", "stopped"),
    "live-playing-ionian-c": ("ionian-c", "playing"),
}
RUNS: dict[str, tuple[str, Source]] = {name: (name, "trig") for name in CASES} | LIVE


def reference(held: int, offset: int, semis: list[int], root: int) -> int:
    """The rule, in Python: `held` moved `offset` degrees of the scale `semis` from `root`."""
    if offset == 0:
        return held
    rel = held - root
    octave, pc = divmod(rel, 12)
    if pc not in semis:
        for d in range(1, 12):
            if (pc - d) % 12 in semis:
                octave += (pc - d) // 12
                pc = (pc - d) % 12
                break
            if (pc + d) % 12 in semis:
                octave += (pc + d) // 12
                pc = (pc + d) % 12
                break
    octaves, degree = divmod(semis.index(pc) + offset, len(semis))
    return root + 12 * (octave + octaves) + semis[degree]


def live_script(extra: list[str], playing: bool) -> list[str]:
    """Select LIVE_TRACK, set its arp to UP, run EXTRA, then hold LIVE_KEYS on the
    KEYBOARD page, with the sequencer stopped or PLAYING."""
    select = [f"press:{sp.TRK}", "wait:10M", f"tap:{sp.TRIG1 + LIVE_TRACK}",
              f"release:{sp.TRK}", "wait:30M"]
    arp = sp.arp_steps("UP")
    hold = ([f"tap:{KEYBOARD}", "wait:40M"] + [f"press:{k}" for k in LIVE_KEYS]
            + [f"wait:{LIVE_HOLD}"] + [f"release:{k}" for k in LIVE_KEYS] + ["wait:20M"])
    if playing:
        hold = [f"tap:{sp.PLAY}", "wait:30M"] + hold + [f"tap:{sp.STOP}", "wait:20M"]
    return ["wait:1500M", f"tap:{sp.NO}", "wait:60M"] + select + arp + extra + hold


def runs(found: list[SF.NoteEvent]) -> list[list[SF.NoteEvent]]:
    """The note-ons, grouped into one run per trig: the arp starts its steps again at each."""
    grouped: list[list[SF.NoteEvent]] = []
    for event in SF.note_ons(found):
        if grouped and event.icount - grouped[-1][-1].icount <= RUN_GAP:
            grouped[-1].append(event)
        else:
            grouped.append([event])
    return grouped


def run(image: pathlib.Path, extra: list[str], source: Source) -> tuple[list, dict]:
    """-> ([(step, note), ...] in play order, {address: bytes peeked})."""
    if source != "trig":
        steps = live_script(extra, source == "playing")
    else:
        steps = sp.script({1: [1]}, "700M", chord=CHORD, chord_length=CHORD_LEN, arp="UP")
        at = steps.index(f"tap:{sp.PLAY}")
        steps[at:at] = extra
    cmd = [str(sp.panel_drive()), str(image), "--ssi-hz", "96000",
           "--capture", f"{sp.EXCHANGE}:1:48", "--steps", ",".join(steps)]
    done = subprocess.run(cmd, capture_output=True, text=True, timeout=1500)
    result = json.loads(done.stdout)
    if result["outcome"] != "done":
        raise SystemExit(f"{image.name}: fault {result['fault']}")
    peeks = {int(r["peek"], 16): bytes.fromhex(r["hex"]) for r in result["results"] if "peek" in r}
    played = [(k, int(e.notes[0])) for group in runs(SF.events(result["captures"]))
              for k, e in enumerate(group) if e.notes]
    return played, peeks


def addresses(image: pathlib.Path) -> tuple[int, int, int]:
    """-> (L, the first sound, the switch byte as found)."""
    _, peeks = run(image, [f"peek:{PLAYBACK:#x}:4", f"peek:{SOUNDS:#x}:4"], "trig")
    lo = int.from_bytes(peeks[PLAYBACK], "big")
    sound = int.from_bytes(peeks[SOUNDS], "big") + SOUND_FIRST
    _, peeks = run(image, [f"peek:{lo + sd.HEADER + sd.H_SWITCH:#x}:1"], "trig")
    return lo, sound, peeks[lo + sd.HEADER + sd.H_SWITCH][0]


def pokes(lo: int, first_sound: int, case: tuple, track_index: int) -> list[str]:
    toggle, hs, hr, hm, switch, ts, tr, tm, _ = case
    header = lo + sd.HEADER
    track = lo + sd.TRACK_STRIDE * track_index
    sound = first_sound + SOUND_STRIDE * track_index
    out = [f"poke:{sound + OFFSETS:#x}:" + bytes(o & 0xFF for o in OFFS).hex(),
           f"poke:{sound + ARP_LEN:#x}:0fffff",

           f"poke:{bs.FLAG:#x}:{toggle:02x}",
           f"poke:{header + sd.H_SCALE:#x}:{hs:02x}{hm:02x}{hr:02x}",
           f"poke:{header + sd.H_SWITCH:#x}:{switch:02x}"]
    if ts is not None:
        out.append(f"poke:{track + sd.T_SCALE:#x}:{ts:02x}{tm:02x}{tr:02x}")
    return out


def expected(case: tuple, stock_played: list, tables: list[list[int]]) -> list[int] | None:
    """-> the notes BUILD must play, or None when stock is not a valid control: each of
    stock's notes must be a note of a three-note chord, taken UP, plus its step's
    offset in semitones."""
    held = [note - OFFS[k % 16] for k, note in stock_played]
    chord = sorted(set(held))
    if len(chord) != len(CHORD) + 1 or any(h != chord[k % len(chord)]
                                           for h, (k, _) in zip(held, stock_played)):
        return None
    if case[-1]:
        return [note for _, note in stock_played]
    _toggle, hs, hr, _hm, switch, ts, tr, _tm, _ = case
    scale = ts if switch & 4 else hs
    root = tr if switch & 2 else hr
    return [reference(h, OFFS[k % 16], tables[scale], root)
            for h, (k, _) in zip(held, stock_played)]


def check(name: str, case: tuple, images: dict, places: dict, tables, source: Source) -> bool:
    """Play CASE on stock and on the build, print both, and compare the build with the rule."""
    track_index = TRACK if source == "trig" else LIVE_TRACK
    played = {who: run(images[who], pokes(*places[who][:2], case, track_index), source)[0]
              for who in images}
    built = [note for _, note in played["build"]]
    print(f"\n{name}: stock  {[note for _, note in played['stock']]}")
    print(f"{' ' * len(name)}  build  {built}")
    want = expected(case, played["stock"], tables)
    if want is None:
        print("  FAIL  stock's notes are not the chord plus the offsets in semitones")
        return False
    print(f"{' ' * len(name)}  want   {want}")
    steps = {k % 16 for k, _ in played["stock"]}
    ok = built == want and len(steps) >= 12
    print(f"  {'ok  ' if ok else 'FAIL'}  {len(built)} notes over {len(steps)} of the 16 offsets")
    return ok


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("build", type=pathlib.Path)
    ap.add_argument("--stock", type=pathlib.Path, default=STOCK)
    ap.add_argument("--case", action="append", choices=list(RUNS))
    a = ap.parse_args()
    tables = sd.scales(load(read_image(a.stock)).container.find(bs.MAIN_OS).unpack())

    images = {"stock": a.stock, "build": a.build}
    places = {who: addresses(image) for who, image in images.items()}
    for who, (lo, sound, switch) in places.items():
        print(f"{who}: playback copy {lo:#010x}, first sound {sound:#010x}, switch {switch:#04x}")

    failures = sum(not check(name, CASES[RUNS[name][0]], images, places, tables, RUNS[name][1])
                   for name in a.case or list(RUNS))
    print(f"\n{failures} failing case(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
