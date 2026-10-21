"""Bloom on the ColdFire (milestone B2): machine type 7, offered by MACHINE SEL, a
WaveTone clone everywhere else in the UI (`docs/bloom-machine.md`, "B2").

This is Waverider Milestone 5's plumbing (`dnfw.waverider.coldfire`,
`docs/machine-list.md`, "What a sixth machine actually cost"), for type 7 instead of
5. **Every site and stock byte is imported from `dnfw.waverider.coldfire`**, so the
measurements stay in one place. What is written here, and why it is not shared:

- **the shims**, Waverider's own, with the type 7. Upstream builds them as f-strings
  over its module's `NEW_TYPE`, so they cannot be reused without changing upstream's
  module; the text is Waverider's, line for line, and diverges only in the constant;
- **rows 5 and 6**: the bus raises every machine bound to the total (`dnfw.mods.bus`,
  `MACH`), and Bloom adds three types (5, 6 and 7) so that it can be 7. Rows 5 and 6
  are **FM Tone's** names and attributes, and they are never offered by MACHINE SEL,
  so a stray 5 or 6 reads as FM Tone wherever it appears;
- **the LOAD shim**, new: a stored-sound bound of 9 keeps -1..7, which would let a
  Waverider sound (type 5) load into a Bloom build as the half-defined type 5. The
  `andl %d1,%d0 ; moveb %d0,%a2@(222)` at `0x400dd2c0` (the type, or 0) becomes a
  `jsr` to a shim that does the same and sends 5 and 6 to 0, FM Tone, as stock would.

**What B2 does not do:** Bloom's own pages (B4), and anything on the DSP. Until B3, the
DSP's lookup `0x25d748[7]` is stock 0, so a Bloom track renders as FM Tone with
WaveTone's parameters. The machine is offered, kept and saved; it does not yet sound
like Bloom.

Pure: `compose(stock, assemble)` takes the stock MAIN OS and an assembler
(`dnfw.patch.assemble.assemble`) and returns the edits. Every edit carries the stock
bytes it replaces, and every cave must be zero with a 4-byte margin. The caves are
Waverider's: the two mods exclude each other, and the matrix refuses the pair on
their overlapping bytes.
"""

from __future__ import annotations

import struct

from ..waverider import coldfire as W
from ..waverider import drive as WD

BASE = W.BASE
NEW_TYPE = 7
CLONE = 1                               # WaveTone, for the UI
PLACEHOLDER = 0                         # FM Tone: rows 5 and 6, and what LOAD makes of them
ADDED = NEW_TYPE + 1 - 5                # the bus's machine count: types 5, 6 and 7
LONG_NAME, SHORT_NAME = "Bloom", "BLM"

LIST_NEW = (0, 2, 1, 3, NEW_TYPE, 4)    # Bloom after Swarmer, before MIDI's divider
SECTION_GROUP = 3                       # Bloom's section of MACHINE SEL: types 5..7
SECTION_LAST = NEW_TYPE

# The stored-sound LOAD, read 2026-10-21 (objdump, stock 1.11):
#   0x400dd2ae  moveb %a3@(244),%d0   the stored type
#   0x400dd2b2  movel %d0,%d1 ; addql #1,%d1 ; mvzb %d1,%d1
#   0x400dd2b8  cmpl %d1,%d2 ; shi %d1    d1 = 0xff if the bound > type + 1, else 0
#   0x400dd2bc  moveb #7,%d2              (the next field's bound: kept)
#   0x400dd2c0  andl %d1,%d0              the type, or 0
#   0x400dd2c2  moveb %d0,%a2@(222)       -> sound+0xDE
#   0x400dd2c6  moveb %a3@(245),%d0       the next field: d1 is reloaded from d0
LOAD_STORE = 0x400DD2C0
LOAD_STORE_STOCK = bytes.fromhex("c0811540" "00de")
LOAD_GUARDS = (
    (0x400DD2AE, "102b00f4", "the LOAD reads the stored type at +244"),
    (0x400DD2B8, "b48152c1", "... compares type + 1 with the bound into d1"),
    (0x400DD2C6, "102b00f5", "... and goes on to the next field, reloading d1 from d0"),
)

GROUP_SOURCE = f"""
| group(type) at {W.GROUP_FN:#010x}: Waverider's (dnfw.waverider.coldfire), with Bloom's
| section: the synths 0..3 -> 1, MIDI (4) -> 2, types 5..{SECTION_LAST} -> {SECTION_GROUP}, else 0.
| Every branch follows the instruction that set its flags.
    move.l  %sp@(4),%d1
    blt.s   0f
    moveq   #1,%d0
    subq.l  #4,%d1
    bcs.s   9f
    moveq   #2,%d0
    tst.l   %d1
    beq.s   9f
    moveq   #{SECTION_GROUP},%d0
    subq.l  #{SECTION_LAST - 4},%d1
    bls.s   9f
0:  moveq   #0,%d0
9:  rts
"""

