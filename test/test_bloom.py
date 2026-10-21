"""Bloom's reference model (milestone B0, `docs/bloom-machine.md`).

Each test states a property the design claims, so the DSP code can later be held
to the same claims. No firmware image is needed.
"""

import math
import wave

import pytest

from dnfw.bloom import clock, duck, osc, presets, pulse, voice
from dnfw.bloom.pulse import Glide
from dnfw.bloom.sound import Sound, linked
from dnfw.cli import main as cli


# ---- the clock --------------------------------------------------------------------

def test_every_note_length_divides_the_position_wrap():
    # the frame's position wraps at 384 sixteenths; a phase that is position x a whole
    # number stays continuous across the wrap only if each length fits whole times
    for name, per_beat in clock.NOTE_LENGTHS.items():
        cycles = per_beat * clock.BEATS_PER_WRAP
        assert abs(cycles - round(cycles)) < 1e-9, name


def test_position_round_trip():
    for beats in (0.0, 1.0, 13.25, 95.999):
        assert clock.beats_from_position(clock.position_from_beats(beats)) == pytest.approx(beats, abs=1e-6)
    assert clock.bpm_from_tempo_word(150 * 120) == 150.0


# ---- the glide --------------------------------------------------------------------

INNERBLOOM = Glide(12.0, 1.0, 8.0)


def _integral(g, t, n=20000):
    h = t / n
    return sum(pulse.rate(g, (i + 0.5) * h) for i in range(n)) * h


@pytest.mark.parametrize("g", [INNERBLOOM, Glide(1.0, 16.0, 16.0), Glide(2.0, 8.0, 4.0, "lin"),
                               Glide(3.0, 3.0, 2.0)])
def test_phase_is_the_integral_of_the_rate(g):
    for t in (0.3 * g.time, 0.77 * g.time, g.time, 1.5 * g.time):
        assert pulse.phase(g, t) == pytest.approx(_integral(g, t), rel=1e-5)


def test_the_brief_is_about_35_pulses():
    assert pulse.glide_cycles(INNERBLOOM) == pytest.approx(8 * 11 / math.log(12), rel=1e-12)
    assert 35 < pulse.glide_cycles(INNERBLOOM) < 36
    assert pulse.rate(INNERBLOOM, 0) == 12.0 and pulse.rate(INNERBLOOM, 8.0) == 1.0


@pytest.mark.parametrize("mode", pulse.MODES)
def test_phase_never_jumps_and_never_runs_backwards(mode):
    # the brief: a change of rate never restarts the phase
    for g in (Glide(12.0, 1.0, 8.0, mode=mode), Glide(1.0, 16.0, 16.0, mode=mode)):
        dt = g.time / 4000
        fastest = max(pulse.rate(g, i * dt) for i in range(6001))
        prev = 0.0
        for i in range(1, 6001):
            p = pulse.phase(g, i * dt)
            assert p >= prev
            # no step covers more than the fastest rate allows: no jump anywhere,
            # at the glide's end included
            assert p - prev <= fastest * dt * 1.01   # the rate still rises within a step
            prev = p


def test_land_ends_the_glide_on_a_whole_cycle_and_keeps_the_end_rate():
    g = Glide(1.0, 16.0, 16.0, mode="land")          # the riser: 1/4 -> 1/64 over 4 bars
    n = pulse.phase(g, g.time)
    assert n == round(n) == pulse.glide_cycles(g)
    assert pulse.rate(g, g.time + 1) == 16.0
    # after the glide the cycles stay on the 1/64 grid
    assert pulse.phase(g, g.time + 0.25) == pytest.approx(n + 4)


def test_land_moves_the_rates_by_only_a_little():
    smooth = Glide(12.0, 1.0, 8.0)
    land = Glide(12.0, 1.0, 8.0, mode="land")
    assert pulse.rate(land, 0) / pulse.rate(smooth, 0) == pytest.approx(35 / pulse.glide_cycles(smooth))
    assert abs(pulse.rate(land, 0) / 12.0 - 1) < 0.02


def test_step_puts_every_edge_on_the_grid():
    g = Glide(clock.note_rate("1/4"), clock.note_rate("1/32"), 4.0, mode="step")
    # every rung completes a whole number of cycles, and each lasts one beat
    for beat in range(5):
        assert pulse.phase(g, beat) == pytest.approx(round(pulse.phase(g, beat)), abs=1e-9)
    assert [pulse.rate(g, b + 0.5) for b in range(4)] == [1.0, 2.0, 4.0, 8.0]


