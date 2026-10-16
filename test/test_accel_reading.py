"""accelprobe's reference against the words the chip wrote: accelprobe1 on the owner's
Digitone II, 2026-10-17 (`python tools/dn2accel.py --save`, kept as accel_reading_2026-10-17.json)."""

from __future__ import annotations

import json
import pathlib

from dnfw.waverider import accelprobe

READING = json.loads(pathlib.Path(__file__).with_name("accel_reading_2026-10-17.json").read_text(encoding="utf-8"))


def test_every_run_finished():
    for r in range(1, len(accelprobe.RUNS) + 1):
        assert READING[f"run{r}.reads"] < accelprobe.LIMIT


def test_the_reference_is_every_word_the_chip_wrote():
    want = accelprobe.expected()
    assert len(want) == 76
    assert {k: READING[k] for k in want} == want


def test_the_orders_before_the_reading_miss_it():
    """The control: the models' order before ElekLabs/digikit#122 misses words."""
    old = accelprobe.expected(iir_order="model", fir_order="model")
    assert sum(READING[k] == v for k, v in old.items()) < 76
