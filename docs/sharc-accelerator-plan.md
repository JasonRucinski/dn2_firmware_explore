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

## The choices for the owner

1. **The first user of IIR0:** the noise, for a small saving now. Or a Formant type on page 5 that runs on IIR0 from the start, a new sound at little core cost. My recommendation is the Formant type: the noise saves at most about 2.7 % of a frame.
2. **The layout:** A (one block late) or B (same block). My recommendation is A for the first user.
3. **FIR0 for the mip levels:** now, or after the first IIR0 user. My recommendation is after, because it frees idle time and not frame load.

All three wait for the accelprobe1 reading. If the chip's rounding order differs from the models', the models change first, in digikit.