def test_both_directions():
    bloom, build = Glide(8.0, 1.0, 4.0), Glide(1.0, 8.0, 4.0)
    assert pulse.rate(bloom, 1) > pulse.rate(bloom, 3)
    assert pulse.rate(build, 1) < pulse.rate(build, 3)


def test_bad_controls_are_refused():
    for args in ((0.0, 1.0, 1.0), (1.0, -1.0, 1.0), (1.0, 1.0, -1.0)):
        with pytest.raises(ValueError):
            Glide(*args)
    with pytest.raises(ValueError):
        Glide(1.0, 2.0, 1.0, curve="cubic")
    with pytest.raises(ValueError):
        Sound(start="1/8")                          # a note length needs SYNC


# ---- shapes and TILT --------------------------------------------------------------

@pytest.mark.parametrize("shap", [0.0, 0.25, 0.5, 0.75, 1.0])
def test_shapes_are_bounded_and_start_low(shap):
    ys = [pulse.shape(i / 1000, shap) for i in range(1000)]
    assert min(ys) >= -1.0 - 1e-9 and max(ys) <= 1.0 + 1e-9
    assert pulse.shape(0.0, shap) < -0.9              # the filter is closed on the trig
    assert max(ys) > 0.9                              # and opens fully during the cycle


def test_tilt_grows_or_shrinks_the_depth_across_the_glide():
    g = Glide(4.0, 1.0, 2.0)
    assert pulse.tilted_depth(40, 0.5, g, 0) == 40
    assert pulse.tilted_depth(40, 0.5, g, 2) == 60
    assert pulse.tilted_depth(40, -1.0, g, 2) == 0
    assert pulse.tilted_depth(40, 0.5, g, 5) == 60    # held after the glide


# ---- the oscillators ------------------------------------------------------------

def test_polyblep_saw_is_bounded_and_centred():
    o = osc.Oscillator()
    ys = [o.next(440.0, 0.0, 0.5) for _ in range(48000)]
    assert max(abs(y) for y in ys) <= 1.0 + 1e-9
    assert abs(sum(ys) / len(ys)) < 0.01


def test_polyblep_smooths_the_saw_step():
    # the naive saw jumps by 2 at the wrap; with the BLEP no single step is that large
    o = osc.Oscillator()
    ys = [o.next(2000.0, 0.0, 0.5) for _ in range(2000)]
    assert max(abs(b - a) for a, b in zip(ys, ys[1:])) < 1.5


# ---- DUCK -------------------------------------------------------------------------

def test_duck_dips_on_the_trig_without_clicking_and_recovers():
    d = duck.Duck([1.0], release=0.1)
    assert d.gain(0.99, 1.0) == 1.0
    assert d.gain(1.0 + duck.ATTACK, 1.0) == pytest.approx(0.0)
    assert d.gain(1.0 + duck.ATTACK / 2, 1.0) == pytest.approx(0.5)   # a ramp, not a jump
    assert d.gain(1.5, 1.0) > 0.98


def test_a_fast_second_trig_continues_from_where_the_first_left_it():
    d = duck.Duck([0.0, 0.0002], release=0.1)
    before = d.envelope(0.0002 - 1e-9)
    # within one nanosecond of the 1 ms ramp's slope: continuous, no jump
    assert d.envelope(0.0002) == pytest.approx(before, abs=1e-5)
    d = duck.Duck([i * 0.4 for i in range(400)], release=0.1)        # a long pattern: no recursion
    assert 0 <= d.envelope(150.0) <= 1


# ---- the voice ----------------------------------------------------------------------

def test_cutoff_is_written_once_a_block():
    demo = presets.get("innerbloom")
    out = voice.render(demo.sound, demo.events(), 0.1, demo.bpm, rate=48000, preview=False)
    assert len(out.cutoff) == math.ceil(4800 / voice.BLOCK)
    assert all(0 <= c <= 127 for c in out.cutoff)
    assert all(math.isfinite(y) for y in out.dry)


