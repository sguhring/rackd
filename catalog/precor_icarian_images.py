"""Precor Icarian: attach the official product renders recovered from the Wayback
Machine's copy of precor.com (July 2011, the last site that still listed the
Icarian line by product code).

    python catalog/precor_icarian_images.py            # dry run + contact sheet
    python catalog/precor_icarian_images.py --write    # attach

Icarian Fitness (Sun Valley, CA) never had an archived website of its own —
icarianfitness.com was a parked page in 2000 and icarian.com belonged to a
software company. After Precor bought the brand the products lived on precor.com
under /products/en/commercial/strength/icarian-strength/, and the Magento image
cache behind those pages is archived. Most renders are 165 px, three are 440–470 px
(the "hero" variants). Small, but they are the real machines on white; run
api/upscale_db.py afterwards if the app needs bigger tiles.

Images are downloaded once into tools/cap/www/img/precor/icarian-<key>.png and
inlined into api/rackd.db for the marketplace rows in MAP. Machines with no
archived render (405 pec deck, 602 leg sled, 607 standing leg curl, 618 glute
isolator, 625 lunge, lateral raise, Flite 546) stay as they are.
"""
from __future__ import annotations

import base64
import io
import json
import sqlite3
import sys
import time
import urllib.request
from pathlib import Path

import pymupdf
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
RESOLVED = ROOT / "catalog" / "machines_resolved.json"
DB = ROOT / "api" / "rackd.db"
OUT = ROOT / "tools" / "cap" / "www" / "img" / "precor"
MAX_PX, JPEG_Q = 512, 82
CACHE = "http://www.precor.com/products/media/catalog/product/cache/1/image/9df78eab33525d08d6e5fb8d27136e95/"

# key -> (wayback timestamp, path under the Magento cache)
PHOTOS: dict[str, tuple[str, str]] = {
    "202": ("20110701170127", "2/0/202_seated_preacher_curl_copy_165x.png"),
    "302": ("20110701171851", "3/0/302_longpull_472w_hero.png"),
    "304": ("20110701173029", "3/0/304_pulldown_438wx515h_hero.jpg"),
    "311": ("20110701152923", "3/1/311_incline-lever-row_0small.png"),
    "312": ("20110701165649", "3/1/312_0.png"),
    "320": ("20110701172716", "3/2/320_dip_chin_assist_472w_hero.jpg"),
    "407b": ("20110701154525", "4/0/407b_0small1.png"),
    "540": ("20110701153346", "5/4/540_bench_press_copy_165small.png"),
    "541": ("20110701152218", "5/4/541_0small.png"),
    "550": ("20110701151948", "5/5/550_shoulder-press_0small.png"),
    "601": ("20110701153239", "6/0/601_angled_leg_press_copy_165.png"),
    "603": ("20110701152611", "6/0/603_hackslide_copy_165.png"),
    "616": ("20110701153111", "6/1/616_seated-calf_1small.png"),
    "624": ("20110701152116", "6/2/624_0.png"),
    "702": ("20110701165748", "7/0/702_vertical-knee-up_dip_0.png"),
    "802": ("20110701152403", "8/0/802_0smithsmall.png"),
    "bicep": ("20110701132009", "b/i/bicep_curl_copy_165x165small.png"),
    "backext": ("20110701164139", "b/a/back_extension_copy_165x165_1.png"),
    "legext": ("20110701122444", "l/e/leg_extension_copy_165x165small.png"),
    "tricep": ("20110701131653", "t/r/tricep_extension_copy_165x165small.png"),
    "cline-legpress": ("20110701174420", "c/-/c-line_leg-press_product-shot_front-w_headrest-lr_0small1.png"),
}

