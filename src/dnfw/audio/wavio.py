"""A WAV file as floats: PCM of 16, 24 or 32 bits, and float of 32 or 64."""

from __future__ import annotations

import pathlib
import struct
from dataclasses import dataclass

import numpy as np

PCM, FLOAT, EXTENSIBLE = 1, 3, 0xFFFE


@dataclass
class Wav:
    rate: int
    data: np.ndarray            # frames x channels, float64, full scale 1.0
    bits: int
    is_float: bool
    at_full_scale: int          # samples at the format's largest value: clipped, or as good as
    comment: str = ""           # the file's own note on where it came from (LIST/INFO ICMT), if any

    @property
    def mono(self) -> np.ndarray:
        return self.data.mean(axis=1)


def read(path: str | pathlib.Path) -> Wav:
    raw = pathlib.Path(path).read_bytes()
    if raw[:4] != b"RIFF" or raw[8:12] != b"WAVE":
        raise ValueError(f"{path}: not a RIFF/WAVE file")
    at, fmt, body, comment = 12, None, None, ""
    while at + 8 <= len(raw):
        tag, size = raw[at:at + 4], struct.unpack_from("<I", raw, at + 4)[0]
        if tag == b"fmt ":
            fmt = raw[at + 8:at + 8 + size]
        elif tag == b"data":
            body = raw[at + 8:at + 8 + size]
        elif tag == b"LIST" and raw[at + 8:at + 12] == b"INFO":
            sub = at + 12
            while sub + 8 <= at + 8 + size:
                name, length = raw[sub:sub + 4], struct.unpack_from("<I", raw, sub + 4)[0]
                if name == b"ICMT":
                    comment = raw[sub + 8:sub + 8 + length].split(b"\0")[0].decode("utf-8", "replace")
                sub += 8 + length + (length & 1)
        at += 8 + size + (size & 1)
    if fmt is None or body is None:
        raise ValueError(f"{path}: no fmt or data chunk")
    code, channels, rate, _, _, bits = struct.unpack_from("<HHIIHH", fmt)
    if code == EXTENSIBLE:
        code = struct.unpack_from("<H", fmt, 24)[0]
    if code == FLOAT and bits in (32, 64):
        x = np.frombuffer(body, dtype=f"<f{bits // 8}").astype(np.float64)
        full = int(np.count_nonzero(np.abs(x) >= 1.0))
    elif code == PCM and bits in (16, 32):
        ints = np.frombuffer(body, dtype=f"<i{bits // 8}")
        top = (1 << (bits - 1)) - 1
        full = int(np.count_nonzero(np.abs(ints.astype(np.int64)) >= top))
        x = ints.astype(np.float64) / (top + 1)
    elif code == PCM and bits == 24:
        b = np.frombuffer(body[:len(body) // 3 * 3], dtype=np.uint8).reshape(-1, 3).astype(np.int32)
        ints = b[:, 0] | b[:, 1] << 8 | b[:, 2] << 16
        ints = np.where(ints >= 1 << 23, ints - (1 << 24), ints)
        full = int(np.count_nonzero(np.abs(ints) >= (1 << 23) - 1))
        x = ints.astype(np.float64) / (1 << 23)
    else:
        raise ValueError(f"{path}: format {code} at {bits} bits is not read")
    frames = len(x) // channels
    return Wav(rate, x[:frames * channels].reshape(frames, channels), bits, code == FLOAT, full, comment)


def info_chunk(comment: str) -> bytes:
    """A LIST/INFO chunk holding COMMENT, for a writer to append after the data chunk: what
    rendered the file (the model, the runner, the instrument) and whether it is looped."""
    text = comment.encode("utf-8") + b"\0"
    text += b"\0" * (len(text) & 1)
    body = b"INFO" + b"ICMT" + struct.pack("<I", len(text)) + text
    return b"LIST" + struct.pack("<I", len(body)) + body
