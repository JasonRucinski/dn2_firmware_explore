# How the stock UI draws its morphing glyphs: stored frames

DN2 1.11, a static read, 2026-10-20. The owner asked a question: does the firmware draw a knob's picture from the value, or pick it from stored frames? Grades: [D] read from the image, [I] inferred.

## The answer

The glyphs are stored frames. Each glyph is a list of small 1-bit pictures in the firmware, one per step, and the value picks one [D]. No maths draws the shape at run time.

A dump of WaveTone's list, read straight from the flash, shows 60 frames of 17 x 17 pixels. A sine turns into a triangle, a saw and then a square. The dump is not in this repo: the frames are Elektron's artwork (the no-Elektron-IP rule).

## Every list, checked (2026-10-20)

`0x401518b4..0x40169dce` is one start-up routine that builds every stored UI bitmap. A parser over it reads each `Bitmap` constructor (size and flash pointer) and each list fill (`0x401c9622`, the frame count) [D]. A contact sheet of every list confirmed each one by eye.

| | Count |
|---|---|
| Frame lists | 106 (2,158 frames) |
| Single still bitmaps | 370 |
| Frames in a list form the parser does not follow | 481 |
| Frame-picker call sites | 75, using 64 distinct lists (53 of them parsed) |

- **The frame count is not fixed.** It is 2 to 101 frames a list, median 13. Among the lists the picker uses: the round dial has 96 frames, the wave morph 60, and other value glyphs 25 to 97. Choice icons (algorithms, routing, filter types) have 2 to 8.
- **The frame size is not fixed either.** 17 x 17 (24 lists) and 19 x 17 (23 lists) are the most common, then 11 x 11 (9). Three lists hold full-screen 128 x 64 sequences.
- **The storage format.** Each frame is `w` columns. A column is ceil(h / 32) 32-bit big-endian words, the top word first, with the most significant bit at the top row. That is why a row-by-row dump looks rotated. A frame of 32 rows or fewer has one word a column. The 128 x 64 sequences, with two words a column, decode cleanly this way [D].
- **Every value glyph seen is stored frames.** No list among the 64 the picker uses is drawn by maths.

## The chain

1. **The draw.** WaveTone's OSC page draws its two icons with `0x40016cee` (`docs/waverider-m7-pages.md`). That routine calls `0x40115b5e(list, value, 0x7800, 0)` and blits the bitmap it returns with `0x401157fc`.
2. **The picker.** `0x40115b5e` takes a list of 28-byte `Bitmap` objects: begin at `+0`, end at `+4`. It works out the frame count with a multiply by the inverse of 7. Then it computes the frame index as value x (count - 1) / range, rounded, and returns `begin + 28 x index` [D]. Flags in its fourth argument change the rounding and the end cases. Two wrappers call it with fixed ranges: `0x40115ca8` (0 or 0x7f00) and `0x40115ccc` (0x8000).
3. **How often it is used.** The picker has 12 direct callers. The wrappers have 50 and 15. A scan of the call sites finds 75 that pass a list (below) [D].
4. **The frame lists.** The lists are objects in RAM near `0x446474dc..0x44647570`, built and freed by static initialisers (near `0x40169c88`). WaveTone's is at `0x4464752c`, with a second one at `0x44647150` for its other table.
5. **The frames.** `0x40151f0e` fills the lists at start-up. For each frame it builds a 17 x 17 `Bitmap` over a pointer into flash (`0x402f1d90`, `0x402f1dd4` and so on, 0x44 bytes apart: 17 rows of 4 bytes). It then adds 60 of them to `0x4464752c` (`0x401530f0`) [D]. So the pixels themselves are in the firmware, drawn by hand.

## What this means for us

- A mod that wants a stock-looking glyph for a new control can do the same. It stores frames and picks one with `0x40115b5e`.
- Waverider's page draws its wave from the table instead (`csrc/waverider/page.c`), because its tables are not known at build time.
- The site's mod glyphs (`site/js/mods/glyphs.js`) are single still frames in the same 1-bit style.

## Not done yet

- **Which control each list draws:** the drawers are callback objects near `0x42432300`, set up at `0x400c3000`. The parameter records do not point at them. The link is a runtime table that is not read yet.
- **The 481 frames in other list forms,** for example lists filled in loops.
- **Whether any glyph outside the picker is drawn by maths.**
