"""Add the Arsenal Strength (USA) strength catalog from their product brochure to
the DB, with each model's own white-background product render inlined as a base64
data URI.

Arsenal Strength builds US plate-loaded ("Reloaded"), selectorized ("M-1") and
rack/bench lines ("Alpha", "Bravo"). Every SKU in the brochure is printed as a
caps NAME span immediately followed by a model CODE span (AR-*, M1-*, ALPHA-*,
BRAVO-*) — that pair is the reliable anchor. Each product's photo is bound to it
by nearest-centre geometry among the page's real product renders (logos, feature
close-ups and full-bleed backgrounds are filtered out), assigned greedily so no
two products claim the same render.

A showcase gym "Arsenal Strength Showroom" is (re)built to hold the catalogue.

Idempotent: re-running wipes the source-tagged rows + the showcase gym and rebuilds.

    python arsenal_catalog.py            # build
    python arsenal_catalog.py --dry      # extract + print, no DB writes
    python arsenal_catalog.py --montage  # render a validation contact sheet
"""
from __future__ import annotations

import base64
import re
import sys
from pathlib import Path

import fitz
from sqlmodel import Session, delete, select

from database import engine
from models import Brand, Exercise, Gym, GymMachine, Machine

PDF = Path(__file__).resolve().parent.parent / "docs" / "Arsenal Strength Catalog 6.2-1.pdf"
SOURCE = "arsenal-brochure"
GYM_NAME = "Arsenal Strength Showroom"

# product pages [0-based] -> mechanism. (front matter, facility tours, flooring,
# resistance bands and the closing pages carry no pickable strength SKUs.)
PAGES: dict[int, str] = {
    10: "plate-loaded", 11: "plate-loaded", 12: "plate-loaded", 13: "plate-loaded",
    14: "plate-loaded", 15: "plate-loaded", 16: "plate-loaded",
    18: "selectorized", 19: "selectorized", 20: "selectorized", 21: "selectorized",
    22: "selectorized",
    24: "rack", 25: "rack", 26: "bench", 27: "bench", 28: "storage",
    29: "plate-loaded", 30: "plate-loaded",
    32: "rack", 33: "plate-loaded",
}

# a model code: AR-/M1-/BRAVO- or ALPHA(-| 7-| 11-) followed by an all-caps token.
# (must contain the hyphen, so caps NAMES that merely start with "ALPHA " — e.g.
# "ALPHA FLAT BENCH" — are not mistaken for codes.)
CODE = re.compile(r"^(AR|M1|BRAVO)-[A-Z0-9-]+$|^ALPHA(\s\d+)?-\s?[A-Z0-9-]+$")
# caps spans that are line/section headers or boilerplate, never a product name.
HEAD = {"M-1", "ALPHA", "BRAVO", "RELOADED", "PLATE LOADED EQUIPMENT",
        "PIN SELECT EQUIPMENT", "SPECIAL FEATURES", "POWERSLIDE SERIES",
        "ALPHA 7 SERIES", "ALPHA 11 SERIES", "OLYMPIC BENCHES", "UTILITY BENCHES",
        "STORAGE RACKS", "RACKS", "BENCHES"}

