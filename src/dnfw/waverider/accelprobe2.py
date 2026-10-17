"""The second accelerator probe: how long IIR0 takes for one biquad-sample, and for a chain of 16 channels.

    section7_accel(stock) -> stock DN2 1.11's section 7, plus the idle-time stub, plus accel.asm
        (the same code as accelprobe's), its state block and these jobs' data.

accelprobe1 (2026-10-17) settled IIR0's order and gave its time for two jobs, setup included,
so the cost of one biquad-sample was bounded (at most 22 cycles), not measured. These six runs
differ in the number of biquads and samples, so their times separate the setup from the work:

    1  IIR0, legacy, 1 biquad, 32 samples          (32 biquad-samples)
    2  IIR0, legacy, 5 biquads, 32 samples         (160)
    3  IIR0, legacy, 5 biquads, 8 samples          (40)
    4  IIR0, ACM, 16 channels of 5 biquads, 32 samples each, IMASK  (2,560: layout A's shape)
    5  job 1 again, on a TCB of its own
    6  job 2 again, on a TCB of its own
    7  IIR0, legacy, 1 biquad, 8 samples          (8)

The 16 channels of run 4 share one coefficient, input and output buffer. Without Save State
each channel reads the same states and writes the same output, so the output is one channel's.
The module has accelprobe's interface, so `tools/dn2accel.py --probe accelprobe2`,
`scripts/build_accelprobe.py --probe accelprobe2` and `scripts/sharc_accel_check.py --probe
accelprobe2` take it. accel.asm and its JUMP are accelprobe's (`accel_code.json`).
"""

from __future__ import annotations

import struct

from dnfw.image import bootstream
from dnfw.waverider import accelprobe as ap
from dnfw.waverider import dsp

ACC_DM, ACC_SW, STATE_DM, STATE_BYTES = ap.ACC_DM, ap.ACC_SW, ap.STATE_DM, ap.STATE_BYTES
RUNS_DM, RESULTS_DM, PUBTAB_DM, MAX_PUB = ap.RUNS_DM, ap.RESULTS_DM, ap.PUBTAB_DM, ap.MAX_PUB
DATA_DM, DATA_BYTES = ap.DATA_DM, 0xC00
REPLY_WORD2, LIMIT, CODE = ap.REPLY_WORD2, ap.LIMIT, ap.CODE
IIR0, EN, DMAEN, ACM, IMASK, WINDOW_SHIFT = ap.IIR0, ap.EN, ap.DMAEN, ap.ACM, ap.IMASK, ap.WINDOW_SHIFT
CHANNELS = 16

_f32 = ap._f32
# Five stable biquads (A0, A1, B1, A2, B2, s1, s2; B = -a), poles at radius 0.53 to 0.86
FIVE = [_f32(c) for c in (0.0675, 0.135, 1.1429, 0.0675, -0.4128, 0.01, -0.02,
                          1.0213, -1.7311, 1.6992, 0.7417, -0.7862, 0.0, 0.0,
                          0.3333, -0.2, 0.5129, 0.1171, -0.2771, 0.03, 0.07,
                          0.2, 0.1, 0.9, 0.05, -0.5, 0.0, 0.0,
                          0.5, -0.3, -0.4, 0.2, -0.3, 0.0, 0.0)]
ONE = FIVE[:7]

# byte offsets in DATA_DM
J1 = {"tcb": 0x000, "coef": 0x040, "inp": 0x080, "out": 0x100, "biquads": 1, "window": 32, "coefs": ONE, "x": ap._floats(32, 71)}
J2 = {"tcb": 0x180, "coef": 0x1C0, "inp": 0x280, "out": 0x300, "biquads": 5, "window": 32, "coefs": FIVE, "x": ap._floats(32, 73)}
J3 = {"tcb": 0x380, "coef": 0x3C0, "inp": 0x480, "out": 0x4A0, "biquads": 5, "window": 8, "coefs": FIVE, "x": ap._floats(8, 79)}
J4 = {"tcb": 0x500, "coef": 0x900, "inp": 0x9C0, "out": 0xA40, "biquads": 5, "window": 32, "coefs": FIVE, "x": ap._floats(32, 83)}
# runs 5 and 6: jobs 1 and 2 again on TCBs of their own (a legacy run writes its indexes + W back
# into its TCB, so a second run on the same TCB would read and write past its buffers)
J5 = {**J1, "tcb": 0xAC0}
J6 = {**J2, "tcb": 0xB00}
# run 7: 1 biquad on 8 samples, so runs 1, 2, 3 and 7 are the four corners of (1 or 5 biquads) x
# (8 or 32 samples): their times solve setup, a cost per biquad, per sample and per biquad-sample
J7 = {**J1, "tcb": 0xB40, "out": 0xB80, "window": 8, "x": J1["x"][:8]}
JOBS = {"iir1": J1, "iir2": J2, "iir3": J3, "iir4": J4, "iir5": J5, "iir6": J6, "iir7": J7}
TCB_STRIDE = 0x40                                  # run 4: channel k's TCB at J4["tcb"] + 0x40 k

