"""Arp offsets in scale: the arpeggiator's step offsets move by degrees of the track's scale.

    python scripts/build_arpscale.py [--out PATH]

Stock 1.11 adds each arp step's OFFSET in semitones, after the keyboard's SCALE
and ROOT have done their work, so an offset leaves the scale: in C major, E plus
2 plays F#. This build adds **SETTINGS > PERSONALIZE > ARP OFS IN SCALE**. Off
(the default, and what a fresh instrument reads) the arp is stock. On, a step's
offset counts degrees of the track's KEYBOARD SETUP scale from its root: in C
major, E plus 2 plays G, and plus 7 is the octave.

## The rule

For a held note and a step offset `k`:

1. `k = 0`: the held note, unchanged, as stock (even a note outside the scale).
2. Otherwise the note moves `k` degrees of the track's scale from its root
   (`scripts/build_scale_degrees.py`, "The move").
3. The arp's octave (RANGE) is added in semitones after, as stock.

Stock behaviour is kept whenever the scale says nothing about degrees (SCALE
CHROMATIC, MODE CHORD MEMORY), and for an arp step reached from anywhere but the
two stock callers (below). A note below 0 rests, as a stock offset's does.

## Where the step adds the offset (`docs/arp-hidden-modes.md`)

The step `0x4002a0bc(track, arp id)` ends, for every mode, in one tail:
`0x4002a38c mvs.b 358(%a1),%d2` (the step's offset), then `0x4002a390 add.l
%d1,%d0; add.l %d2,%d0; bra 0x4002a39c`. At `0x4002a390` `%d0` is the held
note, `%d1` 12 x the arp's octave and `%d2` the offset; `0x4002a39c` restores
`%d2-%d7/%a2-%a4` and returns `%d0`. Those six bytes become `jmp arp`. arpmodes
guards `0x4002a38c` and `0x4002a39a` and enters the tail at `0x4002a376`, so
its SHUF and RAND go through this hook too.

## Where the scale is

The step's two callers, `0x400266e0` and `0x4002686e`, are in the frame ISR
`0x40025e36`, which keeps its voice record at `-36(%fp)`; the step leaves `%a6`
alone and calls nothing. So when the step's return address is one of the two,
`build_scale_degrees.scale_lookup` finds the record's track's SCALE and ROOT in
the playing pattern (`scripts/build_scale_degrees.py`, "Where the scale is,
while the pattern plays").

## The toggle and the PERSONALIZE item

As reloadconfirm's (`scripts/build_reload_confirm.py`): one byte in the settings
block's unaddressed tail, saved and restored with the block, zero on a fresh
instrument, ignored by stock. reloadconfirm has `0x405cd8ae`; this is the next
byte, `0x405cd8af`. Only 1 means on. Written only through the stock setting
writer `0x400bb4f8`.

The item is `scripts/build_personalize_toggle.py`'s, as reloadconfirm's is,
appended from a different site, so the two mods do not hook the same bytes:
after the last stock item is appended, `0x40098630 jsr (%a3); move.l
%d3,-(%sp); jsr (%a3)`, three of the destructor calls, replayed unchanged.
reloadconfirm hooks the epilogue (`0x4009863e`) and guards `0x4009862c`, so
with both, RELOAD CONFIRM comes after this item.

## Code and RAM

One platform `CODE` chunk at `0x467a8000`, in the free run between arpmodes'
RAM (`0x467a0000`, 2,320 B) and `0x467b0000` (`docs/mod-memory-regions.md`). No
other RAM but the toggle's byte.
"""

from __future__ import annotations

import argparse
import pathlib
import struct
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "src"))

from dnfw.cli.files import read_image
from dnfw.container.section import compress
from dnfw.firmware import build as fwbuild
from dnfw.firmware.load import load
from dnfw.mods import platform
from dnfw.patch.assemble import assemble, available

import build_personalize_toggle as toggle
from build_scale_degrees import (BASE, SCALE_CONTEXT, degree_move, scale_lookup,
                                 scales)

MAIN_OS = 3

CODE_VA = 0x467A8000            # past arpmodes' RAM (0x467a0000, 2,320 B), below 0x467b0000
FLAG = 0x405CD8AF               # the toggle: reloadconfirm's 0x405cd8ae, plus one

