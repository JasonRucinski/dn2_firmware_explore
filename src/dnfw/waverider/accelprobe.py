"""A diagnostic DSP stream: do the DSP's filter accelerators, FIR0 and IIR0, compute what
digikit's models say?

    section7_accel(stock) -> stock DN2 1.11's section 7, plus the idle-time stub
        (`dsp.section7_idle_only`), plus accel.asm, its state block and the jobs' data.

The DN2 1.11 engine never starts FIR0 or IIR0. digikit models both (tools/sharc_core/fir.py,
iir.py), and two choices in each model come from no manual: the order of the float
operations inside a biquad and inside the FIR's four MACs. Five jobs settle them on the chip:

    1, 2  IIR0, legacy, 2 biquads, 16 samples, Save State: run twice (the second run goes on
          from the first's saved state and write-back)
    3     IIR0, Auto Configuration Mode, 1 biquad, 8 samples, IMASK
    4     FIR0, legacy, 11 taps, 16 samples
    5     FIR0, Auto Configuration Mode, 37 taps, 8 samples, IMASK

Their TCBs, coefficients and inputs load with the stream (DATA_DM, in L1 block 1, which the
accelerators reach at LOAD_ALIAS + the DM byte address, as word addresses). accel.asm runs
them in the idle task once, then publishes their outputs, write-back words and timings
through reply word 2 (`tools/dn2accel.py`). The values are not exactly representable on
purpose (pseudo-random floats), so a different order of rounding shows.
"""

from __future__ import annotations

import json
import pathlib
import struct

from dnfw.image import bootstream, sharc_object
from dnfw.waverider import dsp

ACC_DM = 0x2DF000                      # accel.asm, after idle_load.asm's padding (dsp.IDLE_PAD_END)
ACC_SW = ACC_DM // 2                   # 0x16f800
STATE_DM = 0x2DF800
STATE_BYTES = 0x600
RUNS_DM = STATE_DM + 0x80
RESULTS_DM = STATE_DM + 0x100
PUBTAB_DM = STATE_DM + 0x200
MAX_PUB = (STATE_BYTES - 0x200) // 4   # 256 words
DATA_DM = 0x2E0000
DATA_BYTES = 0x800
REPLY_WORD2 = (0x2C49D8, 0x2C59D8)

FIR0, IIR0 = 0x310C3000, 0x310C4000
EN, DMAEN, CCINTR, ACM = 1 << 0, 1 << 8, 1 << 11, 1 << 31
IIR_SS = 1 << 10
WINDOW_SHIFT, IMASK = 14, 1 << 24
LIMIT = 1_000_000                      # accel.asm's poll limit

CODE = pathlib.Path(__file__).with_name("accel_code.json")


def word_address(dm: int) -> int:
    """A DM byte address as the accelerators take it: the system address >> 2."""
    return (dsp.LOAD_ALIAS + dm) >> 2


def _f32(x: float) -> float:
    return struct.unpack("<f", struct.pack("<f", x))[0]


def _floats(n: int, seed: int, scale: float = 1.0) -> list[float]:
    """N float32 values in -scale..scale with full mantissas (a fixed sequence)."""
    out, s = [], seed
    for _ in range(n):
        s = (s * 1103515245 + 12345) & 0x7FFFFFFF
        out.append(_f32(scale * (2.0 * s / 0x7FFFFFFF - 1.0)))
    return out


# Each job's place in DATA_DM (byte offsets) and its words. Biquads are (A0, A1, B1, A2, B2,
# Dk2, Dk1) in the IIR's coefficient order (HWR 39); B = -a, so B1, B2 hold a stable filter.
IIR_A = {"tcb": 0x000, "coef": 0x040, "inp": 0x080, "out": 0x100, "biquads": 2, "window": 16,
         "coefs": [_f32(0.0675), _f32(0.135), _f32(1.1429), _f32(0.0675), _f32(-0.4128), _f32(0.01), _f32(-0.02),
                   _f32(1.0213), _f32(-1.7311), _f32(1.6992), _f32(0.7417), _f32(-0.7862), _f32(0.0), _f32(0.0)],
         "x": _floats(32, 11)}
IIR_B = {"tcb": 0x180, "coef": 0x1C0, "inp": 0x200, "out": 0x220, "biquads": 1, "window": 8,
         "coefs": [_f32(0.3333), _f32(-0.2), _f32(0.5129), _f32(0.1171), _f32(-0.2771), _f32(0.03), _f32(0.07)],
         "x": _floats(8, 23)}
