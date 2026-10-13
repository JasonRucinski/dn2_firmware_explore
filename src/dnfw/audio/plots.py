"""One sheet per render: the waveform, a close-up, the spectrum and the spectrogram.

Drawn with Pillow, so the report needs nothing a `dnfw` install does not already have.
Frequency axes are logarithmic, 20 Hz to Nyquist; levels are dB re full scale.
"""

from __future__ import annotations

import pathlib
import textwrap

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from . import metrics
from .wavio import Wav

WIDTH, LEFT, RIGHT, GAP = 1400, 72, 24, 34
BG, PANEL, GRID, TEXT, TRACE, MARK = (16, 17, 20), (26, 28, 33), (58, 62, 70), (214, 216, 220), (120, 200, 255), (255, 170, 60)
F_LOW = 20.0
DB_RANGE = (-110.0, 0.0)
# dB -> colour: nothing, faint, present, loud, full scale
HEAT = ((-110, (0, 0, 4)), (-85, (40, 11, 84)), (-60, (140, 41, 129)), (-35, (240, 96, 60)),
        (-12, (252, 220, 120)), (0, (255, 255, 255)))
FREQ_TICKS = (20, 50, 100, 200, 500, 1000, 2000, 5000, 10000, 20000)


def _font(size: int = 13):
    try:
        return ImageFont.load_default(size)
    except TypeError:                       # Pillow before 10.1: one size only
        return ImageFont.load_default()


def _hz(v: float) -> str:
    return f"{v / 1000:g}k" if v >= 1000 else f"{v:g}"


def _panel(draw: ImageDraw.ImageDraw, top: int, height: int, title: str) -> tuple[int, int, int, int]:
    box = (LEFT, top, WIDTH - RIGHT, top + height)
    draw.rectangle(box, fill=PANEL)
    draw.text((LEFT, top - 17), title, fill=TEXT, font=_font())
    return box


def _wave(draw, box, x: np.ndarray, rate: int, start: int = 0, label_ms: bool = False) -> None:
    left, top, right, bottom = box
    width, mid, half = right - left, (top + bottom) // 2, (bottom - top) // 2 - 4
    for level, name in ((1.0, "+1"), (0.0, "0"), (-1.0, "-1")):
        y = mid - int(level * half)
        draw.line((left, y, right, y), fill=GRID)
        draw.text((left - 26, y - 7), name, fill=TEXT, font=_font(11))
    if not len(x):
        return
    edges = np.linspace(0, len(x), width + 1).astype(int)
    for px in range(width):
        seg = x[edges[px]:max(edges[px + 1], edges[px] + 1)]
        lo, hi = float(seg.min()), float(seg.max())
        draw.line((left + px, mid - int(np.clip(hi, -1.2, 1.2) * half),
                   left + px, mid - int(np.clip(lo, -1.2, 1.2) * half)), fill=TRACE)
    span = len(x) / rate
    for k in range(6):
        t = start / rate + span * k / 5
        text = f"{t * 1000:.1f} ms" if label_ms else f"{t:.2f} s"
        draw.text((left + int(width * k / 5) - (0 if k < 5 else 44), bottom + 3), text, fill=TEXT, font=_font(11))


def _fx(freq, left: int, width: int, nyquist: float):
    return left + (np.log(np.maximum(freq, F_LOW) / F_LOW) / np.log(nyquist / F_LOW) * (width - 1))


def _spectrum(draw, box, freqs, amp, nyquist: float, f0: float | None) -> None:
    left, top, right, bottom = box
    width, height = right - left, bottom - top
    lo, hi = DB_RANGE
    for level in range(int(lo) + 10, 1, 20):
        y = top + int((hi - level) / (hi - lo) * (height - 1))
        draw.line((left, y, right, y), fill=GRID)
        draw.text((left - 34, y - 7), f"{level}", fill=TEXT, font=_font(11))
    for tick in FREQ_TICKS:
        if tick < nyquist:
            x = int(_fx(tick, left, width, nyquist))
            draw.line((x, top, x, bottom), fill=GRID)
            draw.text((x - 8, bottom + 3), _hz(tick), fill=TEXT, font=_font(11))
    level = 20 * np.log10(np.maximum(amp, 10 ** (lo / 20)))
    cols = np.full(width, lo)
    xs = _fx(freqs[1:], 0, width, nyquist).astype(int)
    np.maximum.at(cols, np.clip(xs, 0, width - 1), level[1:])
    seen = np.flatnonzero(cols > lo)
    if len(seen):                                   # low bins are sparse on a log axis: join them
        cols = np.interp(np.arange(width), seen, cols[seen])
    ys = top + ((hi - np.clip(cols, lo, hi)) / (hi - lo) * (height - 1)).astype(int)
    draw.line([(left + px, int(ys[px])) for px in range(width)], fill=TRACE)
    if f0:
        for h in range(1, 9):
            if h * f0 < nyquist:
                x = int(_fx(h * f0, left, width, nyquist))
                draw.line((x, top, x, top + 6), fill=MARK)


