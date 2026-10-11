"""Note events in the frames the ColdFire sends the DSP: when each voice was triggered.

The frame at `0x80005e60` carries four u16 voice masks at bytes 34..41
(docs/drive-load-command.md, "The trigger masks are one-frame events"): +34 note-on,
+36 note-off, +38 and +40 repeat them. A note-on or note-off can sit in the mask for two
frames, so consecutive frames carrying the same non-zero mask are one event.

`panel_drive --capture 0x400cf7be:1:48` keeps those bytes on every send; this module turns the
captures into events and measures the step period from them. It does no I/O.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass

NOTE_ON, NOTE_OFF = 34, 36
CPU_HZ = 132_000_000          # the clock panel_drive's SSI lane paces against (--ssi-hz)


@dataclass(frozen=True)
class NoteEvent:
    icount: int
    kind: str                 # "on" or "off"
    voices: tuple[int, ...]   # voice numbers whose bit is set


def _voices(mask: int) -> tuple[int, ...]:
    return tuple(v for v in range(16) if mask >> v & 1)


def events(captures: list[dict]) -> list[NoteEvent]:
    """Each capture is panel_drive's {"icount", "hex"}; frames come in send order."""
    out: list[NoteEvent] = []
    previous = {"on": 0, "off": 0}
    for capture in captures:
        frame = bytes.fromhex(capture["hex"])
        if len(frame) < NOTE_OFF + 2:
            continue
        masks = {
            "on": struct.unpack_from(">H", frame, NOTE_ON)[0],
            "off": struct.unpack_from(">H", frame, NOTE_OFF)[0],
        }
        for kind, mask in masks.items():
            if mask and mask != previous[kind]:
                out.append(NoteEvent(capture["icount"], kind, _voices(mask)))
            previous[kind] = mask
    return out


def note_ons(found: list[NoteEvent]) -> list[NoteEvent]:
    return [e for e in found if e.kind == "on"]


def seconds(icount_delta: int) -> float:
    return icount_delta / CPU_HZ


def gaps(found: list[NoteEvent]) -> list[int]:
    """Instructions between consecutive note-ons."""
    ons = note_ons(found)
    return [b.icount - a.icount for a, b in zip(ons, ons[1:])]


def step_period(found: list[NoteEvent], steps_between: int) -> float | None:
    """Mean instructions per step, when the note-ons are `steps_between` steps apart."""
    spacing = gaps(found)
    if not spacing or steps_between <= 0:
        return None
    return sum(spacing) / len(spacing) / steps_between


def bpm(instructions_per_step: float) -> float:
    """Tempo from one step: the sequencer's step is a sixteenth, four to the beat."""
    return 60.0 / (seconds(1) * instructions_per_step * 4)