SHIMS = f"""
| Waverider's five shims (dnfw.waverider.coldfire.SHIMS), with type {NEW_TYPE}.
slot_shim:
    move.l  %sp@(12),%d0
    movea.l %sp@(16),%a1
    moveq   #{NEW_TYPE},%d2
    cmp.l   %d0,%d2
    bne.s   1f
    moveq   #{CLONE},%d0
1:  jmp     {W.SLOT_RESUME:#010x}

canon_arg:
    move.l  %sp@(8),%d0
    moveq   #{NEW_TYPE},%d1
    cmp.l   %d0,%d1
    bne.s   1f
    moveq   #{CLONE},%d0
1:  moveq   #4,%d1
    rts

canon_page:
    move.l  %sp@(12),%d1
    move.l  %sp@(16),%d0
    subq.l  #{NEW_TYPE},%d1
    bne.s   1f
    moveq   #{CLONE},%d1
    rts
1:  addq.l  #{NEW_TYPE},%d1
    rts

canon_track:
    mvs.b   %a0@(222),%d0
    moveq   #{NEW_TYPE},%d1
    cmp.l   %d0,%d1
    bne.s   1f
    moveq   #{CLONE},%d0
1:  jmp     {W.TRACK_TYPE_EXIT:#010x}

raw_track:
    move.l  %a2,%sp@-
    movea.l %sp@(8),%a2
    movea.l %a2@,%a0
    move.l  %a2,%sp@-
    movea.l %a0@(40),%a0
    jsr     %a0@
    addq.l  #4,%sp
    tst.l   %d0
    beq.s   1f
    movea.l %d0,%a0
    mvs.b   %a0@(222),%d0
    bra.s   2f
1:  moveq   #-1,%d0
2:  movea.l %sp@+,%a2
    rts
"""
SHIM_LABELS = ("slot_shim", "canon_arg", "canon_page", "canon_track", "raw_track")

SHIMS2 = f"""
| Waverider's ownership shim (SHIMS2), with type {NEW_TYPE}.
canon_valid:
    mvs.b   %a0@(222),%d3
    moveq   #{NEW_TYPE},%d0
    cmp.l   %d3,%d0
    bne.s   1f
    moveq   #{CLONE},%d3
1:  movea.l %sp@+,%a1
    move.l  %d2,%sp@-
    jmp     %a1@

| The stored-sound LOAD, from {LOAD_STORE:#010x} by jsr: the stock `andl %d1,%d0` (the
| type, or 0), then 5 and 6 to {PLACEHOLDER} (FM Tone), then the stock store at sound+0xDE.
| d1 is free: the LOAD reloads it from d0 for the next field. d0 is 0..255 here.
load_type:
    and.l   %d1,%d0
    moveq   #5,%d1
    cmp.l   %d1,%d0
    bcs.s   1f
    moveq   #6,%d1
    cmp.l   %d1,%d0
    bhi.s   1f
    moveq   #{PLACEHOLDER},%d0
1:  move.b  %d0,%a2@(222)
    rts
"""
SHIM2_LABELS = ("canon_valid", "load_type")

Edit = W.Edit
ComposeError = W.ComposeError
_read, _need, _long, _cave_free = W._read, W._need, W._long, W._cave_free


def group_function(assemble) -> bytes:
    code = assemble(GROUP_SOURCE, base=W.GROUP_FN)
    if len(code) > len(W.GROUP_STOCK):
        raise ComposeError(f"the group function grew: {len(code)} > {len(W.GROUP_STOCK)}")
    return code + bytes(len(W.GROUP_STOCK) - len(code))


def _blob(assemble, source: str, labels: tuple[str, ...], base: int) -> tuple[bytes, dict]:
    table = "\n    .align 2\n" + "\n".join(f"    .long {n}" for n in labels) + "\n"
    blob = assemble(source + table, base=base)
    code = blob[:-4 * len(labels)]
    return code, dict(zip(labels, struct.unpack(f">{len(labels)}I", blob[-4 * len(labels):])))


