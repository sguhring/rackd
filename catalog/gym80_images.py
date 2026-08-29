"""Attach gym80 product photos from the Gesamtbroschuere to the catalog.

    python catalog/gym80_images.py            # dry run — report pairing rate
    python catalog/gym80_images.py --write    # render crops + set `image`

Companion to gym80_to_catalog.py, same idea as watson_images.py but the layout
is mirrored: the brochure is a 2x2 grid of quadrants on a portrait page and the
photo sits ABOVE its product code, not below.

Two gym80-specific traps:

  * The spec block under each product is bare millimetre/kg numbers (1570, 350,
    135 ...) which match the product-code regex exactly. So we do NOT re-detect
    codes here — we import the validated list from gym80_to_catalog, which
    confirms a code by requiring an ALL-CAPS heading above it.
  * A photo is reused across cells at the PDF object level, so we render the
    image's rect rather than extracting its xref (see watson_images.py).

Idempotent: re-running overwrites the same img/gym80/<code>.jpg.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pymupdf

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
import gym80_to_catalog as g80  # noqa: E402

PDF = ROOT / "docs" / "gym80-Gesamtbroschuere.pdf"
RESOLVED = ROOT / "catalog" / "machines_resolved.json"
OUT = ROOT / "tools" / "cap" / "www" / "img" / "gym80"
BRAND = "gym80"

CODE = re.compile(r"^\d{3,4}[A-Z]?$")
GAP = 60          # a quadrant's photo ends just above its code line
MIN_PX = 80       # ignore logos / rules / decorative slivers
DPI = 150


def pair(page, valid: set[str]) -> dict[str, pymupdf.Rect]:
    """code -> rect of the photo sitting directly above it in the same column."""
    imgs = []
    seen = set()
    for x in page.get_images(full=True):
        for r in page.get_image_rects(x[0]):
            key = (x[0], round(r.x0), round(r.y0))
            if r.width >= MIN_PX and r.height >= MIN_PX and key not in seen:
                seen.add(key)
                imgs.append(r)
    out: dict[str, pymupdf.Rect] = {}
    for w in page.get_text("words"):
        code = w[4]
        if code not in valid:
            continue
        cx, cy = w[0], w[1]
        col = [r for r in imgs if r.x0 - 12 <= cx <= r.x1 + 12]
        cands = [(cy - r.y1, r) for r in col if 0 <= cy - r.y1 <= GAP]
        if not cands:
            # feature-spread template: the code is set over the top of its
            # photo instead of under it, so nothing ends above the code line.
            cands = [(r.y1 - r.y0, r) for r in col if r.y0 - 12 <= cy <= r.y1]
        if cands:
            cands.sort()                       # nearest above / tightest wins
            out[code] = cands[0][1]
    return out


def main() -> None:
    write = "--write" in sys.argv
    valid = {code for _, code, _ in g80.extract()}
    doc = pymupdf.open(PDF)
    found: dict[str, tuple[int, pymupdf.Rect]] = {}
    for pno in range(1, doc.page_count + 1):
        for code, rect in pair(doc[pno - 1], valid).items():
            found.setdefault(code, (pno, rect))

    resolved = json.loads(RESOLVED.read_text(encoding="utf-8"))
    rows = [r for r in resolved if r["brand"] == BRAND]

    def code_of(m: str) -> str | None:
        t = m.split()[-1]
        return t if CODE.match(t) else None

    matched = [r for r in rows if (c := code_of(r["model"])) and c in found]
    missing = [r for r in rows if (c := code_of(r["model"])) and c not in found]
    nocode = [r for r in rows if not code_of(r["model"])]

    print(f"gym80 rows in catalog  : {len(rows)}")
    print(f"validated product codes: {len(valid)}")
    print(f"codes paired to a photo: {len(found)}")
    print(f"  rows matched         : {len(matched)}")
    print(f"  rows unmatched       : {len(missing)}")
    print(f"  rows with no code    : {len(nocode)}")
    if not write:
        for r in missing[:20]:
            print("   MISS", r["model"])
        print("\ndry run — pass --write to extract and attach")
        return

    OUT.mkdir(parents=True, exist_ok=True)
    for r in matched:
        code = code_of(r["model"])
        pno, rect = found[code]
        doc[pno - 1].get_pixmap(clip=rect, dpi=DPI).save(OUT / f"{code}.jpg", jpg_quality=88)
        r["image"] = f"img/gym80/{code}.jpg"
    RESOLVED.write_text(json.dumps(resolved, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8")
    print(f"\nwrote {len(matched)} images to {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
