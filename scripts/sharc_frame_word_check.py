"""Does the stock DSP block handler depend on a given word of the ColdFire's frame?

Runs the unmodified section 7 of OS 1.11 in digikit's runner for a few blocks with a note on,
once per pattern written over four frame bytes at OFFSET. Per pattern it reports how often
the handler's frame-word read sites ran, and it diffs every track buffer, the reply tail and
DSP data memory (0x200000..0x300000, outside the frame copy and the two receive buffers)
against the all-zero pattern. A word nothing depends on gives 0 differing memory words.

    python scripts/sharc_frame_word_check.py [--offset 2644] [--width 4] [--machine 1] [--blocks 3]

The default offset is the Waverider song position (csrc/waverider/sync.c). Findings for it:
docs/waverider-frame-words.md.
"""
import argparse
import pathlib
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import sharc_waverider_m5 as g  # noqa: E402
from dnfw import sharcemu  # noqa: E402

FRAME_COPY = 0x25C48C
FRAME_COPY_BYTES = 0xA80            # the 672-word copy the block handler makes of the frame
# the two receive buffers, and the runner's own input page (m4.RX_BASE = 0x2c0478, 0x100 apart,
# where it pokes each frame: a word that differs there is the frame itself)
RX_BUFFERS = ((0x2C29D0, 0x1000), (0x2C39D0, 0x1000), (0x2C0478, 0x100 + 0xAC0))
# sites that read the receive buffer directly (naturarum/dn2-cfw notes/T6.0 section 1.2)
SITES = {0x1C3084: "0xa54 (r2=dm(-0xa,i5))", 0x1C3052: "0xa7a", 0x1C3069: "0xa7c",
         0x1C309C: "0xa7e", 0x1C2CD6: "0x22"}
PATTERNS = {"zero": bytes(4), "pattern": bytes.fromhex("11223344"), "ones": bytes.fromhex("ffffffff")}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--offset", type=int, default=2644, help="frame byte offset")
    ap.add_argument("--width", type=int, default=4, choices=(2, 4),
                    help="bytes written: 2 for one 16-bit word (4 also overwrites the next word)")
    ap.add_argument("--machine", type=int, default=1, help="track 1's machine type (0 FM, 1 WaveTone, ...)")
    ap.add_argument("--blocks", type=int, default=3)
    a = ap.parse_args()

    skip = [(FRAME_COPY, FRAME_COPY + FRAME_COPY_BYTES), *((lo, lo + n) for lo, n in RX_BUFFERS)]
    dk = g.m1.Digikit(sharcemu.path())
    g.fx.bind(str(sharcemu.path() / "tools"))
    image = ROOT / "00_Resources/00_Firmware/Digitone_II_OS1.11_dist.zip"
    g.m4.IMAGE = image
    stock = g.m1.dn2_section7(image)
    sound, machines = g.m4.init_sound(image)
    stock_image = g.Image(dk, stock)

    results = {}
    with tempfile.TemporaryDirectory(dir=g.OUT) as tmp:
        snap, m2mach = g.snapshot_path(dk, stock, pathlib.Path(tmp))
        for name, pat in PATTERNS.items():
            hits = {s: 0 for s in SITES}

            def mk(s):
                def hook(r):
                    hits[s] += 1
                return hook

            def frames(b, pat=pat):
                f = bytearray(g.base_frame(sound, machines, t0=a.machine, trigger=(b == 1)).to_bytes())
                f[a.offset:a.offset + a.width] = pat[:a.width]
                return bytes(f)

            state = g.init_on(snap, m2mach, stock_image)
            run = g.run_blocks(state, frames, a.blocks, extra_hooks={sw: mk(sw) for sw in SITES})
            st = run["state"].state
            words = {}
            for addr in range(0x200000, 0x300000, 4):
                if any(lo <= addr < hi for lo, hi in skip):
                    continue
                w = g.m2.word(st, addr)
                if w is not None:
                    words[addr] = w
            results[name] = {"bits": repr(run["buffer_bits"]), "reply": repr(run["reply_tail"]), "mem": words}
            print(f"{name:8s} ok {run['ok']} blocks {run['blocks']} site runs "
                  + " ".join(f"{SITES[s]}={h}" for s, h in hits.items()), flush=True)

    base = results["zero"]
    print(f"compared with the zero pattern (offset {a.offset}, {a.width} bytes, machine {a.machine}):")
    for name, r in results.items():
        if name == "zero":
            continue
        diff = [x for x in base["mem"] if base["mem"][x] != r["mem"].get(x)]
        print(f"  {name:8s} buffers {'IDENTICAL' if r['bits'] == base['bits'] else 'DIFFERENT'}"
              f", reply {'IDENTICAL' if r['reply'] == base['reply'] else 'DIFFERENT'}"
              f", memory words that differ: {len(diff)}"
              + (" first " + ", ".join(f"{x:#x} {base['mem'][x]:#010x}->{r['mem'].get(x, 0):#010x}"
                                       for x in diff[:12]) if diff else ""), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
