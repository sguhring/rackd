"""Attach Precor product photos from the commercial catalogue.

    python catalog/precor_images.py            # dry run
    python catalog/precor_images.py --write

59 of Precor's 101 scraper cutouts are ghosted. The catalogue carries the same
product codes our scraped titles do ("DPL0305 Discovery Series Plate Loaded Lat
Pulldown" <-> "DPL0305"), so the join is on the code and never on the name.

Matching is EXACT. The catalogue is the current line-up and uses RSL (Resolute,
launched 2020) where our older rows use DSL (Discovery Selectorized), and the
two share numeric suffixes -- DSL0204 vs RSL0204. Mapping one onto the other
would attach a photo of the successor machine, the same generation trap as
Cybex Eagle vs Eagle NX, so a DSL row simply goes unmatched.

Layout: landscape spread, six products across, every code on a constant
baseline with its photo directly above.

Idempotent: re-running overwrites the same img/precor/<code>.jpg.
"""
from __future__ import annotations

import collections
import json
import re
import sys
from pathlib import Path

import pymupdf

ROOT = Path(__file__).resolve().parent.parent
PDF = ROOT / "docs" / "precor-commercial-catalogue.pdf"
RESOLVED = ROOT / "catalog" / "machines_resolved.json"
OUT = ROOT / "tools" / "cap" / "www" / "img" / "precor"
BRAND = "Precor"

CODE = re.compile(r"^[A-Z]{2,3}\d{3,4}[A-Z]{0,2}$")
MIN_PX = 60
MAX_PAGE_FRAC = 0.35    # above this it is a lifestyle/section photo
GAP = 80                # photo bottom sits just above the code baseline
DPI = 150


def pair(page) -> dict[str, tuple[int, pymupdf.Rect]]:
    area = page.rect.width * page.rect.height
    spots = []
    for b in page.get_text("dict")["blocks"]:
        for l in b.get("lines", []):
            for sp in l["spans"]:
                t = sp["text"].strip()
                if CODE.match(t):
                    spots.append((t, sp["bbox"]))
    imgs, seen = [], set()
    for x in page.get_images(full=True):
        for r in page.get_image_rects(x[0]):
            key = (x[0], round(r.x0), round(r.y0))
            if key in seen:
                continue
            seen.add(key)
            if r.width >= MIN_PX and r.height >= MIN_PX and (r.width * r.height) / area <= MAX_PAGE_FRAC:
                imgs.append((x[0], r))
    # Rank on horizontal centre and let each photo be claimed once, so two
    # neighbouring columns cannot both take the same wide image.
    cands = []
    for code, bb in spots:
        cx = (bb[0] + bb[2]) / 2
        for j, (xref, r) in enumerate(imgs):
            if r.x0 - 40 <= cx <= r.x1 + 40 and -20 <= bb[1] - r.y1 <= GAP:
                cands.append((abs(cx - (r.x0 + r.x1) / 2), code, j))
    cands.sort()
    out, used_c, used_i = {}, set(), set()
    for _, code, j in cands:
        if code in used_c or j in used_i:
            continue
        out[code] = imgs[j]
        used_c.add(code); used_i.add(j)
    return out


def main() -> None:
    write = "--write" in sys.argv
    doc = pymupdf.open(PDF)
    found: dict[str, tuple[int, int, pymupdf.Rect]] = {}
    for pno in range(1, doc.page_count + 1):
        for code, (xref, rect) in pair(doc[pno - 1]).items():
            found.setdefault(code, (pno, xref, rect))

    resolved = json.loads(RESOLVED.read_text(encoding="utf-8"))
    rows = [r for r in resolved if r["brand"] == BRAND]

    def code_of(model: str) -> str | None:
        for tok in re.findall(r"\b[A-Z]{2,3}\d{3,4}[A-Z]{0,2}\b", model.upper()):
            if tok in found:
                return tok
        return None

    ok = [(r, c) for r in rows if (c := code_of(r["model"]))]
    coded = [r for r in rows if re.search(r"\b[A-Z]{2,3}\d{3,4}[A-Z]{0,2}\b", r["model"].upper())]
    print(f"catalogue codes paired to a photo: {len(found)}")
    print(f"{BRAND} rows: {len(rows)}   carrying a code: {len(coded)}   matched: {len(ok)}")
    if not write:
        for r in coded[:14]:
            if not code_of(r["model"]):
                print("   MISS", r["model"][:60])
        print("\ndry run — pass --write to extract and attach")
        return

    placements = collections.Counter()
    for i in range(doc.page_count):
        for x in {x[0] for x in doc[i].get_images(full=True)}:
            placements[x] += len(doc[i].get_image_rects(x))

    OUT.mkdir(parents=True, exist_ok=True)
    for r, code in ok:
        pno, xref, rect = found[code]
        dest = OUT / f"{code}.jpg"
        if placements[xref] == 1:
            pix = pymupdf.Pixmap(doc, xref)
            if pix.alpha or (pix.colorspace and pix.colorspace.n > 3):
                pix = pymupdf.Pixmap(pymupdf.csRGB, pix)
            pix.save(dest, jpg_quality=90)
        else:
            doc[pno - 1].get_pixmap(clip=rect, dpi=DPI).save(dest, jpg_quality=90)
        r["image"] = f"img/precor/{code}.jpg"
    RESOLVED.write_text(json.dumps(resolved, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\nwrote {len({c for _, c in ok})} images, attached to {len(ok)} rows")


if __name__ == "__main__":
    main()
