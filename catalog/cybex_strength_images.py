"""Attach Cybex product photos from the "CYBEX Strength" catalog (docs/CYBEX Strength.pdf).

    python catalog/cybex_strength_images.py            # dry run
    python catalog/cybex_strength_images.py --write    # extract, attach, inline into DB

The catalog covers four lines, each with 4-digit product codes printed as a
13pt "CODE name" label directly under the photo:

  VR2 selectorized   45xx / 46xx / 47xx   pages 3-5
  VR selectorized    48xx                 pages 6-7
  Plate Loaded       52xx / 53xx / 54xx   pages 8-9
  FT 360             single hero photo    page 12

Our Cybex rows are marketplace listings, so the join is a hand-checked map from
model string to product code (MAP below). Lines not in this catalog — Eagle,
Eagle NX, VR1, VR3, Prestige, Classic, Galileo, Bravo, Modular — are left alone.
Benches, racks and the modular system (pages 10-14) are skipped: the modular
photos are 60 px thumbnails.

Writes tools/cap/www/img/cybex/<code>.jpg, sets `image` on matched rows in
catalog/machines_resolved.json, and (with --write) replaces the marketplace URL
in api/rackd.db for the same rows. Rows that already carry an inlined photo are
not touched.
"""
from __future__ import annotations

import base64
import io
import json
import re
import sqlite3
import sys
from collections import Counter
from pathlib import Path

import pymupdf
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
PDF = ROOT / "docs" / "CYBEX Strength.pdf"
RESOLVED = ROOT / "catalog" / "machines_resolved.json"
DB = ROOT / "api" / "rackd.db"
OUT = ROOT / "tools" / "cap" / "www" / "img" / "cybex"
BRAND = "Cybex"

MAX_PX, JPEG_Q = 512, 82
PAGES = [3, 4, 5, 6, 7, 8, 9]
CODE = re.compile(r"^(4[5-8]\d{2}|5[2-4]\d{2}|5560|5580)$")
FT360 = ("FT360", 12, 724)                       # code, page, hero image xref

# model string (as in the DB / resolved catalog) -> catalog code
MAP: dict[str, str] = {
    # VR2 (4506-4715)
    "VR2 Ab Crunch": "4705",
    "VR2 Adjustable Pec Fly": "4545",
    "VR2 Back Extension": "4711",
    "VR2 Bicep Arm Curl": "4535",
    "VR2 Bicep Curl w/Swivel Handles": "4535",
    "VR2 Bilateral Diverging Lat Pulldown": "4515",
    "VR2 Chest Press": "4507",
    "VR2 Hip Abduction / Outer Thigh": "4645",
    "VR2 Hip Adduction / Inner Thigh 4640": "4640",
    "VR2 Lat Pulldown": "4515",
    "VR2 Lateral Raise 4530": "4530",
    "VR2 Leg Extension": "4611",
    "VR2 Leg Extension w/ ROM Feature": "4611",
    "VR2 Leg Extension w/300 lb. Stack": "4611",
    "VR2 Leg Press": "4605",
    "VR2 Low Row / Rear Delt": "4520",
    "VR2 Pec Fly Machine 4545": "4545",
    "VR2 Prone Leg Curl": "4616",
    "VR2 Rotary Calf": "4620",
    "VR2 Seated Leg Curl": "4626",
    "VR2 Seated Leg Squat Press w / 500 Lb Stack - Belt Driven - Beast": "4605",
    "VR2 Shoulder Press": "4527",
    "VR2 Torso Rotation": "4715",
    "VR2 Tricep Arm Extension": "4540",
    # VR (4800-4890)
    "VR Lat Pulldown": "4810",
    "VR Standing Calf": "4875",
    "VR Standing Calf Raise": "4875",
    "VR Rotary Hip & Glute": "4865",
    "VR Glute Kickback": "4880",
    "VR Multi Grip Row & Rear Delt Combo": "4815",
    # Plate Loaded (5221-5580)
    "Plate Loaded Smith Press": "5341",
    "Plate Loaded Smith Press Machine 5341": "5341",
    "Plate Loaded Squat Press": "5235",
    "Leverage Squat Press Plate Loaded (Newer Style)": "5235",
    "Plate Loaded 45 Degree Leg Press": "5321",
    "Plate Loaded 45 Degree Leg Press (Newer Style)": "5321",
    "45 Degree Plate Loaded Linear Leg Press": "5321",
    "Plate Loaded 45 Degree Linear Hack Squat": "5330",
    "Platinum 45 Degree Plate Loaded Linear Hack Squat": "5330",
    "Plate Loaded Rotary Calf - Rare - Best Calf of All Time": "5245",
    "Plate Loaded Seated Calf - Style": "5450",
    "Plate Loaded Seated Calf Raise": "5450",
    "Plate Loaded ISO Lateral Converging Multi Grip Overhead Shoulder Press": "5222",
    "Plate Loaded ISO Lateral Converging Overhead Shoulder Press": "5222",
    "Plate Loaded Advanced ISO Lateral Converging Horizontal Bench Press & Fly Combo Machine - Multi Grip Handle Option": "5226",
    # FT 360
    "FT-360 Functional Trainer": "FT360",
    "FT360 Functional Trainer": "FT360",
    "FT 360 Functional Trainer Dual Pulley Cable Crossover - 300 lb. Stack": "FT360",
}