# The arp step's tail.
ARP_SITE = 0x4002A390
ARP_DISPLACED = bytes.fromhex("d081" "d082" "6006")   # add.l %d1,%d0; add.l %d2,%d0; bra 0x4002a39c
STEP_EXIT = 0x4002A39C          # restores the step's registers, returns %d0
CALLER_RETURNS = (0x400266E6, 0x40026874)    # after the two stock calls of the step
STEP_FRAME = 36                 # the step's own frame: its return address is at 36(%sp)
MENU_SITE = 0x40098630          # PersonalizeMenuView's constructor, after the last stock append
MENU_DISPLACED = bytes.fromhex("4e93" "2f03" "4e93")  # jsr (%a3); move.l %d3,-(%sp); jsr (%a3)
MENU_BACK = MENU_SITE + len(MENU_DISPLACED)

NAME = "ARP OFS IN SCALE"       # 16 characters, as LIVE REC OVERDUB

LABELS = ("arp", "menu_hook")



SOURCE = f"""
| The arp step's tail (0x4002a390), reached by jmp. %d0 the held note, %d1 12 x
| the arp's octave, %d2 the step's offset; out: %d0 the note, at 0x4002a39c,
| which restores %d2-%d7/%a2-%a4. %d0 and %d1 are kept until stock is ruled out.
arp:
    tst.l   %d2
    beq.w   arp_stock                   | offset 0: the held note
    mvz.b   {FLAG:#x},%d3
    moveq   #1,%d4
    cmp.l   %d4,%d3
    bne.w   arp_stock                   | the toggle is off
    move.l  {STEP_FRAME}(%sp),%d3       | the step's caller: only the frame ISR's
    cmpi.l  #{CALLER_RETURNS[0]:#x},%d3 | two calls have the record at -36(%fp)
    beq.s   1f
    cmpi.l  #{CALLER_RETURNS[1]:#x},%d3
    bne.w   arp_stock
1:
{scale_lookup('arp_stock')}
{degree_move('arp')}
    add.l   %d1,%d0                     | the arp's octave
    jmp     {STEP_EXIT:#x}

arp_stock:
    add.l   %d1,%d0                     | the displaced instructions
    add.l   %d2,%d0
    jmp     {STEP_EXIT:#x}

{toggle.routines(FLAG)}
| PersonalizeMenuView's constructor, after its last stock item is appended,
| reached by jmp: the displaced destructor calls, then append this item. %a4 is
| the view; %a3 (the destructor) and %d6 are the constructor's, so kept.
menu_hook:
    jsr     (%a3)                       | the displaced instructions
    move.l  %d3,-(%sp)
    jsr     (%a3)
    lea     -8(%sp),%sp
    movem.l %d6/%a3,(%sp)
{toggle.append_item()}
    movem.l (%sp),%d6/%a3
    lea     8(%sp),%sp
    jmp     {MENU_BACK:#x}

item_name:
    .asciz  "{NAME}"
"""

# (va, stock bytes, label): each site becomes `jmp label`, nop-padded.
HOOKS = (
    (ARP_SITE, ARP_DISPLACED, "arp"),
    (MENU_SITE, MENU_DISPLACED, "menu_hook"),
)

# Read, not written: the code the hooks rely on.
CONTEXT = (
    (0x4002A0BC, bytes.fromhex("4fefffdc48d71cfc"), "the step: a 36-byte frame, %d2-%d7/%a2-%a4 saved"),
    (0x4002A0F4, bytes.fromhex("22680020"), "the step: %a1 = its sound (+32)"),
    (0x4002A38C, bytes.fromhex("75290166"), "the step: %d2 = the step's offset (+358)"),
    (0x4002A37E, bytes.fromhex("2401e58a"), "the step: %d2 = octave x 4 ..."),
    (0x4002A386, bytes.fromhex("e989d3c39282"), "... %d1 = octave x 12"),
    (STEP_EXIT, bytes.fromhex("4cd71cfc4fef00244e75"), "the step's exit: restore, return %d0"),
    (0x400266D8, bytes.fromhex("2f2800602f2800104eb94002a0bc"),
     "the ISR's first call: step(record +16, record +96)"),
    (0x40026868, bytes.fromhex("2f052f2800104eb94002a0bc"), "the ISR's second call: step(record +16, ...)"),
    (0x400266C2, bytes.fromhex("206effdc"), "the first call's record: -36(%fp)"),
    (0x40026848, bytes.fromhex("206effdc"), "the second call's record: -36(%fp)"),
) + SCALE_CONTEXT + (
    (0x40098638, bytes.fromhex("4e932f044e93"),
     "constructor: the last destructor calls (reloadconfirm hooks the epilogue after them)"),
) + toggle.CONTEXT