# (brand, model) -> key
MAP: dict[tuple[str, str], str] = {
    ("Precor", "Icarian 601 45 Degree Plate Loaded Linear Leg Press"): "601",
    ("Precor", "Icarian 601 45 Degree Plate Loaded Linear Leg Press Extra Loading Horn"): "601",
    ("Precor", "Icarian Angled 45 Degree Plate Loaded Leg Press"): "601",
    ("Precor", "Icarian 320 Assisted Dip & Pull-up Machine"): "320",
    ("Precor", "Icarian Assisted Dip & Pull-up Machine"): "320",
    ("Precor", "Icarian Chin Dip Assist"): "320",
    ("Precor", "Icarian 45 Degree Back Extension"): "312",
    ("Precor", "Icarian Leg Extension 605"): "legext",
    ("Precor", "Icarian Super Squat 624"): "624",
    ("Precor", "Icarian Linear Hack Squat"): "603",
    ("Precor", "Icarian Plate Loaded Seated Calf Raise"): "616",
    ("Precor", "Icarian Seated Calf Raise"): "616",
    ("Precor", "Icarian Flite FLT 550 ISO Lateral Plate Loaded Shoulder Press - RARE"): "550",
    ("Precor", "Icarian Chest Supported T Bar Row"): "311",
    ("Precor", "Icarian Adjustable Cable Crossover"): "407b",
    ("Precor", "Icarian Dual Adjustable Pulley Cable Crossover w/Multi Grip Pull-up"): "407b",
    ("Precor", "Icarian Seated Preacher Curl"): "202",
    ("Precor", "Icarian CW-702 VKR Vertical Knee Raise"): "702",
    ("Precor", "Dip & Leg Raise - Chest Abs Triceps & Obliques"): "702",
    ("Precor", "Icarian Smith Machine"): "802",
    ("Precor", "Icarian Platinum Linear Counter Balanced Smith Machine"): "802",
    ("Precor", "Icarian Lat Pulldown"): "304",
    ("Precor", "Icarian Lat Pulldown Machine"): "304",
    ("Precor", "Icarian Tricep Extension"): "tricep",
    ("Precor", "Bicep 205 - Flat Top - Rare"): "bicep",
    ("Precor", "Icarian 205 Flat Bicep Curl"): "bicep",
    ("Precor", "Experience C Line Leg Press"): "cline-legpress",
    ("Icarian", "210 Flat Top Tricep Extension - Rare - Insane Pumps"): "tricep",
    ("Icarian", "Chest Supported Multi Grip T Bar Row - First Generation RARE"): "311",
    ("Icarian", "Hyper Extension Roman Chair - Abs Back Glutes Hips Obliques - TOTAL CORE UNIT - & Rare"): "312",
}


def fetch_all() -> dict[str, Path]:
    OUT.mkdir(parents=True, exist_ok=True)
    files = {}
    for key, (ts, path) in PHOTOS.items():
        fn = OUT / f"icarian-{key}.png"
        if not fn.exists():
            url = f"http://web.archive.org/web/{ts}id_/{CACHE}{path}"
            for attempt in range(4):
                try:
                    data = urllib.request.urlopen(
                        urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (rackd)"}), timeout=60).read()
                    im = Image.open(io.BytesIO(data)).convert("RGBA")
                    bg = Image.new("RGB", im.size, (255, 255, 255))
                    bg.paste(im, mask=im.split()[-1])
                    bg.save(fn, "PNG")
                    break
                except Exception as e:  # noqa: BLE001 — Wayback throttles; retry
                    print(f"   {key}: retry {attempt} ({type(e).__name__})")
                    time.sleep(10 * (attempt + 1))
            time.sleep(3)
        if fn.exists():
            files[key] = fn
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
    for i, (key, fn) in enumerate(sorted(files.items())):
        x, y = (i % cols) * W, (i // cols) * (W + 16)
        page.insert_image(pymupdf.Rect(x + 3, y + 3, x + W - 3, y + W - 3), filename=str(fn), keep_proportion=True)
        page.insert_text((x + 5, y + W + 10), key, fontsize=8)
    page.get_pixmap(dpi=72).save(str(dest))


def main() -> None:
    write = "--write" in sys.argv
    files = fetch_all()
    contact_sheet(files, OUT / "_icarian_sheet.png")
    print(f"photos: {len(files)}  missing: {sorted(PHOTOS.keys() - files.keys())}")
    for (brand, model), key in MAP.items():
        print(f"   {key:<15} <- {brand[:7]:7} {model[:60]}")
    print(f"{len(MAP)} rows to re-photo")
    if not write:
        return
    con = sqlite3.connect(DB)
    brands = dict(con.execute("select name, id from brand").fetchall())
    uris = {k: inline(fn) for k, fn in files.items()}
    resolved = json.loads(RESOLVED.read_text(encoding="utf-8"))
    updated = 0
    for (brand, model), key in MAP.items():
        if key not in uris:
            continue
        cur = con.execute(
            "update machine set image_url=? where brand_id=? and lower(trim(model))=lower(trim(?)) "
            "and (image_url is null or image_url like 'http%')", (uris[key], brands[brand], model))
        updated += cur.rowcount
        for r in resolved:
            if r["brand"] == brand and r["model"] == model:
                r["image"] = f"img/precor/icarian-{key}.png"
    con.commit()
    RESOLVED.write_text(json.dumps(resolved, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"updated {updated} DB rows")


if __name__ == "__main__":
    main()
