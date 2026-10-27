"""Attach PRIME Plate Loaded product photos from the 2023 brochure.

    python catalog/prime_images.py            # dry run
    python catalog/prime_images.py --write

The Evolution line already has photos (img/prime/prime-evolution-*.png); this
covers the Plate Loaded line, which sits on pages 18-19 of the 2023 brochure as
a two-column grid with the thumbnail immediately LEFT of its 14pt heading and
roughly level with it.

Restricted to those two pages on purpose: page 20 repeats the pair as a combined
"LEG EXTENSION/PRONE LEG CURL" feature, which would otherwise compete with the
individual p18 entries for the same rows.

Idempotent: re-running overwrites the same img/prime/prime-plate-loaded-*.jpg.
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
PDF = ROOT / "docs" / "786989897-PRIME-Product-Brochure-2023.pdf"
RESOLVED = ROOT / "catalog" / "machines_resolved.json"
OUT = ROOT / "tools" / "cap" / "www" / "img" / "prime"
BRAND = "Prime"
PAGES = (18, 19)

HEAD_PT = 13.5      # machine headings are 14pt; section blurbs are 19pt
MIN_PX = 80
DPI = 200


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", s.lower())


def pair(page) -> dict[str, tuple[int, pymupdf.Rect]]:
    heads = [(sp["text"].strip(), sp["bbox"])
             for b in page.get_text("dict")["blocks"]
             for l in b.get("lines", []) for sp in l["spans"]
             if HEAD_PT <= sp["size"] < 16 and sp["text"].strip()]
    imgs, seen = [], set()
    for x in page.get_images(full=True):
        for r in page.get_image_rects(x[0]):
            key = (x[0], round(r.x0), round(r.y0))
            if key not in seen and r.width >= MIN_PX and r.height >= MIN_PX:
                seen.add(key)
                imgs.append((x[0], r))
    if not heads or not imgs:
        return {}
    # A heading's photo is level with it; rank on vertical centre distance and
    # let each photo be claimed once, minimising total distance over the page.
    cost = []
    for _, bb in heads:
        hy = (bb[1] + bb[3]) / 2
        cost.append([abs(hy - (r.y0 + r.y1) / 2) + 0.25 * abs(bb[0] - r.x1)
                     for _, r in imgs])
    n, m = len(heads), len(imgs)
    best, best_total = None, float("inf")
    if n <= 8 and m <= 8:
        for perm in permutations(range(m), min(n, m)):
            total = sum(cost[i][perm[i]] for i in range(len(perm)))
            if total < best_total:
                best_total, best = total, perm
        idx = [(i, best[i]) for i in range(len(best))]
    else:
        pairs = sorted((cost[i][j], i, j) for i in range(n) for j in range(m))
        idx, ui, uj = [], set(), set()
        for _, i, j in pairs:
            if i not in ui and j not in uj:
                idx.append((i, j)); ui.add(i); uj.add(j)
    return {heads[i][0]: imgs[j] for i, j in idx}


def main() -> None:
    write = "--write" in sys.argv
    doc = pymupdf.open(PDF)
    heads: dict[str, tuple[int, int, pymupdf.Rect]] = {}
    for pno in PAGES:
        for label, (xref, rect) in pair(doc[pno - 1]).items():
            heads.setdefault(norm(label), (pno, xref, rect))

    resolved = json.loads(RESOLVED.read_text(encoding="utf-8"))
    rows = [r for r in resolved if r["brand"] == BRAND and "Plate Loaded" in r["model"]]

    def key_for(model: str) -> str | None:
        name = model.split("Plate Loaded", 1)[1].strip()
        for k in (norm(name), norm(name.replace("Low ", ""))):
            if k in heads:
                return k
        return None

    hits = [(r, key_for(r["model"])) for r in rows]
    ok = [(r, k) for r, k in hits if k]
    print(f"headings paired on p{PAGES}: {len(heads)} -> {sorted(heads)}")
    print(f"{BRAND} Plate Loaded rows: {len(rows)}   matched: {len(ok)}")
    for r, k in hits:
        print(f"   {'OK  ' if k else 'MISS'} {r['model']:44} -> {k}")
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
        slug = re.sub(r"[^a-z0-9]+", "-", r["model"].replace("PRIME", "").strip().lower()).strip("-")
        dest = OUT / f"prime-{slug}.jpg"
        if placements[xref] == 1:
            pix = pymupdf.Pixmap(doc, xref)
            if pix.alpha or (pix.colorspace and pix.colorspace.n > 3):
                pix = pymupdf.Pixmap(pymupdf.csRGB, pix)
            pix.save(dest, jpg_quality=90)
        else:
            doc[pno - 1].get_pixmap(clip=rect, dpi=DPI).save(dest, jpg_quality=90)
        r["image"] = f"img/prime/prime-{slug}.jpg"
    RESOLVED.write_text(json.dumps(resolved, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\nwrote {len(ok)} images to {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
