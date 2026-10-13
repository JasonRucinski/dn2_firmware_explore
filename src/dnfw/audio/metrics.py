"""A render as numbers, and the numbers as plain findings.

Levels are dB re full scale; a full-scale sine reads 0 dB peak and -3 dB RMS. Spectral
figures come from an averaged, Hann-windowed spectrum scaled so that a full-scale sine's
peak bin reads 0 dB.
"""

from __future__ import annotations

import numpy as np

from .wavio import Wav

FLOOR_DB = -120.0
BAND_EDGES_HZ = (100, 250, 600, 1500, 3500, 8000, 15000, 20000)   # the last band is what is above 20 kHz
SILENT = 1e-3


def db(x) -> float:
    return float(max(FLOOR_DB, 20 * np.log10(max(float(x), 1e-12))))


def power_db(p) -> float:
    return float(max(FLOOR_DB, 10 * np.log10(max(float(p), 1e-24))))


def _blackman_harris(n: int) -> np.ndarray:
    """Four terms: side lobes 92 dB down, a main lobe of four bins each side."""
    k = 2 * np.pi * np.arange(n) / n
    return 0.35875 - 0.48829 * np.cos(k) + 0.14128 * np.cos(2 * k) - 0.01168 * np.cos(3 * k)


def spectrum(mono: np.ndarray, rate: int, nfft: int = 8192, sharp: bool = False) -> tuple[np.ndarray, np.ndarray]:
    """-> (frequencies, mean amplitude per bin, a full-scale sine's peak bin at 1.0). SHARP trades
    a wider peak for side lobes far below a 16-bit file's noise: for what lies between harmonics."""
    nfft = min(nfft, max(256, 1 << int(np.log2(max(len(mono), 256)))))
    if len(mono) < nfft:
        mono = np.pad(mono, (0, nfft - len(mono)))
    window = _blackman_harris(nfft) if sharp else np.hanning(nfft)
    hop = nfft // 2
    count = 1 + (len(mono) - nfft) // hop
    idx = np.arange(nfft)[None, :] + hop * np.arange(count)[:, None]
    spec = np.abs(np.fft.rfft(mono[idx] * window, axis=1)) * 2 / window.sum()
    return np.fft.rfftfreq(nfft, 1 / rate), np.sqrt((spec ** 2).mean(axis=0))


def stft_db(mono: np.ndarray, rate: int, nfft: int = 2048, hop: int = 512) -> tuple[np.ndarray, np.ndarray]:
    """-> (frequencies, dB per frame and bin: frames x bins), for the spectrogram."""
    if len(mono) < nfft:
        mono = np.pad(mono, (0, nfft - len(mono)))
    window = np.hanning(nfft)
    count = 1 + (len(mono) - nfft) // hop
    idx = np.arange(nfft)[None, :] + hop * np.arange(count)[:, None]
    spec = np.abs(np.fft.rfft(mono[idx] * window, axis=1)) * 2 / window.sum()
    return np.fft.rfftfreq(nfft, 1 / rate), 20 * np.log10(np.maximum(spec, 10 ** (FLOOR_DB / 20)))


def loudest(mono: np.ndarray, rate: int, seconds: float = 0.5) -> tuple[int, int]:
    """-> (start, length) of the loudest stretch of SECONDS: where the pitch is read."""
    n = min(len(mono), int(seconds * rate))
    if n <= 0:
        return 0, 0
    total = np.concatenate(([0.0], np.cumsum(mono ** 2)))
    return int(np.argmax(total[n:] - total[:-n])), n


def fundamental(seg: np.ndarray, rate: int) -> float | None:
    """The pitch of SEG by autocorrelation, 20 Hz..4 kHz; None when it has none."""
    n = len(seg)
    if n < 256:
        return None
    seg = seg - seg.mean()
    if np.abs(seg).max() < SILENT:
        return None
    size = 1 << int(np.ceil(np.log2(2 * n)))
    ac = np.fft.irfft(np.abs(np.fft.rfft(seg, size)) ** 2)[:n]
    if ac[0] <= 0:
        return None
    ac = ac / ac[0]
    below = np.flatnonzero(ac < 0)                    # past lag 0's own lobe, or every lag looks like a period
    lo, hi = max(int(rate / 4000), int(below[0]) if len(below) else n), min(n - 2, int(rate / 20))
    if hi <= lo + 2:
        return None
    best = float(ac[lo:hi].max())
    if best < 0.5:
        return None
    k = next((j for j in range(lo + 1, hi) if ac[j] >= 0.9 * best and ac[j] >= ac[j - 1] and ac[j] >= ac[j + 1]),
             lo + int(np.argmax(ac[lo:hi])))          # the first peak as good as the best: no octave drop
    a, b, c = ac[k - 1], ac[k], ac[k + 1]
    curve = a - 2 * b + c
    shift = float(np.clip(0.5 * (a - c) / curve, -0.5, 0.5)) if curve < 0 else 0.0
    return float(rate / (k + shift))


