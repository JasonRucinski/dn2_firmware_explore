"""The glyph animator (`tools/glyph_animator.html`, model in `tools/glyph_anim_core.js`): the knob
picks the stock frame, the firmware format encodes and decodes, and the animation file
(`site/js/mods/glyph-anims.js`) round-trips. `scripts/js_glyph_anim_check.mjs` runs it under node."""

import pathlib
import shutil
import subprocess

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
HARNESS = ROOT / "scripts" / "js_glyph_anim_check.mjs"


def test_the_animator_model_under_node():
    node = shutil.which("node")
    if not node:
        pytest.skip("node is not on PATH; the animator check cannot run")
    done = subprocess.run([node, str(HARNESS)], capture_output=True, text=True, cwd=ROOT)
    assert done.returncode == 0, done.stdout + done.stderr
    assert done.stdout.count("OK  ") == 12


def test_the_two_editors_link_to_each_other():
    still = (ROOT / "tools/glyph_editor.html").read_text(encoding="utf-8")
    anim = (ROOT / "tools/glyph_animator.html").read_text(encoding="utf-8")
    assert 'href="glyph_animator.html"' in still and 'href="glyph_editor.html"' in anim
    assert '<script src="glyph_anim_core.js"></script>' in anim
