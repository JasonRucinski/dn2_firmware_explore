// The glyph animator's model (tools/glyph_anim_core.js) under node: the knob picks the frame
// by the stock formula, the firmware format encodes a hand-made 17x17 frame to the words
// worked out by hand and decodes back, and the animation file round-trips byte for byte.
// Run by test/test_glyph_animator.py.
import { readFileSync } from "node:fs";
import vm from "node:vm";

const ROOT = new URL("../", import.meta.url);
const ctx = {};
vm.runInNewContext(readFileSync(new URL("tools/glyph_anim_core.js", ROOT), "utf8"), ctx);
const G = ctx.GlyphAnim;
const ok = (name, pass) => { console.log(`${pass ? "OK  " : "FAIL"} ${name}`); if (!pass) process.exitCode = 1; };

// 1. The knob: index = round(value x (frames - 1) / range), value = knob x 256.
let knobOk = true;
for (const range of [0x7f00, 0x8000]) {
  for (const n of [2, 13, 60, 96]) {
    for (const knob of [0, 1, 64, 126, 127]) {
      const want = Math.round((knob * 256 * (n - 1)) / range);
      if (G.knobFrame(knob, n, range) !== Math.min(n - 1, want)) knobOk = false;
    }
  }
}
ok("the knob picks round(value x (frames - 1) / range) at 0, 1, 64, 126, 127 for 2, 13, 60, 96 frames", knobOk);
ok("knob 127 at range 0x7f00 is the last frame, knob 0 the first",
   G.knobFrame(127, 96, 0x7f00) === 95 && G.knobFrame(0, 96, 0x7f00) === 0 && G.knobFrame(64, 13, 0x7f00) === 6);

// 2. The firmware format, against a 17x17 frame worked out by hand.
const hand = G.blank(17, 17).map((r) => [...r]);
hand[0][0] = "#";                                        // column 0: top row only -> 0x80000000
hand[16][2] = "#";                                       // column 2: row 16 -> bit 31-16 -> 0x00008000
for (let y = 0; y < 17; y++) hand[y][3] = "#";           // column 3: all 17 rows -> 0xffff8000
hand[1][16] = "#"; hand[8][16] = "#";                    // column 16: rows 1 and 8 -> 0x40800000
const frame = hand.map((r) => r.join(""));
const want = Array(17).fill(0);
want[0] = 0x80000000; want[2] = 0x00008000; want[3] = 0xffff8000; want[16] = 0x40800000;
const bytes = G.encode([frame], 17, 17);
const words = [...Array(17)].map((_, i) => ((bytes[i * 4] << 24) | (bytes[i * 4 + 1] << 16) | (bytes[i * 4 + 2] << 8) | bytes[i * 4 + 3]) >>> 0);
ok("a 17x17 frame encodes to 17 big-endian words, top row in the most significant bit",
   bytes.length === 68 && words.every((w, i) => w === want[i]));
ok("the words decode back to the same frame", JSON.stringify(G.decode(bytes, 17, 17)) === JSON.stringify([frame]));
const hex = G.toHex(bytes, 17, 17);
ok("hex text has one line per frame and reads back to the same bytes",
   hex.split("\n").length === 1 && hex.startsWith("80000000 00000000 00008000 ffff8000")
   && JSON.stringify([...G.fromHex(hex)]) === JSON.stringify([...bytes]));

let seed = 7;
const rand = () => ((seed = (seed * 1103515245 + 12345) % 2147483648) / 2147483648);
let rt = true;
for (const [w, h, n] of [[17, 17, 13], [19, 17, 3], [11, 11, 2], [128, 64, 2], [5, 33, 4]]) {
  const fs = [...Array(n)].map(() => [...Array(h)].map(() => [...Array(w)].map(() => (rand() < 0.4 ? "#" : ".")).join("")));
  const b = G.encode(fs, w, h);
  rt &&= b.length === n * w * Math.ceil(h / 32) * 4 && JSON.stringify(G.decode(b, w, h)) === JSON.stringify(fs);
}
ok("random frames of 17x17, 19x17, 11x11, 128x64 and 5x33 encode and decode unchanged", rt);
let refused = false;
try { G.decode(new Uint8Array(70), 17, 17); } catch { refused = true; }
ok("bytes that are not whole frames are refused", refused);

// 3. The animation file.
const text = readFileSync(new URL("site/js/mods/glyph-anims.js", ROOT), "utf8");
const anims = G.parse(text);
ok("the shipped file reads back and writes the same text", G.serialise(anims) === text);
ok("the shipped example is valid: 13 frames of 17x17",
   anims.sinesquare && G.valid(anims.sinesquare) && anims.sinesquare.frames.length === 13
   && anims.sinesquare.width === 17 && anims.sinesquare.height === 17);
const two = { a: { width: 3, height: 2, frames: [["#..", ".#."], ["...", "###"]] }, b: { width: 1, height: 1, frames: [["#"]] } };
ok("several animations round-trip through the file", JSON.stringify(G.parse(G.serialise(two))) === JSON.stringify(two));
ok("JSON reads to the same model", JSON.stringify(G.fromJSON(JSON.stringify(two))) === JSON.stringify(two));

// 4. The tween is plain frames: its ends are the key frames.
const tw = G.tween([G.blank(4, 4), G.blank(4, 4), G.blank(4, 4), G.OPS.invert(G.blank(4, 4))], 0, 3);
ok("a dissolve fills the frames between, from one key frame toward the other",
   tw[1].join("").split("#").length < tw[2].join("").split("#").length && G.valid({ width: 4, height: 4, frames: tw }));
