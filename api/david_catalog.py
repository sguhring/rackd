"""Add DAVID medical exercise devices from the manufacturer's public pages.

    python api/david_catalog.py            # dry run: list + contact sheet
    python api/david_catalog.py --write    # add rows (idempotent per source)

Source: davidhealth.com. robots.txt allows crawling and the WordPress REST API is
restricted, so this uses the public sitemap-linked solution pages. Each page
renders product cards with a model/name link and an official product image.
"""
from __future__ import annotations

import base64
import html
import io
import re
import sqlite3
import sys
import time
import urllib.request
from pathlib import Path
from urllib.parse import urljoin

import pymupdf
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "api" / "rackd.db"
OUT = ROOT / "tools" / "cap" / "www" / "img" / "david"
SITE = "https://davidhealth.com"
BRAND, ABBR, SOURCE = "David", "DV", "davidhealth-site"
MAX_PX, JPEG_Q = 900, 86
UA = {"User-Agent": "Mozilla/5.0 (rackd catalog)"}

PAGES = {
    "Spine devices": f"{SITE}/device-based-solution/spine-devices/",
    "Hip and Knee devices": f"{SITE}/device-based-solution/hip-and-knee-devices/",
    "Shoulder devices": f"{SITE}/device-based-solution/shoulder-solution/",
}

CARD = re.compile(
    r'<a href="(?P<url>https://davidhealth\.com/global-content/[^"]+)">'
    r'<div[^>]+background-image:\s*url\(\'(?P<img>[^\']+)\'\)[^>]*></div></a>.*?'
    r'<h4[^>]*>\s*<a href="[^"]+">(?P<title>G\d{3}[^<]+)</a>',
    re.S,
)

EXERCISE_BY_CODE = {
    "G110": "back-extension",
    "G120": "torso-rotation",
    "G130": "ab-crunch",
    "G200": "leg-extension",
    "G210": "leg-press",
    "G220": "leg-press",
    "G250": "leg-press",
    "G260": "glute",
    "G300": "leg-curl",
    "G310": "hip-abduction",
    "G320": "hip-adduction",
    "G420": "lat-pulldown",
    "G460": "lateral-raise",
    "G510": "chest-press",
}

MUSCLE = {
    "back-extension": "lower back",
    "torso-rotation": "obliques",
    "ab-crunch": "abs",
    "leg-extension": "quads",
    "leg-press": "quads · glutes",
    "glute": "glutes",
    "leg-curl": "hamstrings",
    "hip-abduction": "abductors",
    "hip-adduction": "adductors",
    "lat-pulldown": "lats · biceps",
    "lateral-raise": "side delts",
    "chest-press": "chest · triceps",
}


def fetch(url: str) -> bytes:
    return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60).read()


def fetch_rows() -> list[dict]:
    rows, seen = [], set()
    for category, page_url in PAGES.items():
        body = fetch(page_url).decode("utf-8", "ignore")
        for m in CARD.finditer(body):
            title = html.unescape(re.sub(r"\s+", " ", m.group("title"))).strip()
            code = title.split(" ", 1)[0]
            if code in seen:
                continue
            seen.add(code)
            slug = EXERCISE_BY_CODE.get(code)
            rows.append({
                "code": code,
                "name": title,
                "category": category,
                "type": "selectorized",
                "slug": slug,
                "muscle": MUSCLE.get(slug or ""),
                "url": m.group("url"),
                "img": urljoin(SITE, m.group("img")),
                "file": OUT / f"{code}.jpg",
            })
        time.sleep(0.4)
    return sorted(rows, key=lambda r: r["code"])


def fetch_image(url: str, dest: Path) -> Path:
    if dest.exists() and dest.stat().st_size > 3000:
        return dest
    raw = fetch(url)
    im = Image.open(io.BytesIO(raw)).convert("RGBA")
    bg = Image.new("RGB", im.size, (255, 255, 255))
    bg.paste(im, mask=im.split()[-1])
    bg.save(dest, "JPEG", quality=92)
    time.sleep(0.3)
    return dest


def inline(path: Path) -> str:
    im = Image.open(path).convert("RGB")
    im.thumbnail((MAX_PX, MAX_PX))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=JPEG_Q, optimize=True)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def contact_sheet(rows: list[dict], dest: Path) -> None:
    W, cols = 160, 8
    page_count = max((len(rows) + cols - 1) // cols, 1)
    doc = pymupdf.open()
    page = doc.new_page(width=W * cols, height=(W + 14) * page_count)
    for i, row in enumerate(rows):
        x, y = (i % cols) * W, (i // cols) * (W + 14)
        page.insert_image(
            pymupdf.Rect(x + 3, y + 3, x + W - 3, y + W - 3),
            filename=str(row["file"]),
            keep_proportion=True,
        )
        page.insert_text((x + 4, y + W + 9), row["name"][:28], fontsize=6)
    page.get_pixmap(dpi=72).save(str(dest))


def main() -> None:
    write = "--write" in sys.argv
    OUT.mkdir(parents=True, exist_ok=True)
    rows = fetch_rows()
    for row in rows:
        fetch_image(row["img"], row["file"])
    contact_sheet(rows, OUT / "_david_sheet.png")

    print(f"{len(rows)} DAVID devices from {len(PAGES)} public solution pages")
    for row in rows:
        print(f"   {row['code']:<5} {row['slug'] or '-':<18} {row['category']:<20} {row['name']}")
    print("unlinked:", [row["code"] for row in rows if not row["slug"]])
    if not write:
        print("\ndry run - pass --write to add/update DB rows")
        return

    con = sqlite3.connect(DB)
    brand = con.execute("select id from brand where name=?", (BRAND,)).fetchone()
    brand_id = brand[0] if brand else con.execute(
        "insert into brand (name, abbr) values (?,?)", (BRAND, ABBR)
    ).lastrowid
    slugs = dict(con.execute("select slug, id from exercise").fetchall())
    old = [i for (i,) in con.execute("select id from machine where source=?", (SOURCE,))]
    if old:
        q = ",".join("?" * len(old))
        con.execute(f"delete from gymmachine where machine_id in ({q})", old)
        con.execute(f"delete from machine where id in ({q})", old)
    for row in rows:
        con.execute(
            "insert into machine (brand_id, model, machine_type, exercise_id, muscle_label, image_url, source) "
            "values (?,?,?,?,?,?,?)",
            (
                brand_id,
                row["name"],
                row["type"],
                slugs.get(row["slug"]) if row["slug"] else None,
                row["muscle"],
                inline(row["file"]),
                SOURCE,
            ),
        )
    con.commit()
    print(f"added {len(rows)} David machines (replaced {len(old)})")


if __name__ == "__main__":
    main()
