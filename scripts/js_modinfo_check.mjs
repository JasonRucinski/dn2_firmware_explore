// The browser /modinfo fill (site/js/modinfo.js), for test/test_js_modinfo.py.
//
//   node scripts/js_modinfo_check.mjs --main MAIN.bin --out DIR
//
// MAIN.bin is a MAIN OS with Waverider applied and its record unfilled. Writes to DIR:
// once.bin (filled with mod "waverider"), twice.bin (once.bin filled again with "fxmod"),
// stock.bin (a MAIN OS without the record: must come back unchanged, so it is MAIN.bin's
// first 64 KB) and xxh32.json (the hash of each vector length 0..64 of 0, 1, 2, ...).

import { readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { fill, xxh32 } from "../site/js/modinfo.js";

const arg = (name) => process.argv[process.argv.indexOf(name) + 1];
const main = new Uint8Array(readFileSync(arg("--main")));
const out = arg("--out");

const once = fill(main, "waverider");
writeFileSync(join(out, "once.bin"), once);
writeFileSync(join(out, "twice.bin"), fill(once, "fxmod"));
writeFileSync(join(out, "stock.bin"), fill(main.slice(0, 65536), "fxmod"));
const vectors = [];
for (let n = 0; n <= 64; n++) {
  const v = Uint8Array.from({ length: n }, (_, k) => (k * 37 + 11) & 255);
  vectors.push([xxh32(v), xxh32(v, 0x9e3779b1)]);
}
writeFileSync(join(out, "xxh32.json"), JSON.stringify(vectors));
