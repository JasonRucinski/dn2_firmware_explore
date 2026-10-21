"""dnfw.bloom.dsp: milestone B3a's section-7 builder.

The runner gate is scripts/sharc_bloom_b3a.py; these need no runner, no assembler and
no firmware beyond the DN2 1.11 image (skipped cleanly when it is absent).
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import re
import struct

import pytest

from dnfw.bloom import dsp, live
from dnfw.image import bootstream
from dnfw.waverider import dsp as W

ROOT = pathlib.Path(__file__).resolve().parents[1]
IMAGE = ROOT / "00_Resources" / "00_Firmware" / "Digitone_II_OS1.11_dist.zip"
SRC = ROOT / "csrc" / "bloom" / "sharc" / "bloom_loop.asm"
PULSE_SRC = ROOT / "csrc" / "bloom" / "sharc" / "pulse.asm"


@pytest.fixture(scope="module")
def stock7() -> bytes:
    if not IMAGE.exists():
        pytest.skip(f"{IMAGE.name} not present")
    from dnfw.cli.files import read_image
    from dnfw.firmware.load import load
    sec = load(read_image(IMAGE)).container.find(7)
    return sec.unpack() or sec.raw_payload


@pytest.fixture(scope="module")
def built(stock7) -> bytes:
    return dsp.section7(stock7)


def test_committed_loop_matches_its_source():
    spec = json.loads(dsp.CODE.read_text(encoding="utf-8"))
    src = SRC.read_bytes().replace(b"\r\n", b"\n")
    assert spec["loop"]["source_sha256"] == hashlib.sha256(src).hexdigest()
    assert spec["loop"]["load_sw"] == hex(dsp.LOOP_SW)
    assert spec["entry_jump"]["source"] == f"JUMP {dsp.LOOP_SW:#x};"
    assert spec["entry_jump"]["object_parcels_be"] == f"063e00{dsp.LOOP_SW:06x}"
    psrc = PULSE_SRC.read_bytes().replace(b"\r\n", b"\n")
    assert spec["pulse"]["source_sha256"] == hashlib.sha256(psrc).hexdigest()
    assert spec["pulse"]["load_sw"] == hex(dsp.PULSE_SW)
    assert spec["pulse_jump"]["object_parcels_be"] == f"063e00{dsp.PULSE_SW:06x}"
    assert spec["pulse_jump"]["at_sw"] == hex(dsp.CALL_SITE_SW)


def _code(path):
    code = [ln.split("//", 1)[0].strip() for ln in path.read_text(encoding="utf-8").splitlines()]
    return [ln for ln in code if ln and not ln.startswith(".")]


@pytest.mark.parametrize("path", [SRC, PULSE_SRC], ids=["loop", "pulse"])
def test_sources_keep_the_shipped_forms(path):
    """No hardware DO loop, no M0-M3 in an access, no float result in F0."""
    code = _code(path)
    assert not any(re.match(r"(?i)^(LCNTR|DO\b)", ln) for ln in code)
    assert not any(re.search(r"(?i)DM\([^)]*\bM[0-3]\b", ln) for ln in code)
    assert not any(re.match(r"(?i)^F0\s*=", ln) for ln in code)


def test_the_ways_back():
    """The loop re-runs the two instructions its JUMP replaced and resumes at 0x1c944c;
    pulse.asm re-runs the displaced `r4 = 0x268438` and jumps back to the call."""
    tail = _code(SRC)[-3:]
    assert tail[0] == "I5 = DM(-24, I6);" and tail[1] == "R10 = DM(-34, I6);"
    assert tail[2] == f"JUMP {dsp.RESUME_SW:#x};"
    tail = _code(PULSE_SRC)[-2:]
    assert tail == ["R4 = 0x268438;", f"JUMP {dsp.CALL_RESUME_SW:#x};"]


def test_pulse_constants_are_live_constants():
    text = PULSE_SRC.read_text(encoding="utf-8")
    bits = lambda x: f"{struct.unpack('<I', struct.pack('<f', x))[0]:#010x}"   # noqa: E731
    for value in (live.PULSE_STEP0, live.PULSE_STEP1, live.PULSE_RATIO, live.PULSE_DEPTH):
        assert bits(value) in text
    assert f"R3 = {live.PULSE_BLOCKS};" in text and f"{live.FREQ_MAX:#x}" in text


def test_spans_stay_in_waverider_region_and_write_it_end_to_end():
    sp = sorted(dsp.spans(), key=lambda s: s[1])
    assert sp[0][1] == W.dm_to_load(W.REGION[0])
    for (_, a, pa), (_, b, _) in zip(sp, sp[1:]):
        assert a + len(pa) == b                     # contiguous: no byte left unwritten
    end = sp[-1][1] + len(sp[-1][2])
    assert end == W.dm_to_load(dsp.PULSE_END) <= W.dm_to_load(W.REGION[1])
    assert sp[-3][1] + len(sp[-3][2]) == W.dm_to_load(dsp.TABLES_END)
    plain = dsp.spans(pulse=False)
    assert len(plain) == len(sp) - 2


def test_tables_are_live_tables():
    by = {what.split(",")[0]: (at, p) for what, at, p in dsp.spans()}
    at, p = by["DT"]
    assert at == W.dm_to_load(dsp.DT_DM)
    assert list(struct.unpack_from(f"<{live.NOTES}f", p)) == live.dt_table()
    at, p = by["INV"]
    assert list(struct.unpack_from(f"<{live.NOTES}f", p)) == live.inv_table()


def test_section7_patches(stock7, built):
    obj = dsp.objects()
    assert bootstream.read_span(built, W.sw_to_load(dsp.ENTRY_SW), 8) == obj["entry_jump"] + W.NOP16
    lookup = struct.unpack("<8I", bootstream.read_span(built, W.dm_to_load(dsp.LOOKUP_DM), 32))
    assert lookup == (0, 1, 2, 3, 4, 0, 0, 7)
    for _, at, payload in dsp.spans():
        assert bootstream.read_span(built, at, len(payload)) == payload
    assert bootstream.read_span(built, W.sw_to_load(dsp.CALL_SITE_SW), 6) == obj["pulse_jump"]
    walked = bootstream.walk(built)
    assert walked.complete and walked.stopped_at == len(built)
    assert len(built) <= W.STREAM_LIMIT


def test_section7_refuses_non_stock(stock7):
    with pytest.raises(dsp.DspError):
        dsp.section7(stock7[:-1] + bytes([stock7[-1] ^ 1]))


def test_section7_without_pulse_keeps_the_call_site(stock7):
    plain = dsp.section7(stock7, pulse=False)
    assert bootstream.read_span(plain, W.sw_to_load(dsp.CALL_SITE_SW), 6) == dsp.CALL_SITE_STOCK
