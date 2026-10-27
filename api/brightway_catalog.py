"""Brightway (Shandong Brightway Fitness Equipment Co., Dezhou): add the Power
Series strength machines from the manufacturer's own site, with its renders.

    python api/brightway_catalog.py            # dry run: list + contact sheet
    python api/brightway_catalog.py --write    # add rows (idempotent per source)

Source: www.brtwfitness.com. The product list is rendered by an AJAX call the
page makes itself (POST /ajax/products with the page's csrf token and category
id 60 = POWER SERIES), which returns every product as "<CODE> <NAME>" plus a
1000 px PNG render on transparent background. Ten series in one list:
  pin-loaded    BF, BH, HS, TY            (BH also carries benches/racks/jungles)
  plate-loaded  BL, PL, PS, TM, TN        (TM/TN also carry benches/racks)
  TB            benches, racks, cable crossovers, functional trainers, smith
Benches, racks, plate trees, dumbbell racks, power cages, stretch trainers and
multi-jungles are skipped (not machines); cable crossovers, functional trainers
and smith machines are kept like the other brands. Exercise links come from the
same keyword rules api/link_exercises.py applies to the rest of the catalog.
"""
from __future__ import annotations

import base64
import html as htmllib
import io
import json
import re
import sqlite3
import sys
import time
import urllib.parse
import urllib.request
from http.cookiejar import CookieJar
from pathlib import Path

import pymupdf
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
from link_exercises import by_rules  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "api" / "rackd.db"
OUT = ROOT / "tools" / "cap" / "www" / "img" / "brightway"
SITE = "https://www.brtwfitness.com"
CATEGORY = 60  # POWER SERIES
BRAND, ABBR, SOURCE = "Brightway", "BW", "brightway-site"
MAX_PX, JPEG_Q = 900, 86
UA = {"User-Agent": "Mozilla/5.0 (rackd catalog)"}

SKIP = re.compile(r"bench|rack|plate tree|cage|multi-jungle|stretch trainer|forearm|work station|"
                  r"vertical knees|knee up|chin up/dip|roman chair", re.I)
PLATE = {"BL", "PL", "PS", "TM", "TN", "TB"}
MUSCLE = {
    "chest-press": "chest · triceps", "incline-chest-press": "upper chest", "pec-fly": "chest",
    "rear-delt": "rear delts", "shoulder-press": "delts · triceps", "lateral-raise": "side delts",
    "lat-pulldown": "lats · biceps", "seated-row": "mid-back · lats", "pullover": "lats", "chin-up": "back · triceps",
    "biceps-curl": "biceps", "triceps-extension": "triceps", "triceps-dip": "triceps · chest",
    "leg-press": "quads · glutes", "hack-squat": "quads · glutes", "leg-extension": "quads", "leg-curl": "hamstrings",
    "calf-raise": "calves", "glute": "glutes", "hip-thrust": "glutes", "hip-abduction": "abductors",
    "hip-adduction": "adductors", "multi-hip": "hips · glutes", "back-extension": "lower back",
    "ab-crunch": "abs", "torso-rotation": "obliques", "leg-raise": "abs · hip flexors", "lunge": "quads · glutes",
    "shrug": "traps", "deadlift": "back · hamstrings",
}


def fetch_list() -> list[dict]:
    jar = CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    page = opener.open(urllib.request.Request(f"{SITE}/products/{CATEGORY}.html", headers=UA), timeout=60).read().decode("utf-8", "ignore")
    csrf = re.search(r'<meta name="csrf" content="([^"]+)"', page).group(1)
    val = lambda n: (re.search(rf'name="{n}"[^>]*value="([^"]*)"', page) or [None, ""])[1]  # noqa: E731
    data = urllib.parse.urlencode({"lanno": val("lanno"), "csrf": csrf, "languageId": val("languageId") or "1",
                                   "currentCategoryId": CATEGORY, "categoryIds": val("categoryIds"),
                                   "page": 1, "pageSize": 1000}).encode()
    html = opener.open(urllib.request.Request(f"{SITE}/ajax/products", data=data,
                                              headers={**UA, "X-Requested-With": "XMLHttpRequest"}), timeout=90).read().decode("utf-8", "ignore")
    items, seen = [], set()
    for url, body in re.findall(r'<li>\s*<a href="(/products/\d+/\d+\.html)" class="item">(.*?)</li>', html, re.S):
        img = re.search(r'src="(/static/assets/upload/[^"]+)"', body)
        name = re.search(r'class="cly">([^<]+)<', body)
        if not (img and name):
            continue
        label = htmllib.unescape(re.sub(r"\s+", " ", name.group(1))).strip()
        m = re.match(r"([A-Z]{2}\d+[A-Z]?)[\s-]*(.+)", label)
        if not m or m.group(1) in seen:
            continue
        seen.add(m.group(1))
        items.append({"code": m.group(1), "name": m.group(2).strip(), "img": SITE + img.group(1), "url": SITE + url})
    return items


