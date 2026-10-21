"""Bloom, a VA machine built around a modulator that bends time (`docs/bloom-machine.md`).

**Milestone B2, the ColdFire half only. Not on the instrument.** MACHINE SEL offers
**BLOOM** after SWARMER, in a section of its own above MIDI's divider. A Bloom track is
machine type 7 in the sound and in the frame, and WaveTone everywhere else in the UI:
its SYN pages are WaveTone's until Bloom's own pages (B4).

**It does not sound like Bloom yet.** Nothing changes on the DSP until B3, and the
DSP's machine lookup sends type 7 to FM Tone's render, so a Bloom track plays FM Tone
with WaveTone's parameters.

## How it applies

Section 3 only, from committed data: `bloom_code.json`, written by
`scripts/gen_bloom_code.py` from `dnfw.bloom.coldfire`. Every guard and every edit's
stock bytes are checked first. The platform's hook bus writes the machine-count bounds
(`dnfw.mods.bus`, `MACH`); Bloom adds three types (5, 6 and 7), with FM Tone's rows for
5 and 6, so it can be 7.

## A sound or project saved with a Bloom track

Saved as machine type 7 by the stock SAVE. This build keeps 7 on LOAD, and loads a
stored 5 or 6 as FM Tone, as stock does. Stock firmware, and a Waverider build, load a
Bloom sound as **FM Tone**, the LOAD bound's own fallback.

## Combining

Bloom uses Waverider's three caves and both add machines through the bus's one
machine count, so the two exclude each other.
"""

from __future__ import annotations

import json
import pathlib

from . import Extent, ModError, Result, bus, platform

ID = "bloom"
NAME = "Bloom, a VA machine (B2: MACHINE SEL and the UI)"
SUMMARY = ("BLOOM in MACHINE SEL, machine type 7, WaveTone's pages for now. ColdFire only: "
           "it does not yet sound like Bloom (that is B3).")
DEVICE = 0x15                      # Digitone II
MAIN_OS = 3
BASE = 0x40000400
SPEC = json.loads((pathlib.Path(__file__).with_name("bloom_code.json")).read_text())


def extents(firmware=None, area_length: int = 0) -> list[Extent]:
    return ([Extent(MAIN_OS, e["va"] - BASE, len(e["new"]) // 2, e["what"]) for e in SPEC["edits"]]
            + platform.extents(area_length))


def ram() -> list[Extent]:
    return []                      # nothing outside the image: the tables are in caves


def _main_os(original: bytes) -> bytes:
    if len(original) < SPEC["stock_length"]:
        raise ModError(f"MAIN OS is {len(original):,} B, shorter than "
                       f"{SPEC['stock_length']:,}: not Digitone II 1.11")
    for g in SPEC["guards"]:
        want = bytes.fromhex(g["bytes"])
        at = g["va"] - BASE
        if original[at:at + len(want)] != want:
            raise ModError(f"0x{g['va']:08x} ({g['what']}) is not stock; this mod is "
                           "for unmodified Digitone II 1.11")
    content = bytearray(original)
    for e in SPEC["edits"]:
        old, new = bytes.fromhex(e["stock"]), bytes.fromhex(e["new"])
        at = e["va"] - BASE
        if bytes(content[at:at + len(old)]) != old:
            raise ModError(f"0x{e['va']:08x} ({e['what']}) is not stock; this mod is for "
                           "unmodified Digitone II 1.11, or another mod already wrote there")
        content[at:at + len(new)] = new
    return bytes(content)


def apply(firmware) -> Result:
    cf = firmware.container.find(MAIN_OS)
    if cf is None:
        raise ModError("image has no MAIN OS")
    main_os = cf.unpack()
    if main_os is None:
        raise ModError("MAIN OS did not depack")
    main_os, others = platform.split(main_os)
    content = platform.join(_main_os(main_os), others + [bus.contribute(b"MACH", SPEC["added_machine_types"])])
    area_length = len(content) - platform.STOCK_LENGTH
    return Result(payloads={MAIN_OS: content}, extents=extents(firmware, area_length),
                  notes=[f"MACHINE SEL offers {SPEC['names'][0].upper()} after SWARMER "
                         f"(type {SPEC['new_type']}; WaveTone's pages)",
                         "ColdFire only (B2): a Bloom track does not yet sound like Bloom",
                         f"{len(SPEC['edits'])} edits in section 3"])
