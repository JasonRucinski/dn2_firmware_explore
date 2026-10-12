# Waverider: a p-locked value shows inverted while its trig is held

## The defect

Owner, 2026-10-06, on the instrument: a p-locked value on a Waverider track plays correctly,
but holding the trig that stores it does not show the value inverted on Waverider's pages. The
stock machines do.

## Cause

The value getter `0x4006538E(view, id, &flag)` sets `flag` when the value shown is the one
locked on the held trig. The stock grid hands that flag to its cells as `locked` (and draws them
held, which is the inverted look). Waverider's pages draw each control as a label and a bar
themselves and never read the flag.

## Fix

`csrc/waverider/page.c`, `locked_cell`: once a cell's label, bar and modulation marker are
drawn, if the getter's flag is set the cell's box is inverted with the firmware's fill routine
(`0x40114954`, mode -1). A cell is 25 pixels wide; the box runs from the bar to the label's
top on the upper row and from the label to the bar on the lower row. The three drawing paths
(TBL's counter, TUNE and DETN's semitones, every other control) all do it.

## Confirmed on the instrument

2026-10-12, `waverider-lockdisp1-usbprobe`, owner: the locks are shown inverted while the trig is
held. The getter's flag fires for a real lock, which the emulator could not show.

## How it is tested

The emulator cannot make a lock (`Lock mem FULL!` on the grid record), so the lock itself is
not reproduced. A test build (`DNFW_WAVERIDER_CDEFS="WR_TEST_LOCKED=238,241,247,252,249"`
while `scripts/gen_waverider_code.py` runs) draws those ids as locked: TUNE, LEV, TBL, MLEV
and PRST on pages 1, 2 and 4. The frames from the panel driver show the inverted cells. The
getter's own flag is what the instrument decides on; that is the part only the unit shows.

## Not covered

- A value being touched (the encoder held) is not drawn inverted on Waverider's pages, as
  it is on some stock cells. The owner has not asked for it.
