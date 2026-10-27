"""Attach HOIST ROC-IT Selectorized photos from the RS-1000 brochure.

    python catalog/hoist_images.py            # dry run
    python catalog/hoist_images.py --write

Every HOIST row in the catalog came from a single used-equipment marketplace,
and 24 of the 28 cutouts are ghosted warehouse shots — the worst image quality
of any brand. This replaces the ones we can identify with studio photography.

Both brochures are the most regular of any so far: one machine per page, each
carrying a name, a product code, one large hero photo and a couple of small
feature thumbnails. So the rule is simply "largest image on the page" (hero
50-175k px^2 vs ~10k for the detail shots).

Matching is by explicit RS-1xxx / RPL-5xxx code only, never by machine name.
HOIST sells a selectorized *and* a plate-loaded machine for most movements, so
name-matching a "Plate Loaded Chest Press" row onto the RS-1301 selectorized
Chest Press would attach a photo of a different machine.

Idempotent: re-running overwrites the same img/hoist/<code>.jpg.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pymupdf

ROOT = Path(__file__).resolve().parent.parent
RESOLVED = ROOT / "catalog" / "machines_resolved.json"
OUT = ROOT / "tools" / "cap" / "www" / "img" / "hoist"
BRAND = "Hoist"

# Both HOIST brochures share a layout, so one rule covers them: name, code,
# one hero photo and a couple of detail thumbnails, one machine per page. The
# final page of each is a summary index repeating every code with no photos,
# which the page range excludes.
SOURCES = [
    (ROOT / "docs" / "hoist-rocit-rs-brochure.pdf", range(6, 28)),            # selectorized
    (ROOT / "docs" / "hoist-rocit-plate-loaded-brochure.pdf", range(4, 17)),  # plate loaded
]

CODE = re.compile(r"R(?:S-1|PL-5)\d{3}")
MIN_HERO = 40000              # px^2; detail thumbnails are ~10k, heroes 50-175k


def heroes() -> dict[str, tuple[Path, int, int]]:
    """RS/RPL code -> (pdf, page, xref of the hero photo)."""
    out: dict[str, tuple[Path, int, int]] = {}
    for pdf, pages in SOURCES:
        if not pdf.exists():
            print(f"note: {pdf.name} not present, skipping")
            continue
        out.update(_heroes_in(pdf, pages))
    return out


def _heroes_in(pdf: Path, pages) -> dict[str, tuple[Path, int, int]]:
    doc = pymupdf.open(pdf)
    out: dict[str, tuple[Path, int, int]] = {}
    for pno in pages:
        if pno > doc.page_count:
            break
        page = doc[pno - 1]
        codes = {w[4] for w in page.get_text("words") if CODE.fullmatch(w[4])}
        if len(codes) != 1:                    # a spread we do not understand
            continue
        best, best_area = None, 0.0
        for x in page.get_images(full=True):
            for r in page.get_image_rects(x[0]):
                area = r.width * r.height
                if area > best_area:
                    best_area, best = area, x[0]
        if best is not None and best_area >= MIN_HERO:
            out[codes.pop()] = (pdf, pno, best)
    return out


def main() -> None:
    write = "--write" in sys.argv
    pics = heroes()
    print(f"hero photos found: {len(pics)} -> {sorted(pics)}\n")

    resolved = json.loads(RESOLVED.read_text(encoding="utf-8"))
    rows = [r for r in resolved if r["brand"] == BRAND]

    def code_of(model: str) -> str | None:
        m = CODE.search(model.upper())
        return m.group(0) if m and m.group(0) in pics else None

    hits = [(r, code_of(r["model"])) for r in rows]
    ok = [(r, c) for r, c in hits if c]
    print(f"{BRAND} rows: {len(rows)}   matched: {len(ok)}")
    for r, c in hits:
        print(f"   {'OK  ' if c else 'skip'} {r['model'][:60]:60} -> {c}")
    if not write:
        print("\ndry run — pass --write to extract and attach")
        return

    OUT.mkdir(parents=True, exist_ok=True)
    docs = {}
    for r, code in ok:
        pdf, _, xref = pics[code]
        doc = docs.setdefault(pdf, pymupdf.open(pdf))
        pix = pymupdf.Pixmap(doc, xref)
        if pix.alpha or (pix.colorspace and pix.colorspace.n > 3):
            pix = pymupdf.Pixmap(pymupdf.csRGB, pix)
        pix.save(OUT / f"{code}.jpg", jpg_quality=90)
        r["image"] = f"img/hoist/{code}.jpg"
    RESOLVED.write_text(json.dumps(resolved, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\nwrote {len({c for _, c in ok})} images, attached to {len(ok)} rows")


if __name__ == "__main__":
    main()
