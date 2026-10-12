# Frame bytes 2644..2647: what stock puts there, and what reads it

Waverider's song position (`csrc/waverider/sync.c`) travels in frame bytes 2644..2647
(0xa54..0xa57). The note in `sync.c` and in `docs/waverider-m10-move.md` called them "unused
in the tail". That was wrong in one respect: stock writes them every frame, and the stock DSP
reads the word. This page says what each side does and what we measured.

The question came from naturarum/dn2-cfw (GitHub issue #49 on this repo, 2026-10-12): their
OS 1.12 notes (`notes/T3.3-fx-frame.md`, `notes/T6.0-fx-params-room.md`) list 0xa54 and 0xa56
as written by the ColdFire and read by the DSP. They are right about both.

## The ColdFire writes them (OS 1.11)

The frame builder at `0x400274a0` (it loads the frame base `0x80005e60`, the stores below are
absolute) fills the words after the per-track arrays:

| frame byte | address | what stock stores |
|---|---|---|
| `0xa50` | `0x800068b0` | a longword read through `%a2` |
| `0xa54` | `0x800068b4` | the builder's own local at `%fp@(-118)` |
| `0xa56` | `0x800068b6` | the byte at `0x42431aad`, shifted left by 8 (low word) |
| `0xa58` | `0x800068b8` | the word at `0x42431c11` |
| `0xa5a + 2r` | `0x800068ba..` | the owner track of row r |

(`0x40027648`, `0x4002764e`, `0x4002766e` in the disassembly. OS 1.12 has the same layout
with the globals 0x1000 higher.) Our hook runs after the builder and before the send
(`0x40025e82`), so with the mod installed the DSP gets our position in 0xa54..0xa57 and never
sees the two stock values.

## The DSP reads the word

The block handler executes `r2 = dm(-0xa, i5)` at sw `0x1c3084` once per block, from the
receive buffer, and splits r2 into its two halves. Four more reads of the receive buffer run
once per block (`0x22`, `0xa7a`, `0xa7c`, `0xa7e`).

## What depends on it: nothing we could find

`scripts/sharc_frame_word_check.py` runs the unmodified section 7 in the runner with a note on,
three blocks, and writes three patterns over the word (zero, 0x11223344, all ones). It compares every track buffer, the
reply tail, and DSP data memory (0x200000..0x300000, outside the frame copy and the receive
buffers).

| word written | machine on track 1 | track buffers | reply | memory words that differ |
|---|---|---|---|---|
| 0xa54..0xa57 | WaveTone | identical | identical | **0** |
| 0xa54..0xa57 | machine type 0 | identical | identical | **0** |
| 0xa54..0xa57 | machine type 3 | identical | identical | **0** |
| 0x74..0x77, the track levels (control) | WaveTone | identical | identical | **11** |

The control shows the check can see a dependence: levels reach DSP memory (and, later in the
chain than the track buffers, the mix), the song position does not. The track buffers alone
would not have shown it; the memory diff is the measure.

## What this does not cover

- Default FX settings and one note. A stock path that reads the halves only under some FX or
  setup state was not exercised.
- Three blocks per case, and the emulator. On the instrument the SYNC build has run for weeks
  with no symptom in any stock machine.
- What the two stock values mean. The local at `%fp@(-118)` and the byte at `0x42431aad` are
  not identified.

## If it ever matters

- **Read the stock values on the unit** (probe PEEK of `0x800068b4` and `0x42431aad` on a
  stock build) to see whether they are ever non-zero.
- **Move the position** to words the stock ColdFire never writes and the DSP never reads. The
  1.12 notes name 0x2a and 0xa18 (16 bits each, so the position would be split in two) and
  the 30-word tail 0xa80..0xabb (outside the DSP's frame copy, so the DSP would read the
  receive buffer). Run `sharc_frame_word_check.py --offset N` on a candidate first. These are
  the words naturarum's second FX page wants, so agree who takes which before using them.
