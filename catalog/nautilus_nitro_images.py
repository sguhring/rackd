"""Nautilus Nitro (S3, 2003–2009): attach the official product photos and add the
full 25-piece line.

    python catalog/nautilus_nitro_images.py            # dry run + contact sheet
    python catalog/nautilus_nitro_images.py --write    # attach + add rows

Source: docs/nautilus-nitro-galerie.html — a hand-built gallery whose links point
straight at the Wayback Machine copies of nautilus.com's own product renders
(media/products/Nautilus/Strength/LargerView/nls_NSS3*.jpg, captured 2007–2008).
The Nitro product pages themselves were never archived; the images were. The
script parses the gallery for code -> URL, downloads each photo once into
tools/cap/www/img/nautilus/nitro-<code>.jpg (Wayback rate-limits, so it sleeps
between requests), then

  1. replaces the marketplace URL on our existing "Nitro ..." listings, and
  2. adds every Nitro machine as an official row "Nitro <name> (S3xx)" under the
     source tag nautilus-nitro-wayback (idempotent), the same way the ONE / NOVA /
     EVO / XPLoad lines were added from the strength catalog.
"""
from __future__ import annotations

import base64
import io
import json
import re
import sqlite3
import sys
import time
import urllib.request
from pathlib import Path

import pymupdf
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
GALLERY = ROOT / "docs" / "nautilus-nitro-galerie.html"
RESOLVED = ROOT / "catalog" / "machines_resolved.json"
DB = ROOT / "api" / "rackd.db"
OUT = ROOT / "tools" / "cap" / "www" / "img" / "nautilus"
BRAND = "Nautilus"
SOURCE = "nautilus-nitro-wayback"
MAX_PX, JPEG_Q = 512, 82

# code -> (display name, exercise slug | None, muscle label)
LINE: dict[str, tuple[str, str | None, str]] = {
    "S3VC": ("Vertical Chest", "chest-press", "chest · triceps"),
    "S3IP": ("Incline Press", "incline-chest-press", "upper chest"),
    "S3PF": ("Pec Fly", "pec-fly", "chest"),
    "S3RDPF": ("Rear Delt / Pec Fly", "pec-fly", "chest · rear delts"),
    "S3OP": ("Overhead Press", "shoulder-press", "delts · triceps"),
    "S3LR": ("Lateral Raise", "lateral-raise", "side delts"),
    "S3MR": ("Mid Row", "seated-row", "mid-back · lats"),
    "S3CR": ("Compound Row", "seated-row", "back · biceps"),
    "S3PO": ("Pullover", "pullover", "lats"),
    "S3LATP": ("Lat Pulldown", "lat-pulldown", "lats · biceps"),
    "S3BC": ("Biceps Curl", "biceps-curl", "biceps"),
    "S3PC": ("Preacher Curl", "biceps-curl", "biceps"),
    "S3TE": ("Triceps Extension", "triceps-extension", "triceps"),
    "S3VTE": ("Ventral Triceps Extension", "triceps-extension", "triceps"),
    "S3SD": ("Seated Dip", "triceps-dip", "triceps · chest"),
    "S3GRV": ("Gravitron Weight Assisted Chin/Dip", "chin-up", "back · triceps"),
    "S3AB": ("Abdominal", "ab-crunch", "abs"),
    "S3LB": ("Low Back", "back-extension", "lower back"),
    "S3RT": ("Rotary Torso", "torso-rotation", "obliques"),
    "S3LP": ("Leg Press", "leg-press", "quads · glutes"),
    "S3LE": ("Leg Extension", "leg-extension", "quads"),
    "S3LC": ("Seated Leg Curl", "leg-curl", "hamstrings"),
    "S3LCP": ("Prone Leg Curl", "leg-curl", "hamstrings"),
    "S3AA": ("Hip Abduction/Adduction", "multi-hip", "abductors · adductors"),
    "S3SC": ("Seated Calf", "calf-raise", "calves"),
}

