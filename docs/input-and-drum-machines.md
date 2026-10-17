# Two new machines: an input machine and a drum sampler

**Opened 2026-10-17**, for the owner of the `JasonRucinski/dn2_firmware_explore`
fork, who asked to use this project to build a new DN2 machine "much like the
Waverider machine". In their words, the hope is twofold:

> *"I want a way to modify the input audio, similar to Machinedrum's input
> machines, and also I want a way to make sampled or sample-like drums. The
> drums on DN2 are sad and I need something better."*

**Two decisions taken with it (fork owner, 2026-10-17):**

- **A standalone mod with its own type 5**, not combined with Waverider. The two
  mods exclude each other in `dnfw mods matrix`.
- **The gates and builds run on the owner's own machine** (WSL, digikit,
  selache, their own OS file; `docs/emulator.md`). This document and the offline
  pieces are written in a cloud session that has none of those, so **nothing in
  it has been run against an image**. Every address below is quoted from the
  document named beside it, not re-measured.

Grades, as elsewhere: **[V]** on the instrument, **[E]** measured in an emulator,
**[D]** read statically, **[S]** second-hand (a manual or a third party, not read
here), **[O]** open.

## In one paragraph

Both machines are the **same shape as Waverider**. A sixth machine type is
offered by MACHINE SEL. It is WaveTone to the ColdFire's UI and our own render
loop to the SHARC. Everything downstream of the machine is stock: the per-track
filter, the amp envelope, the FX sends, the LFOs and the p-locks. Almost all of
the ColdFire half and the DSP plumbing exists and has passed on the instrument.
What is new is **one render loop each**.
- **The input machine's loop is trivial.** It copies the input into the track's
  buffer. Its one real unknown is where the analog input lands in SHARC memory,
  and the cheapest test for that is read-only, on a usbprobe build.
- **The drum sampler's loop is a one-shot sample player.** The stock DSP image
  already loads a user-replaceable bank of PCM into DDR: 34 entries of 100 ms,
  3.4 s in all. The `transients` mod already rewrites that bank, confirmed on
  hardware. So a first drum sampler needs **no new storage path at all**.

## What carries over from Waverider

| piece | Waverider's version | grade there | doc |
|---|---|---|---|
| MACHINE SEL list, row group, names, attribute rows, the permission test, the stored-sound LOAD bound | `dnfw.waverider.coldfire`, 31 edits in four clean caves | **[V]** M5b onwards | `docs/machine-list.md`, "What a sixth machine actually cost" rows 1-9 |
| type 5 is WaveTone to the UI: `param_set_slot_to_id`, the SYN page tables, `getMachineType`, the sound's parameter-ownership test | the same module | **[V]** | same, and "The double YES" for the tail `jmp` at `0x40031394` |
| its own SYN pages, labels and the page draw | `dnfw.waverider.pages`, `csrc/waverider/page.c`, one platform `CODE` chunk | **[V]** M7-M10 | `docs/waverider-m7-pages.md` |
| the DSP entry: `JUMP` at sw `0x1c9448`, after Swarmer's loop; the lookup `0x25d748[5] = 5` | `dnfw.waverider.dsp` | **[V]** M5c onwards | `docs/waverider-m5-dsp.md` |
| where our DSP code and state may live: **L1 block 1's free tail**, byte `0x2dd600..0x2e7000` | same | **[V]** | `docs/waverider-dsp-silence.md` (block 2 is the PM cache's) |
| reading the knobs: slot s of track t at `168 + 2s + 146t` in the unpack's frame copy `0x25c48c`, **at half the sound's value** | `machine9_live.asm` | **[V]** | `docs/waverider-m9-oscillators.md`, `docs/waverider-m5-dsp.md` correction 5 |
| a level control that is exactly unity at its default (`LEV x 1/25600`, 1.0 at 100) | `reader_m9.asm` | **[V]** M9a | `docs/waverider-m9-oscillators.md` |
| the trig: the note mask at frame offset 34, bit t | `modulator.asm` | **[V]** M10a | `docs/waverider-m10-move.md` |
| a value reported back to the ColdFire through the reply's unused tail (`+0xa9c`) | M10b-3 | **[V]** | `docs/waverider-m10-move.md` |
| the gates: boot from reset, engine + SAVE/LOAD, `check_coldfire`, the SHARC runner against a Python reference, `dnfw inspect` | `scripts/emu_boot_check.py`, `emu_boot_engine.py`, `sharc_waverider_m5.py` | | README, "How a change is checked" |

