"""Attach Cybex VR1 product photos from the VR1 brochure (docs/Cybey_V1.pdf).

    python catalog/cybex_vr1_images.py            # dry run
    python catalog/cybex_vr1_images.py --write    # extract, attach, inline into DB

The brochure is a scan with no text layer, so pairing is by hand: every product
page shows one machine at the top and one at the bottom, each under its heading,
and PHOTOS pins each product to the page + image xref (checked by eye against
the page renders). The photos include a person on the machine — that is what
the brochure offers, and it beats a ghosted marketplace shot.

Our VR1 rows are marketplace listings; MAP joins each model string to a product.
Rows already carrying an inlined photo are left alone.
"""
from __future__ import annotations

import base64
import io
import json
import re
import sqlite3
import sys
from pathlib import Path

import pymupdf
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
PDF = ROOT / "docs" / "Cybey_V1.pdf"
RESOLVED = ROOT / "catalog" / "machines_resolved.json"
DB = ROOT / "api" / "rackd.db"
OUT = ROOT / "tools" / "cap" / "www" / "img" / "cybex"
BRAND = "Cybex"
MAX_PX, JPEG_Q = 512, 82

# product -> (page, image xref)
PHOTOS: dict[str, tuple[int, int]] = {
    "chest press": (9, 47), "overhead press": (9, 48),
    "row/rear delt": (10, 56), "lat pull": (10, 57),
    "arm extension": (11, 66), "arm curl": (11, 67),
    "abdominal": (12, 74), "back extension": (12, 76),
    "leg press": (13, 83), "calf": (13, 84),
    "leg extension": (14, 93), "seated leg curl": (14, 91),
    "glute": (15, 101), "pulldown": (15, 109),
    "arm curl traditional": (16, 114), "arm ext traditional": (16, 115),
    "multi press": (18, 130), "fly/rear delt": (18, 129),
    "ab/back extension": (19, 143), "biceps/triceps": (19, 145),
    "lat/row": (20, 153),
    "leg ext/leg curl": (21, 165), "hip ab/ad": (21, 168),
}

# model string (as in the DB / resolved catalog) -> product
MAP: dict[str, str] = {
    "Multi Grip VR1 Row & Rear Delt": "row/rear delt",
    "VR1 Dual Abdominal/Back Extension": "ab/back extension",
    "VR1 Dual Purpose Lat/Row 13250": "lat/row",
    "VR1 Dual Purpose Leg Ext/Seated Leg Curl 13260": "leg ext/leg curl",
    "VR1 Dual Purpose Multi-Press 13240": "multi press",
    "VR1 Leg Extension & Leg Curl 2 in 1 Combo Machine - Space Saver": "leg ext/leg curl",
    "VR1 Leg Extension & Leg Curl Combo Machine": "leg ext/leg curl",
    "VR1 Platinum Bicep & Tricep Combo Total Body Dual Pulley Machine": "biceps/triceps",
    "VR1 Seated Leg Press": "leg press",
}


def slug(s: str) -> str:
    return "vr1-" + re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def extract(doc: pymupdf.Document, xref: int, dest: Path) -> None:
    pix = pymupdf.Pixmap(doc, xref)
    if pix.colorspace and pix.colorspace.n > 3:
        pix = pymupdf.Pixmap(pymupdf.csRGB, pix)
    if pix.alpha:
        pix = pymupdf.Pixmap(pix, 0)
    pix.save(dest, jpg_quality=90)


def inline(path: Path) -> str:
    im = Image.open(path)
    if im.mode not in ("RGB", "L"):
        im = im.convert("RGB")
    im.thumbnail((MAX_PX, MAX_PX))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=JPEG_Q, optimize=True)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def main() -> None:
    write = "--write" in sys.argv
    doc = pymupdf.open(PDF)
    resolved = json.loads(RESOLVED.read_text(encoding="utf-8"))
    by_model = {r["model"].strip().lower(): r for r in resolved if r["brand"] == BRAND}
    hits: list[tuple[dict, str]] = []
    for model, product in MAP.items():
        r = by_model.get(model.strip().lower())
        if r is None:
            print(f"   not in catalog json: {model}")
            continue
        hits.append((r, product))
        pno, xref = PHOTOS[product]
        print(f"   {product:<20} p{pno:<3} xref {xref:<4} <- {r['model'][:70]}")
    print(f"\n{len(hits)} rows matched to {len({p for _, p in hits})} photos")
    if not write:
        print("\ndry run — pass --write to extract and attach")
        return

    OUT.mkdir(parents=True, exist_ok=True)
    for product in {p for _, p in hits}:
        extract(doc, PHOTOS[product][1], OUT / f"{slug(product)}.jpg")
    for r, product in hits:
        r["image"] = f"img/cybex/{slug(product)}.jpg"
    RESOLVED.write_text(json.dumps(resolved, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    con = sqlite3.connect(DB)
    (brand_id,) = con.execute("select id from brand where name=?", (BRAND,)).fetchone()
    uris = {p: inline(OUT / f"{slug(p)}.jpg") for _, p in hits}
    updated = 0
    for r, product in hits:
        cur = con.execute(
            "update machine set image_url=? where brand_id=? and lower(trim(model))=lower(trim(?)) "
            "and (image_url is null or image_url like 'http%')",
            (uris[product], brand_id, r["model"]))
        updated += cur.rowcount
    con.commit()
    print(f"wrote {len(uris)} photos to {OUT.relative_to(ROOT)}, attached {len(hits)} catalog rows, "
          f"updated {updated} DB rows")


if __name__ == "__main__":
    main()