def compose(stock: bytes, assemble) -> dict:
    """-> {"content", "edits", "layout"}. ASSEMBLE(source, base=...) -> bytes."""
    content = bytearray(stock)
    for va, want, why in W.GUARDS + LOAD_GUARDS:
        _need(content, va, bytes.fromhex(want), why)
    edits: list[Edit] = []

    def edit(va: int, new: bytes, what: str, stock_bytes: bytes | None = None) -> None:
        old = _read(content, va, len(new)) if stock_bytes is None else stock_bytes
        _need(content, va, old, what)
        content[va - BASE:va - BASE + len(new)] = new
        edits.append(Edit(va, old, new, what))

    for cave in (W.CODE_CAVE, W.DATA_CAVE, W.NAME_CAVE):
        _cave_free(content, cave)

    # the code cave: the five machine shims
    shim, layout = _blob(assemble, SHIMS, SHIM_LABELS, W.CODE_CAVE[0])
    if len(shim) > W.CODE_CAVE[1]:
        raise ComposeError(f"the code cave overflows: {len(shim)} > {W.CODE_CAVE[1]}")
    edit(W.CODE_CAVE[0], shim, f"the shims: type {NEW_TYPE} resolves as WaveTone in slot_to_id, "
                               "the SYN page tables and getMachineType; the real type for identity")

    # the name cave: the two names, the ownership and LOAD shims, the MACHINE SEL list
    names = LONG_NAME.encode("ascii") + b"\0" + SHORT_NAME.encode("ascii") + b"\0"
    names += bytes(-len(names) % 4)
    layout["long_name"] = W.NAME_CAVE[0]
    layout["short_name"] = W.NAME_CAVE[0] + len(LONG_NAME) + 1
    shim2, l2 = _blob(assemble, SHIMS2, SHIM2_LABELS, W.NAME_CAVE[0] + len(names))
    layout.update(l2)
    blob = names + shim2 + bytes(-len(shim2) % 4)
    layout["list"] = W.NAME_CAVE[0] + len(blob)
    blob += b"".join(_long(t) for t in LIST_NEW)
    if len(blob) > W.NAME_CAVE[1]:
        raise ComposeError(f"the name cave overflows: {len(blob)} > {W.NAME_CAVE[1]}")
    edit(W.NAME_CAVE[0], blob, f"Bloom's names ({LONG_NAME!r}, {SHORT_NAME!r}), the ownership "
                               "and LOAD shims, the six-entry MACHINE SEL list")

    # the data cave: eight name rows and eight attribute rows (5, 6 FM Tone's; 7 Bloom's)
    _need(content, W.LIST_STOCK_VA, b"".join(_long(t) for t in W.LIST_STOCK), "the MACHINE SEL list")
    names_rows = _read(content, W.NAMES_STOCK_VA, W.NAME_ROW * 5)
    attr_rows = _read(content, W.ATTR_STOCK_VA, W.ATTR_ROW * 5)

    def row(rows: bytes, size: int, t: int) -> bytes:
        return rows[size * t:size * (t + 1)]

    layout["names"] = W.DATA_CAVE[0]
    layout["attributes"] = layout["names"] + W.NAME_ROW * (NEW_TYPE + 1)
    bloom_names = _long(layout["long_name"]) + _long(layout["short_name"]) + _long(0)
    data = (names_rows + row(names_rows, W.NAME_ROW, PLACEHOLDER) * 2 + bloom_names
            + attr_rows + row(attr_rows, W.ATTR_ROW, PLACEHOLDER) * 2
            + row(attr_rows, W.ATTR_ROW, CLONE))
    if len(data) > W.DATA_CAVE[1]:
        raise ComposeError(f"the data cave overflows: {len(data)} > {W.DATA_CAVE[1]}")
    edit(W.DATA_CAVE[0], data, "Bloom's data: eight name rows and eight attribute rows "
                               "(5 and 6 FM Tone's placeholders, 7 Bloom's with WaveTone's attributes)")

    # 1. the MACHINE SEL list and its sections
    n = len(LIST_NEW)
    edit(W.LIST_ALLOC, bytes.fromhex("4878") + struct.pack(">H", 4 * n),
         f"MACHINE SEL list: storage for {n} longs", bytes.fromhex("48780014"))
    edit(W.LIST_END, bytes.fromhex("4879") + _long(layout["list"] + 4 * n),
         "MACHINE SEL list: the copy's end", bytes.fromhex("4879") + _long(W.LIST_STOCK_VA + 20))
    edit(W.LIST_CAP, bytes.fromhex("41e8") + struct.pack(">H", 4 * n),
         f"MACHINE SEL list: the vector's capacity, {n} longs", bytes.fromhex("41e80014"))
    edit(W.LIST_BEGIN, bytes.fromhex("4879") + _long(layout["list"]),
         "MACHINE SEL list: the copy's start", bytes.fromhex("4879") + _long(W.LIST_STOCK_VA))
    edit(W.GROUP_FN, group_function(assemble),
         f"the MACHINE SEL group: Bloom ({NEW_TYPE}) a section of its own, divided off like MIDI",
         W.GROUP_STOCK)

    # 2. the names; 3. the attribute rows. Their bounds are the bus's machine count.
    for bound, base, op, col in W.NAME_SITES:
        _need(content, bound, bytes.fromhex("7204"), f"name column {col // 4}: the bound")
        edit(base + 2, _long(layout["names"] + col), f"name column {col // 4}: the eight-row table",
             _long(W.NAMES_STOCK_VA + col))
        _need(content, base, bytes.fromhex(op), "the name accessor's base instruction")
    for bound in W.ATTR_BOUNDS:
        _need(content, bound, bytes.fromhex("7404" if bound == 0x400DC19C else "7204"),
              "attribute rows: the bound")
    for site, col in W.ATTR_BASES:
        _need(content, site, bytes.fromhex("41f9"), "the attribute accessor's lea")
        edit(site + 2, _long(layout["attributes"] + col), "attribute rows: the eight-row copy",
             _long(W.ATTR_STOCK_VA + col))

    # 5. the stored-sound LOAD: the bound is the bus's (-1..7 kept); 5 and 6 -> FM Tone here
    _need(content, W.LOAD_BOUND, bytes.fromhex("7406"), "stored-sound LOAD: the bound")
    edit(LOAD_STORE, bytes.fromhex("4eb9") + _long(layout["load_type"]),
         "stored-sound LOAD: keep 7, send 5 and 6 to FM Tone, then store the type",
         LOAD_STORE_STOCK)

    # 4. slot_to_id
    edit(W.SLOT_HOOK, bytes.fromhex("4ef9") + _long(layout["slot_shim"]) + bytes.fromhex("4e71"),
         "param_set_slot_to_id: detour to the shim", W.SLOT_HOOK_STOCK)

    # 6. the SYN page tables: type 7 reads WaveTone's rows (Bloom's own pages are B4)
    for site, what in W.CANON_ARG_SITES + ((W.COUNT_SITE, "SYN page count(type)"),):
        edit(site, bytes.fromhex("4eb9") + _long(layout["canon_arg"]),
             f"{what}: type {NEW_TYPE} reads WaveTone's row", W.CANON_ARG_STOCK)
    _need(content, W.PAGE_SITE - 4, bytes.fromhex("2f027404"), "0x400c24ee's push of d2 and its bound")
    edit(W.PAGE_SITE, bytes.fromhex("4eb9") + _long(layout["canon_page"]) + bytes.fromhex("4e71"),
         f"SYN page(type, n): type {NEW_TYPE} reads WaveTone's pages", W.PAGE_STOCK)

    # 7. getMachineType(track): WaveTone for the UI, the real type where it is identity
    _need(content, W.TRACK_TYPE_FN, W.TRACK_TYPE_FN_STOCK, "getMachineType(track), as raw_track copies it")
    edit(W.TRACK_TYPE_READ, bytes.fromhex("4ef9") + _long(layout["canon_track"]),
         f"getMachineType(track): type {NEW_TYPE} is reported as WaveTone", W.TRACK_TYPE_READ_STOCK)
    for op_va, op, what in W.IDENTITY_SITES + ((WD.CLEAR_SITE, "4eb9", "CLEAR TRK PRESET (TRK + PLAY)"),):
        _need(content, op_va, bytes.fromhex(op), f"{what}: the instruction")
        edit(op_va + 2, _long(layout["raw_track"]), f"{what}: asks for the real type",
             _long(W.TRACK_TYPE_FN))

    # 7b. getMachineType(model, track): the real type, for MACHINE SEL and the re-commits
    _need(content, W.MODEL_TRACK_TYPE_JMP, bytes.fromhex("4ef9"), "0x4003134e's tail jump")
    edit(W.MODEL_TRACK_TYPE_JMP + 2, _long(layout["raw_track"]),
         "getMachineType(model, track) 0x4003134e: the real type (MACHINE SEL's marker and "
         "cursor, the track swap, the machine restores)", _long(W.TRACK_TYPE_FN))

    # 8. the sound's "is this parameter mine?"
    _need(content, W.VALID_SITE + len(W.VALID_STOCK), W.VALID_NEXT, "the ownership test's record-page call")
    edit(W.VALID_SITE, bytes.fromhex("4eb9") + _long(layout["canon_valid"]),
         f"the sound's parameter-ownership test: type {NEW_TYPE} owns WaveTone's machine parameters",
         W.VALID_STOCK)

    return {"content": bytes(content), "edits": edits, "layout": layout}
