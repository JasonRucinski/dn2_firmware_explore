"""Bloom B1's harness (`scripts/sharc_bloom_b1.py`): what can be checked without the
runner or an OS image. The run itself needs both, and reports to out/bloom/."""

import struct
import sys
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

b1 = pytest.importorskip("sharc_bloom_b1")


def test_the_field_written_is_freq_as_the_unpack_lays_it_out():
    from dnfw.waverider import frame as FR
    assert FR.RECORD_FIELDS[67] == (0x1CC, "u", "FREQ")
    assert b1.FREQ_OFFSET == 0x1CC


def test_record_bits_match_the_unpacks_u_scaling():
    for word in (0x7F00, 0x2000, 0):
        assert struct.unpack("<f", struct.pack("<I", b1.record_bits(word)))[0] == pytest.approx(word / 32768)
    assert b1.record_bits(0x7F00) == 0x3F7E0000


def test_the_comparison_is_relative_rms():
    assert b1.rel([1.0, -1.0], [1.0, -1.0]) == 0.0
    assert b1.rel([0.0, 0.0], [1.0, -1.0]) == pytest.approx(1.0)


def test_it_refuses_to_run_without_the_image(tmp_path):
    with pytest.raises(SystemExit, match="OS 1.11"):
        b1.main(["--image", str(tmp_path / "missing.zip"), "--digikit", str(tmp_path)])
