"""Bloom B1b (offline): does the stock filter follow when Bloom's DSP code rewrites the
incoming frame's FREQ word before the unpack?

    python scripts/sharc_bloom_b1b.py \\
        --image 00_Resources/00_Firmware/Digitone_II_OS1.11_dist.zip \\
        --digikit ../digikit-wt-sharcemu [--blocks 10] [--k 4]

B1 (`scripts/sharc_bloom_b1.py`, `docs/bloom-machine.md`) answered no for the track
record: a FREQ written there, at the filter's setup or after it, changed nothing, while
the same value arriving in the frame changed the filter from the next block. So whatever
turns FREQ into filter coefficients runs in or before the unpack. B1b moves the write
earlier still, to where Bloom's own code could run: **a hook at the unpack's entry**
(sw `0x1c2712`, which the per-block driver calls from `0x1c9fbc`) that rewrites track 0's
FREQ word in the received frame page, before anything has read it. The runner makes the
write, so this measures the firmware's response to the word, at the moment Bloom would
write it.

| run | the frame as sent | at the unpack's entry, from block K |
|---|---|---|
| A | FREQ open | nothing: the control |
| B | FREQ dark from block K | nothing: the reference (B1's run B) |
| E | FREQ open | **track 0's FREQ word rewritten dark**: the question |

**PASS** when the hook fires in every block; the word holds the frame's own (open) value
before the write and the dark value after it; B differs from A from block K (the control
discriminates); and E follows B from block K, within 1 % RMS. E is expected to match B
exactly, one block late as B is, because it changes the same bytes the frame would carry.

Results to `out/bloom/b1b_report.json`. Exit 0 on PASS.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import sharc_bloom_b1 as b1                                    # noqa: E402

OUT = b1.OUT
MATCH_RMS = b1.MATCH_RMS


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0],
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--image", type=pathlib.Path, default=b1.m4.IMAGE)
    p.add_argument("--digikit", type=pathlib.Path,
                   default=pathlib.Path(os.environ.get("DNFW_DIGIKIT_SHARC",
                                                       ROOT.parent / "digikit-wt-sharcemu")))
    p.add_argument("--blocks", type=int, default=10)
    p.add_argument("--k", type=int, default=4)
    p.add_argument("--freq", type=float, default=375.0)
    a = p.parse_args(argv)
    if not 2 <= a.k < a.blocks - 1:
        raise SystemExit("--k must leave a block before it after the trig, and one after it")
    if not a.image.exists():
        raise SystemExit(f"{a.image}: the Digitone II OS 1.11 file is needed (bring your own)")
    OUT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=OUT) as tmp:
        dk, mach, init, sound = b1.load(a.image, a.digikit, pathlib.Path(tmp))
        k, n = a.k, a.blocks
        words = b1.frame_words(sound, b1.DARK)
        runs = {
            "A": b1.run(init, sound, n, k, a.freq, frame_freq=lambda b: b1.OPEN),
            "B": b1.run(init, sound, n, k, a.freq,
                        frame_freq=lambda b: b1.DARK if b >= k else b1.OPEN),
            "E": b1.run(init, sound, n, k, a.freq, frame_freq=lambda b: b1.OPEN, write_at="frame"),
        }
    ok_runs = all(r["ok"] for r in runs.values())
    num = {"image_sha256": mach.sha, "digikit_head": dk.head, "k": k, "blocks": n,
           "frame_words_written": {hex(o): hex(w) for o, w in words.items()}}
    checks = {"all three runs return every block": ok_runs,
              "the frame carries track 0's FREQ in exactly one word": len(words) == 1}
    if ok_runs:
        A, B, E = (runs[x]["pre_amp"] for x in "ABE")
        after = slice(k * b1.BLOCK, n * b1.BLOCK)
        pe = runs["E"]["per_block"]
        num.update({
            "unpack_hits_per_block": [x["unpack_hits"] for x in pe],
            "B_vs_A_after_k": b1.rel(B[after], A[after]),
            "E_vs_B_after_k": b1.rel(E[after], B[after]),
            "E_vs_A_after_k": b1.rel(E[after], A[after]),
            "E_equals_B_bit_for_bit": E == B,
            "record_at_setup_E": [hex(x["record_before"] or 0) for x in pe],
            "record_at_setup_B": [hex(x["record_before"] or 0) for x in runs["B"]["per_block"]],
        })
        checks.update({
            "the hook at the unpack's entry fires in every block":
                all(x["unpack_hits"] >= 1 for x in pe),
            "the word held the frame's own FREQ before the write, every written block":
                all(x["frame_before_ok"] for x in pe[k:]),
            "the word holds the dark FREQ after the write, every written block":
                all(x["frame_written_ok"] for x in pe[k:]),
            "control: B differs from A from block K (>10 % RMS)": num["B_vs_A_after_k"] > 0.1,
            "E differs from A from block K (the rewrite is heard)": num["E_vs_A_after_k"] > 0.1,
            f"E follows B from block K (within {MATCH_RMS:.0%} RMS)": num["E_vs_B_after_k"] <= MATCH_RMS,
        })
    else:
        num["halts"] = {x: r.get("halt") for x, r in runs.items() if not r["ok"]}
    passed = all(checks.values())
    path = OUT / "b1b_report.json"
    path.write_text(json.dumps({"pass": passed, "checks": checks, "numbers": num,
                                "per_block": {x: r["per_block"] for x, r in runs.items()}},
                               indent=2, default=str) + "\n", encoding="utf-8")
    for name, v in checks.items():
        print(f"  {'PASS' if v else 'FAIL'}  {name}")
    for key in ("B_vs_A_after_k", "E_vs_B_after_k", "E_vs_A_after_k", "E_equals_B_bit_for_bit"):
        if key in num:
            print(f"  {key}: {num[key]}")
    print(f"\nB1b {'PASS' if passed else 'FAIL'}: {path}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
