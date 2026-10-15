"""`dnfw wav`: the metrics and findings on signals whose answers are known."""

from __future__ import annotations

import struct
import wave

import numpy as np
import pytest
from PIL import Image

from dnfw.audio import metrics, plots, wavio
from dnfw.cli import main as cli

RATE = 48000


def write(path, x: np.ndarray, rate: int = RATE):
    ints = np.clip(np.round(x * 32768), -32768, 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1 if ints.ndim == 1 else ints.shape[1])
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(ints.tobytes())
    return path


def sine(hz: float, seconds: float = 1.0, level: float = 0.5) -> np.ndarray:
    return level * np.sin(2 * np.pi * hz * np.arange(int(seconds * RATE)) / RATE)


def measured(tmp_path, x):
    return metrics.measure(wavio.read(write(tmp_path / "a.wav", x)))


def test_a_sine_reads_its_level_and_pitch_and_raises_nothing(tmp_path):
    m = measured(tmp_path, sine(440.0))
    assert m["peak_db"] == pytest.approx(-6.02, abs=0.05) and m["rms_db"] == pytest.approx(-9.03, abs=0.05)
    assert m["fundamental_hz"] == pytest.approx(440.0, abs=0.5)
    assert m["inharmonic_db"] < -60 and m["above_20k_db"] < -80
    assert m["steps"]["isolated"] == 0 and [f for f in m["findings"] if "does not say" not in f] == []


def test_a_low_note_is_not_read_as_its_shortest_lag(tmp_path):
    assert measured(tmp_path, sine(32.7, 2.0))["fundamental_hz"] == pytest.approx(32.7, abs=0.2)


def test_clipping_and_dc_are_findings(tmp_path):
    m = measured(tmp_path, np.clip(sine(200.0, level=1.5), -1, 1) * 0.99997 + 0.0)
    assert m["at_full_scale"] > 0 and any("full scale" in f for f in m["findings"])
    m = measured(tmp_path, sine(200.0, level=0.3) + 0.05)
    assert m["dc_offset"][0] == pytest.approx(0.05, abs=0.001) and any("DC offset" in f for f in m["findings"])


def test_one_click_is_isolated_and_a_saw_is_periodic(tmp_path):
    x = sine(220.0, level=0.3)
    x[24000:] += 0.4                                   # one jump, half way
    m = measured(tmp_path, x)
    assert m["steps"]["isolated"] == 1 and m["steps"]["times_s"] == [pytest.approx(0.5, abs=0.001)]
    saw = 0.6 * (2 * ((55.0 * np.arange(RATE) / RATE) % 1.0) - 1)
    m = measured(tmp_path, saw)
    assert m["steps"]["periodic"] >= 50 and m["steps"]["isolated"] == 0


def test_silence_is_said(tmp_path):
    assert any("silent" in f for f in measured(tmp_path, np.zeros(RATE))["findings"])


def test_compare_tells_the_same_render_from_one_lsb(tmp_path):
    a = wavio.read(write(tmp_path / "a.wav", sine(300.0)))
    assert metrics.compare(a, a)["identical"]
    x = sine(300.0)
    x[1000] += 1 / 32768
    result = metrics.compare(a, wavio.read(write(tmp_path / "b.wav", x)))
    assert not result["identical"] and result["max_difference_lsb16"] == 1.0
    assert result["differing_frames"] == 1 and result["first_difference_s"] == pytest.approx(1000 / RATE, abs=1e-5)


def test_a_float_file_and_a_stereo_file_are_read(tmp_path):
    x = sine(100.0, 0.1).astype("<f4")
    head = b"RIFF" + struct.pack("<I", 36 + x.nbytes) + b"WAVEfmt " + struct.pack("<IHHIIHH", 16, 3, 1, RATE, RATE * 4, 4, 32)
    (tmp_path / "f.wav").write_bytes(head + b"data" + struct.pack("<I", x.nbytes) + x.tobytes())
    w = wavio.read(tmp_path / "f.wav")
    assert w.is_float and w.data.shape == (4800, 1) and abs(w.data).max() == pytest.approx(0.5, abs=1e-3)
    m = measured(tmp_path, np.stack([sine(440.0), 0.25 * sine(440.0)], axis=1))
    assert m["channels"] == 2 and m["stereo_balance_db"] == pytest.approx(12.04, abs=0.1)
    assert any("left minus right" in f for f in m["findings"])


def test_the_command_writes_the_numbers_and_the_sheet(tmp_path, capsys):
    path = write(tmp_path / "note.wav", sine(440.0))
    assert cli.main(["wav", "report", str(path)]) == 0
    assert "does not say what rendered it" in capsys.readouterr().out
    assert (tmp_path / "note.json").exists()
    with Image.open(tmp_path / "note.png") as sheet:
        assert sheet.size[0] == plots.WIDTH and sheet.size[1] > 900
    assert cli.main(["wav", "compare", str(path), str(path)]) == 0


def test_a_file_says_what_rendered_it_and_a_loop_is_a_finding(tmp_path):
    path = write(tmp_path / "loop.wav", sine(440.0))
    path.write_bytes(path.read_bytes() + wavio.info_chunk("runner, 384 samples looped"))
    wav = wavio.read(path)
    assert wav.comment == "runner, 384 samples looped" and len(wav.data) == RATE
    assert any("looped" in f for f in metrics.measure(wav)["findings"])
    assert any("does not say" in f for f in measured(tmp_path, sine(440.0))["findings"])


def test_a_float_file_written_here_reads_back_and_not_looped_is_no_finding(tmp_path):
    x = sine(440.0)
    wavio.write(tmp_path / "long.wav", x, RATE, "the runner, not looped, 375 blocks")
    wav = wavio.read(tmp_path / "long.wav")
    assert wav.is_float and np.array_equal(wav.mono, np.asarray(x, dtype="<f4").astype(np.float64))
    assert not any("loop" in f for f in metrics.measure(wav)["findings"])
