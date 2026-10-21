"""Bloom, a VA machine built around a modulator that bends time (`docs/bloom-machine.md`).

**Milestones B2 and B3. Not on the instrument yet.** MACHINE SEL offers **BLOOM** after
SWARMER, in a section of its own above MIDI's divider. A Bloom track is machine type 7
in the sound and in the frame, and WaveTone everywhere else in the UI: its SYN pages
are WaveTone's until Bloom's own pages (B4).

**What it sounds like (B3):** a plain PolyBLEP saw at the trig note plus TUN1, through
the stock filter and amp, and the Innerbloom gesture on the filter: from each trig, a
triangle on FREQ, 32 steps either way, whose rate glides from 12 Hz to 1 Hz over 8
seconds, then stays at 1 Hz. Fixed in v0; its controls come with the pages (B4).

## How it applies

- **Section 3**, from committed data: `bloom_code.json`, written by
  `scripts/gen_bloom_code.py` from `dnfw.bloom.coldfire`. Every guard and every edit's
  stock bytes are checked first. The platform's hook bus writes the machine-count bounds
  (`dnfw.mods.bus`, `MACH`); Bloom adds three types (5, 6 and 7), with FM Tone's rows for
  5 and 6, so it can be 7.
- **Section 7**, the DSP boot stream: `dnfw.bloom.dsp.section7`, from the committed
  `dnfw/bloom/sharc_code.json` (the type-7 loop, PULSE, their JUMPs, the lookup).

## A sound or project saved with a Bloom track

Saved as machine type 7 by the stock SAVE. This build keeps 7 on LOAD, and loads a
stored 5 or 6 as FM Tone, as stock does. Stock firmware, and a Waverider build, load a
Bloom sound as **FM Tone**, the LOAD bound's own fallback.

## Combining

Bloom uses Waverider's three caves, its L1 region and its two DSP hook sites, and both
add machines through the bus's one machine count, so the two exclude each other.
"""

from __future__ import annotations

import json
import pathlib

from ..bloom import dsp
from . import Extent, ModError, Result, bus, platform

ID = "bloom"
NAME = "Bloom, a VA machine (B3: a saw, and the Innerbloom pulse on the filter)"
SUMMARY = ("BLOOM in MACHINE SEL, machine type 7, WaveTone's pages for now. A PolyBLEP saw "
           "whose filter pulses from 12 Hz down to 1 Hz over 8 s from each trig.")
DEVICE = 0x15                      # Digitone II
MAIN_OS, DSP_STREAM = 3, 7
BASE = 0x40000400
SPEC = json.loads((pathlib.Path(__file__).with_name("bloom_code.json")).read_text())


def extents(firmware=None, area_length: int = 0) -> list[Extent]:
    out = ([Extent(MAIN_OS, e["va"] - BASE, len(e["new"]) // 2, e["what"]) for e in SPEC["edits"]]
           + platform.extents(area_length))
    size = None
    if firmware is not None:
        section = firmware.container.find(DSP_STREAM)
        content = section.unpack() if section is not None else None
        size = len(content) if content is not None else None
    # The boot stream is rebuilt as a whole (blocks inserted before its final block),
    # so the whole of it is declared: nothing else may write it too.
    out.append(Extent(DSP_STREAM, 0, size or 836_956,
                      "the DSP boot stream, rebuilt: Bloom's loop, PULSE, state and tables in "
                      "L1 block 1, the entry and pulse jumps, the machine lookup"))
    return out


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
    ds = firmware.container.find(DSP_STREAM)
    if cf is None or ds is None:
        raise ModError("image has no MAIN OS or no DSP boot stream")
    main_os, stream = cf.unpack(), ds.unpack()
    if main_os is None or stream is None:
        raise ModError("MAIN OS or the DSP boot stream did not depack")
    try:
        section7 = dsp.section7(stream)
    except dsp.DspError as exc:
        raise ModError(f"the DSP boot stream: {exc}") from exc
    main_os, others = platform.split(main_os)
    content = platform.join(_main_os(main_os), others + [bus.contribute(b"MACH", SPEC["added_machine_types"])])
    area_length = len(content) - platform.STOCK_LENGTH
    return Result(payloads={MAIN_OS: content, DSP_STREAM: section7},
                  extents=extents(firmware, area_length),
                  notes=[f"MACHINE SEL offers {SPEC['names'][0].upper()} after SWARMER "
                         f"(type {SPEC['new_type']}; WaveTone's pages)",
                         "a PolyBLEP saw; FREQ pulses 12 Hz -> 1 Hz over 8 s from each trig (B3 v0)",
                         f"{len(SPEC['edits'])} edits in section 3; section 7 "
                         f"{len(stream):,} -> {len(section7):,} B"])
