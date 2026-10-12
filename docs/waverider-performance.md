# Waverider: performance on the instrument

All readings are from a Digitone II on OS 1.11 through the USB probe: the SHARC's load is
`1 - idle cycles / total cycles` over one-second intervals, and "longest stretch" is the longest
busy period of a frame as a share of a frame (a frame is 1/1500 s). Overruns count busy stretches
longer than a whole frame. The test plan has every run's steps; the entry names are in the
last column.

## Against the factory machines

The same 16-note chord on 16 voices, the same saved project, osc 2, sub and noise on for Waverider.

| Machine | Load (median) | Longest stretch | Overruns | Entry |
|---|---|---|---|---|
| WaveTone | 58.0 % | 61.2 % | 0 | mip2h table, 2026-10-09 |
| FM Tone | 62.9 % | 66.2 % | 0 | mip2h table, 2026-10-09 |
| FM Tone, heavy patch | 63.1 % | 69.2 % (worst) | 0 | mip2h table, 2026-10-09 |
| Waverider, Prim. (mip2h) | 64.6 % | | 0 | waverider-mip2h2-usbprobe |
| Waverider, Prim. (stage 3) | 64.8 % | 68.0 % (max 68.3) | 0 | waverider-stage3d-usbprobe |
| Waverider, 64x2048 table on both | 66.2 % | 69.5 % (max 69.9) | 0 | waverider-stage3d-usbprobe |

With a table of 64 frames of 2048 points the worst stretch leaves about 30 % of a frame free.

## Held over time

| Run | Result |
|---|---|
| 10 minutes, the chord looping on a 64x2048 table, both oscillators | 65.0 % median (64.9 to 65.2), flat across the run; 0 overruns in 600 s; longest stretch median 68.3 %, max 69.6 % |
| Nothing playing, the same project | 63.4 % (63.3 to 63.5) |

The 16 voices render every frame whether a note plays or not, so playing adds under a point.

## What costs what

Per voice and block, measured in the SHARC runner (`scripts/sharc_waverider_p3_cost.py`):

| Part | Cycles per voice per block |
|---|---|
| Sub-oscillator | +742 |
| Noise, WHT | +905 |
| Noise, PNK with a decay | +2,022 |
| Sub and noise together | +2,764 (about 6.6 % of a frame on 16 voices) |
| FM Tone's whole voice, for comparison | +11,113 |

A 64x2048 table cost about 1.4 points more than Prim. on 2026-10-10 with both oscillators on it.
A later read of a table at pool position 4 cost 0.2 points; whether that table was playing is
being checked.

## Building a table

The DSP builds a pool table's mip levels in its spare time after the pool loads: a 64x2048
table takes about 0.16 s, and a pool of 128 is ready a few seconds after the load. While a table
builds, its slot plays Prim.; on a reload the old table plays on and the new one fades in.

## What has not been measured yet

- 4096-point tables on the instrument.
- A soak of 10 minutes or more with Waverider on every voice and an FM Tone track beside it.
- The reload click on the instrument (the runner shows a step of 0.002 of the sine's amplitude,
  from 0.5 before the spare region).