FIR_C = {"tcb": 0x280, "coef": 0x2C0, "inp": 0x300, "out": 0x380, "taps": 11, "window": 16}
FIR_C["c"] = _floats(11, 37, 0.4)
FIR_C["x"] = _floats(11 - 1 + 16, 41)
FIR_D = {"tcb": 0x400, "coef": 0x440, "inp": 0x500, "out": 0x5C0, "taps": 37, "window": 8}
FIR_D["c"] = _floats(37, 53, 0.1)
FIR_D["x"] = _floats(37 - 1 + 8, 59)
JOBS = {"iir_a": IIR_A, "iir_b": IIR_B, "fir_c": FIR_C, "fir_d": FIR_D}

# The runs, in order: (job, accelerator, CTL1 without EN | DMAEN, the TCB's word count)
RUNS = (("iir_a", IIR0, IIR_SS, 13), ("iir_a", IIR0, IIR_SS, 13), ("iir_b", IIR0, ACM, 16),
        ("fir_c", FIR0, 0, 13), ("fir_d", FIR0, ACM, 16))


def _at(job: dict, key: str) -> int:
    return DATA_DM + job[key]


def _tcb(job: dict, ctl2: int, acm: bool) -> list[int]:
    """TCB + 0 (CHNPTR) .. TCB + 12 / 15 (CTL2), the same layout for IIR0 and FIR0 (HWR
    Tables 38-6, 38-7, 39-5, 39-6): one channel, so a null chain pointer (ACM) or itself."""
    base = [0, 1, word_address(_at(job, "coef")),                     # COEF count/length, MOD, IDX
            word_address(_at(job, "out")), 0, 1, word_address(_at(job, "out")),  # OUT base, len, mod, idx
            word_address(_at(job, "inp")), 0, 1, word_address(_at(job, "inp")),  # IN base, len, mod, idx
            ctl2]
    if acm:
        return [0, 0, 0, 0] + base
    return [word_address(_at(job, "tcb")) + 12] + base


def chain_pointer(job: dict, acm: bool) -> int:
    return word_address(_at(job, "tcb")) + (15 if acm else 12)


def data() -> bytes:
    """DATA_BYTES at DATA_DM: every job's TCB, coefficients and input; outputs zeroed."""
    out = bytearray(DATA_BYTES)
    put = lambda off, words: [struct.pack_into("<I" if isinstance(w, int) else "<f", out, off + 4 * k, w)
                              for k, w in enumerate(words)]
    for name, job in JOBS.items():
        acm = name in ("iir_b", "fir_d")
        if name.startswith("iir"):
            ctl2 = (job["biquads"] - 1) | ((job["window"] - 1) << WINDOW_SHIFT) | (IMASK if acm else 0)
            put(job["coef"], job["coefs"])
        else:
            ctl2 = (job["taps"] - 1) | ((job["window"] - 1) << WINDOW_SHIFT) | (IMASK if acm else 0)
            put(job["coef"], list(reversed(job["c"])))                 # C[N-1] first (HWR 38)
        put(job["tcb"], _tcb(job, ctl2, acm))
        put(job["inp"], job["x"])
    return bytes(out)


def published() -> list[tuple[str, int]]:
    """(name, DM byte address) of every word accel.asm publishes, in PUBTAB order."""
    out = []
    a, b, c, d = IIR_A, IIR_B, FIR_C, FIR_D
    out += [(f"iir_a.out[{k}]", _at(a, "out") + 4 * k) for k in range(2 * a["window"])]
    out += [(f"iir_a.coef[{k}]", _at(a, "coef") + 4 * k) for k in (5, 6, 12, 13)]    # the saved states
    out += [("iir_a.tcb.outidx", _at(a, "tcb") + 4 * 7), ("iir_a.tcb.inidx", _at(a, "tcb") + 4 * 11)]
    out += [(f"iir_b.out[{k}]", _at(b, "out") + 4 * k) for k in range(b["window"])]
    out += [("iir_b.tcb.outidx", _at(b, "tcb") + 4 * 10), ("iir_b.tcb.inidx", _at(b, "tcb") + 4 * 14)]
    out += [(f"fir_c.out[{k}]", _at(c, "out") + 4 * k) for k in range(c["window"])]
    out += [("fir_c.tcb.outidx", _at(c, "tcb") + 4 * 7), ("fir_c.tcb.inidx", _at(c, "tcb") + 4 * 11)]
    out += [(f"fir_d.out[{k}]", _at(d, "out") + 4 * k) for k in range(d["window"])]
    out += [("fir_d.tcb.outidx", _at(d, "tcb") + 4 * 10), ("fir_d.tcb.inidx", _at(d, "tcb") + 4 * 14)]
    for r in range(len(RUNS)):
        out += [(f"run{r + 1}.{what}", RESULTS_DM + 16 * r + 4 * k) for k, what in enumerate(("cycles", "dmastat", "reads"))]
    if len(out) > MAX_PUB:
        raise dsp.DspError(f"{len(out)} published words, PUBTAB holds {MAX_PUB}")
    return out


