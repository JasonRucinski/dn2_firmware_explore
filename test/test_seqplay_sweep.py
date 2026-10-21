"""The sweep's comparison: kind, voices and notes exact, time within a tolerance."""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))

import emu_seqplay_sweep as S

BASE = [(0, "on", (0,), (60.0,)), (16_544_000, "off", (0,), ())]


def test_a_few_instructions_of_jitter_is_inside_the_tolerance():
    mine = [(0, "on", (0,), (60.0,)), (16_544_018, "off", (0,), ())]
    assert S.first_difference(BASE, mine, 1000) is None
    assert S.first_difference(BASE, mine, 0) is not None
    assert S.worst_offset(BASE, mine) == 18


def test_a_different_voice_or_note_is_a_difference_at_any_tolerance():
    assert S.first_difference(BASE, [(0, "on", (1,), (60.0,)), BASE[1]], 10**9)
    assert S.first_difference(BASE, [(0, "on", (0,), (61.0,)), BASE[1]], 10**9)


def test_a_missing_event_is_a_difference():
    assert "1 events" in S.first_difference(BASE, BASE[:1], 1000)
