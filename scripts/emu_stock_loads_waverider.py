"""What stock 1.11 does with a project saved with a Waverider track, in the emulator.

    python scripts/emu_stock_loads_waverider.py WAVERIDER.syx STOCK.syx [--card out/dk-dn2-card.img]

The owner asked on 2026-10-14 (the Waverider page says stock can load such a project and its
Waverider tracks will not play as Waverider; it had not been tried). Two panel_drive runs on the
card image (its writes stay in memory, so the projects travel as files):

1. **On the Waverider build:** track 1 made a Waverider track in MACHINE SEL, SAVE PROJECT AS 002,
   and the file read back over the Data API as DNX reads it. Then the control: a fresh boot,
   track 1 left as it boots, SAVE PROJECT AS 002, read back.
2. **On stock 1.11:** both files written over the Data API as DNX writes a project (the Waverider
   one to /projects/2, the control to /projects/3), then LOAD PROJECT of each from the panel,
   each followed by track 1's SYN page and MACHINE SEL on screen, with the firmware's fault
   reporter (0x4011ea6a) watched throughout.

Writes OUT/*.pbm, OUT/sheet.png (the frames inverted, white on black as the OLED shows them,
scaled 2:1) and OUT/report.json. Pass and fail are read from the frames by a person: the
machine named in each SYN page header and marked in MACHINE SEL.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import struct
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from emu_waverider_projects import load, save_as, taps          # noqa: E402
from emu_waverider_rename import Frames, dec                     # noqa: E402

PANEL = ROOT.parent / "digikit-rust/out/native/target-host/release/examples/panel_drive.exe"
ROUTER = ["--call-at", "0x4002e464", "--call-fn", "0x4012166e", "--call-args", "2",
          "--capture", "0x401233f2:0:1"]
REPORTER = "0x4011ea6a"
READ_CHUNK = 0x4000                  # what the device grants a read
SEQUENCES = 820                      # 12.9 MB / 16 KiB = 787, and some to spare
FUNC, SYN, DOWN, YES, NO = 17, 2, 14, 10, 12


def machine_sel(tag):
    """Open MACHINE SEL on the active track, capture it, close it with NO"""
    return (["press:17", "wait:20M", "tap:2", "wait:40M", "release:17", "wait:60M", f"frame:{tag}"]
            + taps(NO, wait="60M"))


def make_waverider():
    return (["press:17", "wait:20M", "tap:2", "wait:40M", "release:17", "wait:60M"]
            + taps(DOWN, DOWN, DOWN, DOWN, wait="40M") + ["frame:wr_sel"] + taps(YES, wait="200M"))


def run(syx, card, out, steps, name):
    steps_file = out / f"{name}.steps"
    steps_file.write_text("\n".join(steps) + "\n")
    r = subprocess.run([str(PANEL), str(syx), "--card-image", str(card), "--out", str(out), *ROUTER,
                        "--watch", REPORTER, "--steps", f"@{steps_file}"],
                       capture_output=True, text=True, timeout=3600)
    report = json.loads(r.stdout.strip().splitlines()[-1])
    (out / f"{name}.json").write_text(json.dumps({k: v for k, v in report.items() if k != "captures"}, indent=1))
    return report


def replies(report):
    stream = b"".join(bytes.fromhex(c["hex"]) for c in report.get("captures", []))
    return [dec((m + b"\xf7").hex())[5:] for m in stream.split(b"\xf7") if m.startswith(b"\xf0")]


def read_file(report) -> bytes:
    """The project file from a run's /projects/2 read replies (as emu_project_save_read.py)"""
    data = bytearray()
    for d in replies(report):
        if len(d) < 22 or d[0] != 1:
            continue
        seq = struct.unpack_from(">I", d, 5)[0]
        length = struct.unpack_from(">I", d, 18)[0]
        if seq == 0 or length == 0:
            continue
        data += d[22:22 + length]
    return bytes(data)


def save_and_read(syx, card, out, name, before):
    f = Frames()
    # the trailing 01 asks for the stored (compressed) form, the only one a write takes; the raw
    # form commits to "Footer was not processed" (DNX, packages/core/src/device/storagewrite.ts)
    f.frame("open", 0x54, b"/projects/2\0" + struct.pack(">I", READ_CHUNK) + b"\x01")
    for k in range(SEQUENCES):
        f.frame(f"seq{k}", 0x55, struct.pack(">II", 1, k))
    f.frame("close", 0x56, struct.pack(">I", 1))
    steps = (["tap:12", "wait:30M"] + before + taps(SYN, wait="60M") + [f"frame:{name}_syn"]
             + save_as(2, name) + [f"send:{h}" for _, h in f.lines])
    report = run(syx, card, out, steps, name)
    return report, read_file(report)


