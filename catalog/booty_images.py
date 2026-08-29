"""Attach Booty Builder product photos from the 2025 commercial catalog.

    python catalog/booty_images.py            # dry run
    python catalog/booty_images.py --write

Companion to booty_to_catalog.py. Layout is a 3-column landscape spread with the
photo ABOVE its 14pt heading (like gym80, unlike Watson). Booty Builder prints no
product codes, so rows are matched to headings by normalised name — which is why
booty_to_catalog disambiguates the two Standing Abductor / Standing Hip Thrust
machines with a "(Plate-Loaded)" / "(Selectorized)" suffix taken from the section.

Idempotent: re-running overwrites the same img/booty/<slug>.jpg.
"""
from __future__ import annotations

import collections
import json
import re
import sys
from pathlib import Path

import pymupdf

ROOT = Path(__file__).resolve().parent.parent
PDF = ROOT / "docs" / "Booty-Builder-2025-Commercial-Catalog-.pdf (1).pdf"
RESOLVED = ROOT / "catalog" / "machines_resolved.json"
OUT = ROOT / "tools" / "cap" / "www" / "img" / "booty"
BRAND = "Booty Builder"

HEAD_PT = 13.0       # machine headings are 14pt; body copy is 12pt
MIN_PX = 100
MAX_PAGE_FRAC = 0.5  # above this it is the full-bleed background photo
GAP = 60             # photo bottom sits just above its heading
OVERLAP = 60         # ... and its transparent base often runs behind the text
DPI = 150


def section_for(pno: int) -> str | None:
    """Section title pages: "Plate Loaded" p4, "Selectorized" p8. Both sections
    contain a Standing Abductor and a Standing Hip Thrust, so the section is
    what tells the two apart."""
    if 4 <= pno <= 6:
        return "plate-loaded"
    if 8 <= pno <= 11:
        return "selectorized"
    return None


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", s.lower())


def pair(page) -> dict[str, tuple[int, pymupdf.Rect]]:
    area = page.rect.width * page.rect.height
    heads = [(sp["text"].strip(), sp["bbox"])
             for b in page.get_text("dict")["blocks"]
             for l in b.get("lines", []) for sp in l["spans"]
             if sp["size"] >= HEAD_PT and sp["text"].strip()]
    imgs, seen = [], set()
    for x in page.get_images(full=True):
        for r in page.get_image_rects(x[0]):
            key = (x[0], round(r.x0), round(r.y0))
            if key in seen:
                continue
            seen.add(key)
            if r.width >= MIN_PX and r.height >= MIN_PX and (r.width * r.height) / area <= MAX_PAGE_FRAC:
                imgs.append((x[0], r))
    # Photos are wide and overlap neighbouring columns, so containment alone is
    # ambiguous: on p8 both DEADLIFT/SPLIT SQUAT and STEP-UP sit inside the same
    # two rects with an identical vertical gap. Rank by horizontal centre
    # distance instead, and let each photo be claimed only once per page.
    cands = []
    for label, bb in heads:
        cx = (bb[0] + bb[2]) / 2
        for j, (xref, r) in enumerate(imgs):
            if r.x0 - 20 <= cx <= r.x1 + 20 and -OVERLAP <= bb[1] - r.y1 <= GAP:
                cands.append((abs(cx - (r.x0 + r.x1) / 2), label, j))
    cands.sort()
    out, used_label, used_img = {}, set(), set()
    for _, label, j in cands:
        if label in used_label or j in used_img:
            continue
        out[label] = imgs[j]
        used_label.add(label); used_img.add(j)
    return out


def main() -> None:
    write = "--write" in sys.argv
    doc = pymupdf.open(PDF)
    heads: dict[tuple[str, str], tuple[int, int, pymupdf.Rect]] = {}
    for pno in range(1, doc.page_count + 1):
        section = section_for(pno)
        if section is None:
            continue
        for label, (xref, rect) in pair(doc[pno - 1]).items():
            heads.setdefault((section, norm(label)), (pno, xref, rect))

    resolved = json.loads(RESOLVED.read_text(encoding="utf-8"))
    rows = [r for r in resolved if r["brand"] == BRAND]

    def key_for(model: str) -> tuple[str, str] | None:
        # "Booty Builder Standing Abductor (Plate-Loaded)" -> (plate-loaded, standingabductor)
        name = model[len(BRAND):].strip()
        m = re.search(r"\(([^)]*)\)\s*$", name)
        suffix = norm(m.group(1)) if m else None
        base = norm(re.sub(r"\s*\([^)]*\)\s*$", "", name))
        wanted = {"plateloaded": "plate-loaded", "selectorized": "selectorized"}.get(suffix)
        cands = [k for k in heads if k[1] == base and (wanted is None or k[0] == wanted)]
        return cands[0] if len(cands) == 1 else None

    matched = [(r, key_for(r["model"])) for r in rows]
    ok = [(r, k) for r, k in matched if k]
    print(f"headings with a photo: {len(heads)}")
    print(f"{BRAND} rows: {len(rows)}   matched: {len(ok)}")
    for r, k in matched:
        print(f"   {'OK  ' if k else 'MISS'} {r['model']}")
    if not write:
        print("\ndry run — pass --write to extract and attach")
        return

    placements = collections.Counter()
    for i in range(doc.page_count):
        for x in {x[0] for x in doc[i].get_images(full=True)}:
            placements[x] += len(doc[i].get_image_rects(x))

    OUT.mkdir(parents=True, exist_ok=True)
    for r, k in ok:
        pno, xref, rect = heads[k]
        slug = re.sub(r"[^a-z0-9]+", "-", r["model"][len(BRAND):].strip().lower()).strip("-")
        dest = OUT / f"{slug}.jpg"
        if placements[xref] == 1:
            pix = pymupdf.Pixmap(doc, xref)
            if pix.alpha or (pix.colorspace and pix.colorspace.n > 3):
                pix = pymupdf.Pixmap(pymupdf.csRGB, pix)
            pix.save(dest, jpg_quality=88)
        else:
            doc[pno - 1].get_pixmap(clip=rect, dpi=DPI).save(dest, jpg_quality=88)
        r["image"] = f"img/booty/{slug}.jpg"
    RESOLVED.write_text(json.dumps(resolved, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\nwrote {len(ok)} images to {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
