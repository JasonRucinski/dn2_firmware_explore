# Waverider's Formant type: the design, and what was built

A Formant type on page 5 makes the oscillators sound like a voice that sings a vowel. It is the first Waverider job for the IIR0 accelerator. The owner chose it on 2026-10-17, and also chose to try layout B first, with layout A as the fallback (`docs/sharc-accelerator-plan.md`).

The sections up to "The choices for the owner" set out the choices before the code, as they stood on 2026-10-17. The last section says what was built in formant2 and why it differs.

## The knobs on page 5

TYPE gets a fourth value, Formant, after Off, Ring and AM. The other three knobs of the shaper row are AMT, P1 and P2. All three store in the sound:

| Knob | Record | Sound slot | An LFO destination |
|---|---|---|---|
| AMT | 261 (MAST) | 48 | yes |
| P1 | 237 | 64 | no |
| P2 | 236 | 63 | no |

Only AMT can take an LFO. A sweep through the vowels is the sound most people want from a formant filter, so the knob that holds the vowel matters.

**Option 1, the vowel on AMT.** AMT moves through the vowels A, E, I, O and U, with a smooth blend between two neighbours. P1 shifts all the formants up or down, from a deep voice to a small one. P2 sets the mix of the dry and the filtered sound. An LFO on AMT sweeps the vowels.

**Option 2, the amount on AMT.** AMT is the mix, as it is the amount for Ring and AM. P1 is the vowel, and P2 is the shift. The vowel cannot take an LFO, so a vowel sweep needs a p-lock on each step.

My recommendation is option 1. It keeps the vowel sweep, and the header names the vowel, so the knob's meaning shows on the screen.

## The filter

A formant filter is usually five band-pass filters side by side, with their outputs added. IIR0 runs its biquads one after another in a channel, not side by side. Two forms fit:

- **Cascade, one channel.** Five resonators in series, as in a cascade formant synthesizer. One IIR0 channel with five biquads does all of it, and the core adds nothing. The shape of each vowel then depends on the five formants together.
- **Parallel, five channels.** Five channels of one biquad each. The core adds the five outputs, 128 additions a block for each voice.

My recommendation is the cascade. It is the form IIR0 runs as it is. The coefficient tables can set each vowel's five formants, but the cascade's shape between them is not the same as the parallel form's.

The filter takes the mix of the two oscillators, after FOLD, the place where Ring and AM work. The sub and the noise add in after it, so they are not filtered.

### The two forms by ear

`scripts/waverider_formant_wav.py` renders both forms on the model's oscillator: table Prim. at POS 0, 110 Hz, the five vowels and then a sweep from A to U. The vowels use the published bass-voice formant values. The script writes `out/waverider/formant/`.

| | Cascade | Parallel |
|---|---|---|
| The spread of loudness across the five vowels | 5 dB | 8 dB |
| The valley between F1 and F2, below the lower of the two peaks (A, E, I, O) | 4.6, 15.0, 16.9, 1.6 dB | 14.9, 31.7, 7.6, 13.8 dB |
| The level of each formant | follows from its frequency and bandwidth | set by the table, one level for each formant |

The parallel form gives deeper valleys between the formants for A, E and O. Each formant stands out more, and the sound is more hollow. The cascade blends formants that are close, so O and U have one strong, round low resonance. Both forms need a gain for each vowel, or a sweep gets louder and quieter. The files ending in `_level` have that gain.

## Layout B on the instrument

The DSP renders the 16 voices one at a time, in stock's chain for each voice. Each voice's amp stage runs after Waverider's loop for that voice: the SHARC runner reads a voice at the amp's input and output (`scripts/sharc_waverider_m5.py`). So the formant result of a voice must be ready before that voice's amp stage. Layout B cannot let the run go on while other voices render.

What layout B can overlap is the same voice's sub and noise. The loop starts the IIR0 run on the oscillators' mix. It renders the sub and the noise while the run goes, then waits for ACDONE and adds the three. The sub and the noise cost 2,764 cycles on one voice (`docs/waverider-performance.md`). With them on, the run can hide behind them. With them off, the core waits for the whole run.

