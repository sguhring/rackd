"""Attach Cybex Eagle and VR3 product photos from the official line brochures.

    python catalog/cybex_lines_images.py            # dry run: extract + contact sheet
    python catalog/cybex_lines_images.py --write    # attach to catalog json + DB

Sources (both recovered from cybexintl.com, see docs/DATA_SOURCES.md):
  docs/cybex-eagle-brochure.pdf       Eagle line (11xxx), embedded studio photos,
                                      spread pages with the product heading in
                                      each quadrant -> pinned by (page, xref).
  docs/cybex-vr3-brochure-2007.pdf    VR3 line (12xxx), 23 products. A page scan
                                      (594x792 px per page, no text layer): each
                                      product page has one machine top and one
                                      bottom, photo on the right of its text. The
                                      photo is cut out by finding the widest run
                                      of dark columns in that half-page.

Neither brochure carries Calf Raise / Glute for Eagle, so those stay as they are.
Our rows are marketplace listings; MAP joins each model string to a product.
Rows that already carry an inlined photo are not touched.
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
from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parent.parent
RESOLVED = ROOT / "catalog" / "machines_resolved.json"
DB = ROOT / "api" / "rackd.db"
OUT = ROOT / "tools" / "cap" / "www" / "img" / "cybex"
BRAND = "Cybex"
MAX_PX, JPEG_Q = 512, 82

EAGLE_PDF = ROOT / "docs" / "cybex-eagle-brochure.pdf"
EAGLE_PHOTOS: dict[str, tuple[int, int]] = {          # product -> (page, xref)
    "chest press": (5, 46),
    "overhead press": (6, 61), "incline press": (6, 63), "incline pull": (6, 67), "lat pulldown": (6, 65),
    "row": (7, 84), "lateral raise": (7, 80), "fly/rear delt": (7, 86), "torso rotation": (7, 82),
    "abdominal": (8, 102), "back extension": (8, 100), "arm extension": (8, 104), "arm curl": (8, 98),
    "leg press": (9, 114),
    "leg extension": (10, 131), "seated leg curl": (10, 133), "prone leg curl": (10, 135),
    "hip abduction/adduction": (10, 129),
}
EAGLE_MAP: dict[str, str] = {
    "Eagle Ab Abdominal Crunch 11090": "abdominal",
    "Eagle Abductor & Adductor Combo Inner/Outer Thigh": "hip abduction/adduction",
    "Eagle Arm / Bicep Curl 11070": "arm curl",
    "Eagle Arm Tricep Extension 11080": "arm extension",
    "Eagle Back Extension 11101": "back extension",
    "Eagle Chest Press 11000": "chest press",
    "Eagle Converging Overhead Shoulder Press": "overhead press",
    "Eagle Hip Abduction/Adduction 11181": "hip abduction/adduction",
    "Eagle Incline Chest Press w / 305 Lb Stack": "incline press",
    "Eagle Incline Pull - Rare": "incline pull",
    "Eagle Incline Pull 11020": "incline pull",
    "Eagle Lat Pulldown 11130": "lat pulldown",
    "Eagle Lateral Raise 11160": "lateral raise",
    "Eagle Leg Extension 11050 w/ROM": "leg extension",
    "Eagle Leg Extension w / 305 Lb Stack": "leg extension",
    "Eagle Leg Press 11040": "leg press",
    "Eagle Overhead Press 11010": "overhead press",
    "Eagle Overhead Tricep Extension - Super Pumps": "arm extension",
    "Eagle Pec Fly/Rear Delt": "fly/rear delt",
    "Eagle Platinum Seated Leg Press w/500 lb. Stack": "leg press",
    "Eagle Prone Leg Curl 11141 w/RLD": "prone leg curl",
    "Eagle Row 11030": "row",
    "Eagle Seated Leg Curl 11061": "seated leg curl",
    "Eagle Torso Rotation 11190": "torso rotation",
    "Eagle Torso Rotation w/305 lb. Stack - Clean": "torso rotation",
    "Eagle Tricep Extension": "arm extension",
}

VR3_PDF = ROOT / "docs" / "cybex-vr3-brochure-2007.pdf"
VR3_PAGES: dict[int, tuple[str, str | None]] = {       # page -> (top product, bottom product)
    9: ("leg extension", "seated leg curl"), 10: ("leg press", "prone leg curl"),
    11: ("hip abduction", "hip adduction"), 13: ("glute", "calf raise"),
    14: ("arm extension", "arm curl"), 15: ("chest press", "overhead press"),
    17: ("pulldown", "lat pull"), 18: ("abdominal", "back extension"),
    19: ("tricep press", "torso rotation"), 20: ("row", "dip/chin assist"),
    21: ("lateral raise", "fly/rear delt"), 22: ("cable column", None),
}
VR3_MAP: dict[str, str] = {
    "VR3 Abdominal": "abdominal",
    "VR3 Platinum Abdominal Crunch": "abdominal",
    "VR3 Arm Tricep Extension 12080": "arm extension",
    "VR3 Tricep Extension": "arm extension",
    "VR3 Back Extension": "back extension",
    "VR3 Low Back Extension - Total Core Machine": "back extension",
    "VR3 Bicep / Arm Curl 12070": "arm curl",
    "VR3 Platinum Bicep Curl": "arm curl",
    "VR3 Cable Column": "cable column",
    "VR3 Chest Press": "chest press",
    "VR3 Platinum Chest Press": "chest press",
    "VR3 Dip/Chin Assist": "dip/chin assist",
    "VR3 Glute": "glute",
    "VR3 Platinum Glute Kickback": "glute",
    "VR3 Hip Abduction / Outer Thigh": "hip abduction",
    "VR3 Hip Adduction / Inner Thigh": "hip adduction",
    "VR3 Lat Pull": "lat pull",
    "VR3 Lateral Raise": "lateral raise",
    "VR3 Platinum Seated Lateral Raise": "lateral raise",
    "VR3 Leg Extension": "leg extension",
    "VR3 Leg Press": "leg press",
    "VR3 Platinum Seated Leg Press w/500 lb. Stack": "leg press",
    "VR3 Seated Leg Press Squat Press": "leg press",
    "VR3 Overhead Shoulder Press": "overhead press",
    "VR3 Pec Fly/Rear Delt": "fly/rear delt",
    "VR3 Pec Fly & Rear Delt Combo - Platinum": "fly/rear delt",
    "VR3 Pulldown": "pulldown",
    "VR3 Platinum Pulldown": "pulldown",
    "VR3 Prone Leg Curl": "prone leg curl",
    "VR3 Row": "row",
    "VR3 Platinum Seated Row": "row",
    "VR3 Seated Leg Curl": "seated leg curl",
    "VR3 Standing Calf": "calf raise",
    "VR3 Platinum Standing Calf Raise": "calf raise",
    "VR3 Torso Rotation": "torso rotation",
    "VR3 Platinum Rotary Torso": "torso rotation",
    "VR3 Tricep Press Seated Dip": "tricep press",
    "VR3 Seated Dip Chest & Tricep Press w/Swivel Handles": "tricep press",
}


def slug(prefix: str, product: str) -> str:
    return f"{prefix}-" + re.sub(r"[^a-z0-9]+", "-", product.lower()).strip("-")


# ── Eagle: embedded photos ────────────────────────────────────────────────────

def eagle_photo(doc: pymupdf.Document, xref: int) -> Image.Image:
    pix = pymupdf.Pixmap(doc, xref)
    if pix.colorspace and pix.colorspace.n > 3:
        pix = pymupdf.Pixmap(pymupdf.csRGB, pix)
    smask = doc.extract_image(xref).get("smask")
    if smask:
        pix = pymupdf.Pixmap(pix, pymupdf.Pixmap(doc, smask))
    im = Image.open(io.BytesIO(pix.tobytes("png")))
    if im.mode == "RGBA":
        bg = Image.new("RGB", im.size, (255, 255, 255))
        bg.paste(im, mask=im.split()[-1])
        return bg
    return im.convert("RGB")


# ── VR3: cut-outs from the page scan ──────────────────────────────────────────

def vr3_page(doc: pymupdf.Document, pno: int) -> Image.Image:
    xref = doc[pno - 1].get_images(full=True)[0][0]
    return Image.open(io.BytesIO(doc.extract_image(xref)["image"])).convert("RGB")


def cut_machine(region: Image.Image, min_col_frac: float = 0.10) -> Image.Image:
    """Crop to the widest run of columns that carry real ink (the machine); the
    bullet text to its left is thin and never reaches the threshold."""
    g = ImageOps.grayscale(region)
    w, h = g.size
    px = g.load()
    col = [sum(1 for y in range(h) if px[x, y] < 225) for x in range(w)]
    dark = [c >= h * min_col_frac for c in col]
    runs, start = [], None
    for x, d in enumerate(dark + [False]):
        if d and start is None:
            start = x
        elif not d and start is not None:
            runs.append((start, x))
            start = None
    if not runs:
        return region
    x0, x1 = max(runs, key=lambda r: r[1] - r[0])
    band = g.crop((x0, 0, x1, h))
    bb = band.point(lambda v: 255 if v < 225 else 0).getbbox()
    y0, y1 = (bb[1], bb[3]) if bb else (0, h)
    pad = max(6, w // 40)
    return region.crop((max(0, x0 - pad), max(0, y0 - pad), min(w, x1 + pad), min(h, y1 + pad)))


def vr3_photo(doc: pymupdf.Document, pno: int, position: str) -> Image.Image:
    im = vr3_page(doc, pno)
    W, H = im.size
    if pno == 22:                                       # cable column: big photo bottom-left
        region = im.crop((0, int(H * 0.28), int(W * 0.58), int(H * 0.98)))
    elif position == "top":
        region = im.crop((int(W * 0.42), int(H * 0.03), W, int(H * 0.49)))
    else:
        region = im.crop((int(W * 0.42), int(H * 0.51), W, int(H * 0.97)))
    return cut_machine(region)


# ── shared ────────────────────────────────────────────────────────────────────

def inline(path: Path) -> str:
    im = Image.open(path)
    if im.mode not in ("RGB", "L"):
        im = im.convert("RGB")
    im.thumbnail((MAX_PX, MAX_PX))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=JPEG_Q, optimize=True)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def contact_sheet(files: list[tuple[str, Path]], dest: Path) -> None:
    W, cols = 170, 8
    rows = (len(files) + cols - 1) // cols
    doc = pymupdf.open()
    page = doc.new_page(width=W * cols, height=(W + 16) * rows)
    for i, (label, fn) in enumerate(files):
        x, y = (i % cols) * W, (i // cols) * (W + 16)
        page.insert_image(pymupdf.Rect(x + 3, y + 3, x + W - 3, y + W - 3), filename=str(fn), keep_proportion=True)
        page.insert_text((x + 5, y + W + 10), label, fontsize=8)
    page.get_pixmap(dpi=72).save(str(dest))


def main() -> None:
    write = "--write" in sys.argv
    OUT.mkdir(parents=True, exist_ok=True)
    resolved = json.loads(RESOLVED.read_text(encoding="utf-8"))
    by_model = {r["model"].strip().lower(): r for r in resolved if r["brand"] == BRAND}

    # extract every photo
    files: dict[str, Path] = {}                         # image key -> file
    eagle = pymupdf.open(EAGLE_PDF)
    for product, (pno, xref) in EAGLE_PHOTOS.items():
        key = slug("eagle", product)
        fn = OUT / f"{key}.jpg"
        eagle_photo(eagle, xref).save(fn, "JPEG", quality=90)
        files[key] = fn
    vr3 = pymupdf.open(VR3_PDF)
    for pno, (top, bottom) in VR3_PAGES.items():
        for product, pos in ((top, "top"), (bottom, "bottom")):
            if not product:
                continue
            key = slug("vr3", product)
            fn = OUT / f"{key}.jpg"
            vr3_photo(vr3, pno, pos).save(fn, "JPEG", quality=90)
            files[key] = fn
    contact_sheet(sorted(files.items()), OUT / "_cybex_lines_sheet.png")
    print(f"extracted {len(files)} photos -> {OUT.relative_to(ROOT)} (+ _cybex_lines_sheet.png)\n")

    hits: list[tuple[dict, str]] = []
    for prefix, mapping in (("eagle", EAGLE_MAP), ("vr3", VR3_MAP)):
        for model, product in mapping.items():
            r = by_model.get(model.strip().lower())
            key = slug(prefix, product)
            if r is None:
                print(f"   not in catalog json: {model}")
            elif key not in files:
                print(f"   no photo for {key}: {model}")
            else:
                hits.append((r, key))
                print(f"   {key:<32} <- {r['model'][:70]}")
    print(f"\n{len(hits)} rows matched to {len({k for _, k in hits})} photos")
    if not write:
        print("\ndry run — pass --write to attach")
        return

    for r, key in hits:
        r["image"] = f"img/cybex/{key}.jpg"
    RESOLVED.write_text(json.dumps(resolved, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    con = sqlite3.connect(DB)
    (brand_id,) = con.execute("select id from brand where name=?", (BRAND,)).fetchone()
    uris = {key: inline(files[key]) for _, key in hits}
    updated = 0
    for r, key in hits:
        cur = con.execute(
            "update machine set image_url=? where brand_id=? and lower(trim(model))=lower(trim(?)) "
            "and (image_url is null or image_url like 'http%')",
            (uris[key], brand_id, r["model"]))
        updated += cur.rowcount
    con.commit()
    print(f"attached {len(hits)} catalog rows, updated {updated} DB rows")


if __name__ == "__main__":
    main()
