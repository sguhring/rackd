"""Attach Watson product photos from the source brochure to the catalog.

    python catalog/watson_images.py            # dry run — report pairing rate
    python catalog/watson_images.py --write    # extract JPEGs + set `image`

Same idea as the Panatta/Strive image passes. The Watson brochure lays each
product page out as a 3-column x 2-row grid; within a cell the ALL-CAPS name and
the zero-padded product code sit at the top and the photo directly beneath it.
So a photo is paired to a product by column overlap + "first image below the
code", which is unambiguous as long as we keep the search inside one cell.

Idempotent: re-running overwrites the same img/watson/<code>.jpg and re-sets the
same `image` value.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pymupdf

ROOT = Path(__file__).resolve().parent.parent
PDF = ROOT / "docs" / "Watson-Gym-Equipment-2026.pdf"
RESOLVED = ROOT / "catalog" / "machines_resolved.json"
OUT = ROOT / "tools" / "cap" / "www" / "img" / "watson"
BRAND = "Watson"

CODE = re.compile(r"^\d{3,4}$")
CELL_H = 60       # a cell photo starts just below its code (~2pt); keep this
                  # tight or a top-row code reaches the bottom row's photo
MIN_PX = 120      # ignore logos / rules / decorative slivers
DPI = 150         # render resolution for the cell crop


def implement_pages() -> range | list[int]:
    return list(range(14, 49)) + list(range(53, 78)) + list(range(88, 97))


def code_positions(page) -> list[tuple[str, pymupdf.Rect]]:
    """Every product code on the page, with its rect."""
    out = []
    for w in page.get_text("words"):          # x0,y0,x1,y1,word,...
        if CODE.match(w[4]):
            out.append((w[4], pymupdf.Rect(w[0], w[1], w[2], w[3])))
    return out


def pair(page) -> dict[str, tuple[int, pymupdf.Rect]]:
    """code -> (xref, rect) for the photo belonging to that code."""
    imgs = []
    for x in page.get_images(full=True):
        for r in page.get_image_rects(x[0]):
            if r.width >= MIN_PX and r.height >= MIN_PX:
                imgs.append((x[0], r))
    out = {}
    for code, crect in code_positions(page):
        col = [(xref, r) for xref, r in imgs
               if r.x0 - 12 <= crect.x0 <= r.x1 + 12]   # same column as the code
        cands = [(r.y0 - crect.y1, xref, r) for xref, r in col
                 if 0 <= r.y0 - crect.y1 <= CELL_H]
        if not cands:
            # oversized "hero" photo: it fills the cell but bleeds up past the
            # code line, so it never starts below it. Accept any image in the
            # column that still extends below the code, nearest top first.
            cands = [(abs(r.y0 - crect.y1), xref, r) for xref, r in col
                     if r.y1 > crect.y1]
        if cands:
            cands.sort()                       # nearest wins
            _, xref, r = cands[0]
            out[code] = (xref, r)
    return out


def main() -> None:
    write = "--write" in sys.argv
    doc = pymupdf.open(PDF)
    found: dict[str, tuple[int, pymupdf.Rect]] = {}   # code -> (pageno, rect)
    for pno in implement_pages():
        if pno > doc.page_count:
            continue
        for code, (_, rect) in pair(doc[pno - 1]).items():
            found.setdefault(code, (pno, rect))

    resolved = json.loads(RESOLVED.read_text(encoding="utf-8"))
    watson = [r for r in resolved if r["brand"] == BRAND]
    # model ends with the product code: "Watson Animal Leg Press 0041"
    def code_of(m: str) -> str | None:
        t = m.split()[-1]
        return t if CODE.match(t) else None

    matched = [r for r in watson if (c := code_of(r["model"])) and c in found]
    missing = [r for r in watson if (c := code_of(r["model"])) and c not in found]
    nocode = [r for r in watson if not code_of(r["model"])]

    print(f"Watson rows in catalog : {len(watson)}")
    print(f"codes paired to a photo: {len(found)}")
    print(f"  rows matched         : {len(matched)}")
    print(f"  rows unmatched       : {len(missing)}")
    print(f"  rows with no code    : {len(nocode)}")
    if not write:
        for r in missing[:15]:
            print("   MISS", r["model"])
        print("\ndry run — pass --write to extract and attach")
        return

    OUT.mkdir(parents=True, exist_ok=True)
    written = 0
    for r in matched:
        code = code_of(r["model"])
        pno, rect = found[code]
        # Render the cell region rather than extracting the image xref: the
        # brochure reuses the same image object across different cells (p41
        # places xref 1677 in two of them), so extracting by xref silently
        # gives two products the same photo. Rendering captures what the page
        # actually shows.
        pix = doc[pno - 1].get_pixmap(clip=rect, dpi=DPI)
        dest = OUT / f"{code}.jpg"
        pix.save(dest, jpg_quality=88)
        r["image"] = f"img/watson/{code}.jpg"
        written += 1
    RESOLVED.write_text(json.dumps(resolved, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8")
    print(f"\nwrote {written} images to {OUT.relative_to(ROOT)} and set `image` on {written} rows")


if __name__ == "__main__":
    main()