## What we do not know yet

How long one biquad takes on IIR0. The reading of 2026-10-17 gives an upper bound only: run 1 did 32 biquad-samples in 706 cycles, setup included, so at most 22 cycles each. Five biquads on 32 samples are 160 biquad-samples:

| Formant on one voice | Cycles a block |
|---|---|
| On IIR0, at most | 160 x 22 = 3,520, setup included |
| On the core (an estimate, at about 5 cycles a biquad-sample) | about 800 |

IIR0's real cost may be near the bound. Then layout B, with the sub and noise off, makes the core wait longer than the filter takes on the core. Then the core version, or layout A, is the better choice.

A second probe build, `accelprobe2`, can measure it. Its first three IIR0 jobs would be 1 biquad on 32 samples, then 5 biquads on 32 samples, then 5 biquads on 8 samples. A fourth job runs one ACM chain of 16 channels of 5 biquads, as layout A would run it. The differences between the runs separate the setup from the cost of each biquad-sample.

## The choices for the owner

1. **The knobs:** option 1 (the vowel on AMT) or option 2 (the mix on AMT).
2. **The filter:** the cascade (one channel) or the parallel form (five channels).
3. **Measure first:** build and flash `accelprobe2` before the Formant code, or write the Formant code first and measure on it.

## What was built (formant2)

The owner chose the vowel on AMT (option 1), the cascade, and layout A after the accelprobe2 reading. Layout A did not fit, so the DSP runs a layout of its own.

### One voice late, not one block late

Layout A needs a block of input and output for every voice in L1, about 7.3 KB. Waverider's L1 region had no room left. formant.asm starts IIR0 on a voice after FOLD. It collects the result at the next voice's FOLD, or at the loop's end. The sub, the noise and the next voice run while IIR0 works. One block of 32 samples in L1 serves every voice, and the voice comes out with no delay.

| Part | Where |
|---|---|
| formant.asm (1,560 bytes) | L1, DM 0x2e7000 (sw 0x173800) |
| 16 voices' coefficients and states, the block IIR0 filters in place, the TCB | L1, 0x2e7660..0x2e7fe4 |
| The vowel table, P1's ratios, the level table, each voice's state | DDR, 0x8070a000..0x8070b000 |

### The coefficients each block

The DSP computes each voice's five biquads in float32, in forms it can repeat bit for bit. exp and cos are short polynomials, and the level comes from a table of 33 x 9 points. They are within 2.4e-7 of the exact forms (0.0011 dB in the response). When the vowel and P1 have not moved since the last block, the DSP writes nothing: a held sound costs 29 instructions a block, not about 420.

### Two fixes after the first test on the instrument

The owner tested formant1 on 2026-10-17.

- **A crackle that followed AMT and P1.** When the coefficients change, IIR0's saved states still hold the old ones for one sample. On a strong low partial, that is a one-sample step, and the high formants ring with it at 3 to 5 kHz. The DSP now rebuilds the states from the two past outputs, with the new coefficients, as a direct-form filter does. AMT also follows the knob by an eighth of the distance a block (90 % in 12 ms). Before, it moved by at most 0.125 a block.

  The test is a 1 s sweep on a dark source. The energy at 2.5 to 5 kHz falls from -40.6 to -57 dB of the total (AMT), and from -42.1 to -78 dB (P1). With the knob held, it is about -88 dB.
- **A crackle on a 16-voice unison.** The level made every vowel as loud as A, but A is 7.83 dB above the dry source. The Formant's peaks were 10 to 13 dB above the plain sound's, and 16 voices in unison drove the mix past full scale. The level now makes each vowel about as loud as the dry source. The peaks are now 2 to 6 dB above the plain sound, and the loudness is within -5 to +3 dB of it.

On formant1, the probe read the DSP load with 16 such voices, with noise, FOLD, WARP and Formant on each. It read 66.8 % on average and 70.1 % at worst in one frame, with no frame missed.
