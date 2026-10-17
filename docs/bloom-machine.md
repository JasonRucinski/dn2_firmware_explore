# Bloom: a machine whose filter pulses and slows down

**Opened 2026-10-17**, for the owner of the `JasonRucinski/dn2_firmware_explore`
fork, who wants as a **machine**, not an imitation with stock LFOs, the effect in
RÜFÜS DU SOL's *Innerbloom* at 5:10-5:18. Their description, in short:
- a sustained, warm, saw-based note or chord;
- a **triangle** modulator opening and closing a resonant **low-pass**;
- the modulator's **rate falling** from about 12 Hz to 1 Hz over about 8 s, on
  an exponential curve;
- its **phase continuous**: a change of rate never restarts it;
- the baseline and the depth may drift, so the pulses get brighter or darker;
- reverb and delay make a tail behind dry, defined pulses;
- for a future-bass version, **the same modulator on the volume too**, for a
  near-silent chop.

The important distinction, theirs: *not* the amp envelope and *not* retriggered
notes, but the speed of a modulation oscillator.

"Bloom" is a working name. Grades as elsewhere: **[V]** instrument, **[E]**
emulator, **[D]** read statically, **[O]** open. **Nothing here has been built
or run**. This session has no image, emulator or instrument, so the addresses
are quoted from the documents named beside them.

## The machine, in three parts

| part | what | runs on | built from |
|---|---|---|---|
| **voice** | two detuned band-limited saws, a level each, a brightness | SHARC | Waverider's two-oscillator loop (`reader_m9.asm`, `machine9_live.asm`) **[V]** M9 |
| **PULSE** | the decelerating modulator, into the filter's cutoff and the volume | **ColdFire**, in the LFO evaluators, once per frame | new; the hook is where `lfo4-tick6a` put a fourth LFO **[V]** |
| **filter, amp, FX** | the stock resonant filters, envelope, chorus, delay and reverb | SHARC | stock, untouched |

### Why the modulator runs on the ColdFire, not in the DSP loop

The stock filter takes its coefficients in its **setup**, called through
`0x8052dba4[filter type]` at `0x1c91ad` in the dispatch's common continuation.
That setup runs **before** any machine renders in the block: the type-5 render
hook is at `0x1c9448`, after Swarmer's. It reads the per-track record that the
unpack fills from the frame (`docs/waverider-feasibility.md`, Milestone 4 step
1; `docs/waverider-dsp-silence.md`, "What the setup arms write") **[D]**. A DSP
machine loop therefore can't move the stock filter during a block; it would
have to bring a filter of its own.

The path that already moves the stock filter's cutoff is the one every stock
LFO uses:
- the LFO evaluators on the ColdFire (`0x40137726`, `0x401373dc`) add each
  LFO's output into the track's per-track modulated mirror, at the slot `DEST`
  names (`docs/lfo4-build-plan.md` §5k);
- the frame builder sends that mirror to the DSP every frame.

`lfo4-tick6a` added a fourth LFO inside both evaluators, aimed at Filter BASE
(slot 76), and the owner heard it on the instrument (*"works"*,
`docs/lfo4-build-plan.md`) **[V]**. PULSE goes in the same place and writes:
- **FREQ, slot 67**, by FDEP;
- **VOL, slot 90**, by VDEP (`src/dnfw/waverider/frame.py`).

So the filter is the stock one, with its own RESO and its own type (Multimode,
Lowpass 4, ...), and all three stock LFOs stay free for other work.

**Update rate.** About 1,500 frames a second. A 12 Hz triangle gets 125 steps a
cycle, and 32 Hz gets 47. That's the rate at which every stock LFO already
moves the cutoff, so it's smooth for the filter.

**On the volume,** a hard edge inside one frame clicks: Waverider's free square
did (`docs/waverider-m10-move.md`, M10a). PULSE's square shape therefore slews
over two or three frames, 1.3-2 ms.

### The glide, phase-continuous by construction

Per Bloom track, every frame, with dt = 1/1500 s:

```
t      += dt                           (since the last trig)
u       = min(t / TIME, 1) ^ CURV      (CURV 1 = exponential in Hz)
log2 R  = log2 START + u * (log2 END - log2 START)
phase  += R * dt                       (an accumulator, never reset by R)
m       = shape(phase)                 (-1..+1; triangle by default)
FREQ'   = FREQ + FDEP * m              (into the modulated mirror, clamped)
VOL'    = VOL  * (1 - VDEP * (1 - m') )   (m' = shape mapped to 0..1)
```

- **A trig restarts the glide** (t = 0). **The phase is not reset**, unless
  PHAS is set to RST.
- Over the glide, the number of pulses is TIME·(START-END)/ln(START/END). For
  the brief's 12 → 1 Hz over 8 s, that's **about 35 pulses**, each further
  apart than the last.
