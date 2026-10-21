"""`dnfw wav`: a rendered WAV as numbers, findings and one sheet of plots.

    dnfw wav report RENDER.wav [-o DIR]
    dnfw wav compare BEFORE.wav AFTER.wav [-o DIR]

`report` writes RENDER.json (levels, DC, steps, band energy, spectral peaks, the pitch and
what lies between its harmonics, and plain findings) and RENDER.png (waveform, close-up,
spectrum, spectrogram) beside the file or into DIR, and prints the findings.
`compare` says whether two renders are the same samples and, if not, by how much, and
writes a sheet of the difference.
"""

from __future__ import annotations

import json
import pathlib

from ..audio import metrics, plots, wavio

NAME = "wav"
HELP = "read a rendered WAV: metrics, findings, and a sheet with its spectrum and spectrogram"


def configure(parser) -> None:
    sub = parser.add_subparsers(dest="action", required=True)
    report = sub.add_parser("report", help="metrics and plots for one render")
    report.add_argument("wav", type=pathlib.Path, nargs="+")
    report.add_argument("-o", "--out", type=pathlib.Path, help="directory for the .json and .png (default: beside the file)")
    compare = sub.add_parser("compare", help="two renders, sample for sample")
    compare.add_argument("before", type=pathlib.Path)
    compare.add_argument("after", type=pathlib.Path)
    compare.add_argument("-o", "--out", type=pathlib.Path)


def _target(path: pathlib.Path, out: pathlib.Path | None, suffix: str) -> pathlib.Path:
    folder = out if out else path.parent
    folder.mkdir(parents=True, exist_ok=True)
    return folder / (path.stem + suffix)


def _report(args) -> int:
    for path in args.wav:
        wav = wavio.read(path)
        measured = metrics.measure(wav)
        _target(path, args.out, ".json").write_text(json.dumps(measured, indent=1) + "\n")
        sheet = plots.sheet(wav, measured, path.name, _target(path, args.out, ".png"))
        print(f"{path.name}: {measured['duration_s']} s, peak {measured['peak_db']} dB, RMS {measured['rms_db']} dB, "
              f"pitch {measured.get('fundamental_hz')} Hz")
        for note in measured["findings"] or ["no finding"]:
            print("  - " + note)
        print(f"  {sheet}")
    return 0


def _compare(args) -> int:
    a, b = wavio.read(args.before), wavio.read(args.after)
    result = metrics.compare(a, b)
    _target(args.after, args.out, ".compare.json").write_text(json.dumps(result, indent=1) + "\n")
    if result.get("identical"):
        print(f"identical: {result['compared']} frames, every sample equal")
        return 0
    print(json.dumps(result))
    if result.get("compared") and result["same_rate"] and result["same_channels"]:
        n = result["compared"]
        diff = wavio.Wav(a.rate, b.data[:n] - a.data[:n], a.bits, True, 0)
        sheet = plots.sheet(diff, metrics.measure(diff), f"{args.after.name} minus {args.before.name}",
                            _target(args.after, args.out, ".compare.png"))
        print(f"  {sheet}")
    return 1


def run(args) -> int:
    return _report(args) if args.action == "report" else _compare(args)
