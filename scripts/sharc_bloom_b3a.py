"""Bloom B3a (offline): the section 7 the Bloom mod ships, run in the runner.

    python scripts/sharc_bloom_b3a.py \\
        --image 00_Resources/00_Firmware/Digitone_II_OS1.11_dist.zip \\
        --digikit ../digikit-wt-sharcemu [--blocks 8]

The image is `dnfw.bloom.dsp.section7(stock)`, byte for byte what the mod applies, and
nothing is poked or redirected: the type-7 loop is entered by the JUMP in the image, and
every input arrives through a 2,688-byte frame run through the firmware's own per-block
routine `sw 0x1c2712` (frame unpack, slot dispatch, per-track chain), as Waverider's M5
gate does (`scripts/sharc_waverider_m5.py`, whose harness this uses).

Runs (track 0 on machine 7 with WaveTone's machine page, a trig on block 1):

| run | what |
|---|---|
| init | note 60, TUN1 0 |
| note72 | note 72 |
| tune12 | note 60, TUN1 +12: the same pitch as note72 |
| two | tracks 0 and 3 on machine 7, track 3 at note 67 |
| wavetone | track 0 on WaveTone (1): Bloom's image against stock's |

**PASS** when: the loop is entered in every block and finds track 0's record at 7 (the
lookup patch carries the type through); the type-7 dispatch takes the no-setup arm; in
every block, every type-7 track's buffer at the loop's exit is bit for bit
`dnfw.bloom.live` fed the DSP's own note cell and TUN1 word, with the phase carried
from the boot's zero (the DSP's phase at each entry is the reference's); tune12 equals
note72 bit for bit; the voice is audible; and the controls hold: with no type-7 track,
all 16 buffers equal a stock run's, and in a type-7 run tracks 1-15 equal a stock run's.

Results to `out/bloom/b3a_report.json`. Exit 0 on PASS.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import pathlib
import struct
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import sharc_dn2_fixups as fx                                  # noqa: E402
import sharc_waverider_m3 as m3                                # noqa: E402
import sharc_waverider_m4 as m4                                # noqa: E402
import sharc_waverider_m5 as m5                                # noqa: E402
import sharc_waverider_render as m1                            # noqa: E402
import sharc_waverider_voice as m2                             # noqa: E402
from dnfw.bloom import dsp, live                               # noqa: E402
from dnfw.waverider import frame as FR                         # noqa: E402
from dnfw.waverider import testtable                           # noqa: E402
from dnfw.waverider import voice as V                          # noqa: E402

OUT = ROOT / "out" / "bloom"
BLOCK = m4.BLOCK
TUN1, TUN1_ZERO = m5.TUN1, m5.TUN1_ZERO
NOTE_CELL = m5.NOTE_CELL


def f32(bits: int) -> float:
    return struct.unpack("<f", struct.pack("<I", bits & 0xFFFFFFFF))[0]


def bits(x: float) -> int:
    return struct.unpack("<I", struct.pack("<f", x))[0]


def init_runner(dk, stock: bytes, image: m5.Image, work: pathlib.Path):
    """The engine-init snapshot (Waverider M2's, cached under out/waverider; built here
    once, about 10 minutes, if missing), re-pointed at IMAGE."""
    reader, _, _ = m1.reader_code(False, work)
    m2mach = m2.Machine(dk, stock, reader, testtable.table())
    snap = m2.OUT / f"m2_init_{m2mach.sha[:12]}.snap"
    if not snap.exists():
        print(f"  building the engine-init snapshot {snap.name} (once)")
        init = m2.run_init(m2mach, snap, True, 3)
        if not init["ok"]:
            raise SystemExit(f"engine init stopped: {init['halt']}")
    return m5.init_on(snap, m2mach, image)


def frames(sound, machines, *, t0=dsp.TYPE, note=0x3C00, tun1=TUN1_ZERO, second=None):
    def fb(b):
        f = m5.base_frame(sound, machines, t0=t0, note=note, trigger=(b == 1),
                          overrides={TUN1: tun1}, others={3: 1} if second else None)
        if second:
            f.header(FR.MACHINE, 3, dsp.TYPE)
            f.header(FR.NOTE, 3, second)
            if b == 1:
                f.trigger(3)
        return f.to_bytes()
    return fb


def run(init, frame_of, blocks: int) -> dict:
    """BLOCKS calls of sw 0x1c2712 (the Python runner). Per block: each track's buffer
    at the loop's exit (0x1c944c) and at the routine's end, as bits; each type-7 track's
    inputs and phase at the loop's entry; the per-type setup arm taken."""
    state = init
    out = {"machine": [], "buffers": [], "inputs": [], "entries": 0, "setup": []}
    for b in range(blocks):
        tap = {}

        def at_dispatch(r):
            tap["bufs"] = [m2.word(r.state, V.TRACK_BUFFERS + 4 * t) for t in range(16)]

        def at_entry(r):
            out["entries"] += 1
            ins = {}
            for t in range(16):
                if m2.word(r.state, V.track_record(t) + V.TRACK_MACHINE) == dsp.TYPE:
                    ins[t] = {"note": m2.word(r.state, NOTE_CELL + 4 * t) or 0,
                              "tun1": m5.frame_word(r.state, FR.slot_offset(t, TUN1)),
                              "phase": m2.word(r.state, dsp.PHASES_DM + 4 * t) or 0}
            tap["inputs"] = ins

        def at_resume(r):
            tap["machine"] = [[m2.word(r.state, tap["bufs"][t] + 4 * k) or 0 for k in range(BLOCK)]
                              for t in range(16)]

        hooks = {m3.DISPATCH: at_dispatch, dsp.LOOP_SW: at_entry, dsp.RESUME_SW: at_resume,
                 m5.SETUP_GUARD: lambda r: out["setup"].append(("guard", b, m2.word_reg(r, "R2"))),
                 m5.SETUP_TABLE_READ: lambda r: out["setup"].append(("table", b, None)),
                 m5.SETUP_NONE: lambda r: out["setup"].append(("none-arm", b, None))}
        r = m4.unpack_call(state, frame_of(b))
        res = fx.run(r, 8_000_000, m4.fixups(hooks))
        if not (res[0] == "halt" and res[1].pc_sw == m4.UNPACK_RETURN):
            halt = f"{res[1].reason} at {res[1].pc_sw:#x}" if res[0] == "halt" else f"{res[0]}"
            return {**out, "ok": False, "blocks": b, "halt": halt}
        out["machine"].append(tap.get("machine"))
        out["buffers"].append([[m2.word(r.state, tap["bufs"][t] + 4 * k) or 0 for k in range(BLOCK)]
                               for t in range(16)])
        out["inputs"].append(tap.get("inputs", {}))
        state = r
    return {**out, "ok": True, "blocks": blocks}


