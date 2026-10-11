# The sequencer in the emulator (2026-10-11)

`scripts/emu_seqplay.py BUILD.syx` plays track 1 headless and lists the notes the ColdFire
sends the DSP, with their times. It makes sequencer, arpeggiator and LFO timing checks possible
without the unit.

## What it needed

The internal step clock is two interrupts the firmware forces itself through INTC0's INTFRCH
(`0xFC048010`), so nothing calls it and a call-graph search finds nothing:

| stage | where | what it does |
|---|---|---|
| audio ISR | `0x40025e36`, path `0x40027aba` | each frame subtracts `2 x [0x402a0dec]` from `0x800053a0`; at zero sets bit 12 |
| source 44 | vector 108, level 5, handler `0x400d7864` | clears bit 12, re-arms, sets bit 25 |
| source 57 | vector 121, level 2, handler `0x400d987a` | the engine; the step count `0x4463ed14` goes up at `0x400da54c` |

`0x400d97ce`, which every earlier search followed, is a different small function. The Rust
emulator kept INTFRC as RAM and delivered only PIT, DTIM and SSI vectors; digikit PR #65 adds
`service_forced`, on the `--ssi-hz` lane.

## How it runs

1. `panel_drive BUILD --ssi-hz 96000` boots from reset and dismisses the start popup.
2. RECORD (code 19), the trig keys (25 is step 1), RECORD again: trigs on track 1. Without RECORD
   a trig key only plays the note.
3. PLAY (20), run, STOP (21).
4. `--capture 0x400cf7be:1:48` keeps the first 48 bytes of the frame (`0x80005e60`) on every
   send; bytes 34 and 36 are the note-on and note-off voice masks
   (`docs/drive-load-command.md`, "The trigger masks are one-frame events").
   `dnfw.seqframes` turns them into events.

## Baseline: stock 1.11

Trigs on steps 1, 5, 9, 13, 120 BPM: note-ons every 0.500 s, each note-off 0.125 s later (a
sixteenth), the voice number going up by one each note. Step period 16.50 M instructions
= 120.0 BPM at 132 MHz, worst gap off by 0.00%. The unit's panel PLAY moved the step word about
8 times a second on the same clock (`emulator-sequencer-not-ticking` in memory).

## Tracks and notes

- `--track N:STEPS` adds a track: TRK (16) held, trig key N, then RECORD and the trig keys.
  Trigs on tracks 1 and 2 at 1, 9 and 1, 5: the shared step 1 is one frame with voices
  `[0, 1]`, the others one voice each; spacing keeps to the union of the steps.
- The note is the u16 at byte `2 + 2 * voice` of the frame, `note << 8 | fine`
  (`dnfw.waverider.frame.NOTE`). It is written in the note-on's frame and stays after it, so
  the decoder reads it at the note-on. Every trig of a fresh pattern reads 60.0 (C4).
- **Not yet: a trig's note cannot be changed from the panel in the emulator.** Measured
  (2026-10-11), cause not found:
  - Holding a trig key plays a preview note, which is an extra note-on in the frames. With
    the preview counted out the pattern's spacing is unchanged: trigs on 1, 5, 9, 13 stay 4.0
    steps apart whether or not a trig key was held first.
  - With no key held, a plain turn changes only the readout in the top rows (0 to 9) of the
    screen; push-and-turn changes nothing on the screen at all; with a trig key held, nothing
    changes whether the turn is plain or pushed. The body of the page never moves, and every
    trig still plays 60.0.
  So the encoder edit is not reaching a value in this setup. Why is open (the push code, the
  turn packet and the page are the candidates; none is tested). Different notes need the
  pattern's trig data written directly.

## Mod regression sweep

`scripts/emu_seqplay_sweep.py BUILD.syx ...` plays the same two-track pattern on stock and on
each build and compares what reached the DSP event by event (time since the first note-on,
kind, voices, notes). A mod that leaves the sequencer alone must match to the instruction.

## Limits

- Boot from reset each run (about 35 s); a state saved without `--ssi-hz` is refused.
- The decoder reads voice masks and notes, not which track a voice belongs to (the allocator
  hands each note the next voice).
