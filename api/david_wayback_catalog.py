"""Add DAVID's older strength lines (C-Line, Future, Modular, Basic) from the archived david.fi.

    python api/david_wayback_catalog.py            # dry run: list + contact sheet
    python api/david_wayback_catalog.py --write    # add rows (idempotent per source)

Source: the Wayback Machine copy of david.fi (David Sports Ltd., 2009-2010). The line pages
(/c-line/, /future-line/, /modular-line/, /basic-line/) list model code + English name, and
every model has an official studio photo at /products/product_images/<code>.jpg (420 px).
The same C-Line appears unchanged in the 2004 Finnish catalog (tuotteet.php?group=4); it was
gone from the 2013 site. Names below are copied from the 2010 English pages.

Racks, benches, stands and the Prevention Line benches are skipped - only machines a user
would log a set against. The current medical G-series lives in api/david_catalog.py.
"""
from __future__ import annotations

import base64
import io
import sqlite3
import sys
import time
import urllib.request
from pathlib import Path

import pymupdf
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "api" / "rackd.db"
OUT = ROOT / "tools" / "cap" / "www" / "img" / "david"
WAYBACK = "https://web.archive.org/web/2010id_/http://www.david.fi/products/product_images/{}.jpg"
BRAND, ABBR, SOURCE = "David", "DV", "david-fi-wayback"
MAX_PX, JPEG_Q = 900, 86
UA = {"User-Agent": "Mozilla/5.0 (rackd catalog)"}

PL, SEL, CABLE, SMITH = "plate-loaded", "selectorized", "cable", "smith/rack"

# (code, name, machine_type, exercise slug or None)
MODELS: list[tuple[str, str, str, str | None]] = [
    # C-Line - plate-loaded
    ("C12", "Leg Extension", PL, "leg-extension"),
    ("C14", "Leg Press", PL, "leg-press"),
    ("C15", "Seated Curl", PL, "leg-curl"),
    ("C15b", "Duo-seated Leg Curl", PL, "leg-curl"),
    ("C20", "Back Extension", PL, "back-extension"),
    ("C22", "Front Pulldown", PL, "lat-pulldown"),
    ("C23", "Seated Row", PL, "seated-row"),
    ("C24", "Lat Pulldown", PL, "lat-pulldown"),
    ("C30", "Bench Press", PL, "chest-press"),
    ("C31", "Incline Press", PL, "incline-chest-press"),
    ("C32", "Decline Press", PL, "chest-press"),
    ("C40", "Shoulder Press", PL, "shoulder-press"),
    ("C41", "Front Press", PL, "shoulder-press"),
    ("C45", "Lateral Raise", PL, "lateral-raise"),
    ("C46", "Rear Deltoid", PL, "rear-delt"),
    ("C70", "Arm Curl", PL, "biceps-curl"),
    ("C80", "Arm Extension", PL, "triceps-extension"),
    ("C92", "Abdominal Compound", PL, "ab-crunch"),
    # Future Line - selectorized (forerunner of the G-series)
    ("F110", "Back Extension", SEL, "back-extension"),
    ("F120", "Rotary Torso", SEL, "torso-rotation"),
    ("F130", "Abdominal Flexion", SEL, "ab-crunch"),
    ("F140", "Cervical Extension", SEL, None),
    ("F150", "Lateral Flexion", SEL, None),
    ("F200", "Leg Extension", SEL, "leg-extension"),
    ("F210", "Leg Press", SEL, "leg-press"),
    ("F260", "Hip Extension", SEL, "glute"),
    ("F300", "Leg Curl", SEL, "leg-curl"),
    ("F310", "Abduction", SEL, "hip-abduction"),
    ("F320", "Adduction", SEL, "hip-adduction"),
    ("F330", "Abduction/Adduction", SEL, "hip-abduction"),
    ("F400", "Pull Over", SEL, "pullover"),
    ("F410", "Rotary Lat", SEL, "pullover"),
    ("F420", "Lat Pulldown", SEL, "lat-pulldown"),
    ("F430", "Rowing Torso", SEL, "rear-delt"),
    ("F440", "Lat Rowing", SEL, "seated-row"),
    ("F450", "Rowing Torso / Pec Deck", SEL, "pec-fly"),
    ("F500", "Pec Deck", SEL, "pec-fly"),
    ("F510", "Chest Press", SEL, "chest-press"),
    ("F520", "Seated Dip", SEL, "triceps-dip"),
    ("F600", "Rotary Deltoid", SEL, "lateral-raise"),
    ("F610", "Shoulder Press", SEL, "shoulder-press"),
    ("F620", "Lateral Raise", SEL, "lateral-raise"),
    ("F640", "Reverse Pull Over", SEL, None),
    ("F700", "Arm Curl", SEL, "biceps-curl"),
    ("F750", "Multi Forearm", SEL, None),
    ("F800", "Arm Extension", SEL, "triceps-extension"),
    # Modular Line - machines only (no benches / stands)
    ("M12", "Leg Extension / Leg Curl", SEL, "leg-extension"),
    ("M14", "Leg Press", SEL, "leg-press"),
    ("M15", "Hack Squat", SEL, "hack-squat"),
    ("M16", "Multi Function Leg Press", SEL, "leg-press"),
    ("M21", "Lat Pulldown", CABLE, "lat-pulldown"),
    ("M22", "Leverage Rowing", SEL, "seated-row"),
    ("M23", "Horizontal Row", CABLE, "seated-row"),
    ("M30", "Multi Press", SEL, "chest-press"),
    ("M61", "High / Low Pulley", CABLE, None),
    ("M62", "Multi Function Pulley Explosive", CABLE, None),
    ("M63", "Adjustable Pulley", CABLE, None),
    ("M82", "Assisted Dip / Chin-Up", SEL, "chin-up"),
    # Basic Line - machines only (no racks / benches / stands)
    ("B14", "Angled Leg Press 45°", PL, "leg-press"),
    ("B15", "Hack Squat", PL, "hack-squat"),
    ("B17", "Seated Calf", PL, "calf-raise"),
    ("B18", "Calf Machine", SEL, "calf-raise"),
    ("B21", "Lat Pulldown", CABLE, "lat-pulldown"),
    ("B22", "Leverage Rowing", CABLE, "seated-row"),
    ("B23", "Horizontal Row", CABLE, "seated-row"),
    ("B24", "Lat Pulldown / Horizontal Row", CABLE, "lat-pulldown"),
    ("B25", "T-Bar Row", PL, "seated-row"),
    ("B60", "Cross Over Unit", CABLE, None),
    ("B61", "High / Low Pulley", CABLE, None),
    ("B65", "Smith's Machine", SMITH, None),
    ("B90", "Abdominal Crunch", "bench", "ab-crunch"),
]

