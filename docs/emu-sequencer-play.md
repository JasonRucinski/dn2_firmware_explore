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

## Limits

- Boot from reset each run (about 35 s); a state saved without `--ssi-hz` is refused.
- The decoder reads voice masks, not notes. Which note or machine a voice got is in the rest of
  the frame.
- Track 1 only so far; trigs on other tracks use the same keys after TRK (16).
