"""Muscle D Fitness: attach the manufacturer's own product photos from the
original Strength Equipment Catalog (docs/muscledfitness.com_.pdf).

    python catalog/muscled_images.py            # dry run + contact sheet
    python catalog/muscled_images.py --write    # attach

The PDF is a print of the muscledfitness.com catalog: 44 pages, each one a
single 1260x1620 page image with no text layer, so products cannot be pulled
out by xref like the other brochures. Every photo below is a hand-pinned crop
rectangle (page, x0, y0, x1, y1) in page-image pixels, checked against the
rendered pages and the contact sheet written next to the crops.

This catalog is the Power Leverage generation (MDP-1xxx / 2xxx, grey frames,
"Pillow block bearings") — the same machines our secondhand listings carry, not
the later V2 redesign muscledfit.com sells today. It also covers the Classic
(MDC), Dual Function (MDD) and Free Weight (MD-) lines. The Elite Leverage
(L***) plate-loaded line is not in it (its "Elite Line" is the red selectorized
MDE range), so those listings keep their marketplace photos.

Crops are written to tools/cap/www/img/muscled/<code>.jpg and inlined into
api/rackd.db for the rows in MAP (only rows still carrying a marketplace URL).
"""
from __future__ import annotations

import base64
import io
import json
import sqlite3
import sys
from pathlib import Path

import pymupdf
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
PDF = ROOT / "docs" / "muscledfitness.com_.pdf"
RESOLVED = ROOT / "catalog" / "machines_resolved.json"
DB = ROOT / "api" / "rackd.db"
OUT = ROOT / "tools" / "cap" / "www" / "img" / "muscled"
BRAND = "Muscle D"
DPI = 144  # renders the 630x810 pt pages at their native 1260x1620 image size
MAX_PX, JPEG_Q = 512, 82

# code -> (page, x0, y0, x1, y1) in 1260x1620 page pixels
PHOTOS: dict[str, tuple[int, int, int, int, int]] = {
    # Power Leverage | legs (p13-14)
    "MDP-2001": (13, 100, 100, 450, 360),
    "MDP-2007": (13, 100, 368, 450, 650),
    "MDP-1035": (13, 110, 645, 420, 940),
    "MDP-2002": (13, 100, 935, 450, 1260),
    "MDP-2003": (13, 100, 1255, 450, 1600),
    "MDP-2010": (14, 100, 85, 450, 420),
    "MDP-2017": (14, 80, 420, 450, 830),
    "MDP-2009": (14, 60, 820, 450, 1210),
    "MDP-2008": (14, 95, 1200, 450, 1600),
    # Power Leverage | chest (p15)
    "MDP-1001": (15, 60, 85, 400, 470),
    "MDP-1002": (15, 10, 460, 390, 780),
    "MDP-1003": (15, 40, 790, 400, 1170),
    "MDP-1007": (15, 30, 1170, 400, 1600),
    # Power Leverage | back and arms (p16)
    "MDP-1006": (16, 30, 85, 400, 395),
    "MDP-1005": (16, 80, 395, 380, 680),
    "MDP-1004": (16, 80, 680, 380, 980),
    "MDP-2012": (16, 80, 975, 380, 1275),
    "MDP-1018": (16, 70, 1265, 400, 1600),
    # Power Leverage | upper body (p17)
    "MDP-1032": (17, 40, 90, 380, 490),
    "MDP-1031": (17, 20, 500, 400, 780),
    "MDP-1027": (17, 50, 780, 400, 1200),
    "MDP-1038": (17, 30, 1210, 400, 1600),
    # Dual Function / Classic / Free Weight
    "MDD-1008": (7, 500, 620, 860, 1250),      # weight assisted chin/dip (chins view)
    "MDC-1011A": (12, 60, 610, 520, 1040),     # tricep dip
    "MD-LPM": (18, 720, 460, 1240, 830),       # 45 degree linear leg press
    "MD-SM": (19, 700, 100, 1240, 770),        # smith machine (SM85 / SM95 share the photo)
}

