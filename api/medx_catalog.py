"""Add the MedX (USA) strength catalog from medxonline.net to the DB, with each
model's product photo inlined as a base64 data URI.

MedX builds medical-grade selectorized strength + spinal/cervical rehab machines.
Their site is WordPress (robots.txt allows all); products live as a custom post type
under /products/<category>/<slug>/ and are listed in product-sitemap.xml. We scrape
each product page for its title + product render. The site sometimes embeds a wrong
or placeholder image on a page while the correct render still exists at a predictable
filename (e.g. Seated-Leg-Curl-1.jpg) — so we also probe name-based filenames and
pick the render whose name best matches the product.

A showcase gym "MedX Showroom" is (re)built to hold the catalogue.

Idempotent: re-running wipes the source-tagged rows + the showcase gym and rebuilds.

    python medx_catalog.py            # build
    python medx_catalog.py --dry      # scrape + print, no DB writes
    python medx_catalog.py --montage  # render a validation contact sheet
"""
from __future__ import annotations

import base64
import re
import sys
import urllib.request
from pathlib import Path

import fitz
from sqlmodel import Session, delete, select

from database import engine
from models import Brand, Exercise, Gym, GymMachine, Machine

SITEMAP = "http://medxonline.net/product-sitemap.xml"
UPLOADS = "http://medxonline.net/wp-content/uploads/2019/02/"
SOURCE = "medx-online"
GYM_NAME = "MedX Showroom"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) rackd-catalog"
PLACEHOLDER = ("tumblr_", "logo", "icon", "favicon", "placeholder", "spinner")

# title -> movement slug (None = no clean movement, e.g. neck / stretch machines)
SLUG: dict[str, str | None] = {
    "leg extension": "leg-extension", "seated leg curl": "leg-curl",
    "prone leg curl": "leg-curl", "leg press": "leg-press", "seated calf": "calf-raise",
    "hip abduction": "hip-abduction", "hip adduction": "hip-adduction",
    "hip extension": "glute", "chest press": "chest-press", "arm cross": "pec-fly",
    "overhead press": "shoulder-press", "lateral raise": "lateral-raise",
    "pullover": "pullover", "seated row": "seated-row", "torso arm": "lat-pulldown",
    "bicep curl": "biceps-curl", "triceps extension": "triceps-extension",
    "seated dip": "triceps-dip", "torso rotation": "torso-rotation",
    "ab isolator": "ab-crunch", "torso flexion": "ab-crunch",
    "lumbar strength": "back-extension", "lumbar extension": "back-extension",
    "four-way neck": None, "cervical extension": None, "super stretch": None,
}

MUSCLE: dict[str, str] = {
    "leg-extension": "quads", "leg-curl": "hamstrings", "leg-press": "quads · glutes",
    "calf-raise": "calves", "hip-abduction": "abductors", "hip-adduction": "adductors",
    "glute": "glutes", "chest-press": "chest · triceps", "pec-fly": "chest",
    "shoulder-press": "delts · triceps", "lateral-raise": "delts", "pullover": "lats",
    "seated-row": "back · biceps", "lat-pulldown": "lats · biceps", "biceps-curl": "biceps",
    "triceps-extension": "triceps", "triceps-dip": "triceps", "torso-rotation": "obliques",
    "ab-crunch": "abs", "back-extension": "lower back",
}


def get(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=25) as r:
        return r.read().decode("utf-8", "replace")


def head_ok(url: str) -> bool:
    try:
        req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status == 200
    except Exception:                       # noqa: BLE001
        return False


def fullsize(u: str) -> str:
    return re.sub(r"-\d+x\d+(\.\w+)$", r"\1", u)   # strip WordPress -300x248 resize suffix


def clean_title(html: str) -> str:
    h = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.S)
    t = re.sub("<.*?>", "", h.group(1)).strip() if h else ""
    if not t:
        m = re.search(r"<title>(.*?)</title>", html, re.S)
        t = re.sub(r"\s*-\s*MedX.*$", "", m.group(1)).strip() if m else "?"
    return re.sub(r"\s+", " ", t)


def scrape() -> list[dict]:
    """One record per unique product: {title, category, images[]} merged across pages."""
    urls = [u for u in re.findall(r"<loc>(.*?)</loc>", get(SITEMAP))
            if u.rstrip("/").rsplit("/", 1)[-1] != "products"]
    merged: dict[str, dict] = {}
    for u in urls:
        html = get(u)
        title = clean_title(html)
        key = title.lower()
        imgs = re.findall(
            r'(?:src|data-src)="(http://medxonline\.net/wp-content/uploads/[^"]+\.(?:jpg|jpeg|png))"', html)
        imgs = [i for i in imgs if not any(p in i.rsplit("/", 1)[-1].lower() for p in PLACEHOLDER)]
        rec = merged.setdefault(key, {"title": title, "category": u.split("/products/")[1].split("/")[0],
                                      "images": []})
        for i in imgs:
            if i not in rec["images"]:
                rec["images"].append(i)
    return list(merged.values())


def pick_image(rec: dict) -> str | None:
    """The render whose filename best matches the product name; probe predictable
    filenames too (the site hides some correct renders). None if nothing matches."""
    toks = set(re.findall(r"[a-z]+", rec["title"].lower()))
    cands = list(rec["images"])
    base = re.sub(r"[^A-Za-z0-9]+", "-", rec["title"]).strip("-")
    for guess in (f"{base}-1.jpg", f"{base}.jpg"):
        url = UPLOADS + guess
        if url not in cands and head_ok(url):
            cands.append(url)

    def score(u: str) -> int:
        fn = u.rsplit("/", 1)[-1].lower()
        return sum(1 for t in toks if t in fn)

    if not cands:
        return None
    best = max(cands, key=score)
    if score(best) < 1:
        return None
    fs = fullsize(best)                      # upgrade to the original size if it exists
    return fs if (fs != best and head_ok(fs)) else best