ROOT = pathlib.Path(__file__).resolve().parent.parent
STOCK = ROOT / "00_Resources/00_Firmware/Digitone_II_OS1.11_dist.zip"
OUT = ROOT / "00_Resources/02_Builds/arpscale_DN2_1.11.syx"


def assemble_stubs(source: str, base: int, labels: tuple[str, ...]) -> tuple[bytes, dict[str, int]]:
    """Assemble once and read each of LABELS' addresses off a trailing table."""
    table = "\n".join(f"    .long {name}" for name in labels)
    blob = assemble(source + "\n    .align 2\n" + table + "\n", base=base)
    width = 4 * len(labels)
    addrs = struct.unpack(">%dI" % len(labels), blob[-width:])
    return blob[:-width], dict(zip(labels, addrs))


def check(content: bytes, va: int, want: bytes, why: str) -> None:
    have = bytes(content[va - BASE:va - BASE + len(want)])
    if have != want:
        raise SystemExit(f"{va:#010x}: expected {want.hex()}, found {have.hex()} "
                         f"-- not the image this build was written against ({why})")


def compose(stock: bytes, log=print) -> dict:
    """Apply the build to a stock MAIN OS. -> {content, blob, labels}: the hooked
    image and the code, 4-padded, for a platform `CODE` chunk at CODE_VA."""
    if not available():
        raise SystemExit("no m68k assembler found")
    content = bytearray(stock)
    if any(content[FLAG - BASE:FLAG - BASE + 1]):
        raise SystemExit("the toggle's byte is not zero in the image")

    log("part 1 -- the code this relies on, asserted")
    for va, want, why in CONTEXT:
        check(content, va, want, why)
        log(f"  {va:#010x}  {want.hex():<28}  {why}")
    log(f"  {len(scales(content))} scales, each holding its root, the two tables agreeing")

    log(f"part 2 -- the code, from {CODE_VA:#010x}")
    payload, at = assemble_stubs(SOURCE, CODE_VA, LABELS)
    blob = payload + bytes(-len(payload) % 4)
    log(f"  {len(payload)} bytes: " + ", ".join(f"{k} {v:#010x}" for k, v in at.items()))

    log("part 3 -- the hooks")
    for va, stock_bytes, label in HOOKS:
        check(content, va, stock_bytes, label)
        new = bytes.fromhex("4ef9") + struct.pack(">I", at[label])
        new += bytes.fromhex("4e71") * ((len(stock_bytes) - len(new)) // 2)
        if len(new) != len(stock_bytes):
            raise SystemExit(f"hook at {va:#010x} does not fit {len(stock_bytes)} bytes")
        content[va - BASE:va - BASE + len(new)] = new
        log(f"  {va:#010x}  {stock_bytes.hex()} -> {new.hex()}  jmp {label}")

    return {"content": bytes(content), "blob": blob, "labels": at}


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--out", type=pathlib.Path, default=OUT)
    a = p.parse_args()
    firmware = load(read_image(STOCK))
    section = firmware.container.find(MAIN_OS)
    if section is None:
        raise SystemExit("image has no MAIN OS section")
    built = compose(section.unpack())
    chunk = platform.area.CodeChunk(CODE_VA, built["blob"]).pack()
    content = platform.join(built["content"], [(platform.area.CODE, chunk)])

    print("part 4 -- repack")
    if a.out.exists():
        raise SystemExit(f"{a.out} exists; builds are never overwritten")
    a.out.parent.mkdir(parents=True, exist_ok=True)
    replacement = compress(section.id, section.dest, content)
    a.out.write_bytes(fwbuild.build(firmware, {MAIN_OS: replacement}))
    print(f"  wrote {a.out} ({a.out.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
