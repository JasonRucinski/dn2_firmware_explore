"""The erase control, /wavepool/129, in the emulator: the store and every pool list removed.

    python scripts/emu_waverider_erase.py BUILD.syx [--card out/dk-dn2-card.img]

Through digikit's sysex_bridge, DNX's own frames (docs/for-dnx-waverider-erase.md):
1. two tables (store slots 0 and 3) and two pool lists (project 0 explicit, project 5
   following the store) are written; /waverider lists 2 used, /wavepool 2 used;
2. a read of /wavepool/129 is refused, and 129 is not in the listing;
3. refusals that leave everything as it was: counts that differ from what the store holds
   (a stale view), a bad hash, a bad magic, version 2, a reserved byte set, a record
   container (a project's pool list) written to 129 with the right project number, and
   a table container (kind 0x57);
4. the request with the counts the store holds: /waverider lists none used, /wavepool
   none used, and project 0 reads as an empty pool again (generation 0, no flag, no
   entries);
5. the driver's TRIM ran once, over the region's last sector (0x640FFF).

The bridge counts the executions of a PC over the session, so the TRIM count and its
last-sector register are read from the final line.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import struct
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from dnfw.waverider import poolrecord as PR                     # noqa: E402
from emu_waverider_rename import ARGS, BRIDGE, Frames, dec      # noqa: E402
from emu_waverider_wavepool import (                            # noqa: E402
    NONE, PIECES, container, listing, parse_record, record, slot_file)

TRIM_ENTRY = 0x4012C4B2
TRIM_LAST_SECTOR_PC = 0x4012C50A        # d0 = sector + count - 1, just before the CMD36 argument
REGION, DATA_END = 0x600000, 0x41000


def erase(tables: int, lists: int, **flaws) -> bytes:
    r = bytearray(PR.erase_request(tables, lists))
    if "magic" in flaws:
        r[0] ^= 0xFF
    if "version" in flaws:
        r[5] = 2
    if "reserved" in flaws:
        r[300] = 1
    if "hash" in flaws:
        r[511] ^= 1
    elif any(k in flaws for k in ("magic", "version", "reserved")):
        r[508:] = struct.pack(">I", PR.store.xxh32(bytes(r[:508])))
    return bytes(r)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("build")
    ap.add_argument("--card", default=str(ROOT / "out/dk-dn2-card.img"))
    a = ap.parse_args()

    f = Frames()
    f.write("t0", "/waverider/0", slot_file(0, "Zero", 3))
    f.write("t3", "/waverider/3", slot_file(3, "Three", 5))
    f.write("p0", "/wavepool/0", container(record(0, [3, NONE, 0]), 0, 0x50))
    f.write("p5", "/wavepool/5", container(record(5, [], follows_store=True), 5, 0x50))
    f.frame("store_before", 0x53, b"/waverider\0")
    f.frame("pools_before", 0x53, b"/wavepool\0")
    f.frame("open129", 0x54, b"/wavepool/129\0")
    for label, req in (("stale_tables", erase(9, 2)), ("stale_lists", erase(2, 0)),
                       ("bad_hash", erase(2, 2, hash=1)), ("bad_magic", erase(2, 2, magic=1)),
                       ("bad_version", erase(2, 2, version=1)), ("bad_reserved", erase(2, 2, reserved=1))):
        f.write(label, "/wavepool/129", container(req, 129, 0x50))
    f.write("as_record", "/wavepool/129", container(record(129, [1]), 129, 0x50))
    f.write("as_table", "/wavepool/129", container(erase(2, 2), 129, 0x57))
    f.frame("store_refused", 0x53, b"/waverider\0")
    f.frame("pools_refused", 0x53, b"/wavepool\0")
    f.write("erase", "/wavepool/129", container(erase(2, 2), 129, 0x50))
    f.frame("store_after", 0x53, b"/waverider\0")
    f.frame("pools_after", 0x53, b"/wavepool\0")
    f.read("r0", "/wavepool/0", PIECES)

    proc = subprocess.run([str(BRIDGE), a.build, *ARGS, "--card-image", a.card,
                           "--count", hex(TRIM_ENTRY), "--regs-at", hex(TRIM_LAST_SECTOR_PC)],
                          input="\n".join(h for _, h in f.lines) + "\n",
                          capture_output=True, text=True, timeout=3600)
    lines = [json.loads(x) for x in proc.stdout.splitlines() if x.startswith("{")]
    out = [o for o in lines if "request" in o]
    tail = next((o for o in lines if "counts" in o), {})
    if len(out) != len(f.lines):
        print("FAIL: the bridge answered", len(out), "of", len(f.lines), proc.stderr[-2000:])
        return 1
    replies = {label: o["replies"] for (label, _), o in zip(f.lines, out)}

    def answer(label):
        return dec(replies[label][0])[5:] if replies[label] else b""

    def used(label):
        return [i for i, _, u in listing(replies[label][0]) if u]

    ok = True

    def check(what, cond, detail=""):
        nonlocal ok
        ok &= bool(cond)
        print(("PASS " if cond else "FAIL ") + what + (f"  ({detail})" if detail else ""))

    check("two tables written", used("store_before") == [0, 3], used("store_before"))
    check("two pool lists written (project 0 explicit, project 5 following the store)",
          used("pools_before") == [0, 5], used("pools_before"))
    check("a read of /wavepool/129 is refused", b"cannot be read" in answer("open129"), answer("open129")[:80])
    check("/wavepool lists 129 projects, the control not among them",
          len(listing(replies["pools_before"][0])) == 129)
    check("every refused request left both lists as they were",
          used("store_refused") == [0, 3] and used("pools_refused") == [0, 5],
          (used("store_refused"), used("pools_refused")))
    check("the request with the counts the store holds removes every table",
          used("store_after") == [], used("store_after"))
    check("and every pool list", used("pools_after") == [], used("pools_after"))
    raw = b"".join(answer(f"r0:chunk{k}")[22:] for k in range(1, PIECES))
    at = raw.find(bytes.fromhex("ac11d303"))
    r0 = parse_record(raw[at + 31:at + 31 + 512]) if at >= 0 else None
    check("project 0 reads as an empty pool again: generation 0, no flag, no entries",
          r0 and r0["generation"] == 0 and r0["flags"] == 0 and r0["entries"] == [] and r0["hash_ok"], r0)
    counts = tail.get("counts", {})
    trims = counts.get(hex(TRIM_ENTRY), counts.get(str(TRIM_ENTRY)))
    check("the driver's TRIM ran once", trims == 1, counts)
    regs = json.dumps(tail.get("regs"))
    check("over the region's last sector, 0x640fff",
          f"{REGION + DATA_END - 1:x}" in regs.lower() or str(REGION + DATA_END - 1) in regs, regs[:200])
    print("PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
