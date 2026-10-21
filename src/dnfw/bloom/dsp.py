"""Bloom's DSP half (milestone B3a): the edits Bloom makes to section 7 (the SHARC boot
stream), applied from committed artefacts (`sharc_code.json`, written by
`scripts/gen_bloom_sharc.py` from `csrc/bloom/sharc/bloom_loop.asm`).

    section7(stock) -> the modified boot stream
    spans()         -> the blocks it adds: (what, load address, payload)
    placements()    -> what goes where, for a report or a mod's extents

**What it does to DN2 1.11's section 7:**

1. **Adds boot blocks** in L1 block 1's free tail, the region Waverider's M5c proved on
   the instrument (`dnfw.waverider.dsp.REGION`; the two mods exclude each other):
   the loop at byte 0x2dd600 (sw 0x16eb00), zero-padded to 0x2dde00; its state, zeros
   (save area, the track counter, 16 phases) to 0x2de000; the tables DT and INV
   (`dnfw.bloom.live`), each padded to 1 KB. The region is written end to end, so no
   byte the loop could reach is left as whatever L1 held.
2. **Enters the type-7 loop**: the two instructions at sw 0x1c9448 (after the Swarmer
   render loop, before the per-track chain) become `JUMP 0x16eb00` and a 16-bit NOP;
   the loop re-executes them before it jumps back to 0x1c944c.
3. **Lets a type-7 frame through**: the frame-nibble -> machine-type lookup
   0x25d748[7] becomes 7 (stock 0, FM Tone).
4. **Pulses FREQ** (B3b, `pulse=True`): `pulse.asm` at byte 0x2de800 (sw 0x16f400) and
   its state, zeros, to 0x2def00; the handler's `r4 = 0x268438` at sw 0x1c9fb9, just
   before it calls the unpack, becomes `JUMP 0x16f400`, and the code re-executes it
   before it jumps back to the call at 0x1c9fbc. It rewrites each Bloom track's FREQ
   word in the received frame (`dnfw.bloom.live.pulse_block`).

It does not touch the per-type setup table: the dispatch indexes it only after
`compu(type, 5)`, so type 7 takes the no-setup arm, as Waverider's type 5 does.

Every stock byte it replaces is checked first, and every added span is checked to lie
inside the region and outside every block of the stock stream. Pure: bytes in, bytes out.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import struct

from ..image import bootstream, sharc_object
from ..waverider import dsp as W
from . import live

CODE = pathlib.Path(__file__).with_name("sharc_code.json")
TYPE = 7

LOOP_DM = 0x2DD600                  # bloom_loop.asm
LOOP_SW = LOOP_DM // 2              # 0x16eb00
STATE_DM = 0x2DDE00                 # save area (28 words), then the track counter at +0x80
PHASES_DM = 0x2DDF00                # 16 float32, one per track
STATE_END = 0x2DE000
DT_DM = 0x2DE000                    # live.dt_table(), 129 float32
INV_DM = 0x2DE400                   # live.inv_table(), 129 float32
TABLES_END = 0x2DE800
CODE_PAD_MIN = 64                   # bytes of zeros (NOPs) at least after the code

PULSE_DM = 0x2DE800                 # pulse.asm (B3b)
PULSE_SW = PULSE_DM // 2            # 0x16f400
PULSE_STATE_DM = 0x2DEC00           # 16 tracks x 32 bytes: step, phase, n, base, last
PULSE_STATE_STRIDE = 32
PULSE_END = 0x2DEF00                # then its save area and scratch (0x2dee00..)

ENTRY_SW = W.ENTRY_SW               # 0x1c9448: i5=dm(-0x18,i6); r10=dm(-0x22,i6)
ENTRY_STOCK = W.ENTRY_STOCK
RESUME_SW = 0x1C944C
CALL_SITE_SW = W.CALL_SITE_SW       # 0x1c9fb9: r4 = 0x268438, before `cjump 0x1c2712`
CALL_SITE_STOCK = W.CALL_SITE_STOCK
CALL_RESUME_SW = 0x1C9FBC
LOOKUP_DM = W.LOOKUP_DM             # 0x25d748, 8 words
LOOKUP_STOCK = W.LOOKUP_STOCK


class DspError(ValueError):
    pass


def _code() -> dict:
    if not CODE.exists():
        raise DspError(f"{CODE.name} is missing: run scripts/gen_bloom_sharc.py --assemble")
    return json.loads(CODE.read_text(encoding="utf-8"))


def objects() -> dict[str, bytes]:
    """The committed objects in memory order: the loop, PULSE, and their JUMPs."""
    spec = _code()
    for key, sw in (("loop", LOOP_SW), ("pulse", PULSE_SW)):
        if int(spec[key]["load_sw"], 16) != sw:
            raise DspError(f"{key} was assembled for sw {spec[key]['load_sw']}, not {sw:#x}")
    return {k: sharc_object.load_bytes(bytes.fromhex(spec[k]["object_parcels_be"]))
            for k in ("loop", "entry_jump", "pulse", "pulse_jump")}


def _table(values: list[float], end: int, at: int) -> bytes:
    data = struct.pack(f"<{len(values)}f", *values)
    return data + bytes(end - at - len(data))


def spans(pulse: bool = True) -> list[tuple[str, int, bytes]]:
    obj = objects()
    loop, code = obj["loop"], obj["pulse"]
    if STATE_DM - LOOP_DM - len(loop) < CODE_PAD_MIN:
        raise DspError(f"bloom_loop.asm ({len(loop)} B) leaves fewer than {CODE_PAD_MIN} bytes of NOPs")
    if PULSE_STATE_DM - PULSE_DM - len(code) < CODE_PAD_MIN:
        raise DspError(f"pulse.asm ({len(code)} B) leaves fewer than {CODE_PAD_MIN} bytes of NOPs")
    extra = [("pulse.asm (bp_pulse)", W.dm_to_load(PULSE_DM), code + bytes(PULSE_STATE_DM - PULSE_DM - len(code))),
             ("pulse state (zeros: 16 tracks, save area, scratch)", W.dm_to_load(PULSE_STATE_DM),
              bytes(PULSE_END - PULSE_STATE_DM))] if pulse else []
    return [("bloom_loop.asm (bl_loop)", W.dm_to_load(LOOP_DM), loop + bytes(STATE_DM - LOOP_DM - len(loop))),
            ("bloom state (zeros: save area, track counter, 16 phases)", W.dm_to_load(STATE_DM),
             bytes(STATE_END - STATE_DM)),
            ("DT, the phase step per note (live.dt_table)", W.dm_to_load(DT_DM),
             _table(live.dt_table(), INV_DM, DT_DM)),
            ("INV, 1 / DT per note (live.inv_table)", W.dm_to_load(INV_DM),
             _table(live.inv_table(), TABLES_END, INV_DM))] + extra


def placements(pulse: bool = True) -> list[dict]:
    obj = objects()
    out = [{"what": what, "load_address": f"{at:#010x}", "dm_byte": f"{at - W.LOAD_ALIAS:#08x}",
            "bytes": len(payload), "sha256": hashlib.sha256(payload).hexdigest()}
           for what, at, payload in spans(pulse)]
    out += [{"what": f"patch: entry JUMP {LOOP_SW:#x} + NOP at sw {ENTRY_SW:#x}",
             "load_address": f"{W.sw_to_load(ENTRY_SW):#010x}", "bytes": len(ENTRY_STOCK),
             "stock": ENTRY_STOCK.hex(), "new": (obj["entry_jump"] + W.NOP16).hex()},
            {"what": f"patch: machine lookup {LOOKUP_DM:#x}[{TYPE}] 0 -> {TYPE}",
             "load_address": f"{W.dm_to_load(LOOKUP_DM + 4 * TYPE):#010x}", "bytes": 4,
             "stock": "00000000", "new": struct.pack("<I", TYPE).hex()}]
    if pulse:
        out.append({"what": f"patch: `r4 = 0x268438` at sw {CALL_SITE_SW:#x} -> JUMP {PULSE_SW:#x}",
                    "load_address": f"{W.sw_to_load(CALL_SITE_SW):#010x}", "bytes": len(CALL_SITE_STOCK),
                    "stock": CALL_SITE_STOCK.hex(), "new": obj["pulse_jump"].hex()})
    return out


def section7(stock: bytes, pulse: bool = True) -> bytes:
    """DN2 1.11's section 7 -> Bloom's (without PULSE when not PULSE: B3a's image, the
    B3b gate's reference). Refuses anything else."""
    digest = hashlib.sha256(stock).hexdigest()
    if digest != W.STOCK_SHA256:
        raise DspError(f"section 7 sha256 {digest[:12]}... is not stock DN2 1.11's "
                       f"({W.STOCK_SHA256[:12]}...)")
    obj = objects()
    entry = obj["entry_jump"] + W.NOP16
    if len(entry) != len(ENTRY_STOCK):
        raise DspError(f"the entry patch is {len(entry)} bytes, not {len(ENTRY_STOCK)}")
    if bootstream.read_span(stock, W.sw_to_load(ENTRY_SW), len(ENTRY_STOCK)) != ENTRY_STOCK:
        raise DspError("sw 0x1c9448 is not the stock `i5=dm(-0x18,i6); r10=dm(-0x22,i6)`")
    lookup = struct.unpack("<8I", bootstream.read_span(stock, W.dm_to_load(LOOKUP_DM), 32))
    if lookup != LOOKUP_STOCK:
        raise DspError(f"the machine lookup is {lookup}, not stock {LOOKUP_STOCK}")
    if len(obj["pulse_jump"]) != len(CALL_SITE_STOCK):
        raise DspError(f"the pulse JUMP is {len(obj['pulse_jump'])} bytes, not {len(CALL_SITE_STOCK)}")
    if bootstream.read_span(stock, W.sw_to_load(CALL_SITE_SW), len(CALL_SITE_STOCK)) != CALL_SITE_STOCK:
        raise DspError("sw 0x1c9fb9 is not the stock `r4 = 0x268438`")
    added = spans(pulse)
    W._check_free(stock, added)
    out = bytearray(bootstream.insert_before_final(
        stock, b"".join(W.stream_blocks(at, payload) for _, at, payload in added)))
    bootstream.write_span(out, W.sw_to_load(ENTRY_SW), entry)
    bootstream.write_span(out, W.dm_to_load(LOOKUP_DM + 4 * TYPE), struct.pack("<I", TYPE))
    if pulse:
        bootstream.write_span(out, W.sw_to_load(CALL_SITE_SW), obj["pulse_jump"])
    return W._finish(out)
