"""Export the machine catalog the app serves into the phone app's bundle, so the
Capacitor build carries the whole catalog and every photo offline.

    python api/export_bundle.py            # writes tools/cap/www/catalog/

Writes
  tools/cap/www/catalog/catalog.json   exercises + machines (API shapes, minus images)
  tools/cap/www/catalog/img/<id>.jpg   one thumbnail per machine that has an inline photo

The app (tools/cap/www/index.html, catalogGet) answers /catalog/exercises, /brands,
/machines and /search from this file when it is present and only falls back to the
hosted API when it is not — so a phone build never depends on the Azure backend
being current. Marketplace photos (http URLs) are kept as URLs; the app already maps
those to the pre-rendered cutouts in img/<hash>.png.

Photos are re-encoded to THUMB_PX so the bundle stays small; the app never shows a
machine photo larger than a list thumbnail.
"""
from __future__ import annotations

import base64
import io
import json
import sqlite3
import time
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "api" / "rackd.db"
OUT = ROOT / "tools" / "cap" / "www" / "catalog"
IMG = OUT / "img"
THUMB_PX, JPEG_Q = 420, 80


def thumb(data_uri: str) -> bytes:
    raw = base64.b64decode(data_uri.split(",", 1)[1])
    im = Image.open(io.BytesIO(raw)).convert("RGB")
    im.thumbnail((THUMB_PX, THUMB_PX))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=JPEG_Q, optimize=True)
    return buf.getvalue()


def main() -> None:
    IMG.mkdir(parents=True, exist_ok=True)
    for old in IMG.glob("*.jpg"):
        old.unlink()
    con = sqlite3.connect(DB)
    exercises = [
        {"slug": s, "name": n, "muscle_group": g}
        for s, n, g in con.execute("select slug, name, muscle_group from exercise order by name")
    ]
    machines = []
    photos = 0
    total = 0
    rows = con.execute(
        "select m.id, b.name, m.model, m.machine_type, m.muscle_label, e.slug, m.image_url "
        "from machine m join brand b on b.id=m.brand_id left join exercise e on e.id=m.exercise_id "
        "order by b.name, m.model").fetchall()
    for mid, brand, model, mtype, muscle, slug, image in rows:
        img = None
        if image and image.startswith("data:"):
            data = thumb(image)
            (IMG / f"{mid}.jpg").write_bytes(data)
            img = f"catalog/img/{mid}.jpg"
            photos += 1
            total += len(data)
        elif image:
            img = image
        machines.append({"id": mid, "brand": brand, "model": model, "machine_type": mtype,
                         "muscle_label": muscle, "exercise": slug, "img": img})
    bundle = {"version": int(time.time()), "exercises": exercises, "machines": machines}
    (OUT / "catalog.json").write_text(json.dumps(bundle, ensure_ascii=False, separators=(",", ":")),
                                      encoding="utf-8")
    print(f"{len(machines)} machines, {len(exercises)} exercises, {photos} photos "
          f"({total / 1048576:.1f} MB), catalog.json {(OUT / 'catalog.json').stat().st_size // 1024} KB")


if __name__ == "__main__":
    main()