def _heat(level: np.ndarray) -> np.ndarray:
    stops = np.array([s[0] for s in HEAT], float)
    colours = np.array([s[1] for s in HEAT], float)
    out = np.empty(level.shape + (3,), np.uint8)
    for c in range(3):
        out[..., c] = np.interp(level, stops, colours[:, c]).astype(np.uint8)
    return out


def _spectrogram(image, draw, box, mono, rate: int) -> None:
    left, top, right, bottom = box
    width, height = right - left, bottom - top
    nyquist = rate / 2
    freqs, level = metrics.stft_db(mono, rate)          # frames x bins
    frames = level.shape[0]
    tcols = np.minimum((np.arange(frames) * width) // max(frames, 1), width - 1)
    if frames < width:                                  # short file: stretch each frame
        timed = level[np.minimum((np.arange(width) * frames) // width, frames - 1)]
    else:
        timed = np.full((width, level.shape[1]), metrics.FLOOR_DB)
        np.maximum.at(timed, tcols, level)
    rows = np.full((height, width), metrics.FLOOR_DB)
    ys = (height - 1 - _fx(freqs[1:], 0, height, nyquist)).astype(int)
    np.maximum.at(rows, np.clip(ys, 0, height - 1), timed[:, 1:].T)
    seen = np.flatnonzero((rows > metrics.FLOOR_DB).any(axis=1))
    if len(seen):                                       # rows no bin lands on, at the low end
        for px in range(width):
            rows[:, px] = np.interp(np.arange(height), seen, rows[seen, px])
    image.paste(Image.fromarray(_heat(rows), "RGB"), (left, top))
    for tick in FREQ_TICKS:
        if tick < nyquist:
            y = top + height - 1 - int(_fx(tick, 0, height, nyquist))
            draw.line((left - 5, y, left, y), fill=TEXT)
            draw.text((left - 40, y - 7), _hz(tick), fill=TEXT, font=_font(11))
    span = len(mono) / rate
    for k in range(6):
        draw.text((left + int(width * k / 5) - (0 if k < 5 else 40), bottom + 3), f"{span * k / 5:.2f} s",
                  fill=TEXT, font=_font(11))
    x0 = right - 220                                    # the colour key
    key = _heat(np.linspace(DB_RANGE[0], 0, 200)[None, :].repeat(8, axis=0))
    image.paste(Image.fromarray(key, "RGB"), (x0, top - 14))
    draw.text((x0 - 62, top - 17), f"{int(DB_RANGE[0])} dB", fill=TEXT, font=_font(11))
    draw.text((x0 + 204, top - 17), "0", fill=TEXT, font=_font(11))


def sheet(wav: Wav, measured: dict, title: str, out: str | pathlib.Path) -> pathlib.Path:
    """The four panels and the findings, as a PNG."""
    mono, rate = wav.mono, wav.rate
    notes = measured.get("findings") or ["no finding"]
    heights = (170, 170, 250, 330)
    head = 64 + 16 * len(notes)
    total = head + sum(h + GAP for h in heights) + 10
    image = Image.new("RGB", (WIDTH, total), BG)
    draw = ImageDraw.Draw(image)
    draw.text((LEFT, 10), title, fill=TEXT, font=_font(17))
    f0 = measured.get("fundamental_hz")
    line = (f"{measured['duration_s']} s at {rate} Hz, {measured['channels']} ch   peak {measured['peak_db']} dB   "
            f"RMS {measured['rms_db']} dB   DC {max((abs(v) for v in measured['dc_offset']), default=0):.4f}   "
            f"pitch {f0 if f0 else 'none'}" + (" Hz" if f0 else ""))
    draw.text((LEFT, 34), line, fill=TEXT, font=_font())
    for k, row in enumerate(textwrap.wrap("source: " + measured.get("source", ""), 84)[:3]):
        draw.text((WIDTH - RIGHT - 520, 8 + 15 * k), row, fill=TEXT, font=_font())
    for k, note in enumerate(notes):
        draw.text((LEFT, 54 + 16 * k), "- " + note, fill=MARK if measured.get("findings") else TEXT, font=_font())
    top = head + 20
    box = _panel(draw, top, heights[0], "waveform (whole file, min and max per column)")
    _wave(draw, box, mono, rate)
    top += heights[0] + GAP
    at = measured.get("pitch_read_at_s") or [0, 0]
    span = min(len(mono), int(rate * (4 / f0 if f0 else 0.02)))
    start = max(0, min(int(rate * (at[0] + at[1]) / 2) - span // 2, len(mono) - span))
    box = _panel(draw, top, heights[1], "close-up in the loudest half second (four cycles, or 20 ms)")
    _wave(draw, box, mono[start:start + span], rate, start, label_ms=True)
    top += heights[1] + GAP
    freqs, amp = metrics.spectrum(mono, rate)
    box = _panel(draw, top, heights[2], "spectrum (averaged, dB re full scale; orange ticks: harmonics 1 to 8)")
    _spectrum(draw, box, freqs, amp, rate / 2, f0)
    top += heights[2] + GAP
    box = _panel(draw, top, heights[3], "spectrogram (log frequency)")
    _spectrogram(image, draw, box, mono, rate)
    out = pathlib.Path(out)
    image.save(out)
    return out
