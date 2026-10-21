"""Bloom B3b (offline): PULSE on FREQ, the section 7 the Bloom mod ships, in the runner.

    python scripts/sharc_bloom_b3b.py \\
        --image 00_Resources/00_Firmware/Digitone_II_OS1.11_dist.zip \\
        --digikit ../digikit-wt-sharcemu [--blocks 12]

The image is `dnfw.bloom.dsp.section7(stock)`. The handler's call of the per-block
routine (sw 0x1c9fbc) is not in the runner's path: the runner calls the routine
`sw 0x1c2712` directly, as the handler does (`scripts/sharc_waverider_m4.py`). So each
block here first runs the image's own hook, `pulse.asm` at sw 0x16f400 (where the
image's JUMP at sw 0x1c9fb9 goes), with the handler's arguments in R4, R8 and R12 and
the frame already in the received page, until it jumps back to the call at 0x1c9fbc;
then it calls the routine as usual, on the page the hook left.

Frames: track 0 and track 3 on machine 7, track 5 on WaveTone, FREQ 64 (0x4000) on all
three; track 0 trigged on block 1, track 3 never. On block 6 track 0's FREQ word is
sent as the word the hook wrote the block before: the ring handing back a page the
hook has already rewritten, which must not move the pulse's base.

**PASS** when: the hook runs once a block and returns to 0x1c9fbc with R4 = 0x268438
(the displaced load) and every other register it touches restored; the frame copy the
unpack made carries, in track 0's FREQ word, `dnfw.bloom.live.pulse_block`'s word for
that block, track 3's and track 5's FREQ unchanged, and every other byte as sent; every
track's buffer at the routine's end equals, bit for bit, a run of the image without the
pulse fed those same words in the frame (B1b's equivalence, now through Bloom's code);
the pulse is heard (track 0 differs from that image fed the plain frames); and, with
track 0's state set 3 blocks short of the glide's end, the glide lands: n reaches
12000, the step becomes STEP1 exactly, and the words keep matching.

Results to `out/bloom/b3b_report.json`. Exit 0 on PASS.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import struct
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import sharc_bloom_b3a as b3a                                  # noqa: E402
import sharc_dn2_fixups as fx                                  # noqa: E402
import sharc_waverider_m3 as m3                                # noqa: E402
import sharc_waverider_m4 as m4                                # noqa: E402
import sharc_waverider_m5 as m5                                # noqa: E402
import sharc_waverider_render as m1                            # noqa: E402
import sharc_waverider_voice as m2                             # noqa: E402
from dnfw.bloom import dsp, live                               # noqa: E402
from dnfw.waverider import frame as FR                         # noqa: E402
from dnfw.waverider import voice as V                          # noqa: E402

OUT = b3a.OUT
BLOCK = m4.BLOCK
FREQ = 67
BASE_WORD = 0x4000
REDELIVER_AT = 6
KEPT = [f"R{k}" for k in range(16) if k != 4] + ["I1", "I2"]


def frame_bytes(sound, machines, b, words=None, redeliver=None) -> bytes:
    """Block B's frame. WORDS {track: FREQ word} replaces the plain FREQ (the reference);
    REDELIVER, on block REDELIVER_AT, is track 0's word as the hook wrote it last block."""
    f = m5.base_frame(sound, machines, t0=dsp.TYPE, trigger=(b == 1), overrides={FREQ: BASE_WORD},
                      others={3: 1, 5: 1})
    f.header(FR.MACHINE, 3, dsp.TYPE)
    f.param(3, FREQ, BASE_WORD)
    f.param(5, FREQ, BASE_WORD)
    if redeliver is not None and b == REDELIVER_AT:
        f.param(0, FREQ, redeliver)
    for t, w in (words or {}).items():
        f.param(t, FREQ, w)
    return f.to_bytes()


def call(state, frame: bytes, *, hook: bool, pokes=None):
    """One block: the received page filled with FRAME, the hook run on it when HOOK
    (stopping at its jump back to the call), then sw 0x1c2712 on that page.
    -> (runner ready to run the routine, hook record)."""
    s = state.state
    idx = m2.word(s, m4.RX_INDEX) or 0
    i7 = m2.word_reg(state, "I6" if s.pc_sw == m4.UNPACK_RETURN else "I7")
    rx = m4.RX_BASE + (idx << 8)
    args = {"R8": m4.UNPACK_LOCAL, "R12": rx, "I6": i7, "I7": i7 - 16}
    rec = None
    if hook:
        regs = {**args, "R4": 0, "R2": 0x2D2D2D2D, "R0": 0x11111111, "R15": 0x0F0F0F0F,
                "I1": 0x12345678, "I2": 0x23456789}
        p = state.fresh_call(dsp.PULSE_SW, regs=regs, return_address=m4.UNPACK_CALLER)
        for k in range(0, len(frame), 4):
            m2.poke(p.state, rx + k, struct.unpack_from("<I", frame, k)[0])
        for addr, value in (pokes or {}).items():
            m2.poke(p.state, addr, value)
        before = {r: m2.word_reg(p, r) for r in KEPT}
        res = fx.run(p, 400_000, m4.fixups({}), stop_at=[dsp.CALL_RESUME_SW])
        after = {r: m2.word_reg(p, r) for r in KEPT}
        rec = {"stopped": res[0] == "stop" and res[1] == dsp.CALL_RESUME_SW, "instructions": res[2],
               "r4": m2.word_reg(p, "R4"), "restored": before == after,
               "changed": {r: (hex(before[r]), hex(after[r])) for r in KEPT if before[r] != after[r]}}
        state = p
    r = state.fresh_call(m4.UNPACK, regs={"R4": 0x268438, **args}, return_address=m4.UNPACK_CALLER)
    for k in range(10):
        m2.poke(r.state, m4.UNPACK_LOCAL + 4 * k, 0)
    m2.poke(r.state, i7 + 4, 0)
    m2.poke(r.state, i7 + 8, m4.RX_PAGE + (idx << 11))
    if not hook:
        for k in range(0, len(frame), 4):
            m2.poke(r.state, rx + k, struct.unpack_from("<I", frame, k)[0])
    return r, rec


