/**
 * The drawing palette that tools/glyph_editor.html and tools/glyph_animator.html share.
 *
 * One subject: turning a pointer drag into a frame. The palette has pencil, line,
 * rectangle and ellipse, a Filled option for the rectangle and the ellipse, and an
 * Erase toggle. The right mouse button also erases. Shift keeps a line to steps of
 * 45 degrees, and a rectangle or an ellipse to a square box. The pixels come from
 * glyph_anim_core.js (GlyphAnim.shape, GlyphAnim.plot); this file holds no geometry.
 * A classic script, so the pages also work when opened from disk.
 */
(function (root) {
  "use strict";

  const TOOLS = [["pencil", "Pencil"], ["line", "Line"], ["rect", "Rectangle"], ["ellipse", "Ellipse"]];

  /** Builds the palette into `container`; returns its state, which `onChange` hears about. */
  function palette(container, onChange = () => {}) {
    const state = { tool: "pencil", filled: false, erase: false };
    const doc = container.ownerDocument;
    const buttons = TOOLS.map(([id, label]) => {
      const b = doc.createElement("button");
      b.type = "button"; b.textContent = label; b.dataset.tool = id;
      b.setAttribute("aria-pressed", String(id === state.tool));
      b.onclick = () => { state.tool = id; sync(); };
      return b;
    });
    const check = (label, key) => {
      const l = doc.createElement("label"), c = doc.createElement("input");
      c.type = "checkbox"; c.dataset.option = key;
      c.onchange = () => { state[key] = c.checked; sync(); };
      l.append(c, " " + label);
      return [l, c];
    };
    const [filledLabel, filledBox] = check("Filled", "filled");
    const [eraseLabel, eraseBox] = check("Erase", "erase");
    function sync() {
      for (const b of buttons) b.setAttribute("aria-pressed", String(b.dataset.tool === state.tool));
      filledBox.disabled = !(state.tool === "rect" || state.tool === "ellipse");
      filledBox.checked = state.filled; eraseBox.checked = state.erase;
      onChange(state);
    }
    container.replaceChildren(...buttons, filledLabel, eraseLabel);
    container.classList.add("palette");
    sync();
    return state;
  }

  /** A drag that starts at cell (x, y) on `frame`: move(x, y, shift) gives the frame to show
   *  while dragging, and `frame` at the end is the result. One drag is one undo step. */
  function drag(state, frame, x, y, { button = 0 } = {}) {
    const G = root.GlyphAnim;
    const erase = state.erase || button === 2;
    const base = frame;
    // the pencil keeps its old habit: the first pixel sets the colour, unless erasing
    const on = state.tool === "pencil" ? !erase && base[y][x] !== "#" : !erase;
    let last = [x, y], current = G.plot(base, [[x, y]], on);
    return {
      on,
      get frame() { return current; },
      move(nx, ny, shift = false) {
        if (state.tool === "pencil") {
          current = G.plot(current, G.line(last[0], last[1], nx, ny), on);
          last = [nx, ny];
        } else {
          current = G.plot(base, G.shape(state.tool, x, y, nx, ny, { filled: state.filled, shift }), on);
        }
        return current;
      },
    };
  }

  /** The size of one cell of a drawing grid `cells` wide in a container `room` CSS pixels wide:
   *  whole device pixels so every cell is the same square, at most `max` CSS pixels, at least
   *  one device pixel. Returns {device, css, width} (width: the grid's CSS width). */
  function fitCell(room, cells, { max = 24, dpr = 1 } = {}) {
    const device = Math.max(1, Math.min(Math.floor(max * dpr), Math.floor((room * dpr) / cells)));
    return { device, css: device / dpr, width: (device * cells) / dpr };
  }

  /** The content width of an element: its width without padding. */
  function contentWidth(el) {
    const s = el.ownerDocument.defaultView.getComputedStyle(el);
    return el.clientWidth - parseFloat(s.paddingLeft) - parseFloat(s.paddingRight);
  }

  const api = { TOOLS, palette, drag, fitCell, contentWidth };
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.GlyphTools = api;
})(typeof globalThis !== "undefined" ? globalThis : this);