# code -> index into the page's filtered product-render list (uimgs order). Hand-
# verified against the rendered brochure pages: these magazine-style layouts place
# each caption beside/below/above its render with no consistent offset, so pure
# nearest-render geometry mis-binds. Captions not listed here fall back to geometry.
BIND: dict[str, int] = {
    # Reloaded (plate-loaded)
    "AR-MTFX": 0, "AR-VLP": 0,
    "AR-LLP": 0, "AR-BLP": 3, "AR-PNDLM": 1,
    "AR-HS": 0, "AR-PS": 1, "AR-GB": 2,
    "AR-TBAR": 0, "AR-LP": 1, "AR-LR": 2,
    "AR-CP": 0, "AR-FLY": 1, "AR-IP": 2, "AR-SP": 3, "AR-MR": 4, "AR-VR": 5,
    "AR-CALF": 0, "AR-VCP": 1, "AR-TKD": 2,
    # M-1 (selectorized)
    "M1-4BT": 1, "M1-8BT": 2, "M1-SLR": 0,
    "M1-LE": 1, "M1-SLC": 0, "M1-LLC": 2, "M1-OTE": 3,
    "M1-SC": 0, "M1-DC": 1, "M1-FLY": 3, "M1-BC": 2,
    "M1-IOT": 1, "M1-GI": 0, "M1-LP-R": 3, "M1-LP": 2,
    # Alpha (racks · benches · storage · iso)
    "ALPHA-PS-HR": 1, "ALPHA-PS-PR": 2,
    "ALPHA7-HR": 2, "ALPHA7-DHR": 1, "ALPHA7-PR": 0,
    "ALPHA11-HR": 4, "ALPHA11-DHR": 3, "ALPHA11-PR": 5,
    "ALPHA-OFB": 0, "ALPHA-CFB": 1, "ALPHA-ODB": 2, "ALPHA-OIB": 3,
    "ALPHA-ADB": 3, "ALPHA-ALB": 1, "ALPHA-BR": 7, "ALPHA-FB": 4,
    "ALPHA-UB": 2, "ALPHA-DBROW": 5, "ALPHA-MAB": 0, "ALPHA-SPC": 6,
    "ALPHA-10BB": 4, "ALPHA-3TPS": 7, "ALPHA-3THEX": 6, "ALPHA-OWT": 5,
    "ALPHA-SS": 0, "ALPHA-GHD": 1,
    "ALPHA-VKR": 0, "ALPHA-45BE": 1, "ALPHA-DLJACK": 3, "ALPHA-MONO": 4, "ALPHA-SM": 5,
    # Bravo (racks · development)
    "BRAVO-HR": 0, "BRAVO-DHR": 2, "BRAVO-PR": 1,
    "BRAVO-GHD": 0, "BRAVO-MAB": 1,
}

# first keyword wins; specific before general. prefix word-boundary match.
SLUG_RULES: list[tuple[str, str]] = [
    ("incline fly", "pec-fly"),
    ("incline chest press", "incline-chest-press"),
    ("incline press", "incline-chest-press"),
    ("chest press", "chest-press"),
    ("pec fly", "pec-fly"),
    ("rear delt", "rear-delt"),
    ("lateral raise", "lateral-raise"),
    ("shoulder press", "shoulder-press"),
    ("lat pulldown", "lat-pulldown"),
    ("pulldown", "lat-pulldown"),
    ("t bar row", "seated-row"),
    ("lever row", "seated-row"),
    ("multi row", "seated-row"),
    ("vertical row", "seated-row"),
    ("bent over row", "seated-row"),
    ("row", "seated-row"),
    ("leg extension", "leg-extension"),
    ("leg curl", "leg-curl"),
    ("leg press", "leg-press"),
    ("hack squat", "hack-squat"),
    ("power squat", "hack-squat"),
    ("pendulum squat", "hack-squat"),
    ("seated calf", "calf-raise"),
    ("standing calf", "calf-raise"),
    ("donkey calf", "calf-raise"),
    ("calf", "calf-raise"),
    ("glute bridge", "hip-thrust"),
    ("glute isolator", "glute"),
    ("glute/ham", "back-extension"),
    ("glute/hamstring", "back-extension"),
    ("inner outer thigh", "multi-hip"),
    ("overhead tricep", "triceps-extension"),
    ("tricep kickback", "triceps-dip"),
    ("tricep", "triceps-extension"),
    ("bicep curl", "biceps-curl"),
    ("preacher curl", "biceps-curl"),
    ("knee raise", "leg-raise"),
    ("back extension", "back-extension"),
]

MUSCLE: dict[str, str] = {
    "leg-press": "quads · glutes", "leg-extension": "quads", "leg-curl": "hamstrings",
    "hack-squat": "quads · glutes", "calf-raise": "calves", "multi-hip": "abductors · adductors",
    "glute": "glutes", "hip-thrust": "glutes", "leg-raise": "lower abs",
    "chest-press": "chest · triceps", "incline-chest-press": "upper chest", "pec-fly": "chest",
    "shoulder-press": "delts · triceps", "lateral-raise": "delts", "rear-delt": "rear delts",
    "lat-pulldown": "lats · biceps", "seated-row": "back · biceps", "pullover": "lats",
    "biceps-curl": "biceps", "triceps-extension": "triceps", "triceps-dip": "triceps",
    "back-extension": "lower back",
}


