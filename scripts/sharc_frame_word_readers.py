"""Which DSP instructions read a given word of the ColdFire's frame?

Runs the unmodified section 7 of OS 1.11 in digikit's runner (a note on, a few blocks) with
a read watchpoint on the word, twice: where the frame lands in the receive buffer, and in
the DSP's frame copy (0x25c48c + offset). Prints each reading instruction (PC in short
words, the decoded form) with its count, so a word's consumers are named, not just
detected (scripts/sharc_frame_word_check.py says only that something changed).

    python scripts/sharc_frame_word_readers.py --offset 42 [--width 2] [--machine 1] [--blocks 2]

The copy loops read every word of the frame once; they show up as the same two PCs for any
offset and are marked. Anything else is a consumer.
"""
import argparse
import collections
import pathlib
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import sharc_waverider_m5 as g  # noqa: E402
from dnfw import sharcemu  # noqa: E402

FRAME_COPY = 0x25C48C
COPY_LOOPS = {0x1C287D: "unpack copy loop", 0x1C3030: "unpack copy loop"}   # naturarum T6.0 1.2


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--offset", type=int, required=True, help="frame byte offset")
    ap.add_argument("--width", type=int, default=2, choices=(2, 4))
    ap.add_argument("--machine", type=int, default=1)
    ap.add_argument("--blocks", type=int, default=2)
    ap.add_argument("--pattern", default="11223344", help="hex bytes written over the word")
    a = ap.parse_args()

    sys.path.insert(0, str(sharcemu.path()))
    from tools import sharc_run as SR   # digikit's executor
    dk = g.m1.Digikit(sharcemu.path())
    g.fx.bind(str(sharcemu.path() / "tools"))
    image = ROOT / "00_Resources/00_Firmware/Digitone_II_OS1.11_dist.zip"
    g.m4.IMAGE = image
    stock = g.m1.dn2_section7(image)
    sound, machines = g.m4.init_sound(image)
    stock_image = g.Image(dk, stock)
    pat = bytes.fromhex(a.pattern)[:a.width]

    hits = collections.defaultdict(lambda: collections.Counter())
    with tempfile.TemporaryDirectory(dir=g.OUT) as tmp:
        snap, m2mach = g.snapshot_path(dk, stock, pathlib.Path(tmp))
        state = g.init_on(snap, m2mach, stock_image)
        for b in range(a.blocks):
            f = bytearray(g.base_frame(sound, machines, t0=a.machine, trigger=(b == 1)).to_bytes())
            f[a.offset:a.offset + a.width] = pat
            r = g.m4.unpack_call(state, bytes(f))
            idx = g.m2.word(r.state, g.m4.RX_INDEX) or 0
            rx = g.m4.RX_BASE + (idx << 8)
            r.attach_watchpoints([
                SR.Watchpoint(rx + a.offset, rx + a.offset + a.width, on_read=True, on_write=False,
                              stop=False, label="rx"),
                SR.Watchpoint(FRAME_COPY + a.offset, FRAME_COPY + a.offset + a.width, on_read=True,
                              on_write=False, stop=False, label="copy"),
            ])
            res = g.fx.run(r, 8_000_000, g.fixups({}))
            if not (res[0] == "halt" and res[1].pc_sw == g.m4.UNPACK_RETURN):
                print(f"block {b}: did not return cleanly: {res[:2]}")
                return 1
            for ev in r.watch_log:
                hits[(ev.label, ev.pc_sw, ev.form)][b] += 1
            state = r

    print(f"reads of frame byte {a.offset:#x}..{a.offset + a.width - 1:#x} "
          f"(machine {a.machine}, {a.blocks} blocks, stock section 7):")
    if not hits:
        print("  none: no instruction read it in these blocks")
    for (label, pc, form), per_block in sorted(hits.items(), key=lambda kv: (kv[0][0], kv[0][1])):
        note = COPY_LOOPS.get(pc, "")
        print(f"  {label:5s} sw {pc:#08x}  x{sum(per_block.values()):<3d} {form}"
              + (f"   <- {note}" if note else "  <- CONSUMER"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
