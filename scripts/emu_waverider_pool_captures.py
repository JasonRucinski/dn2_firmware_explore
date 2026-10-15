"""Screen captures of Waverider's wavetable page and its lists, for the manual.

    python scripts/emu_waverider_pool_captures.py BUILD.syx [--out out/wrcaps-pool] [--panel-drive EXE]

One panel_drive run from reset, on a +Drive that holds a store of five tables and a pool
list for the working project (`scripts/emu_waverider_pool.py` writes its card the same way).
The pool list names store slots 3, 0, 9 and 7: slot 9 holds no table, so pool slot 003
reads MISSING, as a table deleted from the +Drive does. Track 1 is made a Waverider track
in MACHINE SEL, then PRESET/KIT pressed twice opens the wavetable page, and each list is
opened with YES and its operations with RIGHT. Nothing is run: NO closes each panel.

Writes OUT/<name>.pbm and OUT/<name>.png (inverted, white on black as the OLED shows them, 2:1).
"""

from __future__ import annotations

import argparse
import json
import math
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from dnfw.waverider import loadframes as LF        # noqa: E402
from dnfw.waverider import poolrecord as PR        # noqa: E402
from dnfw.waverider import store as ST             # noqa: E402
from dnfw.waverider import testtable               # noqa: E402

PANEL = ROOT.parent / "digikit-rust/out/native/target-host/release/examples/panel_drive.exe"
PRESET_KIT, YES, UP, NO, DOWN, RIGHT, FUNC, SYN = 7, 10, 11, 12, 14, 15, 17, 2
POOL_LIST = [3, 0, 9, 7]             # pool slots 001..004 -> store slots; 9 is empty: MISSING


def harmonics(frames: int, points: int, top: int) -> list[list[int]]:
    """frame f: the first 1 + f * top // frames harmonics of a saw, scaled to 20,000"""
    out = []
    for f in range(frames):
        n = 1 + f * top // max(1, frames - 1)
        w = [sum(math.sin(2 * math.pi * h * k / points) / h for h in range(1, n + 1)) for k in range(points)]
        peak = max(abs(x) for x in w)
        out.append([int(round(20000 * x / peak)) for x in w])
    return out


def store_extents(work: pathlib.Path) -> list[str]:
    tables = {0: ("Pulse narrowing", testtable.pool_table()), 3: ("Saw to sine", testtable.table()),
              4: ("Saw build", harmonics(16, 512, 24)), 6: ("Odd steps", harmonics(8, 256, 9)),
              7: ("Five of 1024", harmonics(5, 1024, 4))}
    entries, files = {}, {}
    for n, (name, t) in tables.items():
        data = LF.table_be(t)
        entries[n] = ST.Entry(name, len(t), len(t[0]), ST.slot_start(n), len(data), ST.xxh32(data), 0, len(data))
        files[ST.REGION + ST.slot_start(n)] = data
    index = ST.index_bytes(entries)
    files[ST.REGION] = ST.superblock(1, len(entries), index, ST.DATA_END)
    files[ST.REGION + 1] = index
    files[PR.sector_a(0)] = PR.Record(0, POOL_LIST, generation=1).to_bytes()
    args = []
    for sector, data in files.items():
        f = work / f"s{sector:x}.bin"
        f.write_bytes(data)
        args += ["--card-extent", f"{sector:#x}:{f}"]
    return args


def tap(code, wait="60M"):
    return [f"tap:{code}", f"wait:{wait}"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("build")
    ap.add_argument("--out", default=str(ROOT / "out/wrcaps-pool"))
    ap.add_argument("--panel-drive", default=str(PANEL))
    a = ap.parse_args()
    out = pathlib.Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    names = []

    def frame(n):
        names.append(n)
        return ["wait:60M", f"frame:{n}"]

    s = ["tap:12", "wait:30M", "press:17", "wait:20M", "tap:2", "wait:40M", "release:17", "wait:60M"]
    s += [x for _ in range(4) for x in tap(DOWN, "40M")] + tap(YES, "200M") + tap(SYN)
    s += tap(PRESET_KIT, "120M") + tap(PRESET_KIT, "160M") + frame("wt_page")
    s += tap(YES, "120M") + frame("wt_load")
    s += tap(RIGHT, "100M") + frame("wt_load_ops") + tap(NO) + tap(NO, "100M")
    s += tap(DOWN) + frame("wt_page_manage") + tap(YES, "120M") + frame("wt_manage")
    s += tap(DOWN) + tap(DOWN) + tap(YES) + tap(YES) + frame("wt_manage_ticked")   # the two not in the pool
    s += tap(RIGHT, "100M") + frame("wt_manage_ops") + tap(NO) + tap(NO, "100M")
    s += tap(DOWN) + tap(YES, "120M") + frame("wt_pool")
    s += tap(DOWN) + tap(DOWN) + frame("wt_pool_missing")
    s += ["wait:100M"] + tap(RIGHT, "100M") + frame("wt_pool_ops") + tap(NO) + tap(NO, "100M") + tap(PRESET_KIT, "100M")

    steps = out / "steps.txt"
    steps.write_text("\n".join(s) + "\n")
    cmd = [a.panel_drive, a.build, *store_extents(out), "--out", str(out), "--watch", "0x4011ea6a",
           "--steps", f"@{steps}"]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
    lines = r.stdout.strip().splitlines()
    if not lines:
        raise SystemExit(f"panel_drive said nothing: {r.stderr[-2000:]}")
    report = json.loads(lines[-1])
    (out / "report.json").write_text(json.dumps({k: v for k, v in report.items() if k != "captures"}, indent=1))
    from PIL import Image, ImageOps
    for n in names:
        p = out / f"{n}.pbm"
        if p.exists():
            ImageOps.invert(Image.open(p).convert("L")).resize((256, 128), Image.NEAREST).save(out / f"{n}.png")
    print(report["outcome"], "fault reporter:", report.get("watched"), "frames:", ", ".join(names))
    return 0 if report["outcome"] == "done" else 1


if __name__ == "__main__":
    raise SystemExit(main())
