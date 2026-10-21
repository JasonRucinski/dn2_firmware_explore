"""Every site page renders in standards mode."""
import pathlib

SITE = pathlib.Path(__file__).resolve().parent.parent / "site"


def test_every_page_starts_with_the_doctype():
    pages = sorted(SITE.glob("*.html"))
    assert pages
    for page in pages:
        # Without it the browser uses quirks mode, where tables drop the body's line height.
        assert page.read_bytes().startswith(b"<!doctype html>\n"), page.name
