# Bloom: a VA machine built around a modulator that bends time

**Rewritten 2026-10-18**, at the fork owner's direction: Bloom is **a new machine of
its own**, not part of Waverider, and *"go crazy"*. This replaces the design of
2026-10-17. That design is kept, condensed, under "Superseded" at the end, with
the reasons it changed.

**Sources.** Facts marked **(upstream)** come from
`angellinares/dn2_firmware_explore` main at `5be76c1`, which is 382 commits ahead
of this fork and not yet merged into it. Everything else is in this tree.

Grades, as elsewhere: **[V]** on the instrument, **[E]** in an emulator, **[D]**
read statically, **[O]** open. **Nothing in this document has been built or
run.** It is a design.

## The brief

The effect in RÜFÜS DU SOL's *Innerbloom*, 5:10-5:18 (the owner's description, in
short):
- a sustained, warm, saw-based chord;
- a **triangle** modulator opening and closing a resonant **low-pass**;
- its **rate falling** from about 12 Hz to 1 Hz over about 8 s, exponentially;
- the modulator's **phase continuous**, never restarted by a rate change;
- the baseline and the depth may drift, so the pulses get brighter or darker;
- reverb and delay make a tail behind dry, defined pulses;
- for future bass, the same modulator **on the volume** too, for a near-silent
  chop.

In the owner's words, it is **not** the amp envelope and **not** retriggered
notes, but the speed of a modulation oscillator.

## The concept

**A virtual-analog voice whose modulator is the instrument.** The pulse speeds up
or slows down, lands on the downbeat, ducks to the kick, and can lock every other
Bloom track to the same breath. The default sound is the brief.

## Forty knobs: the hard ceiling

A sound carries **40 machine slots, 25..64** (`docs/engine-state.md`), and a
machine's controls are those slots. Bloom borrows WaveTone's records for them, as
Waverider does, so p-locks, CC, LFO destinations and SAVE/LOAD are stock. That
gives **five pages of eight**:

| page | A | B | C | D | E | F | G | H |
|---|---|---|---|---|---|---|---|---|
| **1 OSC** | WAV1: saw ↔ pulse ↔ tri | PW1 | WAV2 | DETN | SYNC: hard sync | XMOD: osc 2 FM / ring | MIX | SUB |
| **2 PULSE** | STRT | END | TIME | CURV | FDEP: cutoff | VDEP: chop | SHAP | TILT |
| **3 MOTION** | ANCH | MODE: smooth / land / step | SWNG | PAN | PDEP: pulse width | P2RT | P2DS | P2DP |
| **4 BLOOM FILTER** | BTYP: LP / BP / vowel / comb | BFRQ | BRES | BDEP | ROUT: series / parallel | DRIV | NOIS | NTYP |
| **5 PLAY** | DUCK: source track | DAMT | DREL | LINK: follow track N | VEL: velocity → depth | STAK: unison 1-4 | SPRD | TRIM |

**Mapping rule (upstream, Waverider M10b-2).** Some spare WaveTone records default
to `0x7f00`, and every sound saved so far holds that value. So a control on such
a record must read 127 as "off". The record-by-record mapping is milestone B2's
work, with that rule and each record's range. Ranges and value text go through
the three hooks M10b introduced (the limits getter `0x400dbff0` and both
value-text paths, `docs/waverider-m10-move.md`).

---

## The engine

### The voice [plausible]

- **Two PolyBLEP oscillators**, the standard alias-reduced VA design. Each
  morphs saw → pulse → triangle (WAV), with pulse width (PW), hard sync (SYNC:
  osc 2 restarts on every cycle of osc 1), and osc 2 into osc 1 as phase
  modulation or ring (XMOD).
  MIX balances them, and DETN detunes osc 2.
- **A sub-oscillator and noise** (SUB; NOIS / NTYP on page 4).
- **DRIV:** a soft-clip drive before the Bloom filter.

**Why not wavetables:** VA needs pulse width and sync, which tables do badly.
Waverider's built-in saw (PRIM, 32 harmonics) also aliases above a fundamental of
about 750 Hz and is thin at the bottom.

**The check:** PolyBLEP costs about what a table read does, and like every DSP
routine here it is checked bit-exact against a Python reference in digikit's
SHARC runner.

### PULSE: a function of the song clock [proven ground]