def sheet(out, names):
    from PIL import Image, ImageDraw, ImageOps
    tiles = []
    for n in names:
        p = out / f"{n}.pbm"
        if p.exists():
            img = ImageOps.invert(Image.open(p).convert("L")).resize((256, 128), Image.NEAREST)
            tiles.append((n, img))
    w, h = 256 + 16, 128 + 28
    cols = 3
    rows = (len(tiles) + cols - 1) // cols
    canvas = Image.new("L", (cols * w + 8, rows * h + 8), 40)
    draw = ImageDraw.Draw(canvas)
    for i, (n, img) in enumerate(tiles):
        x, y = 8 + (i % cols) * w, 8 + (i // cols) * h
        draw.text((x, y), n, fill=230)
        canvas.paste(img, (x, y + 16))
    canvas.save(out / "sheet.png")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("waverider")
    ap.add_argument("stock")
    ap.add_argument("--card", default=str(ROOT / "out/dk-dn2-card.img"))
    ap.add_argument("--out", default=str(ROOT / "out/stock_loads_waverider"))
    ap.add_argument("--reuse", action="store_true", help="skip step 1: use OUT/wr_project.bin and ctl_project.bin")
    a = ap.parse_args()
    out = pathlib.Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    result = {}

    if a.reuse:
        wr_file, ctl_file = ((out / f"{n}_project.bin").read_bytes() for n in ("wr", "ctl"))
        saved = []
    else:
        wr_report, wr_file = save_and_read(a.waverider, a.card, out, "wr", make_waverider())
        ctl_report, ctl_file = save_and_read(a.waverider, a.card, out, "ctl", [])
        saved = [("wr", wr_report, wr_file), ("ctl", ctl_report, ctl_file)]
    for name, rep, data in saved:
        (out / f"{name}_project.bin").write_bytes(data)
        result[f"{name}_save"] = {"outcome": rep["outcome"], "bytes": len(data),
                                  "faults": rep.get("watched")}
        print(f"{name}: save run {rep['outcome']}, {len(data):,} bytes read back")
    if not wr_file or not ctl_file:
        print("FAIL: a project did not read back")
        (out / "report.json").write_text(json.dumps(result, indent=1))
        return 1

    f = Frames()
    f.write("put2", "/projects/2", wr_file)
    f.write("put3", "/projects/3", ctl_file)
    steps = ["tap:12", "wait:30M"] + [f"send:{h}" for _, h in f.lines]
    for row, tag in ((0, "s_wr"), (1, "s_ctl")):
        steps += (load(row, tag) + taps(NO, wait="60M") + [f"frame:{tag}_ask2"]
                  + taps(YES, wait="1500M") + [f"frame:{tag}_done"] + taps(NO, NO, NO, wait="40M")
                  + taps(SYN, wait="60M") + [f"frame:{tag}_syn"] + taps(SYN, wait="60M")
                  + [f"frame:{tag}_syn2"] + machine_sel(f"{tag}_sel"))
    st = run(a.stock, a.card, out, steps, "stock")
    got = replies(st)
    commits = [d for d in got if d[:1] == b"\x01" and len(d) < 22]
    # in request order, one reply each: per file the open, every chunk, the commit
    per = len(f.lines) // 2
    for label, k in (("put2 open", 0), ("put2 chunk0", 1), ("put2 commit", per - 1), ("put3 commit", len(f.lines) - 1)):
        d = got[k] if k < len(got) else b""
        print(f"  {label}: {d[:40].hex()}  {d[:60]!r}")
    result["stock_load"] = {"outcome": st["outcome"], "faults": st.get("watched"),
                            "fault": st.get("fault"), "replies": len(replies(st)), "short_replies": len(commits)}
    print(f"stock run {st['outcome']}; fault reporter: {st.get('watched')}")
    (out / "report.json").write_text(json.dumps(result, indent=1))
    sheet(out, ["wr_sel", "wr_syn", "ctl_syn", "s_wr_list", "s_wr_done", "s_wr_syn", "s_wr_syn2",
                "s_wr_sel", "s_ctl_done", "s_ctl_syn", "s_ctl_syn2", "s_ctl_sel"])
    print(f"frames in {out}, sheet.png")
    return 0 if st["outcome"] == "done" else 1


if __name__ == "__main__":
    raise SystemExit(main())
