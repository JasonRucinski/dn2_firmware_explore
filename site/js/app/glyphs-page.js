/**
 * Puts the mod glyphs on a page.
 *
 * One subject: every element with `data-glyph="ID"` gets the SVG of that mod's
 * glyph (`mods/glyphs.js`). An id with no glyph leaves the element empty.
 */

import { glyphSvg } from "../mods/glyphs.js";

export function mountGlyphs(doc = document) {
  for (const el of doc.querySelectorAll("[data-glyph]")) {
    const svg = glyphSvg(el.dataset.glyph, doc);
    if (svg) el.replaceChildren(svg);
  }
}

if (typeof document !== "undefined") mountGlyphs();