def spans(page) -> list[tuple]:
    out = []
    for blk in page.get_text("dict")["blocks"]:
        if "lines" not in blk:
            continue
        for ln in blk["lines"]:
            for sp in ln["spans"]:
                t = re.sub(r"\s+", " ", sp["text"]).strip()
                if t:
                    out.append((sp["bbox"], t))
    return out


def is_product(im: dict) -> bool:
    """A real product render: not a logo, feature close-up or full-bleed background."""
    if im["xref"] == 0:
        return False
    b = im["bbox"]
    w, h = b[2] - b[0], b[3] - b[1]
    if b[0] < 6 and w > 590:          # dark full-height side-panel background
        return False
    return w > 150 and h > 150 and im["width"] > 250


def captions(page) -> list[dict]:
    """(name, code) pairs: a CODE span with the caps NAME span just left of it."""
    sp = spans(page)
    codes = [s for s in sp if CODE.match(s[1])]
    out = []
    for cb, ct in codes:
        cands = [(nb, nt) for nb, nt in sp
                 if not CODE.match(nt) and abs(nb[1] - cb[1]) < 4
                 and nb[2] <= cb[0] + 2 and cb[0] - nb[2] < 14
                 and re.search(r"[A-Za-z]", nt) and nt not in HEAD]
        if not cands:
            continue
        nb, nt = max(cands, key=lambda c: c[0][2])   # the span nearest to the code's left
        out.append({"name": nt, "code": re.sub(r"[\s­]+", "", ct),
                    "anchor": ((cb[0] + nb[0]) / 2, (cb[1] + cb[3]) / 2)})
    return out


def uimgs(page) -> list[dict]:
    """The page's product renders, deduped by xref (BIND indexes into this list)."""
    seen, u = set(), []
    for im in page.get_image_info(xrefs=True):
        if is_product(im) and im["xref"] not in seen:
            seen.add(im["xref"])
            u.append(im)
    return u


def nearest(anchor, imgs: list[dict]) -> int | None:
    """Fallback for captions absent from BIND: nearest render centre."""
    ax, ay = anchor
    best, bi = 1e18, None
    for i, im in enumerate(imgs):
        b = im["bbox"]
        d = (ax - (b[0] + b[2]) / 2) ** 2 + (ay - (b[1] + b[3]) / 2) ** 2
        if d < best:
            best, bi = d, i
    return bi


def slug_for(name: str):
    low = name.lower()
    for kw, slug in SLUG_RULES:
        if re.search(r"\b" + re.escape(kw), low):
            return slug
    return None


def extract(doc: fitz.Document) -> list[dict]:
    out, fellback = [], []
    for pno, mech in PAGES.items():
        page = doc.load_page(pno)
        caps = captions(page)
        u = uimgs(page)
        for c in caps:
            idx = BIND.get(c["code"])
            if idx is None:
                idx = nearest(c["anchor"], u)
                fellback.append(f"p{pno}:{c['code']}")
            c["xref"] = u[idx]["xref"] if (idx is not None and idx < len(u)) else None
            c.update(page=pno, mech=mech, slug=slug_for(c["name"]))
        out.extend(caps)
    if fellback:
        print("note: geometry-fallback (not in BIND):", ", ".join(fellback))
    return out


def data_uri(doc: fitz.Document, xref: int) -> str:
    pix = fitz.Pixmap(doc, xref)
    if pix.colorspace and pix.colorspace.n == 4:
        pix = fitz.Pixmap(fitz.csRGB, pix)
    while pix.width > 1200:
        pix.shrink(1)
    if pix.alpha:
        pix = fitz.Pixmap(pix, 0)
    jpg = pix.tobytes("jpg", jpg_quality=88)
    return "data:image/jpeg;base64," + base64.b64encode(jpg).decode("ascii")