def title(name: str) -> str:
    fixed = {"pecfly": "Pec Fly", "pec fly": "Pec Fly", "dy row": "DY Row", "iso-lateral": "Iso-Lateral",
             "iso lat": "Iso Lat", "3d": "3D", "v squat": "V Squat"}
    t = re.sub(r"\s*/\s*", " / ", name.lower()).replace("&", " & ")
    t = re.sub(r"\s+", " ", t).strip().title()
    for k, v in fixed.items():
        t = re.sub(re.escape(k.title()), v, t)
    return t


def fetch_image(url: str, dest: Path) -> Path:
    if not (dest.exists() and dest.stat().st_size > 3000):
        for attempt in range(3):
            try:
                raw = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60).read()
                im = Image.open(io.BytesIO(raw)).convert("RGBA")
                bg = Image.new("RGB", im.size, (255, 255, 255))
                bg.paste(im, mask=im.split()[-1])
                bg.save(dest, "JPEG", quality=92)
                break
            except Exception as e:  # noqa: BLE001
                print(f"   retry {attempt} {url.rsplit('/', 1)[-1]} ({type(e).__name__})")
                time.sleep(3 * (attempt + 1))
        time.sleep(0.4)
    return dest


def inline(path: Path) -> str:
    im = Image.open(path).convert("RGB")
    im.thumbnail((MAX_PX, MAX_PX))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=JPEG_Q, optimize=True)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def contact_sheet(rows: list[dict], dest: Path) -> None:
    W, cols = 150, 10
    n = (len(rows) + cols - 1) // cols
    d = pymupdf.open()
    page = d.new_page(width=W * cols, height=(W + 14) * n)
    for i, r in enumerate(rows):
        x, y = (i % cols) * W, (i // cols) * (W + 14)
        page.insert_image(pymupdf.Rect(x + 3, y + 3, x + W - 3, y + W - 3), filename=str(r["file"]), keep_proportion=True)
        page.insert_text((x + 4, y + W + 9), f"{r['code']} {r['name'][:22]}", fontsize=6)
    page.get_pixmap(dpi=72).save(str(dest))


def main() -> None:
    write = "--write" in sys.argv
    OUT.mkdir(parents=True, exist_ok=True)
    items = fetch_list()
    rows = []
    for it in items:
        if SKIP.search(it["name"]):
            continue
        series = it["code"][:2]
        name = it["name"]
        low = name.lower()
        if "smith" in low:
            mtype = "smith/rack"
        elif "crossover" in low or "functional trainer" in low:
            mtype = "cable"
        else:
            mtype = "plate-loaded" if series in PLATE else "selectorized"
        slug = by_rules(name, None)
        rows.append({"code": it["code"], "name": title(name), "series": series, "type": mtype, "slug": slug,
                     "img": it["img"], "file": OUT / f"{it['code']}.jpg"})
    for r in rows:
        fetch_image(r["img"], r["file"])
    contact_sheet(rows, OUT / "_brightway_sheet.png")
    skipped = len(items) - len(rows)
    print(f"{len(items)} products on the site, {len(rows)} machines, {skipped} skipped (benches/racks/jungles)")
    for r in rows:
        print(f"   {r['code']:<7} {r['type']:<13} {r['slug'] or '-':<20} {r['name']}")
    print("unlinked:", [r["code"] for r in rows if not r["slug"]])
    if not write:
        return
    con = sqlite3.connect(DB)
    b = con.execute("select id from brand where name=?", (BRAND,)).fetchone()
    brand_id = b[0] if b else con.execute("insert into brand (name, abbr) values (?,?)", (BRAND, ABBR)).lastrowid
    slugs = dict(con.execute("select slug, id from exercise").fetchall())
    old = [i for (i,) in con.execute("select id from machine where source=?", (SOURCE,))]
    if old:
        q = ",".join("?" * len(old))
        con.execute(f"delete from gymmachine where machine_id in ({q})", old)
        con.execute(f"delete from machine where id in ({q})", old)
    for r in rows:
        con.execute(
            "insert into machine (brand_id, model, machine_type, exercise_id, muscle_label, image_url, source) "
            "values (?,?,?,?,?,?,?)",
            (brand_id, f"{r['code']} {r['name']}", r["type"], slugs.get(r["slug"]) if r["slug"] else None,
             MUSCLE.get(r["slug"] or "", None), inline(r["file"]), SOURCE))
    con.commit()
    print(f"added {len(rows)} Brightway machines (replaced {len(old)})")


if __name__ == "__main__":
    main()
