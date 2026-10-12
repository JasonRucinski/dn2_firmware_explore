# Waverider page 5, "Shape": the controls reserved for the sound features

Owner's order (2026-10-12): wavefolder, phase warp, ring and AM, osc 2 modulates osc 1, noise
into POS, formant or comb bank. The layout is option 4 of the layout page: four live knobs and
one typed shaper slot. This page reserves its eight records before any of the features land,
so a saved sound's record layout does not move when they do. Waverider is an alpha: a layout
that proves wrong in testing can still change.

## The page

| A | B | C | D | E | F | G | H |
|---|---|---|---|---|---|---|---|
| FOLD | WARP | FM | NPOS | TYPE | AMT | P1 | P2 |

- **A to D** are live knobs: wave fold, phase warp, FM depth from osc 2 into osc 1, noise into POS.
- **E to H** are one shaper slot: TYPE picks Off, Ring, AM, Formant or Comb (the list grows
  without a new record), AMT is its amount, P1 and P2 its two parameters.
- **The scope** is drawn in the wave's place, as on page 4, so a fold is seen while it turns.
- **Values** store, p-lock and are LFO destinations like every other Waverider control (they
  ride stock records, as the sub and noise do). Until a feature is wired they change nothing in the sound.

## Where the eight records sit

A WaveTone-type sound has sound slots 25 to 64. Waverider uses 238 to 260 (slots 25 to 47) and
FM Tone's 227 to 234 (slots 50 to 57, page 3). The rest:

| Control | Record | Sound slot | Borrowed from |
|---|---|---|---|
| FOLD | 208 | 58 | FM Tone |
| WARP | 209 | 59 | FM Tone |
| FM | 210 | 60 | FM Tone |
| NPOS | 211 | 61 | FM Tone |
| TYPE | 235 | 62 | FM Tone |
| AMT | 236 | 63 | FM Tone |
| P1 | 237 | 64 | FM Tone |
| P2 | 261 | 48 | WaveTone's master tuning (MAST) |

Record 262 (FINE, slot 49) stays free for a later control.

**Why MAST is free:** the Waverider voice never reads frame parameters 48, 49 or 58 to 64. The
DSP's render is bit-identical with each at its default and at its extremes, and TUN1 (parameter
25) as the control does change it (`scripts/sharc_waverider_inert.py`, 2026-10-12). Not checked:
whether the ColdFire folds MAST into the note before the frame is built.

**The stock answer table** (`param_set_slot_to_id`, `0x400dc02a`) gives, for FM Tone, slots 58
to 61 the ids 208 to 211 and 62 to 64 the ids 235 to 237 (read in the emulator, 2026-10-12).
`wr_slot_id` answers these for a Waverider sound, as it does 227 to 234 for page 3.

## What is still open

- **Defaults of an old sound.** A sound created before this page holds FM Tone's stock values
  in slots 58 to 61 (0x4000, read from the live frame), so FOLD, WARP, FM and NPOS read 64 on
  it. A feature wired to them must not read 64 as "on", or must re-default them.
- **The labels** are fixed text. A label that follows TYPE needs a knob label that follows a
  value, which has not been shown to be possible.
- **Changing TYPE under a held note** must crossfade, or it clicks.
- **How many SYN pages a machine can show:** five now (page count `wr_count`); more is
  unmeasured.

## Where it is in the code

- `src/dnfw/waverider/pages.py`: `SHAPE`, `SHAPE_LABELS`, `SHAPE_RUNS`, `SHAPE_PLAIN`,
  `PAGES[4]`, `slot_id_runs()` (the `wr_slot_id` search), `C_LOAD` moved to `LOAD + 0x1000`
  (the pages assembly is 3,484 B).
- `csrc/waverider/page.c`: `SHAPE_PAGE` draws the scope.
- Generated: `src/dnfw/mods/waverider_code.json` (`scripts/gen_waverider_code.py`).