def montage(doc: fitz.Document, machines: list[dict]) -> None:
    """Render every product's assigned render in a labelled grid, to eyeball binding."""
    cols, cw, ch, per = 4, 260, 240, 24
    for half, start in enumerate(range(0, len(machines), per)):
        chunk = machines[start:start + per]
        rows = (len(chunk) + cols - 1) // cols
        out = fitz.open()
        pg = out.new_page(width=cols * cw, height=rows * ch)
        for i, m in enumerate(chunk):
            r, c = divmod(i, cols)
            x, y = c * cw, r * ch
            rect = fitz.Rect(x + 4, y + 4, x + cw - 4, y + ch - 40)
            if m.get("xref"):
                try:
                    pg.insert_image(rect, pixmap=fitz.Pixmap(doc, m["xref"]), keep_proportion=True)
                except Exception as e:                   # noqa: BLE001
                    pg.insert_text((x + 6, y + 60), f"ERR {e}", fontsize=6)
            else:
                pg.insert_text((x + 6, y + 60), "NO IMAGE", fontsize=8, color=(1, 0, 0))
            label = f"{m['name'][:32]}\n{m['code']} -> {m['slug']}"
            pg.insert_textbox(fitz.Rect(x + 4, y + ch - 38, x + cw - 4, y + ch),
                              label, fontsize=9, align=1)
        path = Path(__file__).resolve().parent / f"_arsenal_montage_{half}.png"
        pg.get_pixmap(dpi=150).save(path)
        print("montage ->", path)


def run(mode: str = "") -> None:
    doc = fitz.open(PDF)
    machines = extract(doc)

    if mode == "dry":
        for m in machines:
            img = "img" if m.get("xref") else "----"
            print(f"p{m['page']:>2} {m['mech']:12s} {img} {m['name']:34s} {m['code']:14s} -> {m['slug']}")
        mapped = sum(1 for m in machines if m["slug"])
        withimg = sum(1 for m in machines if m.get("xref"))
        print(f"\nTOTAL {len(machines)} machines, {mapped} movement-mapped, {withimg} with photo.")
        return
    if mode == "montage":
        montage(doc, machines)
        return

    with Session(engine) as s:
        brand = s.exec(select(Brand).where(Brand.name == "Arsenal Strength")).first()
        if not brand:
            brand = Brand(name="Arsenal Strength", abbr="AR")
            s.add(brand)
            s.commit()
            s.refresh(brand)

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

        cache: dict[int, str] = {}
        added: list[Machine] = []
        for d in machines:
            xref = d.get("xref")
            if xref and xref not in cache:
                cache[xref] = data_uri(doc, xref)
            slug = d["slug"]
            m = Machine(
                brand_id=brand.id,
                model=d["name"].title(),
                machine_type=d["mech"],
                exercise_id=slug_to_id.get(slug) if slug else None,
                muscle_label=MUSCLE.get(slug) if slug else None,
                image_url=cache.get(xref) if xref else None,
                source=SOURCE,
            )
            s.add(m)
            added.append(m)
        s.commit()
        for m in added:
            s.refresh(m)

        gym = Gym(name=GYM_NAME, area="masters of strength · made in the USA · demo")
        s.add(gym)
        s.commit()
        s.refresh(gym)
        for m in added:
            s.add(GymMachine(gym_id=gym.id, machine_id=m.id, added_by="catalog"))
        s.commit()

        mapped = sum(1 for d in machines if d["slug"])
        withimg = sum(1 for d in machines if d.get("xref"))
        kb = sum(len(v) for v in cache.values()) * 3 // 4 // 1024
        print(f"Arsenal: {len(added)} machines added ({mapped} movement-mapped, "
              f"{withimg} with photo), {len(cache)} renders (~{kb}KB), gym '{GYM_NAME}' id={gym.id}.")


if __name__ == "__main__":
    mode = "dry" if "--dry" in sys.argv else "montage" if "--montage" in sys.argv else ""
    run(mode)
