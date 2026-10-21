"""Bloom B1 (offline): does a cutoff written into the track record just before the stock
filter's setup move the stock filter within the same block?

    python scripts/sharc_bloom_b1.py \\
        --image 00_Resources/00_Firmware/Digitone_II_OS1.11_dist.zip \\
        --digikit ../digikit-wt-sharcemu [--blocks 10] [--k 4]

`docs/bloom-machine.md`, "Two filters, both pulsed". Bloom pulses the stock filter by
writing FREQ into the track record (`+0x1cc`, `frame.RECORD_FIELDS`, value / 32768 as
float32) from a setup arm, which the dispatch runs before the common continuation calls
the filter's setup through `0x8052dba4[type]` at sw `0x1c91ad`
(`docs/waverider-dsp-silence.md`, "What the setup arms write"). That design rests on one
assumption, asked here and nowhere else: **the filter recomputes its coefficients from
the record every block**, so a write before its setup is heard in that block.

No SHARC code of Bloom's is involved. The runner itself writes the record at the PC the
arm would run at, so this measures the firmware, not our arm. The signal is Waverider
Milestone 4's type-5 voice on track 0 (a steady, known-good saw-like table through the
per-track chain, filter Multimode), and the tap is track 0's buffer at the amp's input:
after the filter, before the amp (`sharc_waverider_m4.run_blocks`'s `pre_amp`).

Four runs of the same blocks, the note triggered on block 1:

| run | the frame's FREQ | the runner writes the record | role |
|---|---|---|---|
| A | open (the init sound's `0x7f00`) every block | nothing | control |
| B | open, then **dark** from block K | nothing | the frame path, as a stock LFO arrives: the reference |
| C | open every block | **dark at sw 0x1c91ad**, from block K | **the question** |
| D | open every block | dark at the type-5 entry (after the setup), from block K | timing: the same write, too late |

**PASS** when the hook is reached every block, the record holds the frame's own value at
the hook before the write (so it is the field the filter reads), B is clearly darker than
A from block K (the experiment can discriminate), and C follows B from block K: equal
blocks, or within 1 % RMS. D is reported, not judged: if it matches A at block K the
setup really is the moment; if it matches B the filter reads FREQ later than its setup,
and a later write would do too.

Also reported: whether the next frame's unpack puts the frame's value back (if so, the
arm writes every block, which is the design). Results to `out/bloom/b1_report.json`.
Exit 0 on PASS. Needs digikit's SHARC runner and the user's own OS 1.11 file.
"""

from __future__ import annotations

import argparse
import json
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
import sharc_waverider_render as m1                            # noqa: E402
import sharc_waverider_voice as m2                             # noqa: E402
from dnfw.waverider import frame as FR                         # noqa: E402
from dnfw.waverider import render, testtable                   # noqa: E402
from dnfw.waverider import voice as V                          # noqa: E402

OUT = ROOT / "out" / "bloom"
BLOCK = m4.BLOCK

FILTER_SETUP = 0x1C91AD          # the common continuation's call of 0x8052dba4[filter type]
FREQ_INDEX = 67
FREQ_OFFSET = FR.RECORD_FIELDS[FREQ_INDEX][0]          # 0x1cc
assert FREQ_OFFSET == 0x1CC and FR.RECORD_FIELDS[FREQ_INDEX][1] == "u"

OPEN = 0x7F00                    # the init sound's FREQ
DARK = 0x2000                    # a quarter of the range: far darker, still passing signal
MATCH_RMS = 0.01                 # C follows B: block RMS within 1 %


def record_bits(word: int) -> int:
    """What the unpack puts in the record for a `u` field: word / 32768 as float32 bits."""
    return struct.unpack("<I", struct.pack("<f", word / 32768.0))[0]


