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

  /* ---- the still glyphs (site/js/mods/glyphs.js) ---- */

  const STILL_RE = /\n  (?:\/\/[^\n]*\n  )?([a-z0-9]+): \[\n((?:    "[.#]+",\n)+)  \],/g;

  /** The still glyphs by mod id, read from the text of glyphs.js. */
  function parseStill(text) {
    const at = text.indexOf("export const GLYPHS = {");
    const body = at < 0 ? "" : text.slice(at);
    const out = {};
    for (const m of ("\n" + body).matchAll(STILL_RE)) out[m[1]] = m[2].match(/[.#]+/g);
    return out;
  }

  /** A frame as hex for a URL: each row as hex digits of 4 pixels, rows joined by "-". */
  function rowsToHex(rows) {
    return rows.map((r) => r.padEnd(Math.ceil(r.length / 4) * 4, ".").match(/.{4}/g)
      .map((q) => parseInt(q.replace(/#/g, "1").replace(/\./g, "0"), 2).toString(16)).join("")).join("-");
  }

  function hexToRows(hex, width) {
    const rows = hex.split("-").map((h) => [...h].map((d) => parseInt(d, 16).toString(2).padStart(4, "0")).join("")
      .replace(/1/g, "#").replace(/0/g, ".").slice(0, width));
    return rows.every((r) => r.length === width && /^[.#]+$/.test(r)) ? rows : null;
  }

  /* ---- rows as text, for copy and paste ---- */

  /** Text to blocks of rows: blocks are separated by blank lines. Only `#` and `.` are
   *  allowed; anything else gives {error} naming the line and the character. */
  function parseBlocks(text) {
    const blocks = [];
    let block = [];
    const lines = text.replace(/\r/g, "").split("\n");
    for (let i = 0; i < lines.length; i++) {
      const line = lines[i].trim();
      if (!line) { if (block.length) blocks.push(block); block = []; continue; }
      const bad = line.match(/[^.#]/);
      if (bad) return { error: `Line ${i + 1} has "${bad[0]}". Use only # and .` };
      block.push(line);
    }
    if (block.length) blocks.push(block);
    if (!blocks.length) return { error: "There are no rows to use." };
    return { blocks };
  }

  /** Rows of any size to a width x height frame at the top left; `trimmed` when some did not fit. */
  function fitRows(rows, width, height) {
    const trimmed = rows.length > height || rows.some((r) => r.length > width);
    return { frame: resize(rows, width, height), trimmed };
  }

  const framesText = (frames) => frames.map((f) => f.join("\n")).join("\n\n");

  /* ---- animated GIF ---- */

  const GIF_COLOURS = { light: { bg: [0xf6, 0xf5, 0xf2], ink: [0x16, 0x18, 0x1c] },
                        dark: { bg: [0x0c, 0x0d, 0x0f], ink: [0xe8, 0xe6, 0xe1] } };

  /** GIF89a delay in hundredths of a second for a speed in frames a second (browsers slow down below 2). */
  const gifDelay = (fps) => Math.max(2, Math.round(100 / Math.max(1, fps)));

  /** LZW of 2-colour indices, code size 2, cut into sub-blocks of 255 bytes. */
  function lzw(indices) {
    const MIN = 2, CLEAR = 4, EOI = 5;
    const out = [];
    let acc = 0, bits = 0, size = MIN + 1, next = EOI + 1, table = new Map();
    const emit = (code) => {
      acc |= code << bits; bits += size;
      while (bits >= 8) { out.push(acc & 255); acc >>>= 8; bits -= 8; }
    };
    emit(CLEAR);
    let prefix = indices[0];
    for (let i = 1; i < indices.length; i++) {
      const k = indices[i], key = (prefix << 8) | k, code = table.get(key);
      if (code !== undefined) { prefix = code; continue; }
      emit(prefix);
      if (next === 4096) { emit(CLEAR); table = new Map(); next = EOI + 1; size = MIN + 1; }
      else { if (next >= 1 << size) size++; table.set(key, next++); }
      prefix = k;
    }
    emit(prefix);
    emit(EOI);
    if (bits > 0) out.push(acc & 255);
    const blocks = [MIN];
    for (let p = 0; p < out.length; p += 255) {
      const chunk = out.slice(p, p + 255);
      blocks.push(chunk.length, ...chunk);
    }
    blocks.push(0);
    return blocks;
  }

  /** The frames as an animated GIF: 2 colours, each pixel `scale` x `scale`, looping forever. */
  function gif(frames, width, height, { scale = 1, theme = "light", delay = 8 } = {}) {
    const W = width * scale, H = height * scale, c = GIF_COLOURS[theme];
    const le = (v) => [v & 255, (v >> 8) & 255];
    const bytes = [..."GIF89a"].map((ch) => ch.charCodeAt(0));
    bytes.push(...le(W), ...le(H), 0x80, 0, 0, ...c.bg, ...c.ink);
    bytes.push(0x21, 0xff, 11, ...[..."NETSCAPE2.0"].map((ch) => ch.charCodeAt(0)), 3, 1, 0, 0, 0);
    for (const f of frames) {
      bytes.push(0x21, 0xf9, 4, 0x04, ...le(delay), 0, 0);
      bytes.push(0x2c, 0, 0, 0, 0, ...le(W), ...le(H), 0);
      const idx = new Uint8Array(W * H);
      for (let y = 0; y < H; y++) {
        const row = f[(y / scale) | 0];
        for (let x = 0; x < W; x++) idx[y * W + x] = row[(x / scale) | 0] === "#" ? 1 : 0;
      }
      const data = lzw(idx);
      for (let i = 0; i < data.length; i++) bytes.push(data[i]);
    }
    bytes.push(0x3b);
    return Uint8Array.from(bytes);
  }

  const api = { gif, gifDelay, GIF_COLOURS, parseBlocks, fitRows, framesText, LIMITS, RANGES, knobFrame, blank, valid, serialise, parse, fromJSON, wordsPerColumn,
    encode, decode, toHex, fromHex, OPS, dissolve, tween, resize, parseStill, rowsToHex, hexToRows };
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.GlyphAnim = api;
})(typeof globalThis !== "undefined" ? globalThis : this);
