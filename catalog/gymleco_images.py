"""Attach Gymleco product photos from the 2026 Produktkatalog.

    python catalog/gymleco_images.py            # dry run
    python catalog/gymleco_images.py --write

Gymleco's 155 rows came from a web scrape and 23 of the cutouts are ghosted.
The catalog is Swedish ("Latsdrag", "Sittande Rodd"), so the machine names do
not line up with our English scraped titles at all — but both sides carry the
same article number, which the scraped titles happen to keep as a prefix:

    catalog   "Sittande Bröstpress / Art.nr: 021"
    our row   "021 Seated Chest Press"

So the join is purely on that number and never on the name. 60 of the 155 rows
have no number in the title and are left alone.

Layout is a 6x2 grid on a landscape double-page spread with the photo directly
above its "Art.nr:" line. Ranked by horizontal centre with each photo claimed
once per page, which is what stops two neighbouring cells fighting over the
same wide image (the trap booty_images.py hit).

Idempotent: re-running overwrites the same img/gymleco/<artnr>.jpg.
"""
from __future__ import annotations

import collections
import json
import re
import sys
from pathlib import Path

import pymupdf

ROOT = Path(__file__).resolve().parent.parent
PDF = ROOT / "docs" / "gymleco-produktkatalog-2026.pdf"
RESOLVED = ROOT / "catalog" / "machines_resolved.json"
OUT = ROOT / "tools" / "cap" / "www" / "img" / "gymleco"
BRAND = "Gymleco"

ARTNR = re.compile(r"Art\.nr:\s*(\d+)")
MIN_PX = 60
MAX_PAGE_FRAC = 0.4     # above this it is a full-bleed section photo
GAP = 90                # photo bottom sits this far above its Art.nr line


def pair(page) -> dict[str, tuple[int, pymupdf.Rect]]:
    area = page.rect.width * page.rect.height
    spots = []
    for b in page.get_text("dict")["blocks"]:
        for l in b.get("lines", []):
            for sp in l["spans"]:
                m = ARTNR.match(sp["text"].strip())
                if m:
                    spots.append((m.group(1), sp["bbox"]))
    imgs, seen = [], set()
    for x in page.get_images(full=True):
        for r in page.get_image_rects(x[0]):
            key = (x[0], round(r.x0), round(r.y0))
            if key in seen:
                continue
            seen.add(key)
            if r.width >= MIN_PX and r.height >= MIN_PX and (r.width * r.height) / area <= MAX_PAGE_FRAC:
                imgs.append((x[0], r))
    cands = []
    for art, bb in spots:
        cx, cy = (bb[0] + bb[2]) / 2, (bb[1] + bb[3]) / 2
        for j, (xref, r) in enumerate(imgs):
            if r.x0 - 30 <= cx <= r.x1 + 30 and 0 <= bb[1] - r.y1 <= GAP:
                cands.append((abs(cx - (r.x0 + r.x1) / 2), art, j))
    if len(cands) < len(spots):
        # Some spreads (p12, p27) set the photo BESIDE its Art.nr rather than
        # above it, on either side. Fall back to horizontal adjacency with the
        # text level with the photo, ranked by how far apart they are.
        placed = {a for _, a, _ in cands}
        for art, bb in spots:
            if art in placed:
                continue
            cx, cy = (bb[0] + bb[2]) / 2, (bb[1] + bb[3]) / 2
            for j, (xref, r) in enumerate(imgs):
                if r.y0 <= cy <= r.y1:
                    cands.append((1000 + abs(cx - (r.x0 + r.x1) / 2), art, j))
    cands.sort()
    out, used_a, used_i = {}, set(), set()
    for _, art, j in cands:
        if art in used_a or j in used_i:
            continue
        out[art] = imgs[j]
        used_a.add(art); used_i.add(j)
    return out


def main() -> None:
    write = "--write" in sys.argv
    doc = pymupdf.open(PDF)
    found: dict[str, tuple[int, int, pymupdf.Rect]] = {}
    for pno in range(1, doc.page_count + 1):
        for art, (xref, rect) in pair(doc[pno - 1]).items():
            found.setdefault(art, (pno, xref, rect))

    resolved = json.loads(RESOLVED.read_text(encoding="utf-8"))
    rows = [r for r in resolved if r["brand"] == BRAND]

    def art_of(model: str) -> str | None:
        m = re.match(r"^(\d{3})\b", model.strip())
        return m.group(1) if m and m.group(1) in found else None

    numbered = [r for r in rows if re.match(r"^\d{3}\b", r["model"].strip())]
    ok = [(r, a) for r in rows if (a := art_of(r["model"]))]
    print(f"catalog Art.nr entries paired to a photo: {len(found)}")
    print(f"{BRAND} rows: {len(rows)}   with an article number: {len(numbered)}   matched: {len(ok)}")
    if not write:
        missing = [r["model"] for r in numbered if not art_of(r["model"])]
        for m in missing[:12]:
            print("   MISS", m)
        print("\ndry run — pass --write to extract and attach")
        return

    placements = collections.Counter()
    for i in range(doc.page_count):
        for x in {x[0] for x in doc[i].get_images(full=True)}:
            placements[x] += len(doc[i].get_image_rects(x))

    OUT.mkdir(parents=True, exist_ok=True)
    for r, art in ok:
        pno, xref, rect = found[art]
        dest = OUT / f"{art}.jpg"
        if placements[xref] == 1:
            pix = pymupdf.Pixmap(doc, xref)
            if pix.alpha or (pix.colorspace and pix.colorspace.n > 3):
                pix = pymupdf.Pixmap(pymupdf.csRGB, pix)
            pix.save(dest, jpg_quality=88)
        else:
            doc[pno - 1].get_pixmap(clip=rect, dpi=150).save(dest, jpg_quality=88)
        r["image"] = f"img/gymleco/{art}.jpg"
    RESOLVED.write_text(json.dumps(resolved, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\nwrote {len({a for _, a in ok})} images, attached to {len(ok)} rows")


if __name__ == "__main__":
    main()
