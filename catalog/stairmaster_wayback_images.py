"""StairMaster Arcuate / Linear (Pacific Fitness design, 1997–2002): attach the
official product renders recovered from the Wayback Machine's copy of
stairmaster.com and add the Linear pieces the catalog did not have.

    python catalog/stairmaster_wayback_images.py            # dry run + contact sheet
    python catalog/stairmaster_wayback_images.py --write    # attach + add rows

docs/STAIRMASTER_ARCUATE.md recorded the line as having no digital footprint and
left one lead unchecked: the Wayback Machine, unreachable at the time. It has
the 2001 site — commercial/products/strength/arcuate/ and /linear/ — with a
render per machine under /Images/Product/. Eleven survive (300 px, or the 200 px
"_sm" thumbnail where the large one was never captured). The Arcuate Seated Row
page is archived but its image is not: no capture of arcuateseatedrowmachine*
exists under either host, so that row keeps its no-photo status.

Images are downloaded once into tools/cap/www/img/stairmaster/<key>.jpg and
inlined into api/rackd.db. Existing StairMaster rows are re-photoed even when
they already carry a picture, because what they carry is an auction photo and
this is the manufacturer's own. The four Linear machines missing from the
catalog are added as official rows under source stairmaster-wayback (idempotent).
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
OUT = ROOT / "tools" / "cap" / "www" / "img" / "stairmaster"
BRAND = "StairMaster"
SOURCE = "stairmaster-wayback"
MAX_PX, JPEG_Q = 512, 82
BASE = "http://stairmaster.com/Images/Product/"

# key -> (wayback timestamp, file under /Images/Product/); timestamp None = local file
# (the Seated Row render was never archived, so it takes the user's own gym photo)
PHOTOS: dict[str, tuple[str | None, str]] = {
    "arcuate-seated-row": (None, "catalog/stairmaster_images/arcuate-seated-row-user.png"),
    "arcuate-bicep-curl": ("20020629", "arcuatebicepcurl.jpg"),
    "arcuate-lat-pull": ("20010902", "arcuatelatpulldown.jpg"),
    "arcuate-chest-press": ("20010902", "arcuateseatedchestpress.jpg"),
    "arcuate-incline-press": ("20011128", "arcuateseatedinclinepress.jpg"),
    "arcuate-leg-press": ("20010902", "arcuateseatedlegpress_sm.jpg"),
    "arcuate-shoulder-press": ("20010902", "arcuateseatedshoulderpress_sm.jpg"),
    "arcuate-tricep": ("20010902", "arcuateseatedtricep.jpg"),
    "linear-ab-torso": ("20010902", "linearlineabdominaltorso.jpg"),
    "linear-fly-rear-deltoid": ("20010902", "linearlineflyreardeltoid_sm.jpg"),
    "linear-inner-thigh": ("20010902", "linearlineinnerthigh.jpg"),
    "linear-leg-extension": ("20010902", "linearlinelegextension.jpg"),
    "linear-lower-back": ("20010902", "linearlinelowerback.jpg"),
    "linear-outer-thigh": ("20010902", "linearlineouterthigh_sm.jpg"),
    "linear-seated-leg-curl": ("20010902", "linearlineseatedlegcurl_sm.jpg"),
    "linear-total-glute": ("20010902", "linearlinetotalglute_sm.jpg"),
}

# existing catalog rows -> key
MAP: dict[str, str] = {
    "Arcuate Bicep Curl": "arcuate-bicep-curl",
    "Arcuate Lat Pull": "arcuate-lat-pull",
    "Arcuate Seated Row": "arcuate-seated-row",
    "Arcuate Chest Press": "arcuate-chest-press",
    "Arcuate Incline Press": "arcuate-incline-press",
    "Arcuate Leg Press": "arcuate-leg-press",
    "Arcuate Shoulder Press": "arcuate-shoulder-press",
    "Arcuate Tricep Press": "arcuate-tricep",
    "Linear Ab Torso": "linear-ab-torso",
    "Linear Fly / Deltoid": "linear-fly-rear-deltoid",
    "Linear Inner Thigh": "linear-inner-thigh",
    "Linear Leg Extension": "linear-leg-extension",
}

# the catalog rows were merged from machines_resolved.json without an exercise link, so the
# app's movement -> brand -> model browse never listed them; set it while we are here.
EXERCISE: dict[str, str] = {
    "Arcuate Bicep Curl": "biceps-curl", "Arcuate Lat Pull": "lat-pulldown",
    "Arcuate Chest Press": "chest-press", "Arcuate Incline Press": "incline-chest-press",
    "Arcuate Leg Press": "leg-press", "Arcuate Seated Row": "seated-row",
    "Arcuate Shoulder Press": "shoulder-press", "Arcuate Tricep Press": "triceps-extension",
    "Linear Ab Torso": "ab-crunch", "Linear Fly / Deltoid": "rear-delt",
    "Linear Inner Thigh": "hip-adduction", "Linear Leg Extension": "leg-extension",
}

# new official rows: model -> (key, exercise slug, muscle label)
NEW: dict[str, tuple[str, str, str]] = {
    "Linear Lower Back": ("linear-lower-back", "back-extension", "lower back"),
    "Linear Outer Thigh": ("linear-outer-thigh", "hip-abduction", "abductors · glutes"),
    "Linear Seated Leg Curl": ("linear-seated-leg-curl", "leg-curl", "hamstrings"),
    "Linear Total Glute": ("linear-total-glute", "glute", "glutes · hamstrings"),
}


def fetch_all() -> dict[str, Path]:
    OUT.mkdir(parents=True, exist_ok=True)
    files = {}
    for key, (ts, name) in PHOTOS.items():
        fn = OUT / f"{key}.jpg"
        if ts is None:
            Image.open(ROOT / name).convert("RGB").save(fn, "JPEG", quality=92)
        elif not (fn.exists() and fn.stat().st_size > 3000):
            url = f"http://web.archive.org/web/{ts}000000id_/{BASE}{name}"
            for attempt in range(4):
                try:
                    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (rackd)"})
                    data = urllib.request.urlopen(req, timeout=60).read()
                    Image.open(io.BytesIO(data)).convert("RGB").save(fn, "JPEG", quality=92)
                    break
                except Exception as e:  # noqa: BLE001 — Wayback throttles; retry
                    print(f"   {key}: retry {attempt} ({type(e).__name__})")
                    time.sleep(8 * (attempt + 1))
            time.sleep(2)
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
    W, cols = 170, 5
    rows = (len(files) + cols - 1) // cols
    d = pymupdf.open()
    page = d.new_page(width=W * cols, height=(W + 16) * rows)
    for i, (key, fn) in enumerate(sorted(files.items())):
        x, y = (i % cols) * W, (i // cols) * (W + 16)
        page.insert_image(pymupdf.Rect(x + 3, y + 3, x + W - 3, y + W - 3), filename=str(fn), keep_proportion=True)
        page.insert_text((x + 5, y + W + 10), key, fontsize=7)
    page.get_pixmap(dpi=72).save(str(dest))


def main() -> None:
    write = "--write" in sys.argv
    files = fetch_all()
    contact_sheet(files, OUT / "_stairmaster_sheet.png")
    print(f"photos: {len(files)}  missing: {sorted(PHOTOS.keys() - files.keys())}")
    for model, key in MAP.items():
        print(f"   {key:<24} <- {model}")
    print(f"{len(MAP)} rows to re-photo, {len(NEW)} official rows to add")
    if not write:
        return

    con = sqlite3.connect(DB)
    (brand_id,) = con.execute("select id from brand where name=?", (BRAND,)).fetchone()
    slugs = dict(con.execute("select slug, id from exercise").fetchall())
    uris = {k: inline(fn) for k, fn in files.items()}

    updated = 0
    for model, key in MAP.items():
        if key not in uris:
            continue
        cur = con.execute("update machine set image_url=? where brand_id=? and lower(trim(model))=lower(trim(?))",
                          (uris[key], brand_id, model))
        updated += cur.rowcount
    linked = 0
    for model, slug in EXERCISE.items():
        linked += con.execute(
            "update machine set exercise_id=? where brand_id=? and lower(trim(model))=lower(trim(?)) and exercise_id is null",
            (slugs[slug], brand_id, model)).rowcount
    resolved = json.loads(RESOLVED.read_text(encoding="utf-8"))
    for r in resolved:
        if r["brand"] == BRAND and r["model"] in MAP:
            r["image"] = f"img/stairmaster/{MAP[r['model']]}.jpg"
    RESOLVED.write_text(json.dumps(resolved, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    old = [i for (i,) in con.execute("select id from machine where source=?", (SOURCE,))]
    if old:
        q = ",".join("?" * len(old))
        con.execute(f"delete from gymmachine where machine_id in ({q})", old)
        con.execute(f"delete from machine where id in ({q})", old)
    added = 0
    for model, (key, slug, muscle) in NEW.items():
        if key not in uris:
            continue
        con.execute(
            "insert into machine (brand_id, model, machine_type, exercise_id, muscle_label, image_url, source) "
            "values (?,?,?,?,?,?,?)", (brand_id, model, "selectorized", slugs[slug], muscle, uris[key], SOURCE))
        added += 1
    con.commit()
    print(f"updated {updated} rows, linked {linked} to exercises, added {added} Linear rows (replaced {len(old)})")


if __name__ == "__main__":
    main()
