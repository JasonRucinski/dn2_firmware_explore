// The mod glyphs (site/js/mods/glyphs.js) under node: each one's SVG covers exactly its lit
// pixels in currentColor with crisp edges, and the page module fills every data-glyph element
// with a known id and leaves an unknown one empty. Run by test/test_js_glyphs.py.
import { GLYPHS, SIZE, glyphSvg, runs } from "../site/js/mods/glyphs.js";
import { mountGlyphs, stepGlyphs } from "../site/js/app/glyphs-page.js";
import { ANIMS } from "../site/js/mods/glyph-anims.js";

const ok = (name, pass) => { console.log(`${pass ? "OK  " : "FAIL"} ${name}`); if (!pass) process.exitCode = 1; };

function node(tag) {
  return { tag, attrs: {}, children: [],
    setAttribute(k, v) { this.attrs[k] = String(v); },
    append(...kids) { this.children.push(...kids); },
    replaceChildren(...kids) { this.children = kids; } };
}
const doc = { createElementNS: (ns, tag) => ({ ...node(tag), ns }) };

ok("runs merges a row into one rect per lit stretch",
   JSON.stringify(runs(["##..#", ".###."])) === JSON.stringify([[0, 0, 2], [4, 0, 1], [1, 1, 3]]));

let covered = true, styled = true;
for (const [id, rows] of Object.entries(GLYPHS)) {
  const svg = glyphSvg(id, doc);
  styled &&= svg.ns === "http://www.w3.org/2000/svg" && svg.attrs.viewBox === `0 0 ${SIZE} ${SIZE}`
    && svg.attrs["shape-rendering"] === "crispEdges" && svg.attrs.fill === "currentColor";
  const lit = new Set();
  for (const r of svg.children) {
    for (let x = +r.attrs.x; x < +r.attrs.x + +r.attrs.width; x++) lit.add(`${x},${r.attrs.y}`);
  }
  const want = new Set();
  rows.forEach((row, y) => [...row].forEach((c, x) => { if (c === "#") want.add(`${x},${y}`); }));
  covered &&= lit.size === want.size && [...want].every((p) => lit.has(p));
}
ok("every glyph's SVG lights exactly its # pixels", covered);
ok("every glyph is in currentColor on a 16x16 crisp-edged grid", styled);
ok("an id with no glyph gives no SVG", glyphSvg("nosuchmod", doc) === null);

const known = { ...node("span"), dataset: { glyph: "lfo4" } };
const unknown = { ...node("span"), dataset: { glyph: "nosuchmod" } };
mountGlyphs({ ...doc, querySelectorAll: () => [known, unknown] });
ok("the page module draws a known glyph and leaves an unknown one empty",
   known.children.length === 1 && known.children[0].tag === "svg" && unknown.children.length === 0);

// A mod with an animation plays it: frame 0 on mount, the next frame on each step, round again
// at the end; with motion off it shows its still glyph.
const lit = (svg) => { const s = new Set(); for (const r of svg.children) for (let x = +r.attrs.x; x < +r.attrs.x + +r.attrs.width; x++) s.add(`${x},${r.attrs.y}`); return s; };
const want = (rows) => { const s = new Set(); rows.forEach((row, y) => [...row].forEach((c, x) => { if (c === "#") s.add(`${x},${y}`); })); return s; };
const same = (a, b) => a.size === b.size && [...a].every((p) => b.has(p));
const anim = ANIMS.waverider;
ok("waverider has an animation of two frames or more", !!anim && anim.frames.length > 1);
const el = { ...node("span"), dataset: { glyph: "waverider" } };
ok("the page module plays one animated glyph", mountGlyphs({ ...doc, querySelectorAll: () => [el] }) === 1);
let frames = true;
for (let i = 0; i <= anim.frames.length; i++) {
  frames &&= same(lit(el.children[0]), want(anim.frames[i % anim.frames.length]));
  stepGlyphs();
}
ok("each step shows the next frame's exact pixels, and it loops", frames);
const still = { ...node("span"), dataset: { glyph: "waverider" } };
mountGlyphs({ ...doc, querySelectorAll: () => [still] }, false);
ok("with motion off it shows the still glyph", same(lit(still.children[0]), want(GLYPHS.waverider)));

