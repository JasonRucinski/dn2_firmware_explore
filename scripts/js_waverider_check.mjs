/**
 * The browser Waverider mod against the Python, byte for byte.
 *
 *   node scripts/js_waverider_check.mjs --syx STOCK.syx --py-main MAIN.bin --py-dsp DSP.bin
 *       [--refusals-out FILE.json] [--syx-out BUILT.syx]
 *
 * `MAIN.bin` and `DSP.bin` are sections 3 and 7 as `dnfw.mods.waverider.apply` produces
 * them. Checks: the same two sections, and the rebuilt image verifies. With
 * `--refusals-out`, also applies the mod to its own output, and the transients mod to it, and records
 * both refusals;
 * `--syx-out` writes the browser's image, for the boot gate.
 */
import { readFileSync, writeFileSync } from "node:fs";
import { build, load, replacement, verify } from "../site/js/firmware.js";
import { apply } from "../site/js/mods/waverider.js";
import * as transients from "../site/js/mods/transients.js";

const arg = (n) => { const i = process.argv.indexOf(`--${n}`); return i >= 0 ? process.argv[i + 1] : null; };
const same = (a, b) => a.length === b.length && a.every((v, i) => v === b[i]);
const checks = [];

const firmware = await load(new Uint8Array(readFileSync(arg("syx"))));
const { main, dsp, notes } = await apply(firmware);
checks.push(["MAIN OS == Python", same(main, new Uint8Array(readFileSync(arg("py-main"))))]);
checks.push(["section 7 == Python", same(dsp, new Uint8Array(readFileSync(arg("py-dsp"))))]);

const built = await build(firmware, new Map([[3, replacement(firmware, 3, main)],
                                             [7, replacement(firmware, 7, dsp)]]));
if (arg("syx-out")) writeFileSync(arg("syx-out"), built);
const rebuilt = await load(built);
const v = await verify(rebuilt);
checks.push([`rebuilt image verifies (${v.filter((c) => c.ok).length}/${v.length})`, v.every((c) => c.ok)]);
checks.push(["the rebuilt image depacks to the same sections",
             same(rebuilt.container.find(3).unpack(), main) && same(rebuilt.container.find(7).unpack(), dsp)]);

if (arg("refusals-out")) {
  let twice = null;
  try { await apply(rebuilt); } catch (e) { twice = e.message; }
  let tr = null;
  try { transients.apply(rebuilt, new Map()); } catch (e) { tr = e.message; }
  writeFileSync(arg("refusals-out"), JSON.stringify({ waverider_twice: twice, transients_after: tr }));
}

for (const [name, ok] of checks) console.log(`${ok ? "OK" : "FAIL"}  ${name}`);
console.log(notes.join("\n"));
process.exit(checks.every(([, ok]) => ok) ? 0 : 1);