def find_photos(doc: pymupdf.Document) -> dict[str, tuple[int, int, pymupdf.Rect]]:
    out: dict[str, tuple[int, int, pymupdf.Rect]] = {}
    for pno in PAGES:
        page = doc[pno - 1]
        imgs, seen = [], set()
        for x in page.get_images(full=True):
            for r in page.get_image_rects(x[0]):
                k = (x[0], round(r.x0), round(r.y0))
                if k in seen:
                    continue
                seen.add(k)
                if r.width >= 70 and r.height >= 70:
                    imgs.append((x[0], r))
        for b in page.get_text("dict")["blocks"]:
            for l in b.get("lines", []):
                spans = l["spans"]
                if not spans or max(s["size"] for s in spans) < 11:
                    continue                                   # spec tables are 7pt
                first = spans[0]["text"].split()
                if not first or not CODE.match(first[0]) or first[0] in out:
                    continue
                lx0, ly0 = l["bbox"][0], l["bbox"][1]
                cx = lx0 + 10
                below = [(ly0 - r.y1, x, r) for x, r in imgs
                         if r.x0 - 12 <= cx <= r.x1 and -40 <= ly0 - r.y1 <= 60]
                if below:
                    gap, x, r = min(below, key=lambda t: abs(t[0]))
                    out[first[0]] = (pno, x, r)
    code, pno, xref = FT360
    out[code] = (pno, xref, doc[pno - 1].get_image_rects(xref)[0])
    return out


def extract(doc: pymupdf.Document, pno: int, xref: int, rect: pymupdf.Rect, dest: Path,
            placements: Counter) -> None:
    if placements[xref] == 1:
        pix = pymupdf.Pixmap(doc, xref)
        if pix.colorspace and pix.colorspace.n > 3:
            pix = pymupdf.Pixmap(pymupdf.csRGB, pix)
        smask = doc.extract_image(xref).get("smask")
        if smask:
            pix = pymupdf.Pixmap(pix, pymupdf.Pixmap(doc, smask))
        if pix.alpha:
            im = Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGBA")
            bg = Image.new("RGB", im.size, (255, 255, 255))
            bg.paste(im, mask=im.split()[-1])
            bg.save(dest, "JPEG", quality=90)
        else:
            pix.save(dest, jpg_quality=90)
    else:
        doc[pno - 1].get_pixmap(clip=rect, dpi=200).save(dest, jpg_quality=90)


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
    photos = find_photos(doc)
    need = set(MAP.values())
    print(f"photos located: {len(photos)}   codes needed: {len(need)}   "
          f"missing: {sorted(need - photos.keys())}\n")

    resolved = json.loads(RESOLVED.read_text(encoding="utf-8"))
    by_model = {r["model"].strip().lower(): r for r in resolved if r["brand"] == BRAND}
    hits: list[tuple[dict, str]] = []
    for model, code in MAP.items():
        r = by_model.get(model.strip().lower())
        if r is None:
            print(f"   not in catalog json: {model}")
        elif code in photos:
            hits.append((r, code))
    for r, code in sorted(hits, key=lambda t: (t[1], t[0]["model"])):
        pno, xref, rect = photos[code]
        print(f"   {code:<6} p{pno:<3} {rect.width:.0f}x{rect.height:.0f}  <- {r['model'][:70]}")
    print(f"\n{len(hits)} rows matched to {len({c for _, c in hits})} photos")
    if not write:
        print("\ndry run — pass --write to extract and attach")
        return

    placements: Counter = Counter()
    for i in range(doc.page_count):
        for x in {x[0] for x in doc[i].get_images(full=True)}:
            placements[x] += len(doc[i].get_image_rects(x))
    OUT.mkdir(parents=True, exist_ok=True)
    for code in {c for _, c in hits}:
        pno, xref, rect = photos[code]
        extract(doc, pno, xref, rect, OUT / f"{code}.jpg", placements)
    for r, code in hits:
        r["image"] = f"img/cybex/{code}.jpg"
    RESOLVED.write_text(json.dumps(resolved, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    con = sqlite3.connect(DB)
    (brand_id,) = con.execute("select id from brand where name=?", (BRAND,)).fetchone()
    uris = {code: inline(OUT / f"{code}.jpg") for _, code in hits}
    updated = 0
    for r, code in hits:
        cur = con.execute(
            "update machine set image_url=? where brand_id=? and lower(trim(model))=lower(trim(?)) "
            "and (image_url is null or image_url like 'http%')",
            (uris[code], brand_id, r["model"]))
        updated += cur.rowcount
    con.commit()
    print(f"wrote {len(uris)} photos to {OUT.relative_to(ROOT)}, attached {len(hits)} catalog rows, "
          f"updated {updated} DB rows")


if __name__ == "__main__":
    main()
