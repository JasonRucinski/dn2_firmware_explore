"""Reading a rendered WAV the way a listener would not: numbers first, then pictures.

`wavio` reads a file, `metrics` turns it into numbers and plain findings (clipping, DC,
steps, energy where none should be), `plots` draws the waveform, the spectrum and the
spectrogram on one sheet. `dnfw wav report` and `dnfw wav compare` are the way in.

The idea of judging a render by metrics and plots before listening is moveforge's
(m-dwyer, docs/references.md); nothing of its code is here.
"""