def test_a_bar_anchored_pulse_continues_across_a_chord_change():
    # breathing-pad: a chord per bar, the glide every 2 bars. At the bar 1 chord change
    # the pulse must not restart; with ANCH trig the same sound does restart there
    demo = presets.get("breathing-pad")
    bar = 4 * 60.0 / demo.bpm
    blk = int(bar * 48000 / voice.BLOCK)
    seconds = bar + 0.02
    on_bar = voice.render(demo.sound, demo.events(), seconds, demo.bpm, preview=False)
    on_trig = voice.render(Sound(**{**demo.sound.__dict__, "anchor": "trig"}), demo.events(),
                           seconds, demo.bpm, preview=False)
    assert abs(on_bar.pulse[blk + 1] - on_bar.pulse[blk - 1]) < 0.2
    assert on_trig.pulse[blk - 1] > 0.5               # the control: high before the trig,
    assert on_trig.pulse[blk + 1] < -0.85             # restarted low just after it


def test_the_chop_never_jumps():
    demo = presets.get("future-chop")
    out = voice.render(demo.sound, demo.events()[:1], 0.6, demo.bpm, demo.kicks(), preview=False)
    # the level the chop and the duck apply, sample to sample, through a held saw:
    # its envelope may not step by more than the softened square's edge allows
    s = demo.sound
    g = s.glide()
    levels = [voice.chop(pulse.value(g, voice.anchor_time(s, i / 48000, 0.0, demo.bpm), s.shap), s.vdep)
              for i in range(int(0.6 * 48000))]
    assert max(abs(b - a) for a, b in zip(levels, levels[1:])) < 0.02


def test_link_takes_the_other_tracks_pulse_and_keeps_its_own_voice():
    chords = Sound(start=6.0, end=0.5, time=4.0, wav1=0.0)
    bass = Sound(wav1=0.5, link=1)
    got = linked(bass, {1: chords})
    assert (got.start, got.end, got.time, got.wav1) == (6.0, 0.5, 4.0, 0.5)
    with pytest.raises(ValueError):
        linked(Sound(link=7), {1: chords})


def test_every_chord_of_a_pattern_sounds():
    # a voice's gate is 0 at its first sample; it must not be taken for finished
    demo = presets.get("future-chop")
    bar = 4 * 60.0 / demo.bpm
    out = voice.render(Sound(), demo.events()[:2], 2 * bar, demo.bpm, preview=False)
    second = out.dry[int(1.2 * bar * 48000):int(1.8 * bar * 48000)]
    assert max(abs(y) for y in second) > 0.05


def test_every_preset_builds():
    for name, demo in presets.PRESETS.items():
        demo.sound.glide()
        assert demo.events() and demo.listen_for, name
    with pytest.raises(ValueError):
        presets.get("nope")


# ---- the command line -----------------------------------------------------------------

def test_cli_render_writes_a_wav(tmp_path, capsys):
    out = tmp_path / "bloom.wav"
    assert cli.main(["bloom", "render", "innerbloom", str(out), "--seconds", "0.05", "--dry"]) == 0
    with wave.open(str(out)) as w:
        assert (w.getnchannels(), w.getsampwidth(), w.getframerate()) == (1, 2, 48000)
        assert w.getnframes() == 2400
    assert cli.main(["bloom", "curve", "riser", "--step", "8"]) == 0
    assert "87.000 cycles" in capsys.readouterr().out


# ---- B3a: the type-7 loop's float32 contract (dnfw.bloom.live) ------------------------------

from dnfw.bloom import live  # noqa: E402


def test_live_tables_are_pitch_steps_and_their_inverses():
    dt, inv = live.dt_table(), live.inv_table()
    assert len(dt) == len(inv) == live.NOTES
    assert dt[69] == pytest.approx(440.0 / 48000, rel=1e-7)
    assert dt[81] == pytest.approx(2 * dt[69], rel=1e-6)
    assert all(abs(d * i - 1) < 1e-6 for d, i in zip(dt, inv))


def test_live_interpolated_inverse_stays_close_to_the_true_one():
    for n in (0.0, 12.5, 60.25, 99.9, 127.0):
        d, i = live.step(n)
        assert abs(d * i - 1) < 0.002


def test_live_note_is_clamped_and_cleaned_as_the_loop_does():
    assert live.note_from_frame(60.0, 0x4000) == 60.0          # TUN1 0
    assert live.note_from_frame(60.0, 0x4c00) == 72.0          # TUN1 +12
    assert live.note_from_frame(float("nan"), 0x4000) == 0.0
    assert live.note_from_frame(-5.0, 0x4000) == 0.0
    assert live.note_from_frame(120.0, 0x7c00) == 127.0


