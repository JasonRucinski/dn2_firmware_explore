"""The clock PULSE runs on: the song position and the tempo the frame carries.

Both are measured upstream (angellinares/dn2_firmware_explore `5be76c1`,
`docs/waverider-m10-move.md`, M10b-2, and `docs/waverider-frame-words.md`):

- **the position**, in frame bytes 2644..2647: 2^32 is 384 sixteenths (24 bars),
  the least common multiple of every straight, dotted and triplet length, so a
  note length's phase is the position times a whole number and is exact in 32 bits;
- **the tempo**, at frame `+0xd8`, as BPM x 120.

PULSE's time base is beats (quarter notes) when SYNC is on, and seconds when it is
off. This module converts between them and nothing else.
"""

from __future__ import annotations

POSITION_SPAN = 1 << 32            # one wrap of the frame's position word
SIXTEENTHS_PER_WRAP = 384          # 24 bars of 4/4
BEATS_PER_WRAP = SIXTEENTHS_PER_WRAP // 4
TEMPO_SCALE = 120                  # the frame's tempo word is BPM x 120


def beats_from_position(word: int) -> float:
    """The frame's 32-bit position word, as beats since the wrap began."""
    return (word % POSITION_SPAN) * BEATS_PER_WRAP / POSITION_SPAN


def position_from_beats(beats: float) -> int:
    """The inverse: the position word the ColdFire would write at `beats`."""
    return int(round(beats * POSITION_SPAN / BEATS_PER_WRAP)) % POSITION_SPAN


def bpm_from_tempo_word(word: int) -> float:
    return word / TEMPO_SCALE


def seconds_per_beat(bpm: float) -> float:
    if bpm <= 0:
        raise ValueError(f"tempo must be positive, not {bpm}")
    return 60.0 / bpm


# Note lengths PULSE offers with SYNC on, as cycles per beat. Straight, dotted and
# triplet, 1/64 to 4 bars: every one divides the position's 384-sixteenth span.
NOTE_LENGTHS = {
    "4 bars": 1 / 16, "2 bars": 1 / 8, "1 bar": 1 / 4, "1/2": 1 / 2, "1/4": 1.0,
    "1/8": 2.0, "1/16": 4.0, "1/32": 8.0, "1/64": 16.0,
    "1/2.": 1 / 3, "1/4.": 2 / 3, "1/8.": 4 / 3, "1/16.": 8 / 3,
    "1/2T": 3 / 4, "1/4T": 3 / 2, "1/8T": 3.0, "1/16T": 6.0, "1/32T": 12.0,
}


def note_rate(name: str) -> float:
    """A note length's rate in cycles per beat."""
    try:
        return NOTE_LENGTHS[name]
    except KeyError:
        raise ValueError(f"unknown note length {name!r}; one of {', '.join(NOTE_LENGTHS)}") from None