def data_uri(raw: bytes) -> str:
    pix = fitz.Pixmap(raw)
    if pix.colorspace and pix.colorspace.n == 4:
        pix = fitz.Pixmap(fitz.csRGB, pix)
    while pix.width > 1200:
        pix.shrink(1)
    if pix.alpha:
        pix = fitz.Pixmap(pix, 0)
    jpg = pix.tobytes("jpg", jpg_quality=88)
    return "data:image/jpeg;base64," + base64.b64encode(jpg).decode("ascii")


def fetch_image(url: str) -> str | None:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=25) as r:
            return data_uri(r.read())
    except Exception:                       # noqa: BLE001
        return None


def collect() -> list[dict]:
    out = []
    for rec in scrape():
        title = rec["title"]
        slug = SLUG.get(title.lower(), "MISSING")
        out.append({"title": title, "category": rec["category"],
                    "image": pick_image(rec), "slug": slug})
    return sorted(out, key=lambda d: d["title"])


def montage(machines: list[dict]) -> None:
    cols, cw, ch = 5, 240, 230
    rows = (len(machines) + cols - 1) // cols
    out = fitz.open()
    pg = out.new_page(width=cols * cw, height=rows * ch)
    for i, m in enumerate(machines):
        r, c = divmod(i, cols)
        x, y = c * cw, r * ch
        if m.get("uri"):
            raw = base64.b64decode(m["uri"].partition(",")[2])
            pg.insert_image(fitz.Rect(x + 5, y + 5, x + cw - 5, y + ch - 34),
                            pixmap=fitz.Pixmap(raw), keep_proportion=True)
        else:
            pg.insert_text((x + 8, y + 60), "NO IMAGE", fontsize=9, color=(1, 0, 0))
        pg.insert_textbox(fitz.Rect(x + 4, y + ch - 32, x + cw - 4, y + ch),
                          f"{m['title']}\n-> {m['slug']}", fontsize=9, align=1)
    path = Path(__file__).resolve().parent / "_medx_montage.png"
    pg.get_pixmap(dpi=120).save(path)
    print("montage ->", path)


def run(mode: str = "") -> None:
    machines = collect()
    bad = [m["title"] for m in machines if m["slug"] == "MISSING"]
    if bad:
        print("WARN unmapped titles (add to SLUG):", bad)

    if mode in ("dry", "montage"):
        for m in machines:
            print(f"  {m['title']:20s} [{m['category']:26s}] {m['slug']!s:18s} "
                  f"{'img' if m['image'] else '----'} {m['image'].rsplit('/',1)[-1] if m['image'] else ''}")
        print(f"\n{len(machines)} products, "
              f"{sum(1 for m in machines if m['slug'] not in (None,'MISSING'))} movement-mapped, "
              f"{sum(1 for m in machines if m['image'])} with image.")
        if mode == "montage":
            for m in machines:
                m["uri"] = fetch_image(m["image"]) if m["image"] else None
            montage(machines)
        return

    for m in machines:
        m["uri"] = fetch_image(m["image"]) if m["image"] else None

    with Session(engine) as s:
        brand = s.exec(select(Brand).where(Brand.name == "MedX")).first()
        if not brand:
            brand = Brand(name="MedX", abbr="MX")
            s.add(brand); s.commit(); s.refresh(brand)

        slug_to_id = {e.slug: e.id for e in s.exec(select(Exercise)).all()}

        old_gym = s.exec(select(Gym).where(Gym.name == GYM_NAME)).first()
        old_ids = [m.id for m in s.exec(select(Machine).where(Machine.source == SOURCE)).all()]
        if old_ids:
            s.exec(delete(GymMachine).where(GymMachine.machine_id.in_(old_ids)))
        if old_gym:
            s.exec(delete(GymMachine).where(GymMachine.gym_id == old_gym.id))
        s.exec(delete(Machine).where(Machine.source == SOURCE))
        if old_gym:
            s.exec(delete(Gym).where(Gym.id == old_gym.id))
        s.commit()

        added = []
        for m in machines:
            slug = m["slug"] if m["slug"] not in (None, "MISSING") else None
            row = Machine(
                brand_id=brand.id, model=m["title"], machine_type="selectorized",
                exercise_id=slug_to_id.get(slug) if slug else None,
                muscle_label=MUSCLE.get(slug) if slug else None,
                image_url=m.get("uri"), source=SOURCE)
            s.add(row); added.append(row)
        s.commit()
        for row in added:
            s.refresh(row)

        gym = Gym(name=GYM_NAME, area="medical-grade strength · made in the USA · demo")
        s.add(gym); s.commit(); s.refresh(gym)
        for row in added:
            s.add(GymMachine(gym_id=gym.id, machine_id=row.id, added_by="catalog"))
        s.commit()

        mapped = sum(1 for m in machines if m["slug"] not in (None, "MISSING"))
        withimg = sum(1 for m in machines if m.get("uri"))
        print(f"MedX: {len(added)} machines added ({mapped} movement-mapped, "
              f"{withimg} with photo), gym '{GYM_NAME}' id={gym.id}.")


if __name__ == "__main__":
    mode = "dry" if "--dry" in sys.argv else "montage" if "--montage" in sys.argv else ""
    run(mode)