**The ColdFire writes the song position into every frame**, at frame bytes
2644..2647. 2³² there is 384 sixteenths (24 bars), the least common multiple of
every straight, dotted and triplet length. The tempo is in the frame too, at
`+0xd8`, as BPM × 120. **(upstream)**: Waverider's `sync.c` does this on the
instrument, and `docs/waverider-frame-words.md` measured that nothing stock
depends on those bytes.

So **PULSE's phase is computed, not accumulated per voice.** For an exponential
glide from rate R₀ to R₁ over a time T:

```
Φ(t) = R₀ · T · (k^(t/T) − 1) / ln k      k = R₁ / R₀,   for t ≤ T
Φ(t) = Φ(T) + R₁ · (t − T)                 after
m    = shape(frac(Φ))                       -1..+1
```

Because the phase comes from the shared clock:
- **A chord pulses as one.** A chord plays on several voices, and each computes
  the same Φ from the same clock. Per-voice accumulators drift apart as notes
  overlap.
- **The phase is continuous** across chord changes and rate changes, by
  construction.
- **It is on the grid**, because it is derived from the sequencer's own
  position.

**The controls (page 2):**
- **STRT / END** are free rates in Hz, or note lengths when SYNC is on.
- **STRT > END blooms** (slows down), and **STRT < END builds** (speeds up).
- **TIME** is seconds free, or bars synced.
- **CURV** sets exponential, linear or logarithmic.
- **FDEP** is the depth on cutoff, **VDEP** the depth on volume.
- **SHAP** is one continuous knob: triangle → pump (a sidechain-like recovery) →
  softened square.
- **TILT:** the depth glides with the rate, so the pulses swell or shrink as they
  slow. One trig makes the whole Innerbloom gesture without an LFO.

**The controls (page 3):**
- **ANCH:** the glide starts at the trig, every N bars of the song position, or
  once from PLAY.
- **MODE:**
  - **smooth** is the plain curve;
  - **land** scales the curve to a whole number of cycles, so the last pulse ends
    on the downbeat. The free curve completes N = T·(R₀−R₁)/ln(R₀/R₁) cycles; it
    is rounded and the rates scaled by the ratio, about 2 % for the brief;
  - **step** is a ladder of note lengths, a whole beat each, so every edge is on
    the grid. That gives rolls and builds.
- **SWNG:** swing on the pulses.

### Two filters, both pulsed

**The stock filter, driven per block [plausible, the first thing to prove].**
- The dispatch runs each machine's **setup arm**, then a common continuation that
  calls the filter's setup through `0x8052dba4[type]` at `0x1c91ad`
  (`docs/waverider-dsp-silence.md`, "What the setup arms write") **[D]**.
- Types 5 and up take no arm today: the guard is `compu(type, 5)`.
- A Bloom arm writes base + FDEP × m into the track record's FREQ (`+0x1cc`)
  **before** the filter's setup reads it (`src/dnfw/waverider/frame.py`,
  `RECORD_FIELDS`).
- **Result:** every stock filter type with its own resonance, at block rate
  (1,500 a second, the rate stock LFOs move it), and no filter cost of ours.
- **The assumption:** the filter's setup recomputes its coefficients every
  block. Stock LFO-on-cutoff working implies it, but B1 measures it.
- **If the assumption fails,** the Bloom filter below becomes the pulsed filter.

**The Bloom filter, on IIR0 [plausible].**
- The ADSP-21569's IIR accelerator is unused by stock. Its rounding order was
  read from the chip on 2026-10-17, and digikit models it **(upstream,
  `docs/sharc-accelerators.md`)**. Waverider's Formant type is its first user
  **(upstream, `docs/waverider-formant.md`)**.
- **BTYP:** low-pass, band-pass, **vowel** (a cascade of formant resonators, so
  the pulse sweeps A-E-I-O-U) or comb.
- **ROUT:** before the stock filter, or in parallel with it.
- **BDEP:** the pulse on its cutoff.
- The accelerator does the arithmetic while the core goes on, so its cost to the
  core is small.

### The chop, per sample [proven ground]

