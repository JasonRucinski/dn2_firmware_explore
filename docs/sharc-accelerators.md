# The DSP's filter accelerators: FIR0 and IIR0 on the instrument

The ADSP-21569 has two filter accelerators, FIR0 and IIR0. The DN2 1.11 engine never starts either of them. Mods can move filter work onto them, which frees the DSP core for other work. digikit models both (ElekLabs/digikit #111 for IIR0, #112 for FIR0).

The HWR does not give the order of the float operations inside a biquad or inside the four MACs of the FIR. Each model picks an order and documents it. Only the silicon can confirm it, and a mod that moves a filter onto an accelerator needs the emulator to match the chip bit for bit.

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

The tool reads reply word 2 until it has every half (or 120 seconds pass). It prints each run's timing, and how many of the 76 output and write-back words equal the models. If some differ, it tries the candidate orders in `accelprobe.IIR_ORDERS` and `accelprobe.FIR_ORDERS` and prints how many words each one matches. `--load` compares a saved reading again, without the instrument.

## Checked in the emulator

`scripts/sharc_accel_check.py --digikit ../digikit-wt-fir0` runs the same section 7 in digikit's SHARC runner, with its peripheral model on. On 2026-10-16 all eight checks passed:

- the idle loop went round 34,727 times, through `accel.asm` each time;
- R0-R7 and I0-I2 held at every exit what they held at the entry;
- every run read ACDONE (the model completes a run at once, so the cycles and reads are 0);
- all 76 output and write-back words equal the reference in the models' order;
- reply word 2 was the same on both pages, and all 182 halves rebuilt the words in memory.

Each candidate order changes between 6 and 34 of the 76 words, so the reading tells the orders apart.

## On the instrument

Not run yet. The test plan has the steps.
