# Reading a render: `dnfw wav`

A rendered WAV as numbers, plain findings and one sheet of plots, so a render can be judged before
anyone listens to it. The method is moveforge's (`docs/references.md`); the code is ours.

```
dnfw wav report RENDER.wav [MORE.wav ...] [-o DIR]
dnfw wav compare BEFORE.wav AFTER.wav [-o DIR]
```

`report` writes `RENDER.json` and `RENDER.png` beside the file, or into `DIR`, and prints the
findings. `compare` exits 0 when the two files hold the same samples; otherwise it prints how they
differ and writes a sheet of the difference.

It reads PCM of 16, 24 and 32 bits and float of 32 and 64. It needs numpy and Pillow, nothing else.

## What the file is

The tool reads a file. It cannot tell what made it, and that decides what a reading means:

| source | what it is | limits |
|---|---|---|
| the model | the Python reference (`dnfw.waverider.render`), which the DSP code is checked against | not the DSP |
| the runner | our SHARC code executed in digikit's SHARC runner inside the stock image, bit for bit | slow: the Waverider tests render 12 blocks (384 samples, 8 ms) and **loop** them to fill a WAV |
| the instrument | the unit's own output, through the probe's tap or a recording | not in this repository's renders yet |

A file can say which it is in a `LIST/INFO` comment (`wavio.info_chunk`); `report` prints it on the
sheet as `source`, raises a finding when it is missing, and another when it says the render is
looped. A looped file's pitch and spectrum describe the loop: 384 samples looped read as 125 Hz
whatever the note was.

## The numbers

| field | what it is |
|---|---|
| `peak_db`, `rms_db`, `crest_db` | dB re full scale. A full-scale sine is 0 and -3 |
| `dc_offset` | the mean of each channel, as a share of full scale |
| `at_full_scale` | samples at the format's largest value: clipped, or one bit from it |
| `silence_ratio` | the share of samples below -60 dB |
| `time_profile_db` | RMS of each eighth of the file |
| `band_energy_db` | energy in nine bands, dB of the total: below 100 Hz, to 250, 600, 1.5 k, 3.5 k, 8 k, 15 k, 20 k, and above 20 k |
| `above_20k_db` | the last band on its own |
| `spectral_peaks` | the twelve strongest peaks of the averaged spectrum |
| `fundamental_hz`, `pitch_read_at_s` | the pitch of the loudest half second, by autocorrelation, and where that half second is |
| `inharmonic_db` | in that half second, the energy that is not at a harmonic of the pitch, dB of its total |
| `steps` | sample-to-sample jumps that stand out from their neighbourhood: `periodic` (even gaps: a saw's edge) and `isolated` (a note's edge, or a click), with the times of the isolated ones |
| `stereo_correlation`, `stereo_balance_db` | for two channels |
| `findings` | the list below |

## The findings

A finding is a sentence with its number in it. None of them is a verdict.

| finding | raised when |
|---|---|
| samples at full scale | any |
| no headroom | the peak is above -0.3 dB |
| DC offset | above 0.5 % of full scale |
| silent | 98 % of the samples are below -60 dB |
| isolated steps | any, with their times |
| energy above 20 kHz | above -50 dB of the total |
| between the harmonics | above -30 dB of the loudest half second |
| left minus right | more than 3 dB |

## The sheet

Top to bottom: the file's name, a line of levels, the findings; the whole waveform as the smallest
and largest sample per column; a close-up of four cycles in the loudest half second; the averaged
spectrum on a logarithmic axis from 20 Hz, with a tick at each of the first eight harmonics; the
spectrogram on the same frequency axis, from -110 dB (black) to full scale (white).

## What it does not see

- **A click inside a bright wave.** A step has to be four times the 99th percentile of the jumps in
  its own 43 ms. A saw's own edge sets that bar high. The spectrogram shows such a click as a
  vertical line.
- **A file with several notes** has one pitch reading, from its loudest half second. The other notes
  are in the spectrogram and not in `inharmonic_db`.
- **Aliasing is not named.** Energy above 20 kHz and energy between the harmonics are where it
  shows; noise and modulation show there too.
- **No goldens yet.** Nothing compares a render with a blessed one; `compare` is sample for sample.