# our marketplace listing -> code
MAP: dict[str, str] = {
    "Power Leverage Line Leverage Leg Press (MDP-2001)": "MDP-2001",
    "Power Leverage Line V Squat (MDP-2007)": "MDP-2007",
    "Power Leverage Front Squat (MDP-1035)": "MDP-1035",
    "Power Leverage Line Glute Blaster / Booty Shaper (MDP-2002)": "MDP-2002",
    "Leverage Elite Booty Shaper": "MDP-2002",  # primo's own photo file is named MDP-2002-Glute-Blaster
    "Power Leverage Line Incline Calf Raise (MDP-2003)": "MDP-2003",
    "Power Leverage Line Standing Calf Raise (MDP-2010)": "MDP-2010",
    "Power Leverage Line Seated Calf (MDP-2017)": "MDP-2017",
    "Power Leverage Line Leg Extension (MDP-2009)": "MDP-2009",
    "Power Leverage Line Kneeling Leg Curl (MDP-2008)": "MDP-2008",
    "Power Leverage Line Iso Lateral Chest Press (MDP-1001)": "MDP-1001",
    "Power Leverage Line Iso Lateral Incline Chest Press (MDP-1002)": "MDP-1002",
    "Power Leverage Line Iso Lateral Wide Chest Press (MDP-1003)": "MDP-1003",
    "Power Leverage Line Iso Lateral Shoulder Press (MDP-1007)": "MDP-1007",
    "Power Leverage Line Iso Lateral Lat Pulldown (MDP-1006)": "MDP-1006",
    "Power Leverage Line Iso Lateral Low Row (MDP-1005)": "MDP-1005",
    "Power Leverage Line Iso Lateral Row (MDP-1004)": "MDP-1004",
    "Power Leverage Line Leverage Row / T-Bar Row (MDP-2012)": "MDP-2012",
    "Power Leverage Line Seated Arm Curl (MDP-1018)": "MDP-1018",
    "Power Leverage Seated Standing Shrug (MDP-1032)": "MDP-1032",
    "Power Leverage Dip/Tricep Machine (MDP-1031)": "MDP-1031",
    "Power Leverage Jammer (MDP-1027)": "MDP-1027",
    "Power Leverage Horizontal Bench Press (MDP-1038)": "MDP-1038",
    "Muscle-D Weight Assisted Chin/Dip Combo Machine with Roller Bearings (MDD-1008A)": "MDD-1008",
    "Muscle-D Tricep/Dip Machine (MDC-1011A)": "MDC-1011A",
    "45 Degree Linear Leg Press Machine": "MD-LPM",
    "Smith Machine 85″ (MD-SM85) & 93″ (MD-SM93)": "MD-SM",
}


def render(doc: pymupdf.Document, pno: int, cache: dict[int, Image.Image]) -> Image.Image:
    if pno not in cache:
        pix = doc[pno - 1].get_pixmap(dpi=DPI)
        cache[pno] = Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGB")
    return cache[pno]


def crop_all(doc: pymupdf.Document) -> dict[str, Path]:
    OUT.mkdir(parents=True, exist_ok=True)
    pages: dict[int, Image.Image] = {}
    files = {}
    for code, (pno, x0, y0, x1, y1) in PHOTOS.items():
        im = render(doc, pno, pages).crop((x0, y0, x1, y1))
        fn = OUT / f"{code}.jpg"
        im.save(fn, "JPEG", quality=92)
        files[code] = fn
    return files


def inline(path: Path) -> str:
    im = Image.open(path).convert("RGB")
    im.thumbnail((MAX_PX, MAX_PX))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=JPEG_Q, optimize=True)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def contact_sheet(files: dict[str, Path], dest: Path) -> None:
    W, cols = 170, 7
    rows = (len(files) + cols - 1) // cols
    d = pymupdf.open()
    page = d.new_page(width=W * cols, height=(W + 16) * rows)
    for i, (code, fn) in enumerate(sorted(files.items())):
        x, y = (i % cols) * W, (i // cols) * (W + 16)
        page.insert_image(pymupdf.Rect(x + 3, y + 3, x + W - 3, y + W - 3), filename=str(fn), keep_proportion=True)
        page.insert_text((x + 5, y + W + 10), code, fontsize=8)
    page.get_pixmap(dpi=72).save(str(dest))


def main() -> None:
    write = "--write" in sys.argv
    doc = pymupdf.open(PDF)
    files = crop_all(doc)
    contact_sheet(files, OUT / "_muscled_sheet.png")
    print(f"photos: {len(files)}")
    for model, code in MAP.items():
        print(f"   {code:<10} <- {model[:70]}")
    print(f"{len(MAP)} rows to re-photo")
    if not write:
        return
    con = sqlite3.connect(DB)
    (brand_id,) = con.execute("select id from brand where name=?", (BRAND,)).fetchone()
    uris = {k: inline(fn) for k, fn in files.items()}
    resolved = json.loads(RESOLVED.read_text(encoding="utf-8"))
    updated = 0
    for model, code in MAP.items():
        cur = con.execute(
            "update machine set image_url=? where brand_id=? and lower(trim(model))=lower(trim(?)) "
            "and (image_url is null or image_url like 'http%')", (uris[code], brand_id, model))
        updated += cur.rowcount
        for r in resolved:
            if r["brand"] == BRAND and r["model"] == model:
                r["image"] = f"img/muscled/{code}.jpg"
    con.commit()
    RESOLVED.write_text(json.dumps(resolved, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"updated {updated} DB rows")


if __name__ == "__main__":
    main()