# (job, accelerator, CTL1 bits beside EN | DMAEN, the TCB's word count), as accelprobe.RUNS
RUNS = (("iir1", IIR0, 0, 13), ("iir2", IIR0, 0, 13), ("iir3", IIR0, 0, 13), ("iir4", IIR0, ACM, 16),
        ("iir5", IIR0, 0, 13), ("iir6", IIR0, 0, 13), ("iir7", IIR0, 0, 13))
IIR_ORDERS = ("silicon", "model")
FIR_ORDERS = ()


def _at(job: dict, key: str) -> int:
    return DATA_DM + job[key]


def _ctl2(job: dict, acm: bool) -> int:
    return (job["biquads"] - 1) | ((job["window"] - 1) << WINDOW_SHIFT) | (IMASK if acm else 0)


def _base(job: dict) -> list[int]:
    """TCB words 1..12 (legacy) or 4..15 (ACM): COEF, OUT, IN, CTL2 (accelprobe._tcb's layout)."""
    w = ap.word_address
    return [0, 1, w(_at(job, "coef")), w(_at(job, "out")), 0, 1, w(_at(job, "out")),
            w(_at(job, "inp")), 0, 1, w(_at(job, "inp")), _ctl2(job, job is J4)]


def tcb_at(k: int) -> int:
    """Run 4's channel K: the TCB's DM byte address."""
    return _at(J4, "tcb") + TCB_STRIDE * k


def chain_pointer(job: dict, acm: bool) -> int:
    if acm:
        return ap.word_address(tcb_at(0)) + 15
    return ap.word_address(_at(job, "tcb")) + 12


def data() -> bytes:
    out = bytearray(DATA_BYTES)

    def put(off: int, words) -> None:
        for k, v in enumerate(words):
            struct.pack_into("<I" if isinstance(v, int) else "<f", out, off + 4 * k, v)

    for job in (J1, J2, J3, J5, J6, J7):
        put(job["tcb"], [ap.word_address(_at(job, "tcb")) + 12] + _base(job))
    for k in range(CHANNELS):                          # a chain: CHNPTR of channel k points at k + 1
        nxt = ap.word_address(tcb_at(k + 1)) + 15 if k + 1 < CHANNELS else 0
        put(tcb_at(k) - DATA_DM, [nxt, 0, 0, 0] + _base(J4))
    for job in (J1, J2, J3, J4):                       # J5 and J6 use J1's and J2's buffers
        put(job["coef"], job["coefs"])
        put(job["inp"], job["x"])
    return bytes(out)


def published() -> list[tuple[str, int]]:
    """(name, DM byte address) of every word accel.asm publishes, in PUBTAB order."""
    out = []
    for name, n in (("iir1", 32), ("iir2", 32), ("iir3", 8), ("iir4", 8), ("iir7", 8)):
        job = JOBS[name]
        out += [(f"{name}.out[{k}]", _at(job, "out") + 4 * k) for k in range(n)]
    for k in (0, CHANNELS - 1):                        # the first and the last channel's write-back
        out += [(f"iir4.tcb{k}.outidx", tcb_at(k) + 4 * 10), (f"iir4.tcb{k}.inidx", tcb_at(k) + 4 * 14)]
    for r in range(len(RUNS)):
        out += [(f"run{r + 1}.{what}", RESULTS_DM + 16 * r + 4 * k) for k, what in enumerate(("cycles", "dmastat", "reads"))]
    if len(out) > MAX_PUB:
        raise dsp.DspError(f"{len(out)} published words, PUBTAB holds {MAX_PUB}")
    return out


def state() -> bytes:
    """accel.asm's state block at boot, as accelprobe.state builds it for these runs."""
    if len(RUNS) > (RESULTS_DM - RUNS_DM) // 16:
        raise dsp.DspError(f"{len(RUNS)} runs, the RUNS table holds {(RESULTS_DM - RUNS_DM) // 16}")
    out = bytearray(STATE_BYTES)
    pub = published()
    struct.pack_into("<IIII", out, 0x4C, len(RUNS), 2 * len(pub), RUNS_DM, RESULTS_DM)
    for r, (name, base, bits, _) in enumerate(RUNS):
        struct.pack_into("<III", out, 0x80 + 16 * r, base, chain_pointer(JOBS[name], bool(bits & ACM)), EN | DMAEN | bits)
    for k, (_, at) in enumerate(pub):
        struct.pack_into("<I", out, 0x200 + 4 * k, at)
    return bytes(out)