def steps(mono: np.ndarray, rate: int) -> dict:
    """Sample-to-sample jumps that stand out from their neighbourhood: four times the 99th
    percentile of the jumps in the same 2048 samples (43 ms at 48 kHz), and at least 2 % of full
    scale. A saw has one a cycle: those come at even gaps and are counted as `periodic`. The
    others are `isolated`: a note's edge, or a click. A click smaller than four of a bright
    wave's own jumps is not seen here; the spectrogram shows it as a vertical line."""
    empty = {"periodic": 0, "isolated": 0, "largest_isolated": 0.0, "times_s": []}
    d = np.abs(np.diff(mono))
    if len(d) < 16 or d.max() < SILENT:
        return empty
    block = 2048
    pad = np.pad(d, (0, -len(d) % block), constant_values=np.nan).reshape(-1, block)
    local = np.maximum(4 * np.nanpercentile(pad, 99, axis=1), 0.02)
    hits = np.flatnonzero(d > np.repeat(local, block)[:len(d)])
    if len(hits) == 0:
        return empty
    groups = [int(hits[0])]
    for h in hits[1:]:
        if h - groups[-1] > rate // 1000:
            groups.append(int(h))
    gaps = np.diff(groups)

    def even(i: int) -> bool:                         # gaps i and i + 1 the same, within 5 %
        return 0 <= i < len(gaps) - 1 and abs(int(gaps[i]) - int(gaps[i + 1])) <= 0.05 * max(gaps[i], gaps[i + 1])

    alone = [g for i, g in enumerate(groups) if not (even(i - 2) or even(i - 1) or even(i))]
    return {"periodic": len(groups) - len(alone), "isolated": len(alone),
            "largest_isolated": round(float(max((d[g] for g in alone), default=0.0)), 5),
            "times_s": [round(g / rate, 4) for g in alone[:8]]}


def measure(wav: Wav) -> dict:
    x, mono, rate = wav.data, wav.mono, wav.rate
    frames = len(mono)
    peak = float(np.abs(x).max()) if frames else 0.0
    rms = float(np.sqrt((x ** 2).mean())) if frames else 0.0
    out = {
        "sample_rate": rate, "channels": x.shape[1], "frames": frames,
        "duration_s": round(frames / rate, 4), "bits": wav.bits,
        "source": wav.comment or "not stated in the file",
        "peak_db": round(db(peak), 2), "rms_db": round(db(rms), 2),
        "crest_db": round(db(peak) - db(rms), 2) if rms > 0 else None,
        "dc_offset": [round(float(v), 6) for v in x.mean(axis=0)] if frames else [],
        "at_full_scale": wav.at_full_scale,
        "silence_ratio": round(float((np.abs(mono) < SILENT).mean()), 4) if frames else 1.0,
    }
    if not frames:
        return out | {"findings": ["the file holds no samples"]}
    parts = np.array_split(mono, 8)
    out["time_profile_db"] = [round(db(np.sqrt((p ** 2).mean())), 1) if len(p) else FLOOR_DB for p in parts]
    freqs, amp = spectrum(mono, rate)
    power = amp ** 2
    total = float(power[1:].sum()) or 1e-24
    edges = (0,) + BAND_EDGES_HZ + (rate,)
    out["band_energy_db"] = [round(power_db(power[(freqs >= lo) & (freqs < hi)].sum() / total), 1)
                             for lo, hi in zip(edges, edges[1:])]
    out["above_20k_db"] = out["band_energy_db"][-1]
    order = np.argsort(amp[1:-1])[::-1] + 1
    peaks = []
    for k in order:
        if amp[k] >= amp[k - 1] and amp[k] >= amp[k + 1] and all(abs(freqs[k] - p[0]) > 4 * freqs[1] for p in peaks):
            peaks.append((float(freqs[k]), db(amp[k])))
        if len(peaks) == 12:
            break
    out["spectral_peaks"] = [{"hz": round(f, 1), "db": round(d, 1)} for f, d in sorted(peaks)]
    start, length = loudest(mono, rate)
    seg = mono[start:start + length]
    f0 = fundamental(seg, rate)
    out["fundamental_hz"] = round(f0, 2) if f0 else None
    out["pitch_read_at_s"] = [round(start / rate, 3), round((start + length) / rate, 3)]
    if f0:                                            # on the same stretch: a file may hold several notes
        sf, sa = spectrum(seg, rate, sharp=True)
        sp = sa ** 2
        harmonic = sf < 5 * sf[1]                     # DC's own lobe
        for h in range(1, int((rate / 2) / f0) + 1):
            harmonic |= np.abs(sf - h * f0) <= max(5 * sf[1], 0.01 * h * f0)
        out["inharmonic_db"] = round(power_db(sp[1:][~harmonic[1:]].sum() / (float(sp[1:].sum()) or 1e-24)), 1)
    out["steps"] = steps(mono, rate)
    if x.shape[1] == 2:
        left, right = x[:, 0], x[:, 1]
        denom = float(np.sqrt((left ** 2).sum() * (right ** 2).sum()))
        out["stereo_correlation"] = round(float((left * right).sum() / denom), 4) if denom else None
        out["stereo_balance_db"] = round(db(np.sqrt((left ** 2).mean())) - db(np.sqrt((right ** 2).mean())), 2)
    out["findings"] = findings(out)
    return out


