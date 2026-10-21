"""Note events decoded from the frames sent to the DSP."""

import struct

from dnfw import seqframes as SF


def capture(icount, on=0, off=0, notes=()):
    frame = bytearray(48)
    for voice, note in enumerate(notes):
        struct.pack_into(">H", frame, 2 + 2 * voice, int(note * 256))
    struct.pack_into(">4H", frame, 34, on, off, on, off)
    return {"icount": icount, "hex": frame.hex()}


def test_a_mask_held_over_two_frames_is_one_event():
    caps = [capture(0), capture(10, on=1), capture(20, on=1), capture(30, off=1), capture(40)]
    found = SF.events(caps)
    assert [(e.icount, e.kind, e.voices) for e in found] == [(10, "on", (0,)), (30, "off", (0,))]


def test_the_same_voice_twice_in_a_row_needs_a_gap_frame():
    caps = [capture(0, on=2), capture(5), capture(9, on=2)]
    assert [e.icount for e in SF.note_ons(SF.events(caps))] == [0, 9]


def test_unison_sets_several_voice_bits():
    assert SF.events([capture(1, on=0x8003)])[0].voices == (0, 1, 15)


def test_step_period_and_tempo():
    caps = []
    for k in range(4):
        caps += [capture(k * 66_000_000, on=1 << k), capture(k * 66_000_000 + 1000)]
    found = SF.events(caps)
    per_step = SF.step_period(found, 4)
    assert per_step == 16_500_000
    assert round(SF.bpm(per_step), 1) == 120.0


def test_short_captures_are_skipped():
    assert SF.events([{"icount": 0, "hex": "00" * 10}]) == []


def test_the_note_is_read_from_each_voice_word_at_the_note_on():
    caps = [capture(0, on=0b101, notes=(60, 0, 64.5)), capture(9, off=0b101, notes=(60, 0, 64.5))]
    found = SF.events(caps)
    assert found[0].notes == (60.0, 64.5)
    assert found[1].notes == ()
