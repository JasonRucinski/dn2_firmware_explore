# The filter accelerators: what to move onto them first

The ADSP-21569 has two filter accelerators, IIR0 and FIR0. The DN2 1.11 engine uses neither. This page ranks the Waverider work that could run on them, with the costs measured so far. It is a plan for the owner to choose from. No code changes yet.

The probe build `accelprobe1-usbprobe` (PR #226, `docs/sharc-accelerators.md` on its branch) answers the two questions that the plan depends on:

- **The rounding order.** digikit's models of IIR0 and FIR0 pick an order for the float operations. The hardware reference does not give one. A mod that moves a filter onto an accelerator needs the emulator to match the chip bit for bit.
- **The speed.** The hardware reference says that IIR0 runs at the core clock. It gives no cycles for each biquad or each tap. The probe keeps the EMUCLK cycles of each of its five runs.

## What the hardware reference gives

IIR0 (HWR chapter 39):

- Transposed direct form II biquads, 32-bit or 40-bit float, rounding "compatible with SHARC+ core MACs".
- Up to 64 cascaded biquads for each channel.
- Up to 32 channels in legacy mode, any number in Auto Configuration Mode (ACM).
- Windows of 1 to 1,024 samples, and Save State: a channel goes on from the state it saved.
- Local memory for 288 biquads, which the core cannot read.
- IIR0 and FIR0 can run at the same time.

The accelerators reach L1 at `0x28000000` plus the DM byte address, as word addresses. A buffer that the core and an accelerator both use must be in L1. The DM and PM caches do not see DDR writes by another bus master.

## The candidates

The frame is 32 samples. At 1 GHz, that is about 670,000 cycles. The performance doc gives 2,764 cycles for the sub and the noise on one voice, which is 6.6 % of a frame on 16 voices.

| Work | Core cost now | On an accelerator | What it frees |
|---|---|---|---|
| The noise's PNK filters and the tilt (IIR0) | 1,117 cycles per voice and block above WHT (measured). The pink section is 30 instructions a sample, the tilt 10. | PNK's three one-poles and the direct path make one third-order filter. That is two biquads in cascade, then the tilt as a third. BRN is one biquad, then the tilt. | At most about 2.7 % of a frame, with all 16 voices on PNK. Less in any real project. |
| A Formant type on page 5 (IIR0) | Not built. An estimate, not measured: 5 band-pass biquads x 32 samples at about 5 cycles each, about 800 cycles per voice and block. | Five biquads per channel, one channel per voice. | About as much as WARP and FM together with SIMD (828 cycles, measured), for each voice that plays it. |
| A Comb type on page 5 (IIR0 or FIR0) | Not built. | A feedback comb is not a biquad cascade. FIR0 can run a feedforward comb. | Depends on the design. To be measured. |
| Building a pool table's mip levels (FIR0) | 0.16 s of idle time for a 64 x 2048 table. | The decimation filters between levels. | Idle time only: a pool is ready sooner. The frame load does not change. |

The noise's decay envelope changes every sample, so it stays on the core in every option.

## How a voice would use IIR0

The type-5 loop renders one voice at a time, inside stock's chain for each track. An accelerator run that the core waits for saves nothing. Two layouts avoid the wait:

- **A. One block late.** Each voice writes this block's input for the accelerator and mixes in the output of the block before. After the last voice, one ACM run starts with one channel for each voice. It runs while stock renders the other tracks and the FX. The filtered sound is 32 samples (0.67 ms) late. Save State keeps each channel's biquads across blocks.
- **B. Same block, split loop.** The loop writes every voice's input first, starts the run, renders the oscillators, then mixes the filtered output. This has no latency, but it changes the loop's structure and needs the run to end before the mix.

A suits the noise and a Formant type. A note restarts the decay envelope on the core, so the envelope stays on time. The filtered noise is one block late, which nobody can hear in noise.

## What the chip showed (2026-10-17)

The owner flashed `accelprobe1-usbprobe`, and the probe read every word (`docs/sharc-accelerators.md` on #229).

- **The order.** The models had three things wrong. IIR0 adds stored word 5 of a biquad to the output, not word 6. FIR0 adds its four sums in pairs. ElekLabs/digikit#122 corrects both models, and the emulator now matches all 76 words of the chip.
- **The write-back in ACM.** After a window, the chip writes 0xFFFFFFFF to each TCB's INIDX and 0 to its OUTIDX. The HWR gives the two values the other way round. Layout A runs one ACM chain each block, so it writes both words again in every voice's TCB before each run.
- **The speed.** Run 1 did 2 biquads on 16 samples, 32 biquad-samples, in 706 cycles with its setup. So one biquad-sample costs at most 22 cycles. Run 4 did 11 taps on 16 samples in 791 cycles, so one tap-sample costs at most 4.5 cycles. The five runs do not separate the setup from the work, so these are upper bounds.

What the bound means for a Formant type with 5 biquads, on 16 voices:

| | Per frame (32 samples) |
|---|---|
| Biquad-samples | 16 x 5 x 32 = 2,560 |
| IIR0's time, at most | about 56,000 cycles, about 8 % of a frame, beside the core |
| The core's work, estimated | write 32 inputs, write 2 TCB words, mix 32 outputs, for each voice |
| The same filters on the core (the estimate above) | about 12,800 cycles, about 1.9 % of a frame |

IIR0 is slower per biquad than the core's estimate, but it runs beside the core. The core keeps only the copies and the TCB words. With layout A, IIR0 has the rest of the frame to finish, so its time fits in every case.

## The choices for the owner

1. **The first user of IIR0:** the noise, for a small saving now. Or a Formant type on page 5 that runs on IIR0 from the start, a new sound at little core cost. My recommendation is the Formant type: the noise saves at most about 2.7 % of a frame.
2. **The layout:** A (one block late) or B (same block). My recommendation is A for the first user.
3. **FIR0 for the mip levels:** now, or after the first IIR0 user. My recommendation is after, because it frees idle time and not frame load.

The accelprobe1 reading is in, and the models are corrected (see above). The three choices are open.
