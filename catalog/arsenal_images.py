"""Attach Arsenal Strength product photos from the source catalog.

    python catalog/arsenal_images.py            # dry run — report pairing rate
    python catalog/arsenal_images.py --write    # render crops + set `image`

Unlike Watson (3x2 grid) and gym80 (2x2 quadrants), the Arsenal catalog is a
free-form landscape magazine spread: a machine's photo may sit left of, below or
above its heading, and photo sizes vary wildly. So there is no fixed geometric
rule to apply — instead we assign each product code to the nearest unused photo
on its page (greedy mutual-nearest, closest pair first).

Logos and full-bleed background art are filtered out first, otherwise they win
the nearest-neighbour race against real product shots.

Idempotent: re-running overwrites the same img/arsenal/<code>.jpg.
"""
from __future__ import annotations

import collections
import json
import re
import sys
from itertools import permutations
from pathlib import Path

import pymupdf

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
import arsenal_to_catalog as ars  # noqa: E402

PDF = ROOT / "docs" / "Arsenal Strength Catalog 6.2-1.pdf"
RESOLVED = ROOT / "catalog" / "machines_resolved.json"
OUT = ROOT / "tools" / "cap" / "www" / "img" / "arsenal"
BRAND = "Arsenal Strength"

MIN_PX = 150        # below this it is a logo, icon or rule
MAX_PAGE_FRAC = 0.5  # above this it is full-bleed background art
DPI = 150


def repeated_xrefs(doc, threshold: int = 4) -> set[int]:
    """Images placed on many pages are branding, not products."""
    seen = collections.Counter()
    for i in range(doc.page_count):
        for x in {x[0] for x in doc[i].get_images(full=True)}:
            seen[x] += 1
    return {x for x, n in seen.items() if n >= threshold}


def page_photos(page, skip: set[int]) -> list[tuple[int, pymupdf.Rect]]:
    area = page.rect.width * page.rect.height
    out, seen = [], set()
    for x in page.get_images(full=True):
        if x[0] in skip:
            continue
        for r in page.get_image_rects(x[0]):
            key = (x[0], round(r.x0), round(r.y0))
            if key in seen:
                continue
            seen.add(key)
            if r.width >= MIN_PX and r.height >= MIN_PX and (r.width * r.height) / area <= MAX_PAGE_FRAC:
                out.append((x[0], r))
    return out


def pair(page, codes: set[str], skip: set[int]) -> dict[str, tuple[int, pymupdf.Rect]]:
    """Greedy nearest assignment: closest (code, photo) pair first, one photo each."""
    spots = []
    for code in codes:
        hits = page.search_for(code)
        if hits:
            spots.append((code, hits[0]))   # first occurrence is the heading
    photos = page_photos(page, skip)
    if not spots or not photos:
        return {}
    # Distance from each heading to each photo centre.
    cost = []
    for code, crect in spots:
        cx, cy = (crect.x0 + crect.x1) / 2, (crect.y0 + crect.y1) / 2
        cost.append([(((cx - (r.x0 + r.x1) / 2) ** 2 + (cy - (r.y0 + r.y1) / 2) ** 2) ** 0.5)
                     for _, r in photos])

    # Minimise TOTAL distance, not each heading's own nearest. Greedy fails on
    # p15: AR-LP grabs the top-left photo because it is closest to anything on
    # the page, which strands AR-TBAR with the wrong one. n is <= 8 per page so
    # brute force over assignments is cheap and exact.
    idx = _best_assignment(cost)
    return {spots[i][0]: photos[j] for i, j in idx}


def _best_assignment(cost: list[list[float]]) -> list[tuple[int, int]]:
    n, m = len(cost), len(cost[0])
    if n > 8 or m > 8:                       # fall back to greedy on huge pages
        pairs = sorted((cost[i][j], i, j) for i in range(n) for j in range(m))
        out, ui, uj = [], set(), set()
        for _, i, j in pairs:
            if i not in ui and j not in uj:
                out.append((i, j)); ui.add(i); uj.add(j)
        return out
    best, best_total = None, float("inf")
    for perm in permutations(range(m), min(n, m)):
        total = sum(cost[i][perm[i]] for i in range(len(perm)))
        if total < best_total:
            best_total, best = total, perm
    return [(i, best[i]) for i in range(len(best))]


def main() -> None:
    write = "--write" in sys.argv
    products = ars.extract()                    # [(name, code), ...]
    codes = {c for _, c in products}
    doc = pymupdf.open(PDF)
    skip = repeated_xrefs(doc)

    found: dict[str, tuple[int, int, pymupdf.Rect]] = {}
    for pno in range(1, doc.page_count + 1):
        for code, (xref, rect) in pair(doc[pno - 1], codes, skip).items():
            found.setdefault(code, (pno, xref, rect))

    resolved = json.loads(RESOLVED.read_text(encoding="utf-8"))
    rows = [r for r in resolved if r["brand"] == BRAND]

    def code_of(model: str) -> str | None:
        m = ars.CODE.search(model)
        return m.group(0) if m else None

    matched = [r for r in rows if (c := code_of(r["model"])) and c in found]
    # racks (ALPHA7/ALPHA11 -HR/-PR/-DHR) are deliberately skipped: they are
    # storage/rack furniture rather than trackable machines.
    missing = [r for r in rows if (c := code_of(r["model"])) and c not in found]
    nocode = [r for r in rows if not code_of(r["model"])]

    print(f"Arsenal rows in catalog : {len(rows)}")
    print(f"product codes parsed    : {len(codes)}")
    print(f"filtered branding xrefs : {len(skip)}")
    print(f"codes paired to a photo : {len(found)}")
    print(f"  rows matched          : {len(matched)}")
    print(f"  rows unmatched        : {len(missing)}")
    print(f"  rows with no code     : {len(nocode)}")
    if not write:
        for r in missing[:15]:
            print("   MISS", r["model"])
        print("\ndry run — pass --write to extract and attach")
        return

    OUT.mkdir(parents=True, exist_ok=True)
    placements = collections.Counter()
    for i in range(doc.page_count):
        for x in {x[0] for x in doc[i].get_images(full=True)}:
            placements[x] += len(doc[i].get_image_rects(x))

    for r in matched:
        code = code_of(r["model"])
        pno, xref, rect = found[code]
        slug = re.sub(r"[^A-Za-z0-9]+", "-", code).strip("-")
        dest = OUT / f"{slug}.jpg"
        # Prefer the embedded image itself: the page draws description text over
        # the photo's rect, so a clip render drags that text into the thumbnail.
        # Only fall back to rendering when the xref is placed more than once,
        # where extracting by xref would give two products the same picture.
        if placements[xref] == 1:
            pix = pymupdf.Pixmap(doc, xref)
            if pix.alpha or (pix.colorspace and pix.colorspace.n > 3):
                pix = pymupdf.Pixmap(pymupdf.csRGB, pix)
            pix.save(dest, jpg_quality=88)
        else:
            doc[pno - 1].get_pixmap(clip=rect, dpi=DPI).save(dest, jpg_quality=88)
        r["image"] = f"img/arsenal/{slug}.jpg"
    RESOLVED.write_text(json.dumps(resolved, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\nwrote {len(matched)} images to {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
