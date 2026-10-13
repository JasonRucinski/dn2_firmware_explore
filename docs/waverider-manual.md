# Waverider, alpha

Waverider is a sixth synth machine for the Digitone II. A Waverider track plays two wavetable
oscillators, a sub-oscillator and a noise generator, with its own modulator (MOVE) that sweeps
each oscillator through its table.

This is an alpha. Sounds you save may not load the same way in a later version. Try it on a new
project, back up the +Drive first, and keep the stock 1.11 firmware file for recovery.

## Before you start

- **Firmware:** Digitone II OS 1.11 only.
- **Combining:** Waverider does not combine with the LFO modulation of the FX, the fourth LFO
  or the FM drum transients mods.
- **Wavetables:** two tables are built in (Prim. and Harm.). More come from DNX, which writes
  them to the +Drive; each project has a pool of up to 128 of them.
- **Recovery:** if the unit does not boot, hold FUNC at power on, open the Early Start-up Menu
  and upgrade with the stock 1.11 file over MIDI DIN.

## Choosing it

Press FUNC + SYN to open MACHINE SEL. WAVERIDER is the fifth entry, after SWARMER. Choose it
and press YES. The SYN key then steps through five pages: the header reads Waverider (1/5) to
(5/5).

## Page 1 and page 2: the oscillators

Both pages have the same controls. Page 1 is oscillator 1, page 2 is oscillator 2.

| Knob | Control | What it does |
|---|---|---|
| A | TUNE (osc 1) / DETN (osc 2) | Pitch in semitones. DETN is the offset from oscillator 1; TUNE moves both |
| B | LEV | Level, 0 to 127. 100 is unity |
| C | POS | Position in the table, 0 to 120 |
| D | TBL | The table: Prim., Harm., then T:001 and up for the pool |
| E | RATE | How fast MOVE runs, 0 to 100. With SYN1 or SYN2 on it reads as a note length |
| F | MLEV | How much MOVE lowers the level, 0 to 127. 0 is none |
| G | MPOS | How far MOVE moves the position, 0 to 100. 50 is none |
| H | MOVE | The shape MOVE follows (eleven, below) |

MOVE shapes: Ramp Up, Ramp Down, Exp Up, Exp Down, Tri Once, Up Loop, Down Loop, Tri Loop,
Square, Rnd Hold, Rnd Glide. The first five stop at their end; the rest repeat.

## Page 3: sub and noise

| Knob | Control | What it does |
|---|---|---|
| A | SUB | Sub-oscillator level, 0 to 127. 0 is off |
| B | OCT | -1, -2 or -3 octaves below the oscillator it follows |
| C | WAVE | SIN, TRI, SQR or PLS (a 25 % pulse) |
| D | SRC | Follows OSC1 or OSC2 |
| E | NOIS | Noise level, 0 to 127. 0 is off |
| F | TYPE | WHT, PNK, BRN or DIG |
| G | COLR | Tilt of the spectrum, -64 to +63. Negative adds low end, positive removes it |
| H | DEC | Decay after each note, 0 to 126 (5 ms to 10 s). Inf holds the noise at full level |

The middle of the page draws the sub and the noise.

## Page 4: sound options

| Knob | Control | What it does |
|---|---|---|
| A | PRST | What the oscillators' phase does on a note: Off, On (restarts at 0, the same note sounds the same each time) or Random |
| B | TRIG | Retrig restarts MOVE on every note; Free lets it run |
| C | DCLK | A crossfade when TBL or POS jumps: Off, or 1 to 100 ms. New sounds start at 3 ms |
| D | TRIM | Output level of the whole machine, -15.0 to 0.0 dB. -11.0 dB is the default, which matches a default WaveTone |
| E | SYN1 | Locks oscillator 1's MOVE to the tempo (Off, On) |
| F | SYN2 | The same for oscillator 2 |
| G | SMT1 | Glide time on oscillator 1's POS. Off at 127 |
| H | SMT2 | The same for oscillator 2 |

The middle of the page shows the track's sound as a scope.

## Page 5: Shape

FOLD, WARP, FM and NPOS on top; TYPE, AMT, P1 and P2 below. They are reserved for the sound
features that come next and **do not change the sound yet**. You can set and p-lock them.

## The wavetable pool

- **Tables:** 1 to 64 frames of 64 to 4096 points each, in powers of two.
- **Names:** the header names the table as you turn TBL, as "T:004 name".
- **Adding and removing:** with DNX, or from the wavetable page (press PRESET/KIT twice) on
  the unit. A project keeps its own pool; CREATE NEW starts with an empty one.
- **While you play:** a table that is being loaded or rebuilt is replaced by Prim. for a moment
  at worst. A reload fades from the old table to the new one over the DCLK time.

## P-locks, LFOs and saving

- **P-locks:** every control on pages 1 to 5 can be p-locked, and the locks stay through a
  reboot and through SAVE and reload. A locked value is shown inverted while you hold its trig.
- **LFO destinations:** every control except Shape's TYPE, AMT and P1 appears in the LFO's
  DEST list, in two groups both headed SYN.

## Going back to stock

To return the unit to what Elektron shipped:

1. In DNX, back up the device, then use **Remove all Waverider data** in Settings. It removes
   every stored table and every pool list from the +Drive and keeps a copy of each table first.
2. Flash the stock 1.11 file over MIDI, as in "Before you start".

Do step 1 first. Stock 1.11 cannot reach the wavetable region, so once it is on, the data stays
where it is. Someone who already flashed stock can flash this build again, remove the data, and
flash stock once more. Your projects, presets, kits and samples are not touched. A project you
saved with Waverider tracks stays on the unit.

## Known limits in this alpha

- Page 5 is inert.
- A pool reload while a note plays on a pool table may click. It has not been measured on the unit; tell us if you hear it.
- 4096-point tables have not been measured on the unit.
- A sound made before page 5 existed shows FOLD, WARP, FM and NPOS at 64.
- The wavetable page in DNX may call a 64x2048 table unplayable. It plays.
- The load on the DSP with a 16-note chord, both oscillators, sub and noise is about 65 %. See
  `docs/waverider-performance.md`.
