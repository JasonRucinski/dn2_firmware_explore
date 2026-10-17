# Waverider's Formant type: the design, before any code

A Formant type on page 5 makes the oscillators sound like a voice that sings a vowel. It is the first Waverider job for the IIR0 accelerator. The owner chose it on 2026-10-17, and also chose to try layout B first, with layout A as the fallback (`docs/sharc-accelerator-plan.md`).

This page sets out the choices that come before the code: the knobs, the filter, and where the accelerator runs. Nothing is built yet.

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

A second probe build, `accelprobe2`, can measure it. Its IIR0 jobs would be 1 biquad on 32 samples, 5 biquads on 32 samples and 5 biquads on 8 samples. A fourth job, one ACM chain of 16 channels of 5 biquads, has the shape of layout A. The differences between the runs separate the setup from the cost of each biquad-sample.

## The choices for the owner

1. **The knobs:** option 1 (the vowel on AMT) or option 2 (the mix on AMT).
2. **The filter:** the cascade (one channel) or the parallel form (five channels).
3. **Measure first:** build and flash `accelprobe2` before the Formant code, or write the Formant code first and measure on it.