**Traps already paid for, which must not be paid for again:**

- **L1 block 2 is the PM data cache's**, not free memory. Code placed there
  silenced the instrument for a week of discriminator flashes
  (`docs/waverider-dsp-silence.md`). Use block 1's tail.
- **The frame carries every slot at half scale.** M5 first shipped with the
  sound's scale and would never have played table 1.
- **`getMachineType` is reached by a tail `jmp`, too**, not only by `jsr`. An
  identity audit that searches for calls misses it (`docs/machine-list.md`,
  "The double YES").
- **A snapshot is not a boot.** `ui1200M` has MACHINE SEL's rows built from the
  stock list. Use `boot400M` with the build patched in, and boot from reset
  before any flash.
- **A demonstration must be obvious within a bar** (`docs/FEATURE-PLAYBOOK.md`).

## Packaging: one standalone mod, two types

"Standalone, own type 5" and "two machines" pull in different directions. Two
separate type-5 mods would exclude each other as well as Waverider, so the
instrument could run either the input machine or the drums, never both.

**Proposed:** one mod, say `machines` (name to be chosen), which carries **the
first machine at type 5 and the second at type 6** (`docs/waverider-feasibility.md`,
"Room for a seventh machine", has the per-row cost of a seventh type). It stays
standalone from Waverider, as decided.
- **What it inherits from Waverider's matrix row:** it is refused with `lfo4`
  (the stored-sound LOAD bound), `fxmod` (`param_set_slot_to_id`) and
  `transients` (section 7). The drum sampler takes over `transients`' job
  anyway; see Part B.
- **Type 6 upstream is reserved for ONESHOT**, which the upstream owner develops
  locally (`docs/dt2-machine-port.md`, banner). This doesn't matter while the
  mod excludes Waverider. It would matter if the machines were ever offered
  upstream, and that's a conversation to have before then.
