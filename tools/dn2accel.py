"""Read the accelerator jobs' result from an accelprobe build (scripts/build_accelprobe.py), over the USB probe.

    python tools/dn2accel.py [--for 120] [--port "Digitone II"] [--save out/accel_reading.json]

accel.asm runs five FIR0 and IIR0 jobs once in the idle task, then publishes every output,
write-back word and timing, half a word at a time, through reply word 2 (the ColdFire's
0x800053ac): TAG << 16 | HALF. This reads that word until every half is seen (or FOR seconds
pass), rebuilds the words and prints:

- each job's timing: the cycles from its start to ACDONE, the DMASTAT read, and the reads
  (1,000,000 means the job never finished);
- how many output and write-back words equal the reference bit for bit
  (`accelprobe.expected()`: the chip's order, read on 2026-10-17);
- if any do not: which candidate order of the float operations matches them instead.

All zeros with no tag seen means the build has no accel code, or the word is not reply
word 2. `--save` keeps the words read, so a reading can be compared again offline.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import struct
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "src"))

from dnfw.waverider import accelprobe  # noqa: E402

REPLY = 0x800053A4
WORD2 = REPLY + 8


def collect(dp, pr, seconds: float) -> dict[int, int]:
    """Half index -> half, from reply word 2, until all are seen or SECONDS pass."""
    want = 2 * len(accelprobe.published())
    seen: dict[int, int] = {}
    end = time.monotonic() + seconds
    while time.monotonic() < end and len(seen) < want:
        data = dp.decode_peek(pr.call(dp.req_peek, WORD2, 4))["data"]
        word = struct.unpack(">I", data[:4])[0]
        if word:
            k, half = accelprobe.decode(word)
            if 0 <= k < want:
                seen[k] = half
    return seen


def compare(words: dict[str, int]) -> list[str]:
    lines = []
    for r in range(1, len(accelprobe.RUNS) + 1):
        c, s, n = (words.get(f"run{r}.{k}") for k in ("cycles", "dmastat", "reads"))
        job = accelprobe.RUNS[r - 1][0]
        if None in (c, s, n):
            lines.append(f"  run {r} ({job}): not all read")
            continue
        state = "never finished" if n >= accelprobe.LIMIT else "finished"
        lines.append(f"  run {r} ({job}): {state}, {c:,} cycles, DMASTAT {s:#x}, {n:,} reads")
    want = accelprobe.expected()
    have = {k: words[k] for k in want if k in words}
    same = [k for k in have if have[k] == want[k]]
    lines.append(f"  words equal to the reference: {len(same)} of {len(have)} read ({len(want)} in all)")
    for prefix, orders, key in (("iir", accelprobe.IIR_ORDERS, "iir_order"), ("fir", accelprobe.FIR_ORDERS, "fir_order")):
        names = [k for k in have if k.startswith(prefix) and (".out[" in k or ".coef[" in k)]
        bad = [k for k in names if have[k] != want[k]]
        if not bad:
            lines.append(f"  {prefix.upper()}0 outputs: all {len(names)} equal to the reference")
            continue
        lines.append(f"  {prefix.upper()}0 outputs: {len(bad)} of {len(names)} differ from the reference, e.g. "
                     f"{bad[0]} {have[bad[0]]:#010x} (model {want[bad[0]]:#010x})")
        for o in orders:
            alt = accelprobe.expected(**{key: o})
            hits = sum(have[k] == alt[k] for k in names)
            lines.append(f"    order {o}: {hits} of {len(names)} equal")
    for k in sorted(k for k in have if ".tcb." in k):
        mark = "ok" if have[k] == want[k] else f"model {want[k]:#010x}"
        lines.append(f"  {k}: {have[k]:#010x} {mark}")
    return lines


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0],
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--for", dest="duration", type=float, default=120.0)
    p.add_argument("--port", default="Digitone II")
    p.add_argument("--save", type=pathlib.Path)
    p.add_argument("--load", type=pathlib.Path, help="compare a saved reading, without the instrument")
    a = p.parse_args(argv)
    if a.load:
        words = json.loads(a.load.read_text(encoding="utf-8"))
    else:
        import dn2probe as dp
        import winmidi
        port = winmidi.Port(a.port, None, None)
        try:
            pr = dp.Probe(port)
            halves = collect(dp, pr, a.duration)
        finally:
            port.close()
        print(time.strftime("%H:%M:%S"), f"halves seen: {len(halves)} of {2 * len(accelprobe.published())}")
        if not halves:
            print("  reply word 2 stayed 0: no accel code in this build, or it never published")
            return 1
        words = accelprobe.words(halves)
        if a.save:
            a.save.parent.mkdir(parents=True, exist_ok=True)
            a.save.write_text(json.dumps(words, indent=1) + "\n", encoding="utf-8", newline="\n")
    print("\n".join(compare(words)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