def state() -> bytes:
    """accel.asm's state block at boot: NRUNS, NHALVES, the next RUNS and RESULTS entries,
    RUNS and PUBTAB; the saves, PHASE, TICK, PUBI and RESULTS 0."""
    out = bytearray(STATE_BYTES)
    pub = published()
    struct.pack_into("<IIII", out, 0x4C, len(RUNS), 2 * len(pub), RUNS_DM, RESULTS_DM)
    for r, (name, base, bits, _) in enumerate(RUNS):
        acm = bool(bits & ACM)
        struct.pack_into("<III", out, 0x80 + 16 * r, base, chain_pointer(JOBS[name], acm), EN | DMAEN | bits)
    for k, (_, at) in enumerate(pub):
        struct.pack_into("<I", out, 0x200 + 4 * k, at)
    return bytes(out)


def objects() -> dict[str, bytes]:
    """The committed accel.asm and the idle back edge's JUMP to it."""
    spec = json.loads(CODE.read_text(encoding="utf-8"))
    return {name: sharc_object.load_bytes(bytes.fromhex(spec[name]["object_parcels_be"]))
            for name in ("accel", "accel_jump")}


def section7_accel(stock: bytes) -> bytes:
    """Stock + the idle stub + accel.asm, its state and the jobs' data. The idle loop's back
    edge goes to accel.asm, which goes on to the idle stub."""
    base = dsp.section7_idle_only(stock)
    obj = objects()
    code = obj["accel"]
    if STATE_DM - ACC_DM - len(code) < 64:
        raise dsp.DspError("accel.asm leaves fewer than 64 bytes of NOP padding")
    if len(obj["accel_jump"]) != len(dsp.IDLE_SITE_STOCK):
        raise dsp.DspError(f"the accel JUMP is {len(obj['accel_jump'])} bytes, not {len(dsp.IDLE_SITE_STOCK)}")
    if not (dsp.IDLE_PAD_END <= ACC_DM and DATA_DM + DATA_BYTES <= dsp.REGION[1]):
        raise dsp.DspError("accel's spans leave the block-1 region")
    added = [("accel.asm (wr_acc)", dsp.dm_to_load(ACC_DM), code + bytes(STATE_DM - ACC_DM - len(code))),
             ("accel state", dsp.dm_to_load(STATE_DM), state()),
             ("accel jobs", dsp.dm_to_load(DATA_DM), data())]
    dsp._check_free(stock, added)
    extra = b"".join(bootstream.block(at, payload) for _, at, payload in added)
    out = bytearray(bootstream.insert_before_final(base, extra))
    bootstream.write_span(out, dsp.l2_sw_to_load(dsp.IDLE_SITE_SW), obj["accel_jump"])
    return dsp._finish(out)


def decode(word: int) -> tuple[int, int]:
    """A reply word 2 as the ColdFire reads it (big-endian u32) -> (half index k, the half)."""
    return (word >> 16) - 1, word & 0xFFFF


def words(halves: dict[int, int]) -> dict[str, int]:
    """Half index -> half, as collected -> name -> the published word, for each word with
    both halves seen."""
    out = {}
    for k, (name, _) in enumerate(published()):
        lo, hi = halves.get(2 * k), halves.get(2 * k + 1)
        if lo is not None and hi is not None:
            out[name] = hi << 16 | lo
    return out


# The reference: what each published word should hold. The defaults are what the chip did
# on 2026-10-17 (accelprobe1 on the owner's Digitone II, every word; test/test_accel_reading.py),
# which digikit's models compute since ElekLabs/digikit#122: IIR0 "silicon" (stored word 5 is
# the state added to y, then x_state_first's order) and FIR0 "pairs". "model" is the models'
# order before that PR; the others were the candidates the reading chose from.
IIR_ORDERS = ("silicon", "model", "y_then_state", "x_state_first", "unrounded_products")
FIR_ORDERS = ("pairs", "model", "newest_first", "one_accumulator", "one_accumulator_newest", "quarters")
SILICON = {"iir_order": "silicon", "fir_order": "pairs"}


def _r(x: float) -> float:
    return _f32(x)


