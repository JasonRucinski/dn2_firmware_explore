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

## Where the position lives now: 0xa18 and 0x2a (since Waverider 0.3.4)

**Moved 2026-10-18.** The high half was at `0x9a8` until 0.3.4. That word is track 15's parameter 57
(`frame.slot_offset(15, 57)`), which became the noise's DEC on page 3 after the census. `sync.c` wrote the
position over it at send time, so on voice 16 the noise's DEC read the position's high half: 0 when stopped,
about 10 in bar 2. The noise there died within milliseconds of each note. The owner heard it on a sound
locked to voice 16.

In the DSP runner, with the high half 0 at `0x9a8`, voice 16's noise level fell from
0.153 to 0.013 within 16 ms.

The high half is now at `0x2a`, in the header after the trig masks (bytes 34 to 41). No voice's slot holds
it, and stock's ColdFire never writes it. `sync.asm` reads the aligned word at `0x28` and keeps its high half.

**`0x934` was tried first and refused.** It is track 14's parameter 72, which the census listed as read only by
the copy loops. The flip test (`diff --words 0x934`, filters 0 and 3) changed 2 DSP memory words from block 3
with filter 3, on machine types 0, 1 and 2. So parameter 72 feeds filter type 3.

**What clears `0x2a`, 2026-10-18 and 19:**

| test | result |
|---|---|
| flip in random frames, machine types 0 and 1, filters 0 and 3, 6 blocks | 0 words differ |
| flip in random frames, machine type 4, filter 0, seed 1 | 0 words differ |
| the corpus of real frames, 40 frames, 80 blocks (`replay --flip 0x2a`) | read only by the two copy loops, in the receive page; never read in the frame copy |
| the control on the same corpus: `0x74`, a track level (`replay --flip 0x74`) | read outside the copy loops, and 429, then 364 memory words differ: the replay sees a real dependence |
| machine type 4, filter 0, **seed 124**: the case that gave 59 words on 2026-10-12 | 52 words differ. The census names the cause: row 3's owner word is `0x25` |
| the same frames with each row's owner set to its track (`diff --valid-owners`) | **0 words differ** |
| naturarum's census in their own emulator, sharcvm (`notes/T6.0c-frame-census-dnfw.md`, 2026-10-13) | free: 0 of 192 flips, 0 of 48 with random voices, 0 of 22 again |

The owner word explains the old result. naturarum traced it in sharcvm: the voice-mix loops at `0x1c1fca` and
`0x1c2535` take their row pointer from the owner word at `0xa5a + 2r` (`0x258f68 + 0x100 x owner`, and its
sibling from `0x259f68`). An owner of `0x25..0x2f` or `0x35..0x3f` puts a row on the frame image, and `0x25`
reaches `0x2a`. Our runner shows the same: the dependence goes with the wild owner. In every real frame we
recorded, each owner is 0 (all 1,200 corpus frames). Stock writes the owning track there, 0 to 15.

`test/test_waverider_songpos.py` checks that both position words miss every Waverider parameter (25 to 64)
on all 16 voices, and the header arrays the frame model knows. It also checks that `sync.asm` reads the
words `sync.c` writes.

The sections below record how `0x9a8` and `0xa18` were chosen. They still hold for `0xa18`.

## Where the position lived until 0.3.4: 0xa18 and 0x9a8

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

> **Correction, 2026-10-13.** "`0x2a` is used in machine 4" is not shown by this. The loop that reads it is
> ordinary DSP code (a multiply-accumulate over 31-word blocks, `0x1c1fca..0x1c1fe3`, and its sibling at
> `0x1c2535..0x1c254e`) whose base pointer `I0` comes out as garbage in fully random frames (in the case that
> reads `0x2a` in the merged census, machine 0, filter 2: `I0 = 0x804acf94`). The runner wraps such an address
> into the receive page, so the loop "reads" the page as data, and flipping a word in it changes what the loop
> computes. That is an artefact of the random frame, not a dependence of the stock sound on the word. `0x2a` was
> dropped as a precaution and stays dropped, but nothing here shows the DSP uses it. (The machine 4 case was not
> re-traced.) See the comparison below.

### The wider census (2026-10-13): 1,343 blocks, one new reader of `0xa18`, and what it does

The random-frame census was rerun over 8 more seeds (`out/census_big`, 240 case files,
every machine type 0..4 and filter 0..5) and merged: **1,343 blocks**, against 169 above and
naturarum's 2,247. `sharc_frame_census.py report --word` over the merge:

| word | read by | after the copy |
|---|---|---|
| `0x9a8` | the two unpack copy loops only (`0x1c287d`, `0x1c3030`) | no reads |
| `0xa18` | the copy loops, and **`0x1c1fda`, twice in 1,343 blocks** | no reads |
| `0x2a` | the copy loops, `0x1c2545` (machine 4) and `0x1c1fda` | a byte loop, as before |

`0x1c1fda` is new here. It is a wide reader: across the merge it touches 728 frame words, in
a few cases a block of the copy and, in exactly one case, a 62-word window of the receive
page, `0x9f4..0xa6e` (machine type 2, filter 2, seed 6014, one block of six), which includes
`0xa18`, `0xa1a` and `0xa54`. A reader is not a dependence, so the same frames were replayed
with the words flipped (`diff --machine 2 --filters 2 --blocks 6 --seed 6014`, all DSP memory
outside the receive pages and the frame copy compared):

| flipped | memory words that differ, blocks 0 to 5 |
|---|---|
| `0xa18` | 0, 0, 0, 0, 0, 0 |
| `0x9a8` | 0, 0, 0, 0, 0, 0 |
| `0xa18` and `0x9a8` | 0, 0, 0, 0, 0, 0 |
| `0x74` (control: a track level) | 5, 833, 525, 435, 429, 427 |

The control shows the replay can see a dependence in these very frames. So the read at
`0x1c1fda` does not carry `0xa18` or `0x9a8` into anything measured, and the position stays
where it is. What the read at `0x1c1fda` is for was not traced: it looks like a window
copy, taken only when a random frame sets a combination real sound does not. That is a
reading of its access pattern, not a disassembly.

### Corpus replay and real frames (2026-10-13): 3,285 blocks, and the flip on every trigger

The same census over the frames the ColdFire really sends (`scripts/frame_corpus.py`: stock 1.11 from
reset, machine types 0 to 4 on track 1, three trig patterns) with naturarum's two augmentations,
`replay --augment both` (as sent, the FX block and header flags randomised, the voice slots, owners and
tail randomised), 8 shards of 40 frames, 2 blocks per variant; plus 9 recorded real frames. Merged with
the random run: **3,285 blocks** (1,343 random, 1,906 corpus replay, 36 real), against naturarum's 2,247.
`report` now merges every census file in a directory (it read only `m*f*.json` before).

| word | direct readers outside the copy loops, 3,285 blocks | where |
|---|---|---|
| `0x9a8` | `0x1c1fe3`, 12 reads | corpus shards 0, 2 and 3, in the augmented variants only |
| `0xa18` | `0x1c1fda` (2 reads, the random run) and, in the frame copy, `0x1c2545` (4 reads) | the random run, and corpus shard 1 |
| `0xa80..0xaba`, the 30-word tail | none | never read in the receive page or the copy, in any block |

A reader is not a dependence, so each variant in which one of these readers touched `0x9a8` or `0xa18`
was replayed twice with both words flipped in the second (`replay --flip 0x9a8,0xa18`), 2 blocks each,
all DSP memory outside the receive pages and the frame copy compared:

| case | variants triggered | memory words that differ |
|---|---|---|
| corpus shards 0, 1, 2, 3, `0x9a8` and `0xa18` flipped | 4 (one per shard, all `voices` variants) | **0 in every block** |
| control: `0x74`, a track level, on 4 real frames | 24 blocks | 131 to 647 in every block |

So none of the new readers carries either word into anything the check can see, and the position
stays at `0xa18` and `0x9a8`. What bounds that:

- **4 triggered variants, 2 blocks each.** The readers fire only in augmented variants (randomised FX
  block, owners or tail), never in a frame as sent.
- **3 variants stopped by the runner** (an unmodeled MMR at `0x1c1fca` or `0x1c2535`: a randomised tail
  steers the DSP to an MMR the runner does not model) before the flip could be compared. Whether `0x9a8`
  or `0xa18` matters there is unknown.
- The readers at `0x1c1fe3`, `0x1c1fda` and `0x1c2545` were not disassembled; what they are for is
  unknown.
- The tail `0xa80..0xabb` stays the fallback: it is read by nothing in 3,285 blocks, and using it needs
  a DSP read of the receive buffer (above).

### Compared with naturarum's census (2026-10-13)

Their notes (`notes/T6.0-fx-params-room.md` section 1.2, OS 1.12, read 2026-10-13, cited by file and in our own
words) describe 2,247 blocks of the stock DSP: 247 recorded captures; 400 with the global block and header words
random; 400 with per-voice slots, owners, note words and tail random; 1,200 with all 16 voices on each machine
type 0 to 4 and filter 0 to 5, a note on in the first block and random slot values. Ours has the same four
kinds: a recorded corpus as sent, `--augment fx`, `--augment voices`, and the random machine by filter grid.
The author states in issue #49 that the DSP section is byte-identical in 1.11 and 1.12, so the two censuses
are of the same code. What agrees and what does not, by word:

| word | theirs | ours (3,285 blocks) | |
|---|---|---|---|
| tail `0xa80..0xabb` | never read, not copied | never read, in no block | agrees |
| `0x22`, `0xa54`, `0xa56`, `0xa7a`, `0xa7c`, `0xa7e` | read straight from the receive buffer at `0x1c2cd6`, `0x1c3084`, `0x1c3052`, `0x1c3069`, `0x1c309c` | the same readers, the same words | agrees |
| `0x2a`, `0xa18`, slot `+0x50` (`0x9a8` on track 15) | never read | readers appear at `0x1c2545`, `0x1c1fda`, `0x1c1fe3`, in random or augmented frames only, in loops whose `I0` is garbage there (traced for `0x9a8` and `0x2a`; `0xa18`'s readers are the same loops); flipping `0xa18` and `0x9a8` on every such variant changed nothing | **agrees, where traced** |
| other direct readers | five words | 1,128 words in all: most by the two sweep loops (the mechanism below, not traced word by word), and the readers at `0x1c31bb..0x1c3207` (`0x94..0xb2`, `0x154..0x160`, `0xa5a..0xa78` and their per-voice repeats), which were not traced | **open** |

**What the extra readers are.** At `0x1c1fca..0x1c1fe3` the DSP runs a floating-point multiply-accumulate over
31-word blocks (`lcntr = 0x1f`, `f0*f2`, `f12+f4`, with `I0` and `I1` as the two block pointers), and a sibling
loop sits at `0x1c2535..0x1c254e`. Traced in the replay variant that reads `0x9a8` (corpus shard 0, file `0016` of
`fmdrum_p2`, voices variant), at the same point of the block (about 288,000 steps in):

| pointer at `0x1c1fca` | the frame as sent | the same frame, slots/owners/tail randomised |
|---|---|---|
| `I0` | `0x258f68`, then `+4` per step | `0xffeb5968`, then `+4` per step |
| `I1`, `I2`, `I3`, `I4`, `I5`, `I6`, `I7` | `0x257eec`, `0x25789a`, `0x268438`, `0x257ee8`, `0x2578b9`, `0x2ffe98`, `0x2ffe50` | identical |

Same code, same place, one pointer wild. The runner wraps the address into the receive page, so the loop reads
frame words as data: that is how "direct readers" of nearly every word appear, only in randomised variants, and
why flipping those words changes nothing in the real path. In a fully random frame (machine 0, filter 2, seed
1002, the case that reads `0x2a`) `I0 = 0x804acf94` at `0x1c2535`. Which frame field feeds `I0` was not traced.

So the two censuses agree: with valid pointers nothing reads `0x2a`, `0xa18` or slot `+0x50`. Two rules for any
such census: a read outside the copy loops in a randomised block is first a question about the pointer, and a
read is a dependence only if flipping the word changes DSP memory (`replay --flip`, `diff`).

What this does for the claim: coverage of the same kinds and a larger count, with agreement on every finding
once the pointer artefact is accounted for. It does not make any word free beyond what the flip tests show
(the tail, and `0x9a8` and `0xa18` for the variants flipped; 3 variants stopped in the runner before they
could be flipped).

### The earlier narrow check

`scripts/sharc_frame_word_readers.py` (reads of one word) and `sharc_frame_word_check.py` (a
memory diff for one word) agree for WaveTone on track 1; they are the quick checks, the census
is the wide one. A four-byte write at 42 or 2584 also hits `0x2c` and `0xa1a`, which stock does
use, so single words are checked with `--width 2`.

The ColdFire writes the two halves after the builder has made the frame. The DSP reads them
from its frame copy as 16-bit halves (`csrc/waverider/sharc/sync.asm`).

## Limits that remain

- Random frames are not real frames: parameters take values no sound produces, and the runner
  stops on a few. 3,285 blocks against naturarum's 2,247 (169 in the first pass); not the same frames, so not the same coverage. A path reached only by real
  sequences (a particular FX mode, a song mode) could still read these words.
- Both words are copies of parameters (k 40 and k 65). If a later OS version made the DSP read
  them, the position would feed it.
- The 30-word tail (`0xa80..0xabb`) is the one place the stock ColdFire never writes and the
  DSP never reads. It needs a DSP read of the receive buffer and writes into the SPI staging
  buffer, and the OS 1.12 notes keep it for a second FX page.