def run(init, frame_of, blocks: int, *, hook: bool, pokes=None) -> dict:
    """BLOCKS blocks; per block: the hook's record, the frame copy the unpack made, every
    track's buffer at the routine's end (bits), track 0's pulse state after it."""
    state = init
    out = {"hooks": [], "copies": [], "buffers": [], "states": []}
    for b in range(blocks):
        tap = {}

        def at_dispatch(r):
            tap["bufs"] = [m2.word(r.state, V.TRACK_BUFFERS + 4 * t) for t in range(16)]

        def at_loop(r):
            tap["copy"] = b"".join(struct.pack("<I", m2.word(r.state, m5.FRAME_COPY + k) or 0)
                                   for k in range(0, FR.FRAME_BYTES, 4))

        r, rec = call(state, frame_of(b, out), hook=hook, pokes=(pokes if b == 0 else None))
        res = fx.run(r, 8_000_000, m4.fixups({m3.DISPATCH: at_dispatch, dsp.LOOP_SW: at_loop}))
        if not (res[0] == "halt" and res[1].pc_sw == m4.UNPACK_RETURN):
            halt = f"{res[1].reason} at {res[1].pc_sw:#x}" if res[0] == "halt" else f"{res[0]}"
            return {**out, "ok": False, "blocks": b, "halt": halt}
        out["hooks"].append(rec)
        out["copies"].append(tap.get("copy"))
        out["buffers"].append([[m2.word(r.state, tap["bufs"][t] + 4 * k) or 0 for k in range(BLOCK)]
                               for t in range(16)])
        st = dsp.PULSE_STATE_DM
        out["states"].append([m2.word(r.state, st + 4 * k) or 0 for k in range(5)])
        state = r
    return {**out, "ok": True, "blocks": blocks}


