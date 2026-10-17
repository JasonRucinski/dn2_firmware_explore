"""accel.asm in digikit's SHARC runner, with its FIR0 and IIR0 models: the jobs run, and the probe reads them.

    python scripts/sharc_accel_check.py --digikit ../digikit-wt-fir0 [--instructions 3000000]

Builds `dnfw.waverider.accelprobe.section7_accel`, starts the idle task at its loop's top on
the engine-init snapshot with digikit's peripheral model on (State.peripheral_model: the SEC,
FIR0 and IIR0), then runs. Checks, each against the machine's state:

- the idle loop goes round, through accel.asm and then the idle stub;
- every register accel.asm uses (R0-R7, I0-I2) holds at its exit what it held at its entry;
- every job finished (ACDONE in the DMASTAT read, in fewer reads than the limit);
- every output and write-back word equals `accelprobe.expected()`, the float32 reference in
  digikit's documented order (so the models, the TCBs and accel.asm's sequence agree);
- reply word 2 of both pages carries TAG << 16 | HALF, halves swapped, and the halves seen
  rebuild the words in memory (what tools/dn2accel.py reads on the instrument).

The instrument is the other half: the same build, read by tools/dn2accel.py, settles whether
the silicon rounds as the models do.
"""

from __future__ import annotations

import argparse
import importlib
import pathlib
import struct
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import sharc_waverider_m5 as m5                                # noqa: E402
from dnfw import sharcemu                                       # noqa: E402
from dnfw.waverider import accelprobe, dsp                      # noqa: E402

REGS = ("R0", "R1", "R2", "R3", "R4", "R5", "R6", "R7", "I0", "I1", "I2")
SENTINELS = {"R0": 0x0A0A0A0A, "R1": 0x1B1B1B1B, "R2": 0x2C2C2C2C, "R3": 0x3D3D3D3D, "R4": 0x4E4E4E4E,
             "R5": 0x5F5F5F5F, "R6": 0x60606060, "R7": 0x71717171, "I0": 0x002C0100, "I1": 0x002C0200,
             "I2": 0x002C0300, "R8": 0x11111111, "R9": 0x22222222, "R10": 0x33333333, "R11": 0x44444444}


def run(dk, stock, instructions):
    image = m5.Image(dk, accelprobe.section7_accel(stock))
    tops, entries, exits, replies = [], [], [], []
    with tempfile.TemporaryDirectory(dir=m5.OUT) as tmp:
        snap, m2mach = m5.snapshot_path(dk, stock, pathlib.Path(tmp))
        init = m5.init_on(snap, m2mach, image)
        st = init.state
        for base, blob in ((accelprobe.STATE_DM, accelprobe.state()), (accelprobe.DATA_DM, accelprobe.data())):
            for k in range(0, len(blob), 4):
                m5.m2.poke(st, base + k, int.from_bytes(blob[k:k + 4], "little"))
        i7 = m5.m2.word_reg(init, "I7")
        r = init.fresh_call(dsp.IDLE_RETURN_SW, regs={"I5": 0x2D0608, "R15": 1, "I6": i7, "I7": i7 - 16,
                                                      **SENTINELS},
                            return_address=dsp.IDLE_RETURN_SW)
        r.state.peripheral_model = True

        def at_top(runner):
            tops.append(1)
            w = [m5.m2.word(runner.state, x) or 0 for x in accelprobe.REPLY_WORD2]
            if not replies or replies[-1] != w:
                replies.append(w)

        def at_entry(runner):
            entries.append({k: m5.m2.word_reg(runner, k) for k in REGS})

        def at_exit(runner):
            exits.append({k: m5.m2.word_reg(runner, k) for k in REGS})

        f = m5.fixups({dsp.IDLE_RETURN_SW: at_top, accelprobe.ACC_SW: at_entry, dsp.IDLE_SW: at_exit})
        res = m5.fx.run(r, instructions, f)
        memory = {name: m5.m2.word(r.state, at) or 0 for name, at in accelprobe.published()}
    return res, tops, entries, exits, replies, memory


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--image", type=pathlib.Path,
                   default=ROOT / "00_Resources/00_Firmware/Digitone_II_OS1.11_dist.zip")
    p.add_argument("--digikit", type=pathlib.Path, default=sharcemu.path())
    p.add_argument("--instructions", type=int, default=3_000_000)
    p.add_argument("--before-122", action="store_true",
                   help="compare with the order digikit's models had before ElekLabs/digikit#122 (an older runner)")
    p.add_argument("--probe", default="accelprobe", choices=("accelprobe", "accelprobe2"),
                   help="the probe's job set (dnfw.waverider.<probe>)")
    a = p.parse_args(argv)
    global accelprobe
    accelprobe = importlib.import_module(f"dnfw.waverider.{a.probe}")
    dk = m5.m1.Digikit(a.digikit)
    m5.fx.bind(str(a.digikit / "tools"))
    m5.m4.IMAGE = a.image
    stock = m5.m1.dn2_section7(a.image)

    res, tops, entries, exits, replies, memory = run(dk, stock, a.instructions)
    want = (accelprobe.expected(iir_order="model", fir_order="model", acm_writeback=(0, 0xFFFFFFFF))
            if a.before_122 else accelprobe.expected())
    wrong = [k for k in want if memory.get(k) != want[k]]
    halves = {}
    for w in replies:
        if w[0]:
            v = ((w[0] << 16) | (w[0] >> 16)) & 0xFFFFFFFF
            k, half = accelprobe.decode(v)
            halves[k] = half
    rebuilt = accelprobe.words(halves)
    runs = [(memory[f"run{r}.cycles"], memory[f"run{r}.dmastat"], memory[f"run{r}.reads"])
            for r in range(1, len(accelprobe.RUNS) + 1)]
    print(f"  run ended: {res[0]}; loop tops {len(tops)}, accel calls {len(entries)}")
    print(f"  runs (cycles, DMASTAT read, reads): {[(c, hex(s), n) for c, s, n in runs]}")
    print(f"  words: {len(want) - len(wrong)}/{len(want)} as expected; halves seen {len(halves)}"
          f" of {2 * len(accelprobe.published())}, words rebuilt {len(rebuilt)}")
    for k in wrong[:6]:
        print(f"    {k}: {memory.get(k, 0):#010x}, expected {want[k]:#010x}")
    checks = {
        "the idle loop goes round (10+ tops)": len(tops) >= 10,
        "accel.asm runs each pass (calls = tops within 1)": abs(len(entries) - len(tops)) <= 1,
        "R0-R7 and I0-I2 at accel.asm's exit equal its entry, every call":
            len(exits) >= len(entries) - 1 > 0 and all(x == y for x, y in zip(entries, exits)),
        "every job finished: ACDONE read, under the limit":
            all(s & 0x40 and n < accelprobe.LIMIT for _, s, n in runs),
        "every output and write-back word is the reference's": not wrong,
        "reply word 2 is the same on both pages, each time": all(w[0] == w[1] for w in replies),
        "every half published decodes to its word in memory":
            bool(halves) and all(rebuilt[k] == memory[k] for k in rebuilt),
        "every half was published": len(halves) == 2 * len(accelprobe.published()),
    }
    for k, v in checks.items():
        print(f"  {'PASS' if v else 'FAIL'}  {k}")
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