def test_live_saw_is_bounded_and_matches_the_float64_model():
    a = live.render(60.0, 0x4000, 20)
    assert max(abs(x) for x in a) <= live.GAIN * 1.0001
    o = osc.Oscillator()
    b = [live.GAIN * o.next(osc.hz(60), 0.0, 0.5) for _ in range(len(a))]
    assert max(abs(x - y) for x, y in zip(a, b)) < 0.005           # float32 phase drift only


def test_live_phase_carries_across_blocks():
    dt, inv = live.step(60.0)
    whole, _ = live.render_block(0.0, dt, inv, 64)
    first, p = live.render_block(0.0, dt, inv, 32)
    second, _ = live.render_block(p, dt, inv, 32)
    assert first + second == whole


# -- B3b: the pulse contract (live.pulse_block) ---------------------------------------------

def _pulse(blocks, page=0x4000, trig_at=(1,)):
    s = live.PulseState()
    return [live.pulse_block(s, page, b in trig_at) for b in range(blocks)], s


def test_pulse_is_silent_until_the_first_trig():
    words, s = _pulse(5, trig_at=())
    assert words == [0x4000] * 5 and s.step == 0.0


def test_pulse_swings_depth_either_way_and_clamps():
    words, _ = _pulse(400)
    assert min(words) == 0x4000 - 8192                  # the trig block: phase 0, m = -1
    assert 0x4000 + 8192 - 300 < max(words) <= 0x4000 + 8192   # a peak near m = +1
    high, _ = _pulse(400, page=0x7800)
    assert max(high) == live.FREQ_MAX
    low, _ = _pulse(400, page=0x0400)
    assert min(low) == 0


def test_pulse_glides_from_12_to_1_hz_over_8_seconds():
    s = live.PulseState()
    live.pulse_block(s, 0x4000, True)
    assert s.step == live._f(live.PULSE_STEP0 * live.PULSE_RATIO)      # stepped once in the trig block
    block_s = live.PULSE_BLOCK / live.RATE
    while s.n < live.PULSE_BLOCKS // 2:
        live.pulse_block(s, 0x4000, False)
    assert abs(s.step / block_s - 12 * (1 / 12) ** 0.5) < 0.01         # ~3.46 Hz at 4 s
    while s.n < live.PULSE_BLOCKS - 1:
        live.pulse_block(s, 0x4000, False)
    assert abs(s.step / live.PULSE_STEP1 - 1) < 1e-3                    # float drift, small
    live.pulse_block(s, 0x4000, False)
    assert s.step == live.PULSE_STEP1 and s.n == live.PULSE_BLOCKS      # lands exactly
    live.pulse_block(s, 0x4000, False)
    assert s.step == live.PULSE_STEP1 and s.n == live.PULSE_BLOCKS


def test_pulse_cycles_match_the_closed_form():
    """Over the glide, the phase advances R0*T*(k-1)/ln k cycles (about 35.4)."""
    import math as _m
    s = live.PulseState()
    live.pulse_block(s, 0x4000, True)
    cycles, last = 0, s.phase
    while s.n < live.PULSE_BLOCKS:
        live.pulse_block(s, 0x4000, False)
        cycles += s.phase < last
        last = s.phase
    k = live.PULSE_END_HZ / live.PULSE_START_HZ
    want = live.PULSE_START_HZ * live.PULSE_TIME_S * (k - 1) / _m.log(k)
    assert abs(cycles + s.phase - want) < 0.05


def test_pulse_rides_the_coldfire_value_not_its_own():
    s = live.PulseState()
    live.pulse_block(s, 0x4000, True)
    w = live.pulse_block(s, 0x4000, False)
    live.pulse_block(s, w, False)               # the ring hands back a rewritten page
    assert s.base == 0x4000
    live.pulse_block(s, 0x3000, False)          # the owner turns FREQ
    assert s.base == 0x3000


def test_a_new_trig_restarts_the_glide():
    s = live.PulseState()
    live.pulse_block(s, 0x4000, True)
    for _ in range(3000):
        live.pulse_block(s, 0x4000, False)
    assert s.step < live.PULSE_STEP0
    live.pulse_block(s, 0x4000, True)
    assert s.n == 1 and s.step == live._f(live.PULSE_STEP0 * live.PULSE_RATIO)
