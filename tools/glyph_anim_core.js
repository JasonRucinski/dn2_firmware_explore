/**
 * The model behind tools/glyph_animator.html: animated 1-bit glyphs as lists of frames.
 *
 * One subject: frames as data. A frame is `height` strings of `width` characters,
 * `#` lit and `.` dark, as in site/js/mods/glyphs.js. This file reads and writes
 * the animation file (site/js/mods/glyph-anims.js), the firmware storage format,
 * and picks the frame for a knob value the way the stock firmware does.
 *
 * A classic script, so the page also works when opened from disk: in a browser it
 * sets `GlyphAnim`; under node, scripts/js_glyph_anim_check.mjs loads it with vm.
 */
(function (root) {
  "use strict";

  const LIMITS = { width: 128, height: 64, frames: 128 };
  const RANGES = { "0x7f00": 0x7f00, "0x8000": 0x8000 };

  /** The frame the stock picker shows: round(value x (frames - 1) / range), value = knob x 256. */
  function knobFrame(knob, frames, range = 0x7f00) {
    if (frames <= 1) return 0;
    const value = knob * 256;
    return Math.min(frames - 1, Math.floor((value * (frames - 1) + range / 2) / range));
  }

  function blank(width, height) {
    return Array.from({ length: height }, () => ".".repeat(width));
  }

  function valid(anim) {
    const { width, height, frames } = anim;
    if (!(width >= 1 && width <= LIMITS.width && height >= 1 && height <= LIMITS.height)) return false;
    if (!(frames.length >= 1 && frames.length <= LIMITS.frames)) return false;
    return frames.every((f) => f.length === height && f.every((r) => r.length === width && /^[.#]*$/.test(r)));
  }

  /* ---- the animation file ---- */

  const HEADER = `/**
 * Animated 1-bit glyphs, by name. Written by tools/glyph_animator.html.
 *
 * Each animation has a frame size and a list of frames. A frame is \`height\`
 * rows of \`width\` characters, \`#\` lit and \`.\` dark. A knob value picks a
 * frame: round(value x (frames - 1) / range). Original art.
 */

export const ANIMS = {
`;

  function serialise(anims) {
    let out = HEADER;
    for (const [name, a] of Object.entries(anims)) {
      out += `  ${name}: {\n    width: ${a.width}, height: ${a.height},\n    frames: [\n`;
      for (const f of a.frames) out += "      [\n" + f.map((r) => `        "${r}",\n`).join("") + "      ],\n";
      out += "    ],\n  },\n";
    }
    return out + "};\n";
  }

  const ANIM_RE = /\n  ([A-Za-z0-9_]+): \{\n    width: (\d+), height: (\d+),\n    frames: \[\n([\s\S]*?)\n    \],\n  \},/g;

  function parse(text) {
    const out = {};
    for (const m of text.matchAll(ANIM_RE)) {
      const frames = m[4].split(/\n      \],?\n?/).filter((s) => s.includes('"'))
        .map((s) => s.match(/"([.#]*)"/g).map((q) => q.slice(1, -1)));
      out[m[1]] = { width: +m[2], height: +m[3], frames };
    }
    return out;
  }

  /** JSON in, the same model out: {name: {width, height, frames: [[rows]]}}. */
  function fromJSON(text) {
    const data = JSON.parse(text);
    for (const [name, a] of Object.entries(data)) {
      if (!valid(a)) throw new Error(`animation ${name} is not valid`);
    }
    return data;
  }

  /* ---- the firmware storage format ---- */

  /** 32-bit words per column: one up to 32 rows, the stock format; more for taller frames. */
  const wordsPerColumn = (height) => Math.ceil(height / 32);

  /** Frames as bytes: per frame, `width` columns left to right; per column, big-endian
   *  32-bit words, the most significant bit at the top row. */
  function encode(frames, width, height) {
    const wpc = wordsPerColumn(height);
    const bytes = new Uint8Array(frames.length * width * wpc * 4);
    let o = 0;
    for (const f of frames) {
      for (let x = 0; x < width; x++) {
        for (let w = 0; w < wpc; w++) {
          let word = 0;
          for (let b = 0; b < 32; b++) {
            const y = w * 32 + b;
            if (y < height && f[y][x] === "#") word |= 1 << (31 - b);
          }
          bytes[o++] = (word >>> 24) & 255; bytes[o++] = (word >>> 16) & 255;
          bytes[o++] = (word >>> 8) & 255; bytes[o++] = word & 255;
        }
      }
    }
    return bytes;
  }

  function decode(bytes, width, height) {
    const wpc = wordsPerColumn(height);
    const size = width * wpc * 4;
    if (!bytes.length || bytes.length % size) {
      throw new Error(`${bytes.length} bytes is not a whole number of ${width}x${height} frames (${size} bytes each)`);
    }
    const frames = [];
    for (let o = 0; o < bytes.length; o += size) {
      const grid = Array.from({ length: height }, () => Array(width).fill("."));
      for (let x = 0; x < width; x++) {
        for (let w = 0; w < wpc; w++) {
          const p = o + (x * wpc + w) * 4;
          const word = ((bytes[p] << 24) | (bytes[p + 1] << 16) | (bytes[p + 2] << 8) | bytes[p + 3]) >>> 0;
          for (let b = 0; b < 32; b++) {
            const y = w * 32 + b;
            if (y < height && (word >>> (31 - b)) & 1) grid[y][x] = "#";
          }
        }
      }
      frames.push(grid.map((r) => r.join("")));
    }
    return frames;
  }

  /** Hex text: one line per frame, one 8-digit word per column (and word). */
  function toHex(bytes, width, height) {
    const words = [];
    for (let p = 0; p < bytes.length; p += 4) {
      words.push([...bytes.slice(p, p + 4)].map((v) => v.toString(16).padStart(2, "0")).join(""));
    }
    const perFrame = width * wordsPerColumn(height);
    const lines = [];
    for (let i = 0; i < words.length; i += perFrame) lines.push(words.slice(i, i + perFrame).join(" "));
    return lines.join("\n");
  }

  function fromHex(text) {
    const digits = text.replace(/0x/gi, "").replace(/[^0-9a-f]/gi, "");
    if (digits.length % 8) throw new Error("the hex text is not a whole number of 32-bit words");
    return Uint8Array.from(digits.match(/../g) || [], (h) => parseInt(h, 16));
  }

  /* ---- edits ---- */

  const OPS = {
    up: (f) => [...f.slice(1), ".".repeat(f[0].length)],
    down: (f) => [".".repeat(f[0].length), ...f.slice(0, -1)],
    left: (f) => f.map((r) => r.slice(1) + "."),
    right: (f) => f.map((r) => "." + r.slice(0, -1)),
    flipx: (f) => f.map((r) => [...r].reverse().join("")),
    flipy: (f) => [...f].reverse(),
    invert: (f) => f.map((r) => r.replace(/./g, (c) => (c === "#" ? "." : "#"))),
    clear: (f) => blank(f[0].length, f.length),
  };

  const BAYER4 = [0, 8, 2, 10, 12, 4, 14, 6, 3, 11, 1, 9, 15, 7, 13, 5];

  /** A dissolve from frame a to frame b at t in 0..1: an ordered dither picks each pixel. */
  function dissolve(a, b, t) {
    return a.map((row, y) => [...row].map((c, x) =>
      ((BAYER4[(y % 4) * 4 + (x % 4)] + 0.5) / 16 < t ? b[y][x] : c)).join(""));
  }

  /** Frames strictly between `from` and `to` become dissolve steps; returns the new list. */
  function tween(frames, from, to) {
    const out = frames.slice();
    for (let i = from + 1; i < to; i++) out[i] = dissolve(frames[from], frames[to], (i - from) / (to - from));
    return out;
  }

  /** Change the frame size, keeping the top-left pixels. */
  function resize(frame, width, height) {
    return Array.from({ length: height }, (_, y) =>
      (frame[y] ?? "").slice(0, width).padEnd(width, "."));
  }

  const api = { LIMITS, RANGES, knobFrame, blank, valid, serialise, parse, fromJSON, wordsPerColumn,
    encode, decode, toHex, fromHex, OPS, dissolve, tween, resize };
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.GlyphAnim = api;
})(typeof globalThis !== "undefined" ? globalThis : this);