def expected(iir_order: str = "silicon", fir_order: str = "pairs",
             acm_writeback: tuple[int, int] = (0xFFFFFFFF, 0)) -> dict[str, int]:
    """name -> the word each published output and write-back should hold (timings aside).
    Runs 5 and 6 write the same outputs as runs 1 and 2 into the same buffers (no Save State)."""
    out = {}
    for name, n in (("iir1", 32), ("iir2", 32), ("iir3", 8), ("iir4", 8), ("iir7", 8)):
        y, _ = ap.iir_expected(JOBS[name], iir_order)
        out.update({f"{name}.out[{k}]": ap._bits(v) for k, v in enumerate(y[:n])})
    for k in (0, CHANNELS - 1):
        out[f"iir4.tcb{k}.inidx"], out[f"iir4.tcb{k}.outidx"] = acm_writeback   # ACM: the chip's by default
    return out


decode, objects = ap.decode, ap.objects


def words(halves: dict[int, int]) -> dict[str, int]:
    out = {}
    for k, (name, _) in enumerate(published()):
        lo, hi = halves.get(2 * k), halves.get(2 * k + 1)
        if lo is not None and hi is not None:
            out[name] = hi << 16 | lo
    return out


def section7_accel(stock: bytes) -> bytes:
    """Stock + the idle stub + accel.asm, its state and these jobs' data (accelprobe.section7_accel's steps)."""
    base = dsp.section7_idle_only(stock)
    obj = objects()
    code = obj["accel"]
    if STATE_DM - ACC_DM - len(code) < 64:
        raise dsp.DspError("accel.asm leaves fewer than 64 bytes of NOP padding")
    if len(obj["accel_jump"]) != len(dsp.IDLE_SITE_STOCK):
        raise dsp.DspError(f"the accel JUMP is {len(obj['accel_jump'])} bytes, not {len(dsp.IDLE_SITE_STOCK)}")
    if not (dsp.IDLE_PAD_END <= ACC_DM and DATA_DM + DATA_BYTES <= dsp.REGION[1]):
        raise dsp.DspError("accelprobe2's spans leave the block-1 region")
    added = [("accel.asm (wr_acc)", dsp.dm_to_load(ACC_DM), code + bytes(STATE_DM - ACC_DM - len(code))),
             ("accel state", dsp.dm_to_load(STATE_DM), state()),
             ("accelprobe2 jobs", dsp.dm_to_load(DATA_DM), data())]
    dsp._check_free(stock, added)
    extra = b"".join(bootstream.block(at, payload) for _, at, payload in added)
    out = bytearray(bootstream.insert_before_final(base, extra))
    bootstream.write_span(out, dsp.l2_sw_to_load(dsp.IDLE_SITE_SW), obj["accel_jump"])
    return dsp._finish(out)


def timing(words: dict[str, int]) -> list[str]:
    """What the run times say: cycles = s0 + kb B + kn N + c B N from the four corners (runs 1, 2,
    3 and 7), then run 4's chain of 16 channels against it, and the repeats' spread."""
    cyc = {r: words.get(f"run{r}.cycles") for r in range(1, len(RUNS) + 1)}
    if None in (cyc[1], cyc[2], cyc[3], cyc[7]):
        return ["  the four corners are not all read: no fit"]
    t11, t52, t53, t17 = cyc[1], cyc[2], cyc[3], cyc[7]     # (1, 32), (5, 32), (5, 8), (1, 8)
    c = ((t52 - t53) - (t11 - t17)) / ((5 - 1) * (32 - 8))  # the B x N term
    kn = (t11 - t17) / (32 - 8) - c * 1
    kb = (t53 - t17) / (5 - 1) - c * 8
    s0 = t17 - kb - 8 * kn - 8 * c
    lines = [f"  fit: {s0:,.0f} cycles of setup, {kb:,.1f} a biquad, {kn:,.1f} a sample, "
             f"{c:,.2f} a biquad-sample (runs 1, 2, 3, 7; the core polled about every 30 cycles)"]
    one = s0 + 5 * kb + 32 * kn + 160 * c
    lines.append(f"  a 5-biquad channel on 32 samples, from the fit: {one:,.0f} cycles")
    if cyc[4] is not None:
        lines.append(f"  run 4, ACM, 16 channels of 5 biquads on 32 samples: {cyc[4]:,} cycles, "
                     f"{cyc[4] / CHANNELS:,.0f} a channel, {cyc[4] / (CHANNELS * 160):,.2f} a biquad-sample")
    for r, of in ((5, 1), (6, 2)):
        if cyc[r] is not None:
            lines.append(f"  run {r} repeats run {of}: {cyc[r]:,} against {cyc[of]:,} cycles")
    return lines
