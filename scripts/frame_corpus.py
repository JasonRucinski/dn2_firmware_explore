"""Capture a corpus of the frames the ColdFire really sends the DSP, across machines and patterns.

    python scripts/frame_corpus.py --out out/frame_corpus [--machines 0,1,2,3,4] [--run 500M]

Boots the stock OS 1.11 from reset with SSI0 paced (`panel_drive --ssi-hz`), sets track 1's
machine in MACHINE SEL, enters trigs, presses PLAY, and keeps the whole 2,688-byte frame at
every send (the capture at the exchange routine 0x400cf7be, tx buffer argument 1). Frames
that differ from the one kept before are written big-endian, the way the ColdFire holds them
(`tools/dn2probe_frame.py`'s format), so `sharc_frame_census.py replay` takes them as they
are. This is the corpus naturarum's T6.0 census calls "every T3.3 capture", made here.

Machines: 0 FM Tone, 1 WaveTone... in MACHINE SEL order the list is FM TONE, FM DRUM,
WAVETONE, SWARMER, MIDI and track 1 starts on WAVETONE, so each machine is a number of UP
or DOWN taps from there. The pattern's trigs are entered with RECORD and the trig keys as
`digikit-rust/tools/seqplay.py` does (it is imported for the key codes and script).
"""
import argparse
import importlib.util
import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
DIGIKIT = ROOT.parent / "digikit-rust"
STOCK = ROOT / "00_Resources/00_Firmware/Digitone_II_OS1.11_dist/Digitone_II_OS1.11.syx"
# the build with a literal --capture length (service_forced, as seqplay.py asks for)
PANEL = DIGIKIT.parent / "digikit-wt-forced/out/target/release/examples/panel_drive.exe"
FRAME = 2688

# MACHINE SEL: taps from WAVETONE (its starting position) to each machine; DOWN 14, UP 11
TO_MACHINE = {0: ["tap:11", "tap:11"], 1: [], 2: ["tap:11"], 3: ["tap:14"], 4: ["tap:14", "tap:14"]}
NAMES = {0: "fmtone", 1: "wavetone", 2: "fmdrum", 3: "swarmer", 4: "midi"}


def load_seqplay():
    spec = importlib.util.spec_from_file_location("seqplay", DIGIKIT / "tools/seqplay.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["seqplay"] = mod
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=pathlib.Path, required=True)
    ap.add_argument("--machines", default="0,1,2,3,4")
    ap.add_argument("--run", default="500M", help="instructions to play")
    ap.add_argument("--ssi-hz", default="96000")
    ap.add_argument("--patterns", default="1,5,9,13;1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16;1,9",
                    help="track 1 steps, semicolon-separated patterns")
    ap.add_argument("--keep", type=int, default=80, help="most frames kept per run")
    a = ap.parse_args()
    sp = load_seqplay()
    a.out.mkdir(parents=True, exist_ok=True)
    total = 0
    for m in [int(x) for x in a.machines.split(",")]:
        for pi, pat in enumerate(a.patterns.split(";")):
            trigs = {1: [int(t) for t in pat.split(",")]}
            steps = sp.script(trigs, a.run, None, 0, None)
            # insert the machine change after the start-up wait and the popup dismissal
            at = 3                                              # wait:1500M, tap:NO, wait:60M
            sel = (["press:17", "tap:2", "release:17", "wait:60M"]
                   + [t for tap in TO_MACHINE[m] for t in (tap, "wait:20M")]
                   + ["tap:10", "wait:100M", "tap:2", "wait:60M"])
            steps = steps[:at] + sel + steps[at:]
            cmd = [str(PANEL), str(STOCK), "--ssi-hz", a.ssi_hz, "--capture",
                   f"{sp.EXCHANGE}:1:{FRAME}", "--steps", ",".join(steps)]
            done = subprocess.run(cmd, capture_output=True, text=True, timeout=3000)
            if not done.stdout.strip():
                print(f"machine {m} pattern {pi}: no output: {done.stderr[-200:]}")
                continue
            result = json.loads(done.stdout.strip().splitlines()[-1])
            frames = [bytes.fromhex(c["hex"]) for c in result["captures"]]
            kept, last = [], None
            for f in frames:
                if len(f) == FRAME and f != last:
                    kept.append(f)
                    last = f
            if len(kept) > a.keep:                               # an even spread over the run
                kept = [kept[i * len(kept) // a.keep] for i in range(a.keep)]
            d = a.out / f"{NAMES[m]}_p{pi}"
            d.mkdir(exist_ok=True)
            for i, f in enumerate(kept):
                (d / f"{i:04d}.frame_be.bin").write_bytes(f)
            total += len(kept)
            print(f"machine {m} ({NAMES[m]}) pattern {pi}: {len(frames)} sends, {len(kept)} distinct kept "
                  f"({result['outcome']})", flush=True)
    print(f"{total} frames in {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
