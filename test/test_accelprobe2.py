"""accelprobe2's jobs: the data's layout, run 4's chain and the timing fit (dnfw.waverider.accelprobe2)."""

from __future__ import annotations

import struct

from dnfw.waverider import accelprobe as ap
from dnfw.waverider import accelprobe2 as a2


def _spans():
    """(name, start, end) of every buffer and TCB in DATA_DM, J5..J7's shared buffers once."""
    out = []
    for name, job in a2.JOBS.items():
        if name != "iir4":
            out.append((f"{name}.tcb", job["tcb"], job["tcb"] + 4 * 13))
    out += [(f"iir4.tcb{k}", a2.tcb_at(k) - a2.DATA_DM, a2.tcb_at(k) - a2.DATA_DM + 4 * 16) for k in range(a2.CHANNELS)]
    for name in ("iir1", "iir2", "iir3", "iir4", "iir7"):
        job = a2.JOBS[name]
        if name != "iir7":
            out.append((f"{name}.coef", job["coef"], job["coef"] + 4 * 7 * job["biquads"]))
            out.append((f"{name}.inp", job["inp"], job["inp"] + 4 * job["window"]))
        out.append((f"{name}.out", job["out"], job["out"] + 4 * job["window"]))
    return out


def test_no_two_spans_overlap_and_all_fit():
    spans = sorted(_spans(), key=lambda s: s[1])
    for (n1, _, e1), (n2, s2, _) in zip(spans, spans[1:]):
        assert e1 <= s2, f"{n1} overlaps {n2}"
    assert spans[-1][2] <= a2.DATA_BYTES


def test_run_4_is_a_chain_of_16_channels_ending_in_a_null_pointer():
    d = a2.data()
    for k in range(a2.CHANNELS):
        nxt = struct.unpack_from("<I", d, a2.tcb_at(k) - a2.DATA_DM)[0]
        assert nxt == (ap.word_address(a2.tcb_at(k + 1)) + 15 if k + 1 < a2.CHANNELS else 0)
    assert a2.chain_pointer(a2.J4, True) == ap.word_address(a2.tcb_at(0)) + 15


def test_the_fit_recovers_known_costs():
    words = {f"run{r}.cycles": int(310 + 22 * b + 6 * n + 3 * b * n)
             for r, (b, n) in {1: (1, 32), 2: (5, 32), 3: (5, 8), 7: (1, 8)}.items()}
    line = a2.timing(words)[0]
    assert "310 cycles of setup" in line and "22.0 a biquad" in line and "6.0 a sample" in line and "3.00 a biquad-sample" in line


def test_it_publishes_every_output_it_checks():
    names = {n for n, _ in a2.published()}
    assert set(a2.expected()) <= names and len(a2.published()) <= a2.MAX_PUB
