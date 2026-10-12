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

## Where the position lives now: 0xa18 and 0x9a8

The position (a u32) is split over two words that no stock DSP code reads:

| word | frame byte | stock ColdFire | stock DSP |
|---|---|---|---|
| low 16 bits | `0xa18` | copies a parameter there (FX setup k 40, the delay routing) | never reads it |
| high 16 bits | `0x9a8` | copies a parameter there (track 15's slot offset 0x50, parameter k 65) | never reads it |

### How they were chosen: a census, and why 0x2a was dropped

The first idea was `0x2a` (nothing in stock writes it) with `0xa18`. Narrow runs (one machine, a
note, two or three blocks) found no reader for either. A wider census then found one for `0x2a`:

`scripts/sharc_frame_census.py` runs the stock DSP over blocks with random frame words, every
machine type 0..4 on all 16 tracks, filters 0..5, with read watchpoints over the whole frame
(receive page and DSP copy). 169 blocks over 30 machine and filter groups; three groups stopped
early where a random frame drove the runner into an unmodeled register, which is the runner's
limit and not a finding. It names every reading instruction per frame word:

| result | words |
|---|---|
| read only by the unpack copy loops | 52: per-voice slot offsets 0x3c, 0x40, 0x50, 0x6e on tracks 2, 3, 5 to 15 (0x6e not on track 3), and `0xa18` |
| read directly from the receive page (outside the copy loops) | `0x22`, `0x94`, `0x154..0x158`, `0x160`, `0xa54`, `0xa56`, `0xa5a`, `0xa7a`, `0xa7c`, `0xa7e`, and a block starting `0x2f0` |
| `0x2a` | read in machine type 4, filter 0: a byte loop at sw `0x1c2545` reads the first 92 bytes (words 0 to 45) of the frame copy |

Does that read matter? `scripts/sharc_frame_census.py diff` replays the same random frames
twice from the same state, flipping chosen words in the second, and compares all DSP memory
outside the receive pages:

| words flipped | case | memory words that differ |
|---|---|---|
| `0x2a` and `0xa18` | machine 4, filter 0, 6 blocks | 59 (from block 1) |
| `0x2a` alone | the same | 59 |
| `0xa18` alone | the same | 0 |
| `0x9a8` and `0xa18` | machine types 0 to 4, filters 0 and 3, 6 blocks | 0 (machine 0 and machine 2 filter 3 stopped early as above, with no difference before stopping) |

So `0x2a` is used in machine 4 / filter 0 and was dropped. `0x9a8` and `0xa18` are not.

### The earlier narrow check

`scripts/sharc_frame_word_readers.py` (reads of one word) and `sharc_frame_word_check.py` (a
memory diff for one word) agree for WaveTone on track 1; they are the quick checks, the census
is the wide one. A four-byte write at 42 or 2584 also hits `0x2c` and `0xa1a`, which stock does
use, so single words are checked with `--width 2`.

The ColdFire writes the two halves after the builder has made the frame. The DSP reads them
from its frame copy as 16-bit halves (`csrc/waverider/sharc/sync.asm`).

## Limits that remain

- Random frames are not real frames: parameters take values no sound produces, and the runner
  stops on a few. 169 blocks is a tenth of naturarum's 2,247. A path reached only by real
  sequences (a particular FX mode, a song mode) could still read these words.
- Both words are copies of parameters (k 40 and k 65). If a later OS version made the DSP read
  them, the position would feed it.
- The 30-word tail (`0xa80..0xabb`) is the one place the stock ColdFire never writes and the
  DSP never reads. It needs a DSP read of the receive buffer and writes into the SPI staging
  buffer, and the OS 1.12 notes keep it for a second FX page.
