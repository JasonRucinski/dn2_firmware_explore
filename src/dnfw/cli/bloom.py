"""`dnfw bloom` -- Bloom's reference model (`docs/bloom-machine.md`, milestone B0).

  `dnfw bloom presets`              the factory sounds, and what each should sound like
  `dnfw bloom curve NAME`           PULSE's rate and pulse count over time, and where
                                     each pulse begins, for a preset
  `dnfw bloom render NAME OUT.wav`  the preset's demonstration pattern, 48 kHz 16-bit
                                     mono. `--dry` writes the machine's own signal (what
                                     the DSP gate compares); the default runs it through
                                     the preview's stand-in filter, which is not the
                                     instrument's

No firmware image is read or written.
"""

import math
import pathlib
import wave

from ..bloom import clock, presets, pulse, voice

NAME = "bloom"
HELP = "Bloom's reference model: factory sounds, PULSE curves and preview renders"


def configure(parser) -> None:
    sub = parser.add_subparsers(dest="action", required=True)
    sub.add_parser("presets", help="list the factory sounds")
    c = sub.add_parser("curve", help="PULSE's rate and pulses over time for a preset")
    c.add_argument("name")
    c.add_argument("--step", type=float, default=0.5, help="print interval, in PULSE's unit")
    r = sub.add_parser("render", help="render a preset's demonstration pattern to a WAV")
    r.add_argument("name")
    r.add_argument("out", type=pathlib.Path)
    r.add_argument("--dry", action="store_true", help="the machine's own signal, no stand-in filter")
    r.add_argument("--seconds", type=float, help="override the pattern's length")


def _presets() -> int:
    for name, demo in presets.PRESETS.items():
        print(f"{name}\n    {demo.listen_for}")
    return 0


def _curve(args) -> int:
    demo = presets.get(args.name)
    s = demo.sound
    g = s.glide()
    unit = "beats" if s.sync else "s"
    per = " per beat" if s.sync else " Hz"
    span = g.time if g.time else (4.0 if s.sync else 2.0)
    print(f"{args.name}: {g.start:g} -> {g.end:g}{per} over {g.time:g} {unit}, "
          f"{g.curve}, {g.mode}; {pulse.glide_cycles(g):.3f} cycles in the glide")
    t = 0.0
    while t <= span + 1e-9:
        print(f"  t {t:7.3f} {unit:5}  rate {pulse.rate(g, t):9.4f}  "
              f"phase {pulse.phase(g, t):9.4f}")
        t += args.step
    starts, k = [], 1
    while True:                                    # each pulse begins at an integer phase
        lo, hi = 0.0, span
        if pulse.phase(g, hi) < k:
            break
        for _ in range(60):
            mid = (lo + hi) / 2
            lo, hi = (mid, hi) if pulse.phase(g, mid) < k else (lo, mid)
        starts.append(hi)
        k += 1
    print(f"  pulses begin at ({unit}): " + ", ".join(f"{x:.3f}" for x in starts))
    return 0


def _render(args) -> int:
    demo = presets.get(args.name)
    seconds = args.seconds or demo.seconds
    out = voice.render(demo.sound, demo.events(), seconds, demo.bpm, demo.kicks(),
                       preview=not args.dry)
    samples = out.dry if args.dry else out.preview
    peak = max((abs(x) for x in samples), default=0.0) or 1.0
    scale = 0.89 / peak                            # about -1 dBFS
    frames = b"".join(int(max(-1.0, min(1.0, x * scale)) * 32767).to_bytes(2, "little", signed=True)
                      for x in samples)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(args.out), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(int(voice.RATE))
        w.writeframes(frames)
    what = "dry (the machine's own signal)" if args.dry else "preview (stand-in filter, not the instrument's)"
    print(f"{args.out}: {seconds:.2f} s, {what}, normalised by {20 * math.log10(scale):+.1f} dB")
    return 0


def run(args) -> int:
    if args.action == "presets":
        return _presets()
    if args.action == "curve":
        return _curve(args)
    return _render(args)