def check_track(run_, t) -> dict:
    """Track T's machine tap against dnfw.bloom.live, block by block, the phase carried
    from zero: -> mismatching samples, phase mismatches at entry, the tap's RMS."""
    p, bad, phase_bad, blocks, samples = 0.0, 0, 0, 0, []
    for b, ins in enumerate(run_["inputs"]):
        if t not in ins:
            continue
        blocks += 1
        i = ins[t]
        phase_bad += bits(p) != i["phase"]
        dt, inv = live.step(live.note_from_frame(f32(i["note"]), i["tun1"]))
        want, p = live.render_block(p, dt, inv, BLOCK)
        got = run_["machine"][b][t]
        bad += sum(bits(w) != g for w, g in zip(want, got))
        samples += [f32(g) for g in got]
    rms = math.sqrt(sum(x * x for x in samples) / len(samples)) if samples else 0.0
    return {"blocks": blocks, "mismatched_samples": bad, "phase_mismatches": phase_bad, "rms": rms}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0],
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--image", type=pathlib.Path, default=m4.IMAGE)
    p.add_argument("--digikit", type=pathlib.Path,
                   default=pathlib.Path(os.environ.get("DNFW_DIGIKIT_SHARC",
                                                       ROOT.parent / "digikit-wt-sharcemu")))
    p.add_argument("--blocks", type=int, default=8)
    a = p.parse_args(argv)
    if not a.image.exists():
        raise SystemExit(f"{a.image}: the Digitone II OS 1.11 file is needed (bring your own)")
    OUT.mkdir(parents=True, exist_ok=True)
    dk = m1.Digikit(a.digikit)
    fx.bind(str(a.digikit / "tools"))
    m4.IMAGE = a.image
    stock = m1.dn2_section7(a.image)
    sound, machines = m4.init_sound(a.image)
    bloom_img, stock_img = m5.Image(dk, dsp.section7(stock)), m5.Image(dk, stock)
    n = a.blocks
    with tempfile.TemporaryDirectory(dir=OUT) as tmp:
        work = pathlib.Path(tmp)
        init = init_runner(dk, stock, bloom_img, work)
        init_stock = init_runner(dk, stock, stock_img, work)
    print("  running")
    runs = {"init": run(init, frames(sound, machines), n),
            "note72": run(init, frames(sound, machines, note=0x4800), n),
            "tune12": run(init, frames(sound, machines, tun1=TUN1_ZERO + 12 * 256), n),
            "two": run(init, frames(sound, machines, second=0x4300), n),
            "wavetone": run(init, frames(sound, machines, t0=1), n)}
    stock_runs = {"init": run(init_stock, frames(sound, machines), n),
                  "wavetone": run(init_stock, frames(sound, machines, t0=1), n)}
    every = {**runs, **{f"stock_{k}": v for k, v in stock_runs.items()}}
    ok_runs = all(r["ok"] for r in every.values())
    checks = {"every run returns every block": ok_runs}
    num = {"section7_bytes": len(bloom_img.stream), "section7_sha256": bloom_img.sha,
           "digikit_head": dk.head, "blocks": n, "placements": dsp.placements()}
    if ok_runs:
        tracks = {name: {t: check_track(runs[name], t) for t in sorted({t for i in runs[name]["inputs"] for t in i})}
                  for name in ("init", "note72", "tune12", "two")}
        num["tracks"] = tracks
        num["setup"] = {name: sorted({s[0] for s in runs[name]["setup"]}) for name in runs}
        num["entries"] = {name: r["entries"] for name, r in every.items()}
        checks.update({
            "the loop is entered once in every block": all(runs[x]["entries"] == n for x in runs),
            "track 0 is machine 7 at the loop, every block (the lookup patch)":
                all(0 in i for i in runs["init"]["inputs"]),
            "the type-7 dispatch takes the no-setup arm, never the table":
                all("table" not in num["setup"][x] for x in ("init", "note72", "tune12", "two")),
            "init, note72, tune12: track 0 bit for bit dnfw.bloom.live, every block":
                all(tracks[x][0]["mismatched_samples"] == 0 and tracks[x][0]["blocks"] == n
                    for x in ("init", "note72", "tune12")),
            "two: tracks 0 and 3 both bit for bit, each its own phase":
                set(tracks["two"]) == {0, 3} and all(v["mismatched_samples"] == 0 for v in tracks["two"].values()),
            "the phase at each entry is the reference's, carried from zero":
                all(v["phase_mismatches"] == 0 for x in tracks.values() for v in x.values()),
            "tune12 equals note72 bit for bit": runs["tune12"]["machine"] == runs["note72"]["machine"],
            "note72 differs from init": runs["note72"]["machine"] != runs["init"]["machine"],
            "the voice is audible (RMS > 0.1 at the machine tap)": tracks["init"][0]["rms"] > 0.1,
            "control: no type-7 track -> all 16 buffers equal stock's, every block":
                runs["wavetone"]["buffers"] == stock_runs["wavetone"]["buffers"],
            "control: in a type-7 run, tracks 1-15 equal stock's":
                all(b[1:] == s[1:] for b, s in zip(runs["init"]["buffers"], stock_runs["init"]["buffers"])),
            "control: the stock image never enters the loop": stock_runs["init"]["entries"] == 0,
        })
    else:
        num["halts"] = {x: r.get("halt") for x, r in every.items() if not r["ok"]}
    passed = all(checks.values())
    path = OUT / "b3a_report.json"
    path.write_text(json.dumps({"pass": passed, "checks": checks, "numbers": num}, indent=2,
                               default=str) + "\n", encoding="utf-8")
    for name, v in checks.items():
        print(f"  {'PASS' if v else 'FAIL'}  {name}")
    for name, tr in num.get("tracks", {}).items():
        for t, v in tr.items():
            print(f"  {name} track {t}: {v}")
    print(f"\nB3a {'PASS' if passed else 'FAIL'}: {path}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
