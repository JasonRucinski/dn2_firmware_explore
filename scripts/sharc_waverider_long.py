"""A long render of the Waverider voice in digikit's SHARC runner, not looped, for `dnfw wav report`.

    python scripts/sharc_waverider_long.py CASE [--blocks 375] [--note 60] [--chunk 25] [--native]

The other runner tests render 12 blocks (8 ms) and loop them to fill a WAV, so a report
on their files describes the loop. This one renders BLOCKS blocks in a row (375 is a
quarter of a second) and writes them as they are, in 32-bit float. The Python runner
takes about 11 seconds a block, so 375 blocks take over an hour; `--native` runs them in
digikit's native engine (scripts/sharc_native.py), about 0.6 seconds a block, and names
its files long_CASE_native_*.

Track 0 is Waverider, osc 1 alone, table 0, triggered on the first block:

| case | what changes |
|---|---|
| hold | nothing: POS stays mid-table |
| sweep | POS moves from 0 to 120 over the render, a step each block |

Every block's machine output is compared bit for bit with `live.render_two` fed the
inputs the DSP unpacked, whichever engine ran. Writes out/waverider/long_CASE_machine.wav (the oscillator's
output, the samples compared), long_CASE_amp_out.wav (after the amp) and
long_CASE_report.json, each chunk as it finishes. Exit 0 when no sample differs.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import sharc_waverider_m5 as g                 # noqa: E402
from dnfw import progress, sharcemu            # noqa: E402
from dnfw.audio import wavio                   # noqa: E402
from dnfw.waverider import dsp, live           # noqa: E402

CASES = {"hold": lambda b, n: 0x3000,
         "sweep": lambda b, n: round(0x7800 * b / max(n - 1, 1))}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("case", choices=sorted(CASES))
    ap.add_argument("--digikit", type=pathlib.Path, default=sharcemu.path())
    ap.add_argument("--image", type=pathlib.Path,
                    default=ROOT / "00_Resources/00_Firmware/Digitone_II_OS1.11_dist.zip")
    ap.add_argument("--blocks", type=int, default=375)
    ap.add_argument("--note", type=int, default=60)
    ap.add_argument("--chunk", type=int, default=25, help="blocks between writes of the files")
    ap.add_argument("--native", action="store_true", help="digikit's native engine, not the Python runner")
    a = ap.parse_args(argv)

    dk = g.m1.Digikit(a.digikit)
    g.fx.bind(str(a.digikit / "tools"))
    g.m4.IMAGE = a.image
    stock = g.m1.dn2_section7(a.image)
    sound, machines = g.m4.init_sound(a.image)
    wr = g.Image(dk, dsp.section7(stock))
    tables = dsp.tables()
    pos = CASES[a.case]
    g.OUT.mkdir(parents=True, exist_ok=True)
    what = f"Waverider osc 1, table 0, note {a.note}, POS {a.case}"
    tag = f"{a.case}_native" if a.native else a.case
    engine = "the runner (native engine)" if a.native else "the runner"
    machine, amp, seq, report = [], [], [], {"case": a.case, "note": a.note, "blocks": a.blocks}

    def write(done, halt=None):
        want = live.render_two(tables, seq, g.BLOCK, "float32")
        bad = g.mismatches(machine, want)
        for name, data, stage in (("machine", machine, "the machine's output, compared with the model"),
                                  ("amp_out", amp, "after the amp, not compared")):
            wavio.write(g.OUT / f"long_{tag}_{name}.wav", data, g.RATE,
                        f"{engine}, not looped, {done} blocks: {what}; {stage}")
        report.update(rendered_blocks=done, samples=len(machine), mismatches=bad, halt=halt)
        (g.OUT / f"long_{tag}_report.json").write_text(json.dumps(report, indent=1) + "\n")
        return bad

    bad = 0
    with tempfile.TemporaryDirectory(dir=g.OUT) as tmp, \
            progress.Job(f"runner long {tag}", total=a.blocks) as job:
        snap, m2mach = g.snapshot_path(dk, stock, pathlib.Path(tmp))
        state = g.init_on(snap, m2mach, wr)
        if a.native:
            state = g.native_on(state, wr)
        for first in range(0, a.blocks, a.chunk):
            n = min(a.chunk, a.blocks - first)

            def fb(b, first=first):
                over = {g.WAV1: pos(first + b, a.blocks), g.TBL1: 0, g.LEV2: 0}
                return g.base_frame(sound, machines, trigger=(first + b == 0), overrides=over,
                                    note=a.note << 8).to_bytes()
            run = g.run_blocks(state, fb, n)
            if not run["ok"]:
                write(first + run["blocks"], run.get("halt"))
                print(f"FAIL halted in block {first + run['blocks']}: {run.get('halt')}")
                return 1
            machine += g.track_series(run, 0)
            amp += run["amp_out"]
            seq += [(i[0]["note"], (i[0]["wav1"], i[0]["tbl1"], i[0]["tun1"], i[0]["lev1"], *i[0]["move1"],
                                    i[0]["sync"][0], i[0]["smth"][0]),
                     (*i[0]["osc2"], *i[0]["move2"], i[0]["sync"][1], i[0]["smth"][1]),
                     (i[0]["trig"], i[0]["triggered"], i[0]["prst"], i[0]["song"], i[0]["tempo"], i[0]["dclk"]))
                    for i in run["t5_inputs"] if 0 in i]
            state = run["state"]
            bad = write(first + n)
            job.update(done=first + n, detail=f"{bad} samples differ from the model")
            print(f"  {first + n}/{a.blocks} blocks, {bad} samples differ from the model", flush=True)
    print("PASS" if bad == 0 else "FAIL", f"{len(machine)} samples, {bad} differ from the model")
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
