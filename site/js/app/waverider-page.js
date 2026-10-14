/**
 * The Waverider page: four tabs, and the patcher in the first.
 * Loading, verifying, building and the download live in `shell.js`.
 */

import { $, buildAndOffer, openFirmware, status, wireDrop } from "./shell.js";
import { replacement } from "../firmware.js";
import { apply, CODE_SUMMARY } from "../mods/waverider.js";

const TABS = ["try", "manual", "tests", "inside"];
let state = { firmware: null, filename: "firmware.syx", built: null };

// ---- tabs: one panel shown; #try, #manual, #tests and #inside open their tab
function show(id, focus = false) {
  if (!TABS.includes(id)) id = "try";
  for (const t of TABS) {
    const on = t === id;
    $(t).hidden = !on;
    $(`tab-${t}`).setAttribute("aria-selected", on ? "true" : "false");
    $(`tab-${t}`).tabIndex = on ? 0 : -1;
  }
  if (focus) $(`tab-${id}`).focus();
  try { history.replaceState(null, "", `#${id}`); } catch { /* a sandboxed view */ }
}

for (const t of TABS) $(`tab-${t}`).addEventListener("click", () => show(t));
document.querySelector('[role="tablist"]').addEventListener("keydown", (e) => {
  const at = TABS.findIndex((t) => $(`tab-${t}`).getAttribute("aria-selected") === "true");
  if (e.key === "ArrowRight" || e.key === "ArrowLeft") {
    e.preventDefault();
    show(TABS[(at + (e.key === "ArrowRight" ? 1 : TABS.length - 1)) % TABS.length], true);
  }
});
for (const b of document.querySelectorAll("[data-go]")) {
  b.addEventListener("click", () => { show(b.dataset.go); window.scrollTo({ top: 0 }); });
}
show(location.hash.slice(1));

// ---- the patcher
async function ready(firmware) {
  // Applying is also the check that this image is one the mod was measured against:
  // every guard is read, section 7 is checked by its hash, and it throws rather than writing.
  state.built = await apply(firmware);
  state.firmware = firmware;
  $("writes").textContent = CODE_SUMMARY;
  for (const id of ["step2", "step3", "bar"]) $(id).classList.remove("hidden");
  status("Loaded. Ready to build.");
}

async function buildImage() {
  const { main, dsp, notes } = state.built;
  await buildAndOffer(
    state.firmware,
    new Map([[3, replacement(state.firmware, 3, main)], [7, replacement(state.firmware, 7, dsp)]]),
    { filename: state.filename, suffix: "waverider", note: notes[0] });
}

function open(file) {
  state.filename = file.name;
  return openFirmware(file, { onReady: ready });
}

wireDrop($("drop"), open);
$("syx").addEventListener("change", (e) => {
  if (e.target.files?.[0]) open(e.target.files[0]);
});
$("buildBtn").addEventListener("click", buildImage);
$("resetBtn").addEventListener("click", () => location.reload());
