# The DSP's filter accelerators: FIR0 and IIR0 on the instrument

The ADSP-21569 has two filter accelerators, FIR0 and IIR0. The DN2 1.11 engine never starts either of them. Mods can move filter work onto them, which frees the DSP core for other work. digikit models both (ElekLabs/digikit #111 for IIR0, #112 for FIR0).

The HWR does not give the order of the float operations inside a biquad or inside the four MACs of the FIR. A mod that moves a filter onto an accelerator needs the emulator to match the chip bit for bit. This probe read the order from the chip on 2026-10-17. The models had it wrong in three places, and ElekLabs/digikit#122 corrects them (see "On the instrument").

## The probe build: `accelprobe1-usbprobe`

`scripts/build_accelprobe.py` makes it from stock 1.11:

- section 3: the USB probe on stock (`dnfw.mods.usbprobe`), so a PC can read the result.
- section 7: stock, the idle stub (`dsp.section7_idle_only`), `csrc/waverider/sharc/accel.asm`, its state block and the data of five jobs (`dnfw.waverider.accelprobe`).

No Waverider code is in either processor.

The idle loop's back edge jumps to `accel.asm`, which goes on to the idle stub. Its first call runs the five jobs in order:

| run | accelerator | mode | job |
|---|---|---|---|
| 1, 2 | IIR0 | legacy | 2 biquads, 16 samples a run, Save State: run 2 goes on from the state that run 1 saved |
| 3 | IIR0 | Auto Configuration | 1 biquad, 8 samples, IMASK |
| 4 | FIR0 | legacy | 11 taps, 16 samples |
| 5 | FIR0 | Auto Configuration | 37 taps, 8 samples, IMASK |

The TCBs, coefficients and inputs load with the boot stream into L1 block 1 (`0x2e0000`). The accelerators reach L1 at `0x28000000` plus the DM byte address, as word addresses. The inputs and coefficients are pseudo-random floats with full mantissas, so a different order of rounding changes the outputs.

For each run, `accel.asm` writes CTL1 = 0, reads DMASTAT (a read clears WDONE and ACDONE), writes CHNPTR, then starts the run with CTL1. It polls DMASTAT until ACDONE, for 1,000,000 reads at most. It keeps the EMUCLK cycles from the start to ACDONE, the DMASTAT read and the number of reads.

After that, `accel.asm` publishes 91 words, half a word at a time, through reply word 2 (the ColdFire's `0x800053ac`): the outputs, the saved states, the write-back words and the timings. Each half goes out as `TAG << 16 | HALF`, with `TAG` = the half's index + 1.

## Reading it

    python tools/dn2accel.py --save out/accel_reading.json

The tool reads reply word 2 until it has every half (or 120 seconds pass). It prints each run's timing, and how many of the 76 output and write-back words equal the reference. The reference is the chip's order since 2026-10-17. If some differ, it tries the candidate orders in `accelprobe.IIR_ORDERS` and `accelprobe.FIR_ORDERS` and prints how many words each one matches. `--load` compares a saved reading again, without the instrument.

## Checked in the emulator

`scripts/sharc_accel_check.py --digikit ../digikit-wt-fir0` runs the same section 7 in digikit's SHARC runner, with its peripheral model on. On 2026-10-16 all eight checks passed:

- the idle loop went round 34,727 times, through `accel.asm` each time;
- R0-R7 and I0-I2 held at every exit what they held at the entry;
- every run read ACDONE (the model completes a run at once, so the cycles and reads are 0);
- all 76 output and write-back words equal the reference in the models' order;
- reply word 2 was the same on both pages, and all 182 halves rebuilt the words in memory.

Each candidate order changes between 6 and 34 of the 76 words, so the reading tells the orders apart.

That check compares the runner with the models' old order. Until the runner has the models of ElekLabs/digikit#122, it reports differences against today's reference.

## On the instrument

The owner flashed `accelprobe1-usbprobe` on 2026-10-17, and `tools/dn2accel.py` read all 182 halves. The reading is in `test/accel_reading_2026-10-17.json`, and `test/test_accel_reading.py` checks the reference against it.

All five runs finished. Only 22 of the 76 words equalled the models. Three things were different on the chip:

- **IIR0 adds stored word 5 to the output.** The HWR lists the two stored states of a biquad as Dk2, Dk1. The model used word 6 as the state that feeds the output. Let s1 be word 5 and s2 be word 6. The chip computes y = A0 x + s1 first. Then it computes s1 = (A1 x + s2) + B1 y and s2 = A2 x + B2 y. Each product and each sum rounds to float32. This order matches all 40 outputs and all 4 saved states.
- **FIR0 adds its four sums in pairs**, as (acc0 + acc1) + (acc2 + acc3). This order ("pairs") matches all 24 outputs. The model added the sums one after another.
- **In ACM, the chip writes 0xFFFFFFFF to INIDX and 0 to OUTIDX** in the TCB, on both accelerators. The HWR gives the two values the other way round.

The reference in `accelprobe.expected()` is now the chip's order. The models' old order is the candidate "model".

The time of each run, in core cycles from the start to ACDONE (the core polled about every 30 cycles):

| run | job | cycles |
|---|---|---|
| 1 | IIR0, 2 biquads, 16 samples | 706 |
| 2 | the same, from the saved state | 731 |
| 3 | IIR0 in ACM, 1 biquad, 8 samples | 493 |
| 4 | FIR0, 11 taps, 16 samples | 791 |
| 5 | FIR0 in ACM, 37 taps, 8 samples | 1,344 |

Each time includes the setup of the run, so these five runs do not give a cost per biquad or per tap on their own.
