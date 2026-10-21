# Waverider level trim: TRIM on page 4

A default Waverider was about 11 dB louder than a default WaveTone. TRIM is a knob that sets
Waverider's output level, with a default that matches WaveTone and a range of -15 dB to 0 dB.

## What was measured (2026-10-12, the instrument, `waverider-stage3d`)

One pattern of 64 steps at 120 BPM: default Waverider on track 1, default WaveTone on track 2,
both at track level 100, the same oscillator values (TUNE 0, LEV 100, DETN 0). Read from the
SSI0 window (`tools/dn2tdm_audio.py`'s window, sampled for 24 s):

| | Waverider (track 1) | WaveTone (track 2) | difference |
|---|---|---|---|
| track tap, peak | -7.8 dBFS | -22.4 dBFS | +14.6 dB |
| track tap, median RMS | -16.7 dBFS | -27.8 dBFS | +11.1 dB |
| main mix with only that track sounding, peak | -14.1 dBFS | -28.4 dBFS | +14.3 dB |
| main mix with only that track sounding, median RMS | -20.6 dBFS | -31.9 dBFS | +11.3 dB |

On the headphones with MAIN VOLUME all the way left, a default WaveTone is silent and a default
Waverider is faintly audible: the knob's residual, with Waverider 11 dB over it.

**Why:** the oscillator reader's gain is LEV x f32(1/25600), so LEV 100 is exactly 1.0 and one
oscillator peaks at full scale (0 dBFS before the amp stage, measured in the runner by
`scripts/sharc_waverider_level.py`). The sub and the noise use the same constant. Two equal
oscillators add 6 dB. WaveTone's own oscillators sit about 11 dB lower at the same setting.

## The knob

- **Where:** page 4, place D (it was empty), label TRIM; record 262, WaveTone's FINE, sound slot
  49. It is the last free sound slot (`docs/waverider-shape.md` has the rest).
- **Range:** -15.0 dB to 0.0 dB, shown as dB in the header ("Level Trim=-11.0 dB").
- **Default:** -11 dB, at the record's stock default (centre, 0x4000). A sound that never had the
  knob holds that value already, so every existing sound moves to -11 dB with no re-default.
- **Steps:** 64 factors, the knob's coarse byte >> 1: linear in dB, 4 dB over the lower 32 steps
  (0.125 dB each) and 11 dB over the upper 31 (0.35 dB each).
- **Like any knob:** it stores, p-locks and takes an LFO.
- **What it scales:** the two oscillators, the sub and the noise, by the same factor, so their
  proportions are unchanged.

## How it is done

- `csrc/waverider/sharc/trim.asm` (sw 0x170100): once per voice and oscillator, before the
  modulator, it reads the voice's FINE word from the frame copy, indexes the 64 factors at DM
  0x2e0300 (`live.trim_table`, f32(10^(dB/20) / 25600)), and stores the factor at DM 0x2de6c8.
- The three places that formed `LEV x f32(1/25600)` (the loop, `sub.asm`, `noise.asm`) load
  that word in place of the constant: same instruction size, so no label moved. The loop's jump
  to the modulator goes through `trim.asm`, which jumps on to it.
- `dnfw.waverider.live.gain(level, trim)` is the model the gates compare against.
- ColdFire: `pages.TRIM_ID`, its label and name, `RANGES[262]`, a dB text formatter
  (`trim_text` in `page.c`, the same steps as `live.trim_db`).

## The slew (0.1.2, 2026-10-17)

A user reported clicks when TRIM moved while a stock table played. The gain changed once a
block, in one step, so a fast turn changed the level by several dB between two samples.

- **What the emulator showed:** a turn of TRIM changes only the TRIM word of each voice in the
  ColdFire's frame (offset 266 + 146t). The note words and every other byte stay as they were,
  as for the control, DCLK on the same page (`scripts/emu_trim_frames.py`). So the click is in
  the DSP.
- **The change:** `trim.asm` keeps the factor that each voice and oscillator used in the last
  block, in word 8 of DCLK's state (DM 0x2e1420 + 128t + 64 osc). Each block, the factor moves
  toward the knob's by 0.1 dB at most. The full 15 dB takes about 150 blocks, 100 ms. A note on
  the voice, or no factor yet, takes the knob's factor at once.
- **The table moved** to DM 0x2e2500, the free tail of the sub's state. The slew made
  `trim.asm` 238 bytes, and the old place of the table left it fewer than 64 bytes of padding.
- **The model:** `live.trim_slew`, and `render_two(..., trims=)`. A held TRIM renders as
  before, bit for bit (`test_a_held_trim_renders_as_before_the_slew`).
- **The runner:** `scripts/sharc_waverider_m5.py` runs the run `trim_jump` (TRIM to 0 dB, then to
  -15 dB, no note). Its tap is bit-exact to the slewed model and differs from the model
  without the slew.

## Not checked

- Whether the ColdFire folds FINE into the note before the frame is built. The DSP side is
  clear (the render is identical with parameters 48 and 49 at their extremes, before this
  change: `scripts/sharc_waverider_inert.py`).
- The level on the instrument after the change: a build, then the same 64-step pattern read the
  same way.
