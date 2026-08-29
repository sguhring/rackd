"""Attach Cybex Eagle NX product photos from the 2014 brochure to the catalog.

    python catalog/cybex_nx_images.py            # dry run
    python catalog/cybex_nx_images.py --write

Unlike Watson/gym80 this is NOT a per-SKU pairing. The Eagle NX brochure
(docs/cybex-eagle-nx-brochure-2014.pdf, (c) 2014) is a 12-page marketing piece
that presents the line as "fifteen premium and unique pieces" — one studio photo
per movement, with no product codes and no unilateral/bilateral variants. Our
Cybex rows come from used-equipment marketplaces and are per-SKU, so several
rows legitimately share one brochure photo (both "Eagle NX Row 20030" and the
seller-coined "Eagle NX Unilateral Row" map to the single `Row` photo).

The point is quality, not coverage: 24 of the 28 Hoist and 145 of the 218 Cybex
scraper cutouts are ghosted warehouse shots on pallets. These are clean.

Layout: 3 columns, photo on top, name directly beneath at a constant y.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pymupdf

ROOT = Path(__file__).resolve().parent.parent
PDF = ROOT / "docs" / "cybex-eagle-nx-brochure-2014.pdf"
RESOLVED = ROOT / "catalog" / "machines_resolved.json"
OUT = ROOT / "tools" / "cap" / "www" / "img" / "cybex"
BRAND = "Cybex"
DPI = 200

# catalog-row keyword -> brochure label. First match wins, so order matters:
# "seated leg curl" must beat "leg curl", "leg press" must not swallow "leg extension".
ALIAS = [
    ("abductor", "Hip Abduction/Adduction"), ("abduction", "Hip Abduction/Adduction"),
    ("adductor", "Hip Abduction/Adduction"), ("adduction", "Hip Abduction/Adduction"),
    ("seated leg curl", "Seated Leg Curl"), ("leg curl", "Seated Leg Curl"),
    ("leg extension", "Leg Extension"), ("leg press", "Leg Press"),
    ("rotary calf", "Calf"), ("calf", "Calf"), ("glute", "Glute"),
    ("torso rotation", "Torso Rotation"), ("back extension", "Back Extension"),
    ("abdominal", "Abdominal"), ("arm extension", "Arm Extension"),
    ("arm curl", "Arm Curl"), ("bicep", "Arm Curl"),
    ("pulldown", "Pulldown"), ("lat pull", "Pulldown"),
    ("chest press", "Chest Press"), ("overhead press", "Overhead Press"),
    ("shoulder press", "Overhead Press"), ("row", "Row"),
]


def photos() -> dict[str, tuple[int, pymupdf.Rect]]:
    """brochure label -> (page, rect of the photo above it)."""
    doc = pymupdf.open(PDF)
    out: dict[str, tuple[int, pymupdf.Rect]] = {}
    for pno in range(1, doc.page_count + 1):
        page = doc[pno - 1]
        names = [(sp["text"].strip(), sp["bbox"])
                 for b in page.get_text("dict")["blocks"]
                 for l in b.get("lines", []) for sp in l["spans"]
                 if sp["size"] >= 11 and sp["text"].strip()]
        imgs = [r for x in page.get_images(full=True)
                for r in page.get_image_rects(x[0]) if r.width >= 100 and r.height >= 100]
        for label, bb in names:
            cx = (bb[0] + bb[2]) / 2
            above = [(bb[1] - r.y1, r) for r in imgs if r.x0 - 40 <= cx <= r.x1 + 40 and r.y1 <= bb[1]]
            if above:
                above.sort()
                out[label] = (pno, above[0][1])
    return out


def main() -> None:
    write = "--write" in sys.argv
    pics = photos()
    print(f"brochure photos found: {len(pics)}  -> {sorted(pics)}\n")

    resolved = json.loads(RESOLVED.read_text(encoding="utf-8"))
    rows = [r for r in resolved if r["brand"] == BRAND and "NX" in r["model"]]

    def label_for(model: str) -> str | None:
        m = model.lower()
        for key, label in ALIAS:
            if key in m and label in pics:
                return label
        return None

    hits = [(r, label_for(r["model"])) for r in rows]
    matched = [(r, l) for r, l in hits if l]
    print(f"Eagle NX rows: {len(rows)}   matched: {len(matched)}")
    for r, l in hits:
        print(f"   {'OK ' if l else 'MISS'} {r['model'][:52]:52} -> {l}")
    if not write:
        print("\ndry run — pass --write to extract and attach")
        return

    doc = pymupdf.open(PDF)
    OUT.mkdir(parents=True, exist_ok=True)
    for r, label in matched:
        pno, rect = pics[label]
        slug = re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-")
        doc[pno - 1].get_pixmap(clip=rect, dpi=DPI).save(OUT / f"eagle-nx-{slug}.jpg", jpg_quality=90)
        r["image"] = f"img/cybex/eagle-nx-{slug}.jpg"
    RESOLVED.write_text(json.dumps(resolved, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\nattached {len(matched)} rows to {len({l for _, l in matched})} photos in {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
