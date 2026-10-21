"""The Bloom mod, milestone B2 (`docs/bloom-machine.md`): machine type 7 on the ColdFire.

It applies to stock 1.11, and the shipped `bloom_code.json` still reproduces the compose
it was generated from. What the data means is asserted:
- the list offers 7 after Swarmer and before MIDI;
- rows 5 and 6 are FM Tone's, and row 7 names Bloom;
- the bus raises the machine bounds by three;
- the stored-sound LOAD calls the shim that sends 5 and 6 to FM Tone.

The behavioural evidence (a boot from reset, the engine and the machine-type
SAVE/LOAD) is the emulator's, not this file's.
"""

import pathlib
import struct

import pytest

from dnfw.bloom import coldfire as CF
from dnfw.mods import ModError, bloom, bus, platform, waverider

ROOT = pathlib.Path(__file__).resolve().parent.parent
STOCK_111 = ROOT / "00_Resources/00_Firmware/Digitone_II_OS1.11_dist.zip"
BASE = bloom.BASE


@pytest.fixture(scope="module")
def dn2_111():
    if not STOCK_111.exists():
        pytest.skip("Digitone II 1.11 is not in 00_Resources")
    from dnfw.cli.files import read_image
    from dnfw.firmware.load import load
    return load(read_image(STOCK_111))


@pytest.fixture(scope="module")
def stock(dn2_111):
    return dn2_111.container.find(3).unpack()


@pytest.fixture(scope="module")
def applied(dn2_111):
    return bloom.apply(dn2_111).payloads[3]


def at(content: bytes, va: int, n: int) -> bytes:
    return bytes(content[va - BASE:va - BASE + n])


def long(content: bytes, va: int) -> int:
    return struct.unpack(">I", at(content, va, 4))[0]


def test_the_spec_is_type_7_with_three_added_types():
    assert bloom.SPEC["new_type"] == CF.NEW_TYPE == 7
    assert bloom.SPEC["added_machine_types"] == CF.ADDED == 3
    assert bloom.SPEC["names"] == ["Bloom", "BLM"]


def test_the_shipped_spec_reproduces_the_compose(stock):
    from dnfw.patch.assemble import assemble, available
    if not available():
        pytest.skip("no m68k assembler")
    built = CF.compose(stock, assemble)
    got = sorted((e.to_json() for e in built["edits"]), key=lambda e: e["va"])
    assert got == bloom.SPEC["edits"]
    assert {k: v for k, v in sorted(built["layout"].items())} == bloom.SPEC["layout"]


def test_machine_sel_offers_bloom_after_swarmer(applied):
    lay = bloom.SPEC["layout"]
    listed = struct.unpack(">6I", at(applied, lay["list"], 24))
    assert listed == (0, 2, 1, 3, 7, 4)


def test_rows_5_and_6_are_fm_tone_and_7_is_bloom(stock, applied):
    lay = bloom.SPEC["layout"]
    names, row = lay["names"], 12
    fm = at(stock, 0x401F77F4, row)
    assert at(applied, names + 5 * row, row) == fm
    assert at(applied, names + 6 * row, row) == fm
    long_ptr, short_ptr = long(applied, names + 7 * row), long(applied, names + 7 * row + 4)
    assert at(applied, long_ptr, 6) == b"Bloom\0" and at(applied, short_ptr, 4) == b"BLM\0"
    attrs = lay["attributes"]
    assert at(applied, attrs + 7 * 4, 4) == at(stock, 0x401F7930 + 4, 4)      # WaveTone's
    assert at(applied, attrs + 5 * 4, 4) == at(stock, 0x401F7930, 4)          # FM Tone's


def test_the_bus_raises_every_machine_bound_by_three(applied):
    for va, _, stock_value, what in bus.MACHINE_BOUNDS:
        assert applied[va - BASE] == stock_value + 3, what


def test_the_load_calls_the_shim_that_sends_5_and_6_to_fm_tone(applied):
    lay = bloom.SPEC["layout"]
    assert at(applied, CF.LOAD_STORE, 6) == bytes.fromhex("4eb9") + struct.pack(">I", lay["load_type"])
    shim = at(applied, lay["load_type"], 22)
    assert shim.startswith(bytes.fromhex("c081"))            # the stock `andl %d1,%d0` first
    assert shim.endswith(bytes.fromhex("154000de4e75"))      # the stock store, then rts


def test_bloom_and_waverider_exclude_each_other():
    overlap = [(a, b) for a in bloom.extents() for b in waverider.extents()
               if a.section == b.section == 3
               and a.start < b.start + b.length and b.start < a.start + a.length]
    assert overlap, "the two share Waverider's caves, so the matrix must refuse the pair"


def test_a_modified_image_is_refused(dn2_111):
    content = bytearray(dn2_111.container.find(3).unpack())
    g = bloom.SPEC["guards"][0]
    content[g["va"] - BASE] ^= 0xFF
    with pytest.raises(ModError, match="not stock"):
        bloom._main_os(platform.split(bytes(content))[0])
