"""Does MIDI CC and NRPN on a Waverider track reach its knob, and nothing else?

    python scripts/emu_waverider_midi.py BUILD.syx [--json OUT]

Restores the booted snapshot (`ui1200M`) twice: stock (the control) and BUILD, installed
as its loader would. Track A is the snapshot's active track and track B another one. In
two set-ups (A Waverider and B WaveTone, then the reverse, so a Waverider is once off the
screen) it calls stock's own receive routines with each track's own object: every CC
0..127 at 0 and 127 (`0x40038a8a`), and every NRPN on MSB 1..3 at the top value
(`0x40037456`). Each call starts from the same sounds. It records what the parameter
setter queues at `0x400f5098` (record id, value word) and every write into the 16 sounds.

The verdict (docs/waverider-midi.md):

- a Waverider track, a number in Waverider's map: exactly one record queued, the map's,
  with Waverider's limits;
- a Waverider track, any other number: what stock queues for that track;
- a WaveTone track: what stock queues, in both set-ups;
- every call: at most one record queued, and no direct write into any sound.

Stock is the control: it must queue nothing for the map's numbers on a Waverider track,
and something for CC 40 on a WaveTone track, or the comparison proves nothing.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from emulib import paths                                     # noqa: E402
from emulib.image import differences                         # noqa: E402
from emulib.machine import Machine                           # noqa: E402

sys.path.insert(0, str(paths.ROOT / "src"))
from dnfw.firmware.load import load                          # noqa: E402
from dnfw.mods import platform                               # noqa: E402

VPTR = 0x401DB7FC                  # a synth track's vtable (the 16 track objects)
CC_IN, NRPN_IN = 0x40038A8A, 0x40037456     # its vtable +108 and +104
QUEUE = 0x400F5098                 # the setter's tail: (?, track, id, value word)
ACTIVE_TRACK, SOUND_TYPE, SOUND_BYTES = 0x42431A6C, 0xDE, 1163
WAVERIDER, WAVETONE = 5, 1
SPEC = json.loads((paths.ROOT / "src/dnfw/mods/waverider_code.json").read_text())
ROWS = [tuple(r) for r in SPEC["midi"]["rows"]]
RANGES = {int(k): v for k, v in SPEC["midi"]["ranges"].items()}
TBL = (247, 251)                   # their limits are the pool's, which the page sets
MESSAGES = ([("cc", n, v) for n in range(128) for v in (0, 127)]
            + [("nrpn", n, 16383) for n in range(128, 4 * 128)])


def main_os(path: pathlib.Path) -> bytes:
    from dnfw.cli.files import read_image
    return load(read_image(path)).container.find(3).unpack()


def run(build: bytes | None, stock: bytes) -> dict:
    from unicorn import UC_HOOK_CODE
    from unicorn.m68k_const import UC_M68K_REG_A7

    m = Machine()
    if build is not None:
        m.apply(differences(stock, build[:platform.STOCK_LENGTH]))
        for va, data in platform.runtime(build):
            m.write(va, data)
        m.flush()
    ram = m.read(0x40300000, 0x466B8000 - 0x40300000)
    objs, at = [], ram.find(VPTR.to_bytes(4, "big"))
    while at >= 0:
        objs.append(0x40300000 + at)
        at = ram.find(VPTR.to_bytes(4, "big"), at + 1)
    if len(objs) != 16:
        raise SystemExit(f"{len(objs)} synth track objects, not 16")
    sounds = []
    for o in objs:
        so = m.long(o + 16)
        sounds.append(m.call(m.long(m.long(so) + 40), so) & 0xFFFFFFFF)
    low, high = min(sounds), max(sounds) + SOUND_BYTES
    a = m.read(ACTIVE_TRACK, 1)[0]
    b = (a + 3) % 16
    base = {t: bytes(m.read(sounds[t], SOUND_BYTES)) for t in (a, b)}
    queued, writes = [], []

    def at_queue(uc, address, size, user):
        sp = uc.reg_read(UC_M68K_REG_A7)
        queued.append(tuple(int.from_bytes(uc.mem_read(sp + 4 * k, 4), "big") for k in (3, 4)))

    m.uc.hook_add(UC_HOOK_CODE, at_queue, begin=QUEUE, end=QUEUE)
    m.watch_writes(low, high - 1, lambda pc, addr, value, size: writes.append((pc, addr)))
    out = {}
    for types in ((WAVERIDER, WAVETONE), (WAVETONE, WAVERIDER)):
        for target, name in ((a, "A"), (b, "B")):
            for t, ty in zip((a, b), types):
                m.write(sounds[t], base[t])
                m.write(sounds[t] + SOUND_TYPE, bytes([ty]))
            m.flush()
            ttype = types[0] if name == "A" else types[1]
            for kind, n, v in MESSAGES:
                queued.clear()
                writes.clear()
                m.call(CC_IN if kind == "cc" else NRPN_IN, objs[target], n, v, target)
                out[(types, name, kind, n, v)] = (ttype, list(queued), len(writes))
    return out


def word(kind: str, value: int) -> int:
    return value << 8 if kind == "cc" else 2 * value


def verdict(stock: dict, build: dict) -> list[str]:
    bad = []
    by_cc = {cc: rid for rid, _, cc in ROWS}
    by_nrpn = {n: rid for rid, n, _ in ROWS}
    for key, (ttype, q, w) in build.items():
        types, name, kind, n, v = key
        _, sq, _ = stock[key]
        where = f"{'A' if name == 'A' else 'B'} type {ttype}, {kind} {n} = {v}"
        if w:
            bad.append(f"{where}: {w} direct writes into the sounds")
        if len(q) > 1:
            bad.append(f"{where}: {len(q)} records queued {q}")
        mapped = (by_cc if kind == "cc" else by_nrpn).get(n)
        if ttype == WAVERIDER and mapped is not None:
            if [r for r, _ in q] != [mapped]:
                bad.append(f"{where}: queued {q}, the map says record {mapped}")
            elif mapped in RANGES and mapped not in TBL:
                lo, hi, _ = RANGES[mapped]
                want = min(max(word(kind, v), lo), hi)
                if q[0][1] & 0xFFFF != want:
                    bad.append(f"{where}: record {mapped} = {q[0][1]:#x}, its limits give {want:#x}")
        elif q != sq:
            bad.append(f"{where}: queued {q}, stock {sq}")
    return bad


def controls(stock: dict) -> list[str]:
    bad = []
    for key, (ttype, q, _) in stock.items():
        types, name, kind, n, v = key
        mapped = {cc for _, _, cc in ROWS} if kind == "cc" else {nr for _, nr, _ in ROWS}
        if ttype == WAVERIDER and n in mapped and q:
            bad.append(f"stock queued {q} for {kind} {n} on a Waverider track")
    if not any(q for (types, name, kind, n, v), (t, q, _) in stock.items()
               if t == WAVETONE and kind == "cc" and n == 40):
        bad.append("stock queued nothing for CC 40 on a WaveTone track")
    return bad


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("build", type=pathlib.Path)
    p.add_argument("--json", type=pathlib.Path, help="write every answer here")
    args = p.parse_args()
    stock_os = main_os(paths.SYX)
    print(f"stock: {len(MESSAGES) * 4:,} calls ...", flush=True)
    stock = run(None, stock_os)
    print(f"{args.build.name}: {len(MESSAGES) * 4:,} calls ...", flush=True)
    build = run(main_os(args.build), stock_os)
    if args.json:
        args.json.write_text(json.dumps([[list(map(str, k)), v] for k, v in build.items()]))
    ctl, bad = controls(stock), verdict(stock, build)
    taken = sum(1 for (t, q, _) in build.values() if t == WAVERIDER and q)
    print(f"Waverider tracks: {taken:,} messages queued one record each; "
          f"{sum(1 for k in build if build[k][0] == WAVETONE):,} WaveTone answers compared with stock")
    for line in (ctl + bad)[:40]:
        print("  FAIL", line)
    if ctl:
        print("CONTROL FAILED: the comparison proves nothing")
        return 2
    print("PASS" if not bad else f"FAIL: {len(bad)}")
    return 0 if not bad else 1


if __name__ == "__main__":
    raise SystemExit(main())