def run(init, sound, blocks, k, freq, *, frame_freq, write_at=None):
    """BLOCKS calls of the per-block routine, as m4.run_blocks, with track 0's FREQ in the
    frame from FRAME_FREQ(b), and from block K a write of DARK into the record at WRITE_AT.
    Taps the buffer after the filter, the record at each hook, and the hook count."""
    rec = V.track_record(0) + FREQ_OFFSET
    positions = [render.sweep(len(testtable.table()), 2)[0]] * blocks     # one timbre, held
    prep = m4.voice_prep(freq, positions)
    state, out = init, {"pre_amp": [], "per_block": []}
    for b in range(blocks):
        tap, hold, seen = {}, {}, {"hits": 0, "record_before": None}

        def at_dispatch(runner):
            hold["buf"] = m2.word(runner.state, V.TRACK_BUFFERS)

        def amp(runner):
            if m2.word_reg(runner, "R12") == hold.get("buf") and "pre_amp" not in tap:
                tap["pre_amp"] = m2.floats(runner.state, hold["buf"], BLOCK)

        def enter5(runner):
            prep(runner.state, b)
            if write_at == "late" and b >= k:
                write(runner)
            runner.state.pc_sw = m3.MACHINE5_SW

        def write(runner):
            seen["hits"] += 1
            if seen["record_before"] is None:
                seen["record_before"] = m2.word(runner.state, rec)
            m2.poke(runner.state, rec, record_bits(DARK))

        def at_setup(runner):
            if seen["record_before"] is None:
                seen["record_before"] = m2.word(runner.state, rec)
            seen["setup_hits"] = seen.get("setup_hits", 0) + 1
            if write_at == "setup" and b >= k:
                write(runner)

        hooks = {m3.DISPATCH: at_dispatch, m3.AMP_STAGE: amp, m3.TYPE5_ENTRY: enter5,
                 FILTER_SETUP: at_setup}
        r = m4.unpack_call(state, m4.make_frame(sound, 5, trig=(b == 1),
                                                overrides={FREQ_INDEX: frame_freq(b)}))
        res = fx.run(r, 8_000_000, m4.fixups(hooks))
        if not (res[0] == "halt" and res[1].pc_sw == m4.UNPACK_RETURN):
            halt = f"{res[1].reason} at {res[1].pc_sw:#x}" if res[0] == "halt" else res[0]
            return {"ok": False, "blocks": b, "halt": halt, **out}
        block = tap.get("pre_amp", [0.0] * BLOCK)
        out["pre_amp"] += block
        out["per_block"].append({"block": b, "rms": V.rms(block),
                                 "setup_hits": seen.get("setup_hits", 0), "writes": seen["hits"],
                                 "record_before": seen["record_before"],
                                 "frame_freq": hex(frame_freq(b))})
        state = r
    return {"ok": True, **out}


def blocks_of(samples, b):
    return samples[b * BLOCK:(b + 1) * BLOCK]


