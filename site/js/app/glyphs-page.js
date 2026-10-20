/**
 * Puts the mod glyphs on a page.
 *
 * One subject: every element with `data-glyph="ID"` gets the SVG of that mod's
 * glyph (`mods/glyphs.js`). An id with no glyph leaves the element empty.
 * A mod with an animation in `mods/glyph-anims.js` (two frames or more) plays
 * it in a loop instead, FRAME_MS a frame. With reduced motion asked for, or the
 * page hidden, the still glyph stays.
 */

import { glyphSvg, rowsSvg } from "../mods/glyphs.js";
import { ANIMS } from "../mods/glyph-anims.js";

export const FRAME_MS = 125;
const playing = [];          // [element, frame SVGs, frame now]

export function mountGlyphs(doc = document, motion = true) {
  playing.length = 0;
  for (const el of doc.querySelectorAll("[data-glyph]")) {
    const anim = ANIMS[el.dataset.glyph];
    if (motion && anim && anim.frames.length > 1) {
      const frames = anim.frames.map((rows) => rowsSvg(rows, doc));
      el.replaceChildren(frames[0]);
      playing.push([el, frames, 0]);
      continue;
    }
    const svg = glyphSvg(el.dataset.glyph, doc);
    if (svg) el.replaceChildren(svg);
  }
  return playing.length;
}

/** One frame on, for every playing glyph. */
export function stepGlyphs() {
  for (const p of playing) {
    p[2] = (p[2] + 1) % p[1].length;
    p[0].replaceChildren(p[1][p[2]]);
  }
}

if (typeof document !== "undefined") {
  const still = typeof matchMedia === "function" && matchMedia("(prefers-reduced-motion: reduce)").matches;
  if (mountGlyphs(document, !still)) {
    setInterval(() => { if (!document.hidden) stepGlyphs(); }, FRAME_MS);
  }
}