def findings(m: dict) -> list[str]:
    """What a reader should look at first. Thresholds are for a synth voice at 48 kHz."""
    notes = []
    if m["source"].startswith("not stated"):
        notes.append("the file does not say what rendered it (model, runner or instrument) or whether it is looped")
    elif "loop" in m["source"].lower():
        notes.append("the file is a short render looped: the pitch and the spectrum describe the loop")
    if m["at_full_scale"]:
        notes.append(f"{m['at_full_scale']} samples at full scale: clipped, or one bit from it")
    if m["peak_db"] > -0.3 and not m["at_full_scale"]:
        notes.append(f"peak {m['peak_db']} dB: no headroom")
    worst = max((abs(v) for v in m["dc_offset"]), default=0.0)
    if worst > 0.005:
        notes.append(f"DC offset {worst:.4f} of full scale")
    if m["silence_ratio"] > 0.98:
        notes.append("silent, or nearly: 98 % of the samples are below -60 dB")
    s = m.get("steps", {})
    if s.get("isolated"):
        notes.append(f"{s['isolated']} isolated step(s), the largest {s['largest_isolated']} of full scale, "
                     f"at {', '.join(str(v) for v in s['times_s'])} s: a note's edge or a click")
    if m.get("above_20k_db", FLOOR_DB) > -50:
        notes.append(f"energy above 20 kHz is {m['above_20k_db']} dB of the total: aliasing or a bright source")
    if m.get("inharmonic_db") is not None and m["inharmonic_db"] > -30:
        notes.append(f"between the harmonics of {m['fundamental_hz']} Hz (read at {m['pitch_read_at_s'][0]} s) lies "
                     f"{m['inharmonic_db']} dB of that stretch's energy: noise, modulation or aliasing")
    if m.get("stereo_balance_db") is not None and abs(m["stereo_balance_db"]) > 3:
        notes.append(f"left minus right is {m['stereo_balance_db']} dB")
    return notes


def compare(a: Wav, b: Wav) -> dict:
    """B against A, sample for sample: are they the same render, and if not, by how much."""
    n = min(len(a.data), len(b.data))
    out = {"frames_a": len(a.data), "frames_b": len(b.data), "compared": n,
           "same_rate": a.rate == b.rate, "same_channels": a.data.shape[1] == b.data.shape[1]}
    if not n or not out["same_rate"] or not out["same_channels"]:
        return out | {"identical": False}
    diff = b.data[:n] - a.data[:n]
    worst = float(np.abs(diff).max())
    out["identical"] = worst == 0.0 and len(a.data) == len(b.data)
    out["max_difference"] = worst
    out["max_difference_lsb16"] = round(worst * 32768, 2)
    out["difference_rms_db"] = round(db(np.sqrt((diff ** 2).mean())), 2)
    out["level_change_db"] = round(db(np.sqrt((b.data[:n] ** 2).mean())) - db(np.sqrt((a.data[:n] ** 2).mean())), 3)
    where = np.flatnonzero(np.abs(diff).max(axis=1) > 0)
    out["first_difference_s"] = round(int(where[0]) / a.rate, 5) if len(where) else None
    out["differing_frames"] = int(len(where))
    return out