# our marketplace listings -> code
MAP: dict[str, str] = {
    "Nitro Abdominal Crunch": "S3AB",
    "Nitro Abductor & Adductor/Inner & Outer Thigh Combo": "S3AA",
    "Nitro Compound Row": "S3CR",
    "Nitro Gravitron Assisted Dip & Pull-up Machine": "S3GRV",
    "Nitro Lat Pulldown w / Swivel Handles": "S3LATP",
    "Nitro Leg Extension w / 330 Lb Big Boy Stack": "S3LE",
    "Nitro Leg Press w/500 lb. Stack": "S3LP",
    "Nitro Low Back Extension": "S3LB",
    "Nitro Pullover": "S3PO",
    "Nitro Seated Leg Curl": "S3LC",
    "Nitro Seated Leg Press w 500 / Lb Stack": "S3LP",
}


def gallery_urls() -> dict[str, str]:
    s = GALLERY.read_text(encoding="utf-8")
    out = {}
    for fig in re.findall(r"<figure>(.*?)</figure>", s, re.S):
        m = re.search(r'href="(https://web\.archive\.org/web/\d+im_/[^"]+)"', fig)
        c = re.search(r"<span>(S3[A-Z]+)", fig)
        if m and c:
            out[c.group(1)] = m.group(1)
    return out


def fetch_all() -> dict[str, Path]:
    OUT.mkdir(parents=True, exist_ok=True)
    files = {}
    for code, url in gallery_urls().items():
        fn = OUT / f"nitro-{code}.jpg"
        if not (fn.exists() and fn.stat().st_size > 5000):
            for attempt in range(4):
                try:
                    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (rackd)"})
                    data = urllib.request.urlopen(req, timeout=60).read()
                    Image.open(io.BytesIO(data)).convert("RGB").save(fn, "JPEG", quality=92)
                    break
                except Exception as e:  # noqa: BLE001 — Wayback throttles; retry
                    print(f"   {code}: retry {attempt} ({type(e).__name__})")
                    time.sleep(8 * (attempt + 1))
            time.sleep(2.5)
        if fn.exists():
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
        page.insert_text((x + 5, y + W + 10), f"{code} {LINE.get(code, ('?',))[0]}"[:30], fontsize=7)
    page.get_pixmap(dpi=72).save(str(dest))


def main() -> None:
    write = "--write" in sys.argv
    files = fetch_all()
    contact_sheet(files, OUT / "_nitro_sheet.png")
    missing = sorted(LINE.keys() - files.keys())
    print(f"photos: {len(files)}  missing: {missing}")
    for model, code in MAP.items():
        print(f"   {code:<7} <- {model}")
    print(f"{len(MAP)} marketplace rows to re-photo, {len(LINE)} official rows to add")
    if not write:
        return

    con = sqlite3.connect(DB)
    (brand_id,) = con.execute("select id from brand where name=?", (BRAND,)).fetchone()
    slugs = dict(con.execute("select slug, id from exercise").fetchall())
    uris = {code: inline(fn) for code, fn in files.items()}

    updated = 0
    for model, code in MAP.items():
        cur = con.execute(
            "update machine set image_url=? where brand_id=? and lower(trim(model))=lower(trim(?)) "
            "and (image_url is null or image_url like 'http%')", (uris[code], brand_id, model))
        updated += cur.rowcount
    resolved = json.loads(RESOLVED.read_text(encoding="utf-8"))
    for r in resolved:
        if r["brand"] == BRAND and r["model"] in MAP:
            r["image"] = f"img/nautilus/nitro-{MAP[r['model']]}.jpg"
    RESOLVED.write_text(json.dumps(resolved, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    old = [i for (i,) in con.execute("select id from machine where source=?", (SOURCE,))]
    if old:
        q = ",".join("?" * len(old))
        con.execute(f"delete from gymmachine where machine_id in ({q})", old)
        con.execute(f"delete from machine where id in ({q})", old)
    added = 0
    for code, (name, slug, muscle) in LINE.items():
        if code not in uris:
            continue
        con.execute(
            "insert into machine (brand_id, model, machine_type, exercise_id, muscle_label, image_url, source) "
            "values (?,?,?,?,?,?,?)",
            (brand_id, f"Nitro {name} ({code})", "selectorized", slugs.get(slug) if slug else None,
             muscle, uris[code], SOURCE))
        added += 1
    con.commit()
    print(f"updated {updated} marketplace rows, added {added} Nitro rows (replaced {len(old)})")


if __name__ == "__main__":
    main()