- **A sound saved with either machine loads as FM Tone** on stock and on any
  build without this mod (the stock LOAD bound's fallback, `0x400dd286`).

**The ColdFire half should be shared, not copied** (`docs/PRINCIPLES.md` §2 and
§4). `dnfw.waverider.coldfire` hard-codes `NEW_TYPE = 5`, `CLONE = 1`, the list,
the names and the caves. Most of it is "add machine type N as a clone of
machine C for the UI". The first code step is to lift that into a module of its
own (`dnfw.machine`, say), parameterised by name, short name, clone and type.
Then rebuild Waverider through it.
- **The proof of a pure refactor is that `waverider_code.json` regenerates byte
  for byte**, and `waverider-m10b3` keeps its sha256.
- `scripts/gen_waverider_code.py` needs the stock MAIN OS and the m68k
  toolchain. So this step runs on the owner's machine.

---

# Part A: the input machine

## What it is

**The model [S]:** the Machinedrum's input machines take the external inputs
and play them through a track. Trigs gate the input through the track's
envelope, and the track's filter, effects, LFOs and parameter locks shape it.
Cited from general knowledge of that instrument, not from its manual. **Before
the page layout is fixed, read the manual's input-machine section and cite it
in our own words**, as Waverider cites Tonverk's.

**On the DN2 this is almost free downstream.** A type-5 track's machine stage
writes one float block per track (`0x804acf90 + 0x80 x t`, 32 samples;
`docs/sharc-voice-path.md` **[E]**). Everything after it is stock:
- the multimode filter and the amp envelope, so a trig opens the input and the
  ADSR shapes it;
- overdrive, the track's level and pan, and the chorus, delay and reverb sends;
- LFOs and p-locks on every one of those;
- conditional trigs, retrigs and probability, from the sequencer.

**The render loop:**
1. read the 32 frames of the input that the DMA has finished;
2. pick L, R or (L+R)/2;
3. convert to float and multiply by the gain;
4. store into the track's block.

That's a handful of instructions a sample. For scale, Waverider's note costs
~720 instructions a block in the emulator, and a stock engine 8,000 to 11,000
(`docs/ideas-backlog.md` §28). The owner's DSP rule is not at risk.

**Mono per track.** A track's buffer is mono, so stereo input processing is two
tracks, one on L and one on R, panned apart.

## The eight layers (`docs/FEATURE-PLAYBOOK.md` §1)

| # | layer | what this machine needs | cost |
|---|---|---|---|
| 1 | parameter records | none new: two of WaveTone's records Waverider doesn't need (GAIN on LEV1, slot 30; SRC on a record whose range covers three values) | reuse |
| 2 | enumeration | WaveTone's, unchanged | none |
| 3 | classifier | the ownership canonicalisation (`docs/machine-list.md` row 9) | reuse |
| 4 | slot space | WaveTone's slots 25..64 | none |
| 5 | **engine** | **the copy loop; the input ring's address is the unknown** | **I0 + I1** |
| 6 | serialization | the LOAD bound (row 5) | reuse |
| 7 | page view | first flash: none (WaveTone's page, two knobs live). Later: a page of its own, through the M7 route | reuse |
| 8 | navigation | the MACHINE SEL list and its row group (rows 1-2) | reuse |

## The one real unknown: where the analog input lands on the SHARC

| evidence | says | grade |
|---|---|---|
| the board's codec is an **AKM AK4621** (U14) | the analog in and out are the codec's | **[D]** `docs/hardware.md` |
| the SSI0 link `0x4E6DF100` / `0x4E6E0100` is **ColdFire <-> SHARC**: into the SHARC it carries **USB audio** (zeroed each frame unless a USB input streams, flag `0x80005366`), out of it the DSP's own output | **the analog input is not on the ColdFire's side at all**; it reaches the SHARC directly | **[D]** `docs/audio-dma.md`, `docs/usbprobe.md` |
| the DAC ring: `sw 0x1c9d3f` converts the master mix `0x268438` (L 32 floats, R `+0x80`) into the page `0x2c0478 + (DM(0x268a38) << 8)`, two 256-byte pages of 32 stereo frames, descriptors built at sw `0x1ca167` | the output's shape: 32 frames, two pages, ping-pong | **[D]**, consistent with the 750 Hz replay **[V]**; `docs/waverider-dsp-silence.md`, `docs/waverider-dsp-compare.md` §4 |
| the driver's listing at sw `0x1c9e76` names the next pair, **`0x2c0678..`**, beside the DAC pages, and 2 KB pages `0x2c08e8 + (page << 11)` that match SSI0's 32 x 64-byte TDM half-buffer | **hypothesis: `0x2c0678 + (page << 8)` is the ADC ring**, the same shape as the DAC's | **[D] hypothesis only** |
| the ext-in mixer's records are ids 132-148 in group 21 (slots 49-59 of the FX block): Input Level, Volume, Pan, the three sends, Dual Mono | stock code on the SHARC reads the input to mix it; **its consumer locates the ring** | **[D]** `docs/fx-master-modulation.md`; the consumer is **[O]** |
| the reply carries, from `+0x1c`, 32 records of 28 three-byte channels, "the per-track stream Overbridge carries; not confirmed channel by channel" | if one channel is the input, a stock + usbprobe build finds it without any DSP change | **[D]** `tools/dn2reply_audio.py` |

### Milestone I0: find the input (three routes, cheapest first)

**(a) On the instrument, read-only, no DSP change.**
1. Flash a **stock + `usbprobe`** image,
   `dnfw mods apply <OS zip> --mod usbprobe -o 00_Resources/02_Builds/usbprobe-input_DN2_1.11.syx`.
   That mod is read-only and has been on the instrument many times.
2. Run `python tools/dn2reply_audio.py no-input --n 40` with nothing plugged in.
3. Feed a steady tone into IN L only, and run it again as `input-l`. Then IN R
   only, as `input-r`.
- **A pass:** a channel that is zero for `no-input` and carries the tone for
  `input-l` (and a different one for `input-r`) is the input, as the SHARC sees
  it. That leads back to the code that writes it into the reply, and so to the
  ring.
- **Its disproof:** no channel moves with the input. The reply doesn't carry
  the input, and route (b) decides. That is a statement about the reply, not
  about the input.
- **Control:** a synth track playing must move its own channel in the same
  runs, or the tool, not the input, is what didn't move.

**(b) Statically, on section 7.** Read the descriptor build next to the DAC's
at sw `0x1ca167`. An RX pair whose `ADDRSTART`s are `0x2c0678` and the next
page settles the hypothesis. Then find the stock code that reads it: it is the
ext-in mixer, and it shows the sample format (24-bit left-justified, or
already float) and which page index is current. selache's `seld`, and
`scripts/sharc_callgraph.py` for the reach set.

**(c) In digikit's SHARC runner.** The runner models no SPORT DMA
(`docs/waverider-dsp-silence.md`), so the ring holds whatever is poked into
it.
1. Poke a marker into the candidate page.
2. Run a block with Input Level up.
3. Look for the marker in the master mix at `0x268438`.
- **Control:** Input Level 0, which must remove it.

This confirms both the ring and the current page, offline.

### Milestone I1: the loop, offline

A type-5 loop (`csrc/<machine>/sharc/`), the shape of `machine9_live.asm`, with
the reader call replaced by the copy:
- the page index read the way the stock consumer reads it;
- SRC and GAIN read from the frame (half scale);
- GAIN as M9a's LEV, so 100 is exactly unity.

**The gate** is a script in the shape of `sharc_waverider_m5.py`:
- the runner, with a known signal poked into the ring, against a Python
  reference;
- bit-exact at the track buffer;
- audible at the amp, with a trig;
- silent with no trig;
- types 0-4 bit-identical to stock.

### Milestone I2: the first flash, and what a pass looks like

**The ColdFire half** is Waverider M5b's edits through the shared module, with
the name changed. Only one question goes into this flash: **does the input
reach a track?** SRC is fixed to (L+R)/2 here, and GAIN is the only live knob.

**The test, written so it cannot be missed:**
1. Turn the volume down first.
2. In MIXER, set the external input's level to 0. Then what is heard is the
   track, not the stock dry path.
3. Plug a sustained source, a synth pad or a phone playing music, into IN L/R.
4. Track 1: MACHINE SEL -> INPUT. AMP: attack 0, decay short, sustain 0.
5. Program trigs on all 16 steps and press play.

| result | means |
|---|---|
| **pass:** the input is heard **chopped into sixteenth notes** by the track's own envelope, and turning the FILTER frequency down darkens it | the input reaches the track, and the stock chain shapes it |
| the input is heard steady, not chopped | the stock dry path is still up (step 2), not our track |
| track 1 silent, other tracks play | wrong ring, wrong page or wrong format (zeros) |
| a loud harsh noise | the format is wrong: integer read as float, or the shift is wrong |
| every track goes silent at the first trig | a DSP trap, as Waverider M5 (`docs/waverider-dsp-silence.md`); power off |
| a stuck 750 Hz buzz | a task-level stall; power off |

This goes into the test plan before it is flashed, with the image's sha256.

### Later, each its own flash

- **SRC:** L, R, (L+R)/2 and, cheaply, **USB in**, which already arrives on
  the SSI0 link.
- **Its own SYN page**, through the M7 route: SRC, GAIN, and a gate threshold,
  which needs a follower in the loop.
- **An envelope follower as a modulation source:** the input's level drives
  the filter, or another track.
  - The LFOs and the modulation apply run on the ColdFire
    (`docs/engine-state.md`), so the follower's value has to cross back through
    the reply, as M10b-3's MOVE report does.
  - Its consumer on the ColdFire side is new work.
- **Voices.** The DSP's 16 per-track passes are voice slots: a trig plays on
  the next voice (`docs/waverider-m10-move.md`). A polyphonic input track would
  copy the input into several voices at once and sum it louder. The first
  flash should say "set the track to one voice", and a later one should render
  only the newest voice.

### Risks

- **Latency:** one or two 32-sample blocks (0.7-1.3 ms), plus the codec's own.
- **Feedback,** if the DN2's output is patched back into its input.
- **The stock dry path** still mixes the input unless its level is down. That
  is a page note, not a bug.
- **[O]** whether the ADC runs at all while the stock input level is 0.

---

# Part B: the drums

## The ask, and the options

"Sampled or sample-like." Five routes, by what each needs:

| route | what plays | where the sound comes from | new storage path | cost | risk |
|---|---|---|---|---|---|
| **B1. a sampler on the transient bank** | our one-shot player | **the stock transient bank in DDR**: 34 x 4,800 int16, 48 kHz, contiguous, **3.4 s** | **none**: the stock boot stream loads it; `transients` rewrites it in place (**[V]** 2026-09-14) | a player + a kit packer | the bank is FM Drum's too |
| B2. a larger baked bank | the same player | more DDR load blocks in section 7 | the boot stream already loads DDR | small | section 7's 1 MB ceiling (below) |
| B3. a `+Drive` sample pool | the same player | user files, preloaded into DDR at project load | **the expensive one**: a superblock, a loader, DNX's format | weeks | `docs/drive-storage-research.md` |
| B4. synthesised drums | analog-style models (kick, snare, hats, clap, toms) | arithmetic, no data | none | a model per drum, tuned by ear | the sound is ours to get right |
| B5. port the DT2's ONESHOT | Elektron's player (6-tap, 256-phase polyphase at 96 kHz, a 2:1 decimator) | as B1-B3 | as B1-B3 | needs the DT2 OS as donor, at apply time | upstream's local work; coordinate first |

**Recommended: B1, then B2, with B3 as the destination and B4 as a later
layer.** B1 reaches the instrument with real samples soonest, because none of
its delivery is new. The player reads the bank through a small directory, as
Waverider reads its tables. So B2 and B3 change where the bank lives, and
nothing in the player. A synthesised body under a sample, B4, is a natural
addition once samples play.

## B1: what the bank already gives

| | | grade |
|---|---|---|
| address | DDR `0x8045c380`, 34 entries of 4,800 samples, int16 little-endian, mono, 48 kHz | **[V]** `src/dnfw/mods/transients.py`, `docs/pcm-hunt.md` §16 |
| delivery | loaded by the **stock** boot stream: two payload blocks with a fill block between them | **[V]**, `dnfw.image.bootstream.spans` |
| replacement | in place, whole entries, by `transients` | **[V]** markers played back from `TRAN` |
| reach from FM Drum | `TRAN = 4 x slot - 8`: slots 2..33 | **[V]** `docs/tran-mapping.md` |
| reach from our player | **all 34**: it reads the bank, not `TRAN` | by construction |

**3.4 s is close to a kit.** For example, at 100 ms a slot:

| sound | length | slots |
|---|---|---|
| kick | 0.5 s | 5 |
| snare | 0.4 s | 4 |
| clap | 0.4 s | 4 |
| closed hat | 0.1 s | 1 |
| open hat | 0.6 s | 6 |
| low tom | 0.4 s | 4 |
| high tom | 0.3 s | 3 |
| rim | 0.1 s | 1 |
| short cymbal | 0.6 s | 6 |
| **total** | **3.4 s** | **34** |

A sample may span consecutive slots. The kit packer lays the kit out and writes
a directory of `{start, length}`. That directory sits in our own block-1 span,
as Waverider's table directory does.

**The cost:** FM Drum's `TRAN` now selects slices of the kit. That's accepted
here, since the point is to replace FM Drum's drums. The packer is
`transients`' own preparation (resample, mono, int16, truncation reported),
used, not copied (`docs/PRINCIPLES.md` §4).

**The samples are the user's own** and never enter the repository. Test
fixtures are synthetic, as everywhere here.

## The voice

A one-shot player per voice:
- on a trig, the position restarts at STRT;
- each sample: step by an increment from TUNE, read with linear interpolation
  (Waverider's reader), apply the level;
- stop at the end of the sample or at LEN, with a short declick ramp;
- REV plays backwards.

That's about a dozen instructions a sample a voice, to be measured. Pitch
follows TUNE, with an option to follow the note.

**Upgrade to 4-point interpolation if pitching down audibly aliases.** B5's
polyphase design is the reference for "good".

**The win over FM Drum** is the sequencer, not the engine. SAMP is a parameter,
so it can be **p-locked per step**. **One track plays a whole kit**, as sample
locks do on a Digitakt, through the stock per-track filter, envelope, FX,
LFOs and conditional trigs.

**Parameters on borrowed WaveTone records** (layer 1, as Waverider M9/M10 did):

| control | candidate record | note |
|---|---|---|
| SAMP | needs a range of at least the kit's size | **WaveTone's `TBL1` is 0..1** (PRIM / HARM). Use a wider record (`WAV1`, 0..120), or widen TBL1's limits as M10b widened MOVE (the limits getter and both value-text paths) |
| TUNE | `TUN1` (238, slot 25, ±60 st, default `0x4000`) | as Waverider |
| STRT, LEN | from the records M10 used for RATE / MPOS (slots 28/29, 34/35) | ranges and value text to be checked per record |
| LEV | `LEV1` (241, slot 30), M9a's unity-at-100 | as Waverider |
| REV | a small enumerated record: Waverider's TRIG (259, slot 46, values 0..2, shown as Retrig / Free since M10b) | its value text would need REV's own names |

## Milestones

| | what | where it runs | depends on |
|---|---|---|---|
| **D0** | `dnfw.drumkit` (name to be chosen): the kit packer (WAVs -> the 34-entry layout + directory) and a Python reference player that renders WAV previews of a kit and a p-locked pattern. **Audition it before any DSP work** | **anywhere, no firmware needed**: pure Python, synthetic-fixture tests | nothing |
| D1 | the SHARC player, in our block-1 span, gated in digikit's runner against D0's reference: bit-exact at the track buffer, audible at the amp, silent without a trig, other types bit-identical | owner's machine | D0 |
| D2 | the first flash: type 5 (or 6) as a clone of WaveTone, SAMP + TUNE + LEV live, the kit written into the bank | owner's machine | D1, the shared ColdFire module |
| D3 | its own SYN page (M7 route), STRT / LEN / REV | owner's machine | D2 |
| D4 | B2: more DDR load blocks in section 7 | owner's machine | D2 |
| D5 | B3: the `+Drive` pool | weeks; DNX for the format | D4 |

**D2's test:**
1. Pack a kit whose sounds are unmistakable: a kick, a snare, a hat.
2. Program track 1 four-on-the-floor, with SAMP p-locked to the snare on steps
   5 and 13 and to the hat on every odd step.
- **A pass** is a recognisable drum pattern within one bar.
- **A failure** looks like Waverider M5's: silence everywhere at the first
  trig, or a buzz. Power off in either case.

**D4's ceiling.** The ColdFire's uploader (`0x400cf34c`) reads section 7 into a
**1 MB** buffer (`docs/for-digikit-coldfire-sharc-link.md` **[D]**). The stock
section is 836,956 bytes, so about 200 KB, **~2 s more at 16-bit mono**, fits
without touching the ColdFire.
- Whether that 1 MB is one immediate that can be raised (25.3 MB of SDRAM is
  free, `docs/memory-map.md`) is **[O]**.
- So is how much longer the SPI upload makes the boot.
- The DSP's DDR is not the limit: the stock image uses about 5.4 MB of it
  (`docs/sharc-image.md`), and around 500 MB is probably unused
  (`docs/drive-storage-research.md` **[D]**).

---

# The order, and the first steps

**Recommended:**
1. **I0(a)** (one read-only flash, existing tools) and **D0** (offline), in
   parallel. Neither touches the DSP.
2. **The shared ColdFire module**, proven by Waverider regenerating byte for
   byte.
3. **I1, I2: the input machine first.** Its loop is the smallest possible DSP
   change, so its first flash tests the standalone mod's plumbing with almost
   nothing else in it, one question.
4. **D1, D2,** on plumbing that has then been on the instrument.

**On the owner's machine before step 1:**
- the setup in `docs/emulator.md`: WSL, digikit at the recorded revision with
  the patched Unicorn, the venv in WSL's own filesystem, and the snapshots;
- selache built in WSL (`docs/sharc-selache.md`);
- the Digitone II 1.11 OS zip in `00_Resources/00_Firmware/`. It is gitignored;
  never commit it.
- `pytest -m "not slow"` green;
- `scripts/emu_boot_check.py` booting stock **and** `waverider-m10b3` from
  reset, which proves the toolchain before it is trusted on anything new.

## What is unverified

- **Everything above, as it applies to these two machines.** It was read from
  this repository's documents in a session with no image, emulator or
  instrument. Nothing has been built.
- **The ADC ring at `0x2c0678`** is a hypothesis from the shape of a driver
  listing. I0 exists to settle it.
- **Whether the reply carries the input** is open; I0(a) answers it.
- **The Machinedrum description** is second-hand **[S]**, until it is read
  from that manual.
- **The per-voice cost of the player** is an estimate. Measure it with the
  emulator's instruction counts and `tools/dn2sharc_load.py`, mindful that word
  0 misreads around our tracks (`docs/sharc-load.md`).
- **The record ranges proposed for SAMP, STRT and LEN** are to be checked per
  record before D2.