def rel(a, b):
    """RMS of the difference over the RMS of B."""
    d = V.rms([x - y for x, y in zip(a, b)])
    return d / (V.rms(b) or 1e-30)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0],
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--image", type=pathlib.Path, default=m4.IMAGE)
    p.add_argument("--digikit", type=pathlib.Path,
                   default=pathlib.Path(os.environ.get("DNFW_DIGIKIT_SHARC",
                                                       ROOT.parent / "digikit-wt-sharcemu")))
    p.add_argument("--blocks", type=int, default=10)
    p.add_argument("--k", type=int, default=4, help="the first block with the dark cutoff")
    p.add_argument("--freq", type=float, default=375.0, help="the voice's pitch, Hz")
    a = p.parse_args(argv)
    if not 2 <= a.k < a.blocks - 1:
        raise SystemExit("--k must leave a block before it after the trig, and one after it")
    if not a.image.exists():
        raise SystemExit(f"{a.image}: the Digitone II OS 1.11 file is needed (bring your own)")
    OUT.mkdir(parents=True, exist_ok=True)
    m4.IMAGE = a.image
    dk = m1.Digikit(a.digikit)
    fx.bind(str(a.digikit / "tools"))
    stream = m1.dn2_section7(a.image)
    sound, _ = m4.init_sound(a.image)
    with tempfile.TemporaryDirectory(dir=OUT) as tmp:
        work = pathlib.Path(tmp)
        reader, _, _ = m1.reader_code(False, work)
        m5, _, _ = m3.load_json(m3.MACHINE5, m3.MACHINE5_SRC, False, work)
        m5d, _, _ = m4.load_code(m4.MACHINE5D, m4.MACHINE5D_SRC, False, work, m4.MACHINE5D_SW)
        mach = m4.M4Machine(dk, stream, reader, m5, m5d, work)
        init = m4.load_init(dk, mach, stream, reader)
        k, n = a.k, a.blocks
        dark_from_k = lambda b: DARK if b >= k else OPEN          # noqa: E731
        runs = {
            "A": run(init, sound, n, k, a.freq, frame_freq=lambda b: OPEN),
            "B": run(init, sound, n, k, a.freq, frame_freq=dark_from_k),
            "C": run(init, sound, n, k, a.freq, frame_freq=lambda b: OPEN, write_at="setup"),
            "D": run(init, sound, n, k, a.freq, frame_freq=lambda b: OPEN, write_at="late"),
        }
    ok_runs = all(r["ok"] for r in runs.values())
    A, B, C, D = (runs[x]["pre_amp"] for x in "ABCD")
    after = slice(k * BLOCK, n * BLOCK)
    n_ = {"image_sha256": mach.sha, "digikit_head": dk.head, "k": k, "blocks": n,
          "rms_after_k": {x: V.rms(runs[x]["pre_amp"][after]) for x in "ABCD"} if ok_runs else None}
    checks = {"all four runs return every block": ok_runs}
    if ok_runs:
        hits = [blk["setup_hits"] for blk in runs["C"]["per_block"]]
        before = runs["C"]["per_block"][k]["record_before"]
        n_.update({
            "setup_hits_per_block": hits,
            "record_at_hook_block_k": hex(before or 0), "expected_frame_value": hex(record_bits(OPEN)),
            "C_vs_B_block_k": rel(blocks_of(C, k), blocks_of(B, k)),
            "C_vs_B_after_k": rel(C[after], B[after]),
            "C_vs_A_after_k": rel(C[after], A[after]),
            "B_vs_A_after_k": rel(B[after], A[after]),
            "D_vs_A_block_k": rel(blocks_of(D, k), blocks_of(A, k)),
            "D_vs_B_block_k": rel(blocks_of(D, k), blocks_of(B, k)),
            "C_record_back_to_frame_value_next_block":
                runs["C"]["per_block"][k + 1]["record_before"] == record_bits(OPEN),
        })
        checks.update({
            f"the hook at sw {FILTER_SETUP:#x} is reached in every block": all(h >= 1 for h in hits),
            "the record holds the frame's own FREQ at the hook (the field the filter reads)":
                before == record_bits(OPEN),
            # A difference, not a direction: on 2026-10-21 the dark FREQ raised the RMS by
            # ~54 % at this pitch, so "darker means quieter" was the wrong test.
            "control: the frame path (B) changes the output from block K (>10 % RMS)":
                rel(B[after], A[after]) > 0.1,
            "C differs from A from block K (the write is heard)": n_["C_vs_A_after_k"] > 0.1,
            f"C follows B in block K itself (within {MATCH_RMS:.0%} RMS)": n_["C_vs_B_block_k"] <= MATCH_RMS,
            f"C follows B from block K on (within {MATCH_RMS:.0%} RMS)": n_["C_vs_B_after_k"] <= MATCH_RMS,
        })
        d = n_["D_vs_A_block_k"] < n_["D_vs_B_block_k"]
        n_["D_reading"] = ("the late write is not heard in block K: the setup is the moment"
                           if d else "the late write is heard in block K: the filter reads FREQ after its setup")
    else:
        n_["halts"] = {x: r.get("halt") for x, r in runs.items() if not r["ok"]}
    passed = all(checks.values())
    report = {"pass": passed, "checks": checks, "numbers": n_,
              "per_block": {x: r["per_block"] for x, r in runs.items()}}
    path = OUT / "b1_report.json"
    path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    for name, v in checks.items():
        print(f"  {'PASS' if v else 'FAIL'}  {name}")
    for key in ("C_vs_B_block_k", "C_vs_B_after_k", "C_vs_A_after_k", "D_reading"):
        if key in n_:
            print(f"  {key}: {n_[key]}")
    print(f"\nB1 {'PASS' if passed else 'FAIL'}: {path}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
