"""Attach HOIST ROC-IT Selectorized photos from the RS-1000 brochure.

    python catalog/hoist_images.py            # dry run
    python catalog/hoist_images.py --write

Every HOIST row in the catalog came from a single used-equipment marketplace,
and 24 of the 28 cutouts are ghosted warehouse shots — the worst image quality
of any brand. This replaces the ones we can identify with studio photography.

The brochure is the most regular of any so far: one machine per page across
pages 6-27, each carrying an 18pt name, a 13pt RS code, one large hero photo
and a couple of small feature thumbnails. So the rule is simply "largest image
on the page" (hero ~120-175k px^2 vs ~10k for the detail shots).

Matching is by explicit RS-1xxx code only, never by machine name. HOIST sells a
selectorized *and* a plate-loaded machine for most movements, so name-matching
a "Plate Loaded Chest Press" row onto the RS-1301 selectorized Chest Press
would attach a photo of a different machine.

Page 28 is the summary index — it repeats all 21 codes and has no photos, so it
is excluded by the page range.

Idempotent: re-running overwrites the same img/hoist/<code>.jpg.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pymupdf

ROOT = Path(__file__).resolve().parent.parent
PDF = ROOT / "docs" / "hoist-rocit-rs-brochure.pdf"
RESOLVED = ROOT / "catalog" / "machines_resolved.json"
OUT = ROOT / "tools" / "cap" / "www" / "img" / "hoist"
BRAND = "Hoist"
PAGES = range(6, 28)          # 6-27; page 28 is the index

CODE = re.compile(r"RS-1\d{3}")
MIN_HERO = 40000              # px^2; detail thumbnails are ~10k, heroes >100k


def heroes() -> dict[str, tuple[int, int]]:
    """RS code -> (page, xref of the hero photo)."""
    doc = pymupdf.open(PDF)
    out: dict[str, tuple[int, int]] = {}
    for pno in PAGES:
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
            out[codes.pop()] = (pno, best)
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

    doc = pymupdf.open(PDF)
    OUT.mkdir(parents=True, exist_ok=True)
    for r, code in ok:
        _, xref = pics[code]
        pix = pymupdf.Pixmap(doc, xref)
        if pix.alpha or (pix.colorspace and pix.colorspace.n > 3):
            pix = pymupdf.Pixmap(pymupdf.csRGB, pix)
        pix.save(OUT / f"{code}.jpg", jpg_quality=90)
        r["image"] = f"img/hoist/{code}.jpg"
    RESOLVED.write_text(json.dumps(resolved, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\nwrote {len({c for _, c in ok})} images, attached to {len(ok)} rows")


if __name__ == "__main__":
    main()