VDEP is applied **inside Bloom's own render**, sample by sample, with
declick ramps of the kind Waverider uses (**upstream**, M10b-2's SMTH and DCLK). Square and pump
shapes never click. It is not done through the amp record, which would step once
a block and click (Waverider M10a's free square did, `docs/waverider-m10-move.md`).

### More motion [plausible]

- **PULSE 2.** A second modulator locked to the first at a ratio, P2RT (3:2,
  4:3, 2:1...). P2DS picks its destination (cutoff, Bloom filter, volume, pan,
  pulse width) and P2DP its depth. Cutoff in three against a chop in two gives
  a cross-rhythm that still blooms together.
- **PAN.** The arm writes the record's pan (`+0x230`) as it writes FREQ, so the
  pulses swing left and right as they slow. A track's buffer is mono
  (`docs/sharc-voice-path.md`), so this is the way to move across the stereo
  field from inside one track.
- **PDEP.** The pulse on osc 1's pulse width: the shimmer moves into the timbre,
  VA's own form of the effect.

---

## The parts that make it more than a synth

**DUCK: a built-in sidechain [plausible].**
- Pick a source track, DAMT and DREL, and Bloom ducks with that envelope on every
  trig of that track, sample-accurately. That is future-bass pumping without the
  master compressor.
- **No new ColdFire work.** The frame already carries the note-trigger mask at
  offset 34 (`docs/waverider-feasibility.md` M4, step 1), and each voice row's
  owner track at `0xa5a + 2r` **(upstream, `docs/waverider-frame-words.md`)**.
  The DSP can tell when the source track triggered.

**LINK: tracks that breathe together [plausible].**
- Bloom follows track N's pulse settings, read from the DSP's frame copy
  (`0x25c48c`), which holds every track's slots.
- The bass on track 2 blooms in phase with the chords on track 1, with one set
  of settings to edit.

**STAK: unison [research for cost].** One to four stacked oscillator pairs per
voice, with SPRD for the detune spread: the thick future-bass chord. It multiplies
the voice's cost, so its ceiling is set by measurement.

**VEL [plausible].** Velocity scales FDEP and VDEP, so harder chords bloom harder.

**TIME follows the note's length [research].** One TIME setting makes the glide
take exactly as long as the trig, so each note blooms over its own length. This
needs each trig's length in the frame, which the ColdFire would have to add, in
a word yet to be found.

**The page shows the motion [plausible].** The PULSE page draws the rate curve
with a moving playhead and a tick per pulse, and the header reads
"1/16 → 1/4 · 1 bar". The DSP reports its phase back through the reply's spare
tail (`+0xa9c`), as Waverider's MOVE report does on the instrument
(`docs/waverider-m10-move.md`, M10b-3).

## Factory sounds, which double as acceptance targets

| sound | what it sets | what it proves |
|---|---|---|
| **Innerbloom** (the init) | free, STRT 12 Hz → END 1 Hz, TIME 8 s, triangle, FDEP half, RESO up | the brief |
| **Future Chop** | synced, 1/8 triplets steady, VDEP 110, SHAP square, DUCK from track 9 | the chop and the sidechain |
| **Riser** | STRT 1/4 → END 1/64 over 4 bars, TILT +, MODE land | building, and landing on the drop |
| **Vowel Bloom** | Bloom filter vowel, BDEP high, 1/8 → 1/2 over 2 bars | IIR0, and the pulse on the vowel |
| **Breathing Pad** | ANCH every 2 bars, LINK target for other tracks, PAN 60 | the shared clock and LINK |

---

## Where each part runs, and why

| part | runs on | why |
|---|---|---|
| PULSE, the chop, DUCK, LINK, the voice, the Bloom filter | SHARC | the song position and tempo are in the frame **(upstream)**. The ColdFire's audio-frame ISR already peaks at 74-112 % of a frame on stock (`docs/usbprobe.md`). The DSP has about a third of its frame free (`docs/sharc-load.md`) |
| the stock filter's cutoff, pan and volume | the SHARC, in Bloom's setup arm | the filter's setup runs before any machine renders **[D]**, and the arm runs before it |
| the song-position writer | ColdFire, once per frame | Bloom's own copy of what Waverider's `sync.c` does **(upstream)**. A shared module once both exist |
| MACHINE SEL, the names, the pages, value text | ColdFire | the route Waverider proved: `docs/machine-list.md`, `docs/waverider-m7-pages.md`, M10b's hooks |

**DSP code space.** Standalone, Bloom has the whole free region of L1 block 1,
`0x2dd600..0x2e8000`, about 42.5 KB, ending 32 KB below the block's top to stay
clear of the DM cache **(upstream, `dnfw.waverider.dsp.REGION`)**.
- **Never L1 block 2:** it is the PM cache's, and code there silenced the
  instrument (`docs/waverider-dsp-silence.md`).
- **Not the L2 above the image** either, which looks free and is not: stock data
  words point into it (same document).

**DSP budget, estimated.** A PolyBLEP oscillator is roughly a dozen cycles a
sample. Two oscillators, the sub, the chop and the pulse are then of the order
of 1,000 cycles per voice per 32-sample block: about 2.5 % of a 666,667-cycle
frame for all 16 voices. STAK multiplies the oscillators' share. The owner's
rule from Waverider applies: *one synth cannot cost more DSP than a whole pattern
of stock synths.* Measure every milestone with the idle-load stub, because the
reply's word 0 misreads around these tracks (`docs/sharc-load.md`).

## Packaging

**v1: its own mod, machine type 5, without Waverider.**
- Upstream's **hook bus** owns the machine count, `MACH`, and allows **one** mod
  to add machines **(upstream, `src/dnfw/mods/bus.py`)**. Bloom's mod is that
  contributor, so it excludes Waverider, and needs the whole DSP region anyway.
- **Saved sounds, a hazard to decide before B2 [O].** A Bloom sound is stored as
  machine type 5.
  - On stock it loads as **FM Tone** (the LOAD bound's fallback).
  - **On a Waverider build it would load as Waverider**, playing Bloom's slots
    as Waverider's controls. The same number means two machines.
  - The option: put Bloom at **type 7**, with placeholder rows for 5 and 6. That
    costs a little plumbing and removes the collision.

**v2: alongside Waverider [research].**
- **A shared machine table on the bus.** The bus's own notes name it as what a
  second machine-adding mod needs.
- **DSP code space for two machines.** Most likely code running from DDR through
  the instruction cache, if the stock startup enables that cache. Which caches
  the startup turns on was never settled (`docs/waverider-dsp-silence.md`).
- **Shared modules** for the song position, the page framework and the
  value-text hooks.

---

## B0, built (2026-10-21): the reference model

`src/dnfw/bloom/`, pure Python, no firmware. `dnfw bloom presets | curve NAME |
render NAME OUT.wav [--dry]`. Tests: `test/test_bloom.py`, 32 passing.

| module | what it holds |
|---|---|
| `clock` | the frame's position word (2^32 = 384 sixteenths) and tempo word (BPM x 120) as beats; the 18 note lengths, each checked to divide the wrap |
| `pulse` | the glide's closed-form phase (exp, lin), `smooth` / `land` / `step`, the SHAP morph, TILT |
| `osc` | PolyBLEP saw and pulse, a naive triangle (its corner aliases far less than a step), the WAV morph |
| `duck` | DUCK: a 1 ms attack, so the dip never clicks, and a release; a trig continues from the level it finds |
| `sound` | a sound's controls in their own units; LINK, one hop only, so links cannot loop |
| `presets` | the factory sounds and their patterns, each with what it should sound like |
| `voice` | the track: per sample the oscillators, chop and DUCK; **per 32-sample block** the cutoff, as the setup arm will write it |

**Measured on the model:**
- `innerbloom`: 35.41 cycles in the glide. The cutoff trace has 10 pulses in its
  first second, 5 at 2-3 s, 3 at 4-5 s and 1 a second from 6 s, each over FREQ
  5..95.
- `riser` with `land`: exactly 87 cycles, with the last ending on beat 16.
- `step-roll`: every pulse begins on a grid line, through quarters, eighths,
  sixteenths and thirty-seconds.

**A bug the tests found in the model itself:** a voice's gate is 0 at its first
sample, and the loop took that for "finished" and dropped the voice. Every chord
after the first was lost. `test_every_chord_of_a_pattern_sounds` holds the fix.

**What B0 does not cover yet:**
- hard sync and XMOD (a sync reset needs its own BLEP);
- SWNG, PAN, PDEP, PULSE 2, the Bloom filter, STAK, VEL, TIME = note length;
- the float32 order of operations the DSP will use. That is fixed at B3,
  against selas' output.

**The preview is not the instrument.** `render` runs the dry signal through a
stand-in two-pole filter, with FREQ mapped 20 Hz .. 20 kHz. It shows the shape
of the motion and nothing about Elektron's filter. `--dry` writes the machine's
own signal, which is what the DSP gate will compare.

## B1, run (2026-10-21): no. A record write does not move the stock filter

`scripts/sharc_bloom_b1.py`. The image is the stock DN2 OS 1.11 zip, verified:
- `dnfw inspect`: every checksum, and the HMAC reproduced;
- section 7 equal to `dnfw.waverider.dsp.STOCK_SHA256`;
- `--mod waverider` applies, so its stock-byte guards all hold.

The runner is digikit `6f812e99`. The harness family was validated on that
revision; `1d841b64` halts every run, the control included, on a return-address
check at the amp, `0xb8042d`. The assembler is selache `2b26d3b`. The runner
itself wrote FREQ into track 0's record, so this measures the firmware, not
Bloom's code.

| run | what changed | RMS of the buffer after the filter, blocks 4-9 | against A |
|---|---|---|---|
| A | nothing (the control) | 0.0394 | |
| B | FREQ dark (`0x2000`) **in the frame**, from block 4 | 0.0608 | **differs, from block 5** |
| C | the record's FREQ written dark at sw `0x1c91ad`, 16 times a block | 0.0394 | **bit-identical** |
| D | the same write after the setup, at the type-5 entry | 0.0394 | bit-identical |

**Why the negative holds:**
- **The hook was reached** in every block, 16 times: once per track.
- **The record held the frame's own FREQ there** (`0x3f7e0000` =
  0x7f00/32768), so the field written is the one the unpack fills.
- **The filter does respond to FREQ:** through the frame path (B) it changes
  clearly.
- **The writes changed nothing:** C and D are identical to A to the last bit.
- **[E]**, digikit's runner. Silicon is not involved.

**What it shows:**
- In B, the record holds the dark value from block 5, one block after the
  frame carried it. This is upstream's "the frame copy holds the previous
  frame" (`docs/drive-load-command.md`, upstream).
- The filter follows the frame, and ignores a record write made after the
  unpack. **So whatever turns FREQ into filter coefficients runs before
  `0x1c91ad`, most likely in the unpack itself,** possibly only when it sees
  the field change. That is unread **[O]**.
- **The design's assumption is false as written**
  ("The stock filter, driven per block", above).

**One check was wrong and is corrected:** "B is darker, so its RMS is under
70 % of A's". The dark setting *raised* the RMS by about 54 %, so the check is
now "B differs from A by more than 10 %". Not verified: the write was not read
back after the poke. The record holding the frame's value again the next block
says only that the unpack rewrote it.

**What this leaves, in order:**
1. **Write the incoming frame, not the record.** Bloom's DSP code runs before the
   unpack (around the per-block routine's call, sw `0x1c9fbc`) and rewrites
   track t's FREQ word in the received page. Run B already shows the filter
   follows that word, at one block's latency (0.67 ms). The open question is
   only the hook point, so this is **B1b**.
2. **Find what consumes FREQ in the unpack**, with a read watch on the record
   and the engine's filter state. This also says whether a change detector
   gates it.
3. **The fallback stands:** the Bloom filter on IIR0 (B6) becomes the pulsed
   filter.

## B1b, run (2026-10-21): yes. Rewriting the incoming frame moves the stock filter

`scripts/sharc_bloom_b1b.py`: the same verified image and digikit `6f812e99` as
B1. A hook at the unpack's entry, sw `0x1c2712`, where Bloom's own code would
run, rewrites track 0's FREQ word in the received frame page before anything
reads it. The frame carries it in one word, at `0x12c`, FREQ in its high half
at byte `0x12e`.

| run | what changed | RMS of the buffer after the filter, per block 4..9 |
|---|---|---|
| A | nothing (the control) | 0.0411, 0.0405, 0.0368, 0.0374, 0.0405, 0.0400 |
| B | FREQ dark in the frame from block 4 (the reference) | 0.0411, **0.0685, 0.0679, 0.0651, 0.0609, 0.0572** |
| E | the frame open, its FREQ word rewritten dark at the hook from block 4 | 0.0411, **0.0685, 0.0679, 0.0651, 0.0609, 0.0572** |

**E equals B bit for bit, in every sample of every block.** The checks:
- the hook fired once a block;
- the word held the frame's own value before every write, and the dark value
  after it;
- the record at the filter's setup holds the dark value from block 5 in both B
  and E;
- **[E]**, digikit's runner.

**What it settles:**
- **The stock filter can be pulsed from the DSP**, by writing the incoming
  frame's FREQ word per track before the unpack.
- **The latency is one block,** 32 samples or 0.67 ms, the same as a value
  arriving from the ColdFire. That is inaudible for a pulse of 32 Hz or slower.
- **The "setup arm" design is replaced by a pre-unpack hook:** a jump at the
  per-block driver's call (sw `0x1c9fbc`) or at the unpack's entry, into Bloom's
  code, which writes FREQ, pan and VOL for each Bloom track's slot, then
  continues.

**Still open:**
- **Which hook site is cleanest in the image:** the call at `0x1c9fbc`, or the
  unpack's first instructions. Each needs its displaced instructions re-run.
- **Whether pan (89) and VOL (90) behave like FREQ.** They are the same kind of
  frame slot, so they very likely do, but untested.
- **Which voice rows are Bloom tracks** at the hook. The machine type is in the
  same frame, at `148 + 2t`, so the hook can read it from the page it is
  rewriting.

## B2: Bloom at machine type 7 (owner, 2026-10-21), the plan

**Decided: type 7.** A Bloom sound is stored as 7, so on a Waverider build (type
5) it loads as the stock fallback, not as Waverider. Types 5 and 6 are left to
Waverider and to upstream's ONESHOT.

**What type 7 costs beyond a sixth type.** It is the list in
`docs/machine-list.md`, "What a sixth machine actually cost", rows 1-9, with the
type number 7. Two places differ, because the stock tests are `type <= N`:
- **The stored-sound LOAD** (`0x400dd286`, stock `moveq #6`: keeps -1..4).
  Raising it to admit 7 also admits 5 and 6, so a Waverider sound would load
  into a Bloom build as a half-defined type 5. Bloom's LOAD needs a shim
  instead: **keep -1..4 and 7; send 5 and 6 to the stock fallback (FM Tone)**.
- **The name, attribute and page accessors** (`moveq #4` bounds, 12- and
  4-byte rows). Rows for 5 and 6 must exist if the bound is 7. They are
  placeholders that are never offered in MACHINE SEL, with FM Tone's attributes
  and the fallback name, so a stray 5 or 6 reads as FM Tone wherever it
  appears.

**What it builds on.** Upstream's hook bus (`src/dnfw/mods/bus.py`, upstream)
owns the machine-count bounds as one contiguous count, `MACH`, with one
contributor. Two consequences:
- B2 belongs on the bus, not on this fork's pre-bus Waverider edits.
- Type 7 needs either the LOAD shim above or a bus count that allows gaps.

**That needs upstream merged into this branch first.** The merge was attempted
2026-10-21 and is waiting on the owner's go-ahead. Its only conflict is this
file's neighbour `ideas-backlog.md`: upstream already used §35-38, so this
fork's §35-37 become §39-41.

**Done so far:**
- the m68k toolchain is installed (binutils, GCC 13.2);
- `scripts/gen_waverider_code.py` regenerates `waverider_code.json` byte for
  byte (41 edits, 490 B), so this environment reproduces the project's
  ColdFire build.

## Milestones, one question per flash

| | asks | runs on | gates |
|---|---|---|---|
| **B0** ✅ | the reference model: voice, PULSE, DUCK, LINK (`dnfw.bloom`, pure Python) | anywhere | unit tests: phase continuous across chord and rate changes; *land* ends on the downbeat; both directions; *step* edges on the grid; DUCK timing against a trigger mask |
| **B1** ❌ answered **no**; **B1b** ✅ passed (2026-10-21) | **does a setup-arm write of FREQ move the stock filter within the block?** The same for pan and VOL | digikit's SHARC runner, on stock section 7 plus the arm | Multimode output changes in the block of the write. **Control:** no write. If it fails, B6 becomes the pulsed filter |
| B2 | the ColdFire half: the Bloom type through the bus, names, attribute rows, page tables, the song-position writer | ColdFire emulator | MACHINE SEL shows BLOOM and YES commits it; SAVE/LOAD keeps the type; boot from reset; `emu_boot_engine` |
| B3 | the DSP v0: a plain PolyBLEP saw, PULSE on FREQ only, the init sound | SHARC runner | bit-exact against B0; `emu_seqplay` **(upstream)**: the pulse edges against the steps |
| **first flash** | B2 + B3: does the pulse reach the stock filter on the instrument, on the grid? | the instrument | `emu_boot_check` from reset, `emu_boot_engine`, `check_coldfire`, the SHARC gate, `dnfw inspect` 21/21 |
| B4 | the full voice, the chop, pages 1-2 | | as above, plus DSP load |
| B5 | DUCK and LINK | | DUCK against a kick trig in the runner, with a control |
| B6 | the Bloom filter on IIR0, vowel included | | bit-exact against B0, using digikit's IIR0 model **(upstream)** |
| B7 | TILT, MODE land / step, SWNG, PULSE 2, PAN, PDEP | | as above |
| B8 | STAK, VEL, TIME = note length, the page's curve | | DSP load against the owner's rule |

### The first flash's test, written so it cannot be missed

1. Turn the volume down first.
2. Track 1: MACHINE SEL → BLOOM. The init sound is Innerbloom.
3. Filter Lowpass 4, RESO high.
4. Hold a chord, live or as one long trig.

| result | means |
|---|---|
| **pass:** the filter **flutters fast at once**, about 12 a second, and **slows smoothly** to one pulse a second over eight seconds; a new trig starts it fast again | the arm runs, the phase is right, the filter follows |
| a steady flutter that never slows | the glide's time base is not advancing: the song-position writer, or TIME's units |
| it slows in jumps, or clicks | Φ is being restarted, or the rate is stepping |
| a saw, but no flutter | the arm did not run, or wrote the wrong record field: check `+0x1cc` against the build |
| other tracks flutter too | the row-to-track gate is wrong |
| every track goes silent at the first trig | a DSP trap, as Waverider M5's (`docs/waverider-dsp-silence.md`); power off |
| a stuck 750 Hz buzz | a task-level stall; power off |

This goes into the test plan with the image's sha256 before it is flashed.

## What is unverified

- **All of it, as Bloom.** It was read from this repository and from upstream's
  documents. Nothing is built.
- **That the stock filter recomputes its coefficients every block.** B1 asks
  exactly this.
- **The row-to-track reading** of `0xa5a + 2r`, which DUCK and LINK rest on. It
  is a static reading of the frame builder **(upstream)**, not traced for this
  use.
- **The cost of STAK**, and of the voice as a whole. These are estimates until
  measured.
- **How a Bloom sound behaves on a Waverider build** (Packaging, above).
- **Whether 1,500 cutoff updates a second** sound smooth at high resonance and
  32 Hz. Stock LFOs work this way, but this sweep has not been judged by ear.

---

## Superseded: the design of 2026-10-17

**Kept, condensed, because a closed path is still a signal**
(`docs/PRINCIPLES.md`). The full text is in this file's history at `2a67d7d`.

**What it said:** Bloom's voice was Waverider's two-oscillator loop. Its
modulator, PULSE, ran on the **ColdFire**, inside the LFO evaluators
(`0x40137726`, `0x401373dc`), where `lfo4-tick6a` put a fourth LFO aimed at the
filter and passed on the instrument. It wrote FREQ (67) and VOL (90) into the
per-track modulated mirror, the path stock LFOs take. The first build, P0, was
PULSE hard-coded for track 1, with no machine type, no UI and no DSP change.

**Why it changed, 2026-10-18:**
- **The tempo and the song position are now in the frame (upstream).** The
  reason to keep the clock on the ColdFire is gone.
- **The ColdFire's ISR has no room.** It peaks at 74-112 % of a frame on stock,
  and the DSP has about a third free.
- **`lfo4` owns the evaluators,** and the hook bus has no event for them, so a
  PULSE there collides with lfo4.
- **A per-voice accumulator cannot keep a chord's voices together.** A phase
  computed from the shared clock can.
- **Its key argument still stands,** and it is why B1 exists: the stock filter's
  setup runs before any machine renders, so the cutoff must be written **before**
  that setup. The old design did it from the ColdFire. This one does it from a
  setup arm on the DSP, which runs earlier in the same block.
- **Bloom is now its own machine** (owner, 2026-10-18), not Waverider's loop with
  a modulator added.