MUSCLE = {
    "chest-press": "chest · triceps", "incline-chest-press": "upper chest", "pec-fly": "chest",
    "rear-delt": "rear delts", "shoulder-press": "delts · triceps", "lateral-raise": "side delts",
    "lat-pulldown": "lats · biceps", "seated-row": "mid-back · lats", "pullover": "lats", "chin-up": "back · triceps",
    "biceps-curl": "biceps", "triceps-extension": "triceps", "triceps-dip": "triceps · chest",
    "leg-press": "quads · glutes", "hack-squat": "quads · glutes", "leg-extension": "quads", "leg-curl": "hamstrings",
    "calf-raise": "calves", "glute": "glutes", "hip-abduction": "abductors", "hip-adduction": "adductors",
    "back-extension": "lower back", "ab-crunch": "abs", "torso-rotation": "obliques",
}


def rows() -> list[dict]:
    return [
        {"code": code, "name": f"{code} {name}", "type": mtype, "slug": slug,
         "muscle": MUSCLE.get(slug or ""), "img": WAYBACK.format(code.lower()), "file": OUT / f"{code}.jpg"}
        for code, name, mtype, slug in MODELS
    ]


def fetch_image(url: str, dest: Path) -> Path:
    if dest.exists() and dest.stat().st_size > 3000:
        return dest
    for attempt in range(4):
        try:
            raw = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=90).read()
            Image.open(io.BytesIO(raw)).convert("RGB").save(dest, "JPEG", quality=92)
            time.sleep(0.5)
            return dest
        except Exception:  # Wayback throttles/flakes; back off and retry
            if attempt == 3:
                raise
            time.sleep(5 * (attempt + 1))
    return dest


def inline(path: Path) -> str:
    im = Image.open(path).convert("RGB")
    im.thumbnail((MAX_PX, MAX_PX))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=JPEG_Q, optimize=True)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def contact_sheet(items: list[dict], dest: Path) -> None:
    W, cols = 160, 8
    page_rows = max((len(items) + cols - 1) // cols, 1)
    doc = pymupdf.open()
    page = doc.new_page(width=W * cols, height=(W + 14) * page_rows)
    for i, row in enumerate(items):
        x, y = (i % cols) * W, (i // cols) * (W + 14)
        page.insert_image(pymupdf.Rect(x + 3, y + 3, x + W - 3, y + W - 3),
                          filename=str(row["file"]), keep_proportion=True)
        page.insert_text((x + 4, y + W + 9), row["name"][:28], fontsize=6)
    page.get_pixmap(dpi=72).save(str(dest))


def main() -> None:
    write = "--write" in sys.argv
    OUT.mkdir(parents=True, exist_ok=True)
    items = rows()
    for row in items:
        fetch_image(row["img"], row["file"])
    contact_sheet(items, OUT / "_david_wayback_sheet.png")

    print(f"{len(items)} DAVID machines from the archived david.fi line pages")
    for row in items:
        print(f"   {row['code']:<5} {row['type']:<13} {row['slug'] or '-':<20} {row['name']}")
    print("unlinked:", [row["code"] for row in items if not row["slug"]])
    if not write:
        print("\ndry run - pass --write to add/update DB rows")
        return

    con = sqlite3.connect(DB)
    brand = con.execute("select id from brand where name=?", (BRAND,)).fetchone()
    brand_id = brand[0] if brand else con.execute(
        "insert into brand (name, abbr) values (?,?)", (BRAND, ABBR)).lastrowid
    slugs = dict(con.execute("select slug, id from exercise").fetchall())
    old = [i for (i,) in con.execute("select id from machine where source=?", (SOURCE,))]
    if old:
        q = ",".join("?" * len(old))
        con.execute(f"delete from gymmachine where machine_id in ({q})", old)
        con.execute(f"delete from machine where id in ({q})", old)
    for row in items:
        con.execute(
            "insert into machine (brand_id, model, machine_type, exercise_id, muscle_label, image_url, source) "
            "values (?,?,?,?,?,?,?)",
            (brand_id, row["name"], row["type"], slugs.get(row["slug"]) if row["slug"] else None,
             row["muscle"], inline(row["file"]), SOURCE))
    con.commit()
    print(f"added {len(items)} David machines (replaced {len(old)})")


if __name__ == "__main__":
    main()