- **Arithmetic:** in fixed point, as the rest of this project's ColdFire code
  is. Don't rely on an FPU inside the frame ISR. log2 R maps to an increment
  through a small table, as Waverider's MOVE does on the SHARC (`F[r mod 10] <<
  (r div 10)`, doubling every 10). Here r is fractional, so the rate never
  steps audibly.
- **Tempo:** the ColdFire already has the tempo; its LFOs are tempo-syncable
  (`docs/modulation-matrix.md`, "follow the tempo"). So TIME in bars, and START
  and END as note divisions, are a later option that needs nothing from the DSP.

### The pages

All records are WaveTone's, borrowed as Waverider borrows them, so p-locks, CC,
the LFO destinations and SAVE/LOAD are stock. Ranges and value text go through
M10b's three hooks (the limits getter `0x400dbff0`, and both value-text paths;
`docs/waverider-m10-move.md`). Labels go through the M7 page route
(`docs/waverider-m7-pages.md`).

| | A | B | C | D | E | F | G | H |
|---|---|---|---|---|---|---|---|---|
| **1 VOICE** | TUNE (TUN1) | DETN (TUN2) | LEV1 | LEV2 | TONE (WAV1: the table's brightness) | TBL (TBL1) | - | - |
| **2 PULSE** | STRT (rate at the trig) | END | TIME | CURV | FDEP (±, on FREQ) | VDEP (on VOL) | SHAP (tri, sine, square, pump) | PHAS (FREE / RST) |

- Page 2's records are the eight Waverider uses for MOVE: RATE 240/244, MPOS
  246/250, MLEV 252/256, MOVE 253/257.
- **PULSE reads them from the same per-track mirror the evaluators read the
  LFOs' own parameters from**, so a p-lock or an LFO on any of them works.
- **Brighter and darker** over the phrase is a p-lock or a stock LFO on the
  stock FREQ (the baseline) or on FDEP (the depth).

**Defaults are the brief:**
- STRT 12 Hz, END 1 Hz, TIME 8 s, CURV exponential;
- triangle shape, FDEP about half the range, VDEP 0;
- PHAS FREE.

A default Bloom sound **is** the Innerbloom pulse.

### The voice

Waverider's loop as it is: two oscillators, osc 2 as a detune from osc 1, a
level each, M9's unity-at-100 level. It's on the instrument, and it's the
lightest engine measured (`docs/ideas-backlog.md` §28). TBL 0 (PRIM) at POS 0
is a **32-harmonic saw**, so TONE, which is POS, is the brightness before the
filter.
- **Known limit:** 32 harmonics alias above a fundamental of about 750 Hz,
  and sound thin at the bottom.
- **The later fix:** a saw table whose frames are band-limited an octave apart,
  with the loop choosing the frame from the note. That's a small change to the
  loop, on its own milestone.

## Milestones, one question per flash

| | asks | what's in it | gates (owner's machine) |
|---|---|---|---|
| **P0** | does a decelerating, phase-continuous modulator in the evaluators move the stock filter on the instrument? | PULSE **hard-coded** for track 1, in the shape of `lfo4-tick6a`: 12 → 1 Hz over 8 s, restarted by track 1's trigs, triangle, a large FDEP on FREQ. **No machine type, no UI, no DSP change**, on any stock machine | `emu_boot_check` from reset; **`emu_boot_engine`**, because it touches evaluator A; `check_coldfire`; `dnfw inspect` |
| P1 | the machine | the Bloom type: Waverider's ColdFire plumbing through the shared module (`docs/input-and-drum-machines.md`, Packaging), its DSP loop, both pages, PULSE reading STRT / END / TIME / CURV / FDEP from the borrowed records. A stock machine has no spare records to carry the controls (`docs/ideas-backlog.md` §32), so the controls arrive with the type | the full set, plus a direct-call harness on the evaluator, and the SHARC runner gate, since the voice is Waverider's |
| P2 | the chop | VDEP and the shapes, with the square's slew | as P1 |
| P3 | tempo | TIME in bars, rates as divisions | as P1 |
| P4 | the saw | the key-tracked band-limited table | the SHARC runner against a reference |

### P0's test, written so it can't be missed

1. Turn the volume down first.
2. Track 1: a held chord on any warm machine (Swarmer or WaveTone), filter
   Lowpass 4 or Multimode, FREQ around the middle, RESO up.
3. One trig on step 1, with a long note.
4. Press play.

| result | means |
|---|---|
| **pass:** a fast **flutter** of the filter at once, about 12 a second, which **slows smoothly** to about one pulse a second by eight seconds, and stays there; the next trig starts it fast again | the modulator runs, glides and reaches the filter |
| flutter at a steady rate, never slowing | the glide is not running: t is not advancing, or TIME's units are wrong |
| it slows in jumps, or clicks as it slows | the phase is being reset on a rate change, or r is stepping in whole units |
| no flutter at all | the hook did not run, or the wrong slot was written: check 67 against the build |
| other tracks flutter too | the per-track gate is wrong |
| `EXCEPTION` at boot | should have been caught by the boot gate first. It is the `lfo4-bridge` failure; run the boot check from reset again |

This goes into the test plan with the image's sha256, before it is flashed.

## Where else PULSE fits

It's a per-track modulator keyed on the machine type, so it can be switched on
for other machine types too:
- **the input machine** (`docs/input-and-drum-machines.md` Part A): a slowing
  filter pulse on external audio;
- **the drum sampler**: the same, on a sustained sample.

Each is one more type in its enable test.

## What is unverified

- **Everything above, for this machine.** It was read from this repository's
  documents. Nothing has been built.
- **The order "setup before render" in the dispatch** is read from documented
  addresses, not traced for this question. If it's wrong, a DSP-side
  modulator becomes possible, but the ColdFire route still stands.
- **Where exactly PULSE sits in the evaluators,** and the format of the
  modulation sum it adds into. Both are known for LFOs 1-4 from the LFO4 work,
  and both must be re-read for a fifth source before P0 is written.
- **The ISR budget.** The audio-frame ISR already peaks at 74-112 % of a frame
  on stock (`docs/usbprobe.md`), so PULSE must cost tens of instructions per
  Bloom track per frame, and nothing on any other track. Measure it with the
  usbprobe STATS (`isr_max`, `isr_over`).
- **That 1,500 updates a second sound smooth on a resonant low-pass at high
  RESO.** Stock LFOs work this way, but nobody has judged this specific sweep.