def _biquad(order: str, c, d, x):
    """One sample through one biquad (c = A0, A1, B1, A2, B2; d = [Dk2, Dk1]) -> y."""
    a0, a1, b1, a2, b2 = c
    if order == "unrounded_products":
        y = _r(a0 * x + d[1])
        d[1] = _r(_r(a1 * x + b1 * y) + d[0])
        d[0] = _r(a2 * x + b2 * y)
        return y
    y = _r(_r(a0 * x) + d[1])
    if order == "model":
        d[1] = _r(_r(_r(a1 * x) + _r(b1 * y)) + d[0])
        d[0] = _r(_r(a2 * x) + _r(b2 * y))
    elif order == "y_then_state":
        d[1] = _r(_r(a1 * x) + _r(_r(b1 * y) + d[0]))
        d[0] = _r(_r(a2 * x) + _r(b2 * y))
    else:                                               # x_state_first
        d[1] = _r(_r(_r(a1 * x) + d[0]) + _r(b1 * y))
        d[0] = _r(_r(a2 * x) + _r(b2 * y))
    return y


def iir_expected(job: dict, order: str = "silicon") -> tuple[list[float], list[float]]:
    """(the outputs over every input, each biquad's words 5 and 6 after them)."""
    co = job["coefs"]
    swap = order == "silicon"                           # _biquad adds d[1] to y: word 5 on the chip
    sections = [(co[7 * k:7 * k + 5], [co[7 * k + 6], co[7 * k + 5]] if swap else [co[7 * k + 5], co[7 * k + 6]])
                for k in range(job["biquads"])]
    out = []
    for x in job["x"]:
        for c, d in sections:
            x = _biquad("x_state_first" if swap else order, c, d, x)
        out.append(x)
    return out, [v for _, d in sections for v in (d[::-1] if swap else d)]


def fir_expected(job: dict, order: str = "pairs") -> list[float]:
    """The window's outputs: y[j] = sum C[N-1-i] x[j + i] in ORDER's rounding."""
    mem = list(reversed(job["c"]))                      # memory order: C[N-1] first
    taps, xs = len(mem), job["x"]
    out = []
    for j in range(job["window"]):
        terms = [_r(mem[i] * xs[j + i]) for i in range(taps)]   # oldest sample first
        if order in ("newest_first", "one_accumulator_newest"):
            terms = terms[::-1]
        if order.startswith("one_accumulator"):
            groups = [terms]
        elif order == "quarters":
            q = -(-taps // 4)
            groups = [terms[k * q:(k + 1) * q] for k in range(4) if terms[k * q:(k + 1) * q]]
        else:
            groups = [terms[k::4] for k in range(min(4, taps))]
        sums = []
        for g in groups:
            s = g[0]
            for t in g[1:]:
                s = _r(s + t)
            sums.append(s)
        if order == "pairs" and len(sums) == 4:
            y = _r(_r(sums[0] + sums[1]) + _r(sums[2] + sums[3]))
        else:
            y = sums[0]
            for s in sums[1:]:
                y = _r(y + s)
        out.append(y)
    return out


def _bits(x: float) -> int:
    return struct.unpack("<I", struct.pack("<f", x))[0]


def expected(iir_order: str = "silicon", fir_order: str = "pairs",
             acm_writeback: tuple[int, int] = (0xFFFFFFFF, 0)) -> dict[str, int]:
    """name -> the word each published output and write-back should hold (RESULTS aside).
    ACM_WRITEBACK is (INIDX, OUTIDX) after an ACM window: the chip's by default; (0, 0xFFFFFFFF)
    is the HWR's, which digikit's models wrote before ElekLabs/digikit#122."""
    out = {}
    a, sa = iir_expected(IIR_A, iir_order)
    out.update({f"iir_a.out[{k}]": _bits(v) for k, v in enumerate(a)})
    out.update({f"iir_a.coef[{k}]": _bits(v) for k, v in zip((5, 6, 12, 13), sa)})
    out["iir_a.tcb.outidx"] = word_address(_at(IIR_A, "out")) + 2 * IIR_A["window"]
    out["iir_a.tcb.inidx"] = word_address(_at(IIR_A, "inp")) + 2 * IIR_A["window"]
    b, _ = iir_expected(IIR_B, iir_order)
    out.update({f"iir_b.out[{k}]": _bits(v) for k, v in enumerate(b)})
    for name, job in (("fir_c", FIR_C), ("fir_d", FIR_D)):
        out.update({f"{name}.out[{k}]": _bits(v) for k, v in enumerate(fir_expected(job, fir_order))})
    out["fir_c.tcb.outidx"] = word_address(_at(FIR_C, "out")) + FIR_C["window"]
    out["fir_c.tcb.inidx"] = word_address(_at(FIR_C, "inp")) + FIR_C["window"]
    for name in ("iir_b", "fir_d"):                     # ACM: all ones and 0 (the chip; the HWR has 0 and all ones)
        out[f"{name}.tcb.inidx"], out[f"{name}.tcb.outidx"] = acm_writeback
    return out