def word_at(copy: bytes, t: int) -> int:
    return struct.unpack_from("<H", copy, FR.slot_offset(t, FREQ))[0]


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0],
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--image", type=pathlib.Path, default=m4.IMAGE)
    p.add_argument("--digikit", type=pathlib.Path,
                   default=pathlib.Path(os.environ.get("DNFW_DIGIKIT_SHARC",
                                                       ROOT.parent / "digikit-wt-sharcemu")))
    p.add_argument("--blocks", type=int, default=12)
    a = p.parse_args(argv)
    if not a.image.exists():
        raise SystemExit(f"{a.image}: the Digitone II OS 1.11 file is needed (bring your own)")
    if a.blocks <= REDELIVER_AT + 1:
        raise SystemExit(f"--blocks must be more than {REDELIVER_AT + 1}")
    OUT.mkdir(parents=True, exist_ok=True)
    dk = m1.Digikit(a.digikit)
    fx.bind(str(a.digikit / "tools"))
    m4.IMAGE = a.image
    stock = m1.dn2_section7(a.image)
    sound, machines = m4.init_sound(a.image)
    img, plain = m5.Image(dk, dsp.section7(stock)), m5.Image(dk, dsp.section7(stock, pulse=False))
    with tempfile.TemporaryDirectory(dir=OUT) as tmp:
        init = b3a.init_runner(dk, stock, img, pathlib.Path(tmp))
        init_plain = b3a.init_runner(dk, stock, plain, pathlib.Path(tmp))
    n = a.blocks

    # the reference: pulse_block on the words the frames carry
    ref, sent, s = [], [], live.PulseState()
    for b in range(n):
        page = ref[-1] if b == REDELIVER_AT else BASE_WORD
        sent.append(page)
        ref.append(live.pulse_block(s, page, b == 1))

    print("  running")
    pulsed = run(init, lambda b, o: frame_bytes(sound, machines, b, redeliver=ref[b - 1] if b else None),
                 n, hook=True)
    fed = run(init_plain, lambda b, o: frame_bytes(sound, machines, b, words={0: ref[b]}), n, hook=False)
    unpulsed = run(init_plain, lambda b, o: frame_bytes(sound, machines, b), n, hook=False)

    # the glide's end: track 0's state 3 blocks short of 12000, no trig
    late_s = live.PulseState()
    live.pulse_block(late_s, BASE_WORD, True)
    while late_s.n < live.PULSE_BLOCKS - 3:
        live.pulse_block(late_s, BASE_WORD, False)
    late_s.phase = 0.25
    f32 = lambda x: struct.unpack("<I", struct.pack("<f", x))[0]      # noqa: E731
    pokes = {dsp.PULSE_STATE_DM: f32(late_s.step), dsp.PULSE_STATE_DM + 4: f32(late_s.phase),
             dsp.PULSE_STATE_DM + 8: late_s.n, dsp.PULSE_STATE_DM + 12: late_s.base,
             dsp.PULSE_STATE_DM + 16: late_s.last}
    late_ref = [live.pulse_block(late_s, BASE_WORD, False) for _ in range(5)]
    late = run(init, lambda b, o: frame_bytes(sound, machines, b + 2), 5, hook=True, pokes=pokes)

    every = {"pulsed": pulsed, "fed": fed, "unpulsed": unpulsed, "late": late}
    ok_runs = all(r["ok"] for r in every.values())
    checks = {"every run returns every block": ok_runs}
    num = {"section7_bytes": len(img.stream), "section7_sha256": img.sha, "digikit_head": dk.head,
           "blocks": n, "reference_words": [hex(w) for w in ref], "sent_words": [hex(w) for w in sent],
           "placements": dsp.placements()}
    if ok_runs:
        spec = json.loads(dsp.CODE.read_text(encoding="utf-8"))["pulse"]
        decode = m4.check_targets(dk, img.memory, dsp.PULSE_SW, spec["instruction_offsets"])
        hooks = pulsed["hooks"] + late["hooks"]
        got0 = [word_at(c, 0) for c in pulsed["copies"]]
        expect_copies = [frame_bytes(sound, machines, b, words={0: ref[b]}) for b in range(n)]
        diffs = [[k for k in range(0, FR.FRAME_BYTES, 2) if c[k:k + 2] != e[k:k + 2]]
                 for c, e in zip(pulsed["copies"], expect_copies)]
        late_got = [word_at(c, 0) for c in late["copies"]]
        num.update({"track0_words": [hex(w) for w in got0], "late_words": [hex(w) for w in late_got],
                    "late_reference": [hex(w) for w in late_ref], "late_states": late["states"],
                    "hook_instructions": [h["instructions"] for h in hooks],
                    "hook_changed": [h["changed"] for h in hooks if h["changed"]],
                    "copy_bytes_differing": [len(d) for d in diffs], "decode": decode})
        first_heard = next((b for b in range(n) if pulsed["buffers"][b][0] != unpulsed["buffers"][b][0]), None)
        num["first_block_heard"] = first_heard
        checks.update({
            "digikit decodes pulse.asm on selas's boundaries, nothing unknown":
                decode["boundaries_match_assembler"] and not decode["unknown_or_uncertain"],
            "the hook returns to the call at 0x1c9fbc, every block": all(h["stopped"] for h in hooks),
            "it leaves R4 = 0x268438, the displaced load": all(h["r4"] == 0x268438 for h in hooks),
            "it restores every other register it uses": all(h["restored"] for h in hooks),
            "track 0's FREQ in the frame copy is pulse_block's word, every block": got0 == ref,
            "the words pulse (more than 4 distinct after the trig)": len(set(ref[2:])) > 4,
            "track 3 (machine 7, never trigged) and track 5 (WaveTone) keep FREQ 0x4000":
                all(word_at(c, 3) == BASE_WORD and word_at(c, 5) == BASE_WORD for c in pulsed["copies"]),
            "every other byte of the frame copy is as sent": all(not d for d in diffs),
            "a re-delivered rewritten page keeps the base (block 6)": got0[REDELIVER_AT] == ref[REDELIVER_AT],
            "all 16 buffers equal the plain image fed the same words, bit for bit":
                pulsed["buffers"] == fed["buffers"],
            "the pulse is heard: track 0 differs from the plain frames":
                first_heard is not None and first_heard <= 3,
            "control: tracks 1-15 equal the plain frames'":
                all(p_[1:] == u[1:] for p_, u in zip(pulsed["buffers"], unpulsed["buffers"])),
            "the glide lands: words match across the end": late_got == late_ref,
            "n reaches 12000 and the step is STEP1 exactly":
                late["states"][-1][2] == live.PULSE_BLOCKS and late["states"][-1][0] == f32(live.PULSE_STEP1),
        })
    else:
        num["halts"] = {x: r.get("halt") for x, r in every.items() if not r["ok"]}
    passed = all(checks.values())
    path = OUT / "b3b_report.json"
    path.write_text(json.dumps({"pass": passed, "checks": checks, "numbers": num}, indent=2,
                               default=str) + "\n", encoding="utf-8")
    for name, v in checks.items():
        print(f"  {'PASS' if v else 'FAIL'}  {name}")
    for key in ("reference_words", "track0_words", "late_reference", "late_words", "first_block_heard",
                "hook_changed", "halts"):
        if key in num:
            print(f"  {key}: {num[key]}")
    print(f"\nB3b {'PASS' if passed else 'FAIL'}: {path}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
