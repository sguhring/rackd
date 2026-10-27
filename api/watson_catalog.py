"""Add Watson Gym Equipment's (UK) strength catalog from their 2025/26 product
brochure to the DB, with each model's own white-background render inlined as a
base64 data URI.

Watson builds heavy-duty British plate-loaded ("Animal"/"Original"), single- and
dual-stack selectorized machines, plus modular multi-gyms. The brochure lays every
product out on a dead-regular 2x3 grid: three columns (x≈154/392/629), two rows
(top/bottom), each cell carrying a caps TITLE, a 4-digit model CODE just below it,
and the product render directly under that. So binding is pure cell geometry — each
TITLE/CODE pair and its render fall in the same grid cell — with the full-bleed
lifestyle photos filtered out by size/position (they straddle cells off-grid).

A showcase gym "Watson Gym" is (re)built to hold the catalogue.

Idempotent: re-running wipes the source-tagged rows + the showcase gym and rebuilds.

    python watson_catalog.py            # build
    python watson_catalog.py --dry      # extract + print, no DB writes
    python watson_catalog.py --montage  # render validation contact sheets
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

PDF = Path(__file__).resolve().parent.parent / "docs" / "Watson-Gym-Equipment-2026.pdf"
SOURCE = "watson-brochure"
GYM_NAME = "Watson Gym"

# product pages [0-based] -> mechanism. (front matter, section dividers and the
# facility-tour spreads carry no pickable product cards.)
PAGES: dict[int, str] = {
    **{p: "plate-loaded" for p in range(13, 26)},     # Plate Loaded (1-based 14-26)
    **{p: "selectorized" for p in range(30, 37)},     # Single Stack (31-37)
    **{p: "selectorized" for p in range(39, 43)},     # Dual Stack   (40-43)
    46: "functional", 47: "functional",               # Multi-Gyms   (47-48)
}

COLS = [154, 392, 629]                                 # grid column x-anchors
CODE = re.compile(r"^\d{4}(?:-\w+)?$")                 # 4-digit catalog code (e.g. 0041, 0119-wcp)

# Spotlight renders: on 5-card pages Watson enlarges one product's photo into the
# empty grid slot, so it lands off the row anchors and the cell-binder misses it (or,
# where an xref is placed twice, mis-binds it). Hand-verified (page0, code) -> xref
# overrides for exactly those cells; geometry handles every other card.
SPOTLIGHT: dict[tuple[int, str], int] = {
    (13, "0487"): 4750,   # ANIMAL CONVERGING STANDING CHEST PRESS
    (24, "0527"): 5348,   # TOTAL CALF/TIBIALIS DEVELOPER
    (31, "0164"): 5545,   # OVERHEAD TRICEP EXTENSION
    (36, "0449"): 5824,   # HYPER EXTENSION
    (39, "0466"): 5894,   # ANIMAL DUAL STACK BICEP CURL
    (40, "0489"): 5948,   # ANIMAL DECLINE CHEST PRESS (its render, off-grid)
    (40, "0129"): 5961,   # ANIMAL LEG EXTENSION (grid mis-binds it to a reused xref)
}

# first matching keyword wins; specific phrasings listed before general ones.
SLUG_RULES: list[tuple[str, str]] = [
    ("incline shoulder press", "shoulder-press"),
    ("super incline chest press", "incline-chest-press"),
    ("incline chest press", "incline-chest-press"),
    ("free motion chest press", "chest-press"),
    ("decline chest press", "chest-press"),
    ("standing chest press", "chest-press"),
    ("converging standing chest press", "chest-press"),
    ("bench press", "chest-press"),
    ("multi-press", "chest-press"),
    ("chest press", "chest-press"),
    ("multi pec", "pec-fly"),
    ("pec fly", "pec-fly"),
    ("delt builder", "lateral-raise"),
    ("lateral raise", "lateral-raise"),
    ("viking press", "shoulder-press"),
    ("free motion shoulder press", "shoulder-press"),
    ("shoulder press", "shoulder-press"),
    ("shrug", "shrug"),
    ("jammer", "jammer-press"),
    ("bicep tricep", "biceps-curl"),
    ("overhead tricep", "triceps-extension"),
    ("tricep extension", "triceps-extension"),
    ("seated tricep dip", "triceps-dip"),
    ("tricep dip", "triceps-dip"),
    ("seated dip", "triceps-dip"),
    ("bicep curl", "biceps-curl"),
    ("assisted chin", "chin-up"),
    ("independent pullover", "pullover"),
    ("pullover", "pullover"),
    ("tru pull", "lat-pulldown"),
    ("front pulldown", "lat-pulldown"),
    ("lat pulldown", "lat-pulldown"),
    ("pulldown", "lat-pulldown"),
    ("low pulley row", "seated-row"),
    ("t-bar row", "seated-row"),
    ("iso linear row", "seated-row"),
    ("mid to low row", "seated-row"),
    ("high pulley row", "seated-row"),
    ("lateral row", "seated-row"),
    ("low row", "seated-row"),
    ("perfect row", "seated-row"),
    ("seated row", "seated-row"),
    ("row", "seated-row"),
    ("total torso", "torso-rotation"),
    ("torso rotation", "torso-rotation"),
    ("abdominal crunch", "ab-crunch"),
    ("ab crunch", "ab-crunch"),
    ("inverse curl", "leg-curl"),
    ("leg extension", "leg-extension"),
    ("leg curl", "leg-curl"),
    ("leg press", "leg-press"),
    ("hack squat", "hack-squat"),
    ("pendulum squat", "hack-squat"),
    ("power squat", "hack-squat"),
    ("leverage squat", "hack-squat"),
    ("hip belt squat", "hack-squat"),
    ("trusquat", "hack-squat"),
    ("squat", "hack-squat"),
    ("dual hip", "multi-hip"),
    ("multi-hip", "multi-hip"),
    ("hip abductor", "hip-abduction"),
    ("hip adductor", "hip-adduction"),
    ("glute", "glute"),
    ("calf", "calf-raise"),
    ("reverse hyper", "back-extension"),
    ("hyper extension", "back-extension"),
    ("back extension", "back-extension"),
]

MUSCLE: dict[str, str] = {
    "leg-press": "quads · glutes", "leg-extension": "quads", "leg-curl": "hamstrings",
    "hack-squat": "quads · glutes", "calf-raise": "calves",
    "hip-abduction": "abductors", "hip-adduction": "adductors", "multi-hip": "hips",
    "glute": "glutes", "back-extension": "lower back",
    "chest-press": "chest · triceps", "incline-chest-press": "upper chest", "pec-fly": "chest",
    "shoulder-press": "delts · triceps", "lateral-raise": "delts", "rear-delt": "rear delts",
    "shrug": "traps", "jammer-press": "shoulders · chest",
    "lat-pulldown": "lats · biceps", "seated-row": "back · biceps", "pullover": "lats",
    "chin-up": "lats · biceps", "biceps-curl": "biceps",
    "triceps-extension": "triceps", "triceps-dip": "triceps",
    "ab-crunch": "abs", "torso-rotation": "obliques",
}


def col(x: float) -> int:
    return min(range(3), key=lambda i: abs(x - COLS[i]))


def grid_row(y: float) -> int:
    return 0 if y < 290 else 1


def spans(page) -> list[tuple]:
    out = []
    for blk in page.get_text("dict").get("blocks", []):
        for ln in blk.get("lines", []):
            for sp in ln["spans"]:
                t = re.sub(r"\s+", " ", sp["text"]).strip()
                if t:
                    out.append((sp["bbox"], t))
    return out


def is_render(im: dict) -> bool:
    """A grid product render: ~square, ~183px, sitting at a grid row. Filters the
    full-bleed lifestyle photos (taller/wider, off the row anchors)."""
    if not im["xref"]:
        return False
    b = im["bbox"]
    w, h, y = b[2] - b[0], b[3] - b[1], b[1]
    return 150 < w < 215 and 150 < h < 215 and (50 < y < 85 or 325 < y < 355)


def slug_for(title: str):
    low = title.lower()
    for kw, slug in SLUG_RULES:
        if kw in low:
            return slug
    return None


def extract(doc: fitz.Document) -> list[dict]:
    out = []
    for pno, mech in PAGES.items():
        page = doc.load_page(pno)
        sp = spans(page)
        codes = [(b, t) for b, t in sp if CODE.match(t)]
        renders = {(col(im["bbox"][0]), grid_row(im["bbox"][1])): im
                   for im in page.get_image_info(xrefs=True) if is_render(im)}
        for cb, ct in codes:
            cell = (col(cb[0]), grid_row(cb[1]))
            title = [t for b, t in sp
                     if col(b[0]) == cell[0] and grid_row(b[1]) == grid_row(cb[1])
                     and b[1] < cb[1] - 2 and cb[1] - b[1] < 40
                     and re.search(r"[A-Za-z]", t) and not CODE.match(t)]
            name = " ".join(title).strip()
            if not name:
                continue
            im = renders.get(cell)
            xref = SPOTLIGHT.get((pno, ct), im["xref"] if im else None)
            out.append({"page": pno, "mech": mech, "code": ct, "name": name,
                        "xref": xref, "slug": slug_for(name)})

    # drop exact repeats (the multi-gym spread re-prints power gyms already listed
    # under Dual Stack — same code+name), keeping the first occurrence.
    seen, deduped = set(), []
    for m in out:
        key = (m["code"], m["name"])
        if key not in seen:
            seen.add(key)
            deduped.append(m)

    # sanity: a render shared by two *different* products signals a mis-bind.
    by_xref: dict[int, list[str]] = {}
    for m in deduped:
        if m["xref"]:
            by_xref.setdefault(m["xref"], []).append(m["name"])
    for xref, names in by_xref.items():
        if len(set(names)) > 1:
            print(f"WARN xref {xref} shared by: {names}")
    return deduped


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
    cols, cw, ch, per = 4, 260, 240, 24
    for half, start in enumerate(range(0, len(machines), per)):
        chunk = machines[start:start + per]
        rows = (len(chunk) + cols - 1) // cols
        pg = fitz.open().new_page(width=cols * cw, height=rows * ch)
        for i, m in enumerate(chunk):
            r, c = divmod(i, cols)
            x, y = c * cw, r * ch
            rect = fitz.Rect(x + 4, y + 4, x + cw - 4, y + ch - 40)
            if m.get("xref"):
                try:
                    pg.insert_image(rect, pixmap=fitz.Pixmap(doc, m["xref"]), keep_proportion=True)
                except Exception as e:                  # noqa: BLE001
                    pg.insert_text((x + 6, y + 60), f"ERR {e}", fontsize=6)
            else:
                pg.insert_text((x + 6, y + 60), "NO IMAGE", fontsize=8, color=(1, 0, 0))
            pg.insert_textbox(fitz.Rect(x + 4, y + ch - 38, x + cw - 4, y + ch),
                              f"{m['name'][:34]}\n{m['code']} -> {m['slug']}", fontsize=9, align=1)
        path = Path(__file__).resolve().parent / f"_watson_montage_{half}.png"
        pg.get_pixmap(dpi=150).save(path)
        print("montage ->", path)


def run(mode: str = "") -> None:
    doc = fitz.open(PDF)
    machines = extract(doc)

    if mode == "dry":
        for m in machines:
            img = "img" if m.get("xref") else "----"
            print(f"p{m['page']+1:>3} {m['mech']:12s} {img} {m['code']:9s} {m['name'][:46]:46s} -> {m['slug']}")
        mapped = sum(1 for m in machines if m["slug"])
        withimg = sum(1 for m in machines if m.get("xref"))
        print(f"\nTOTAL {len(machines)} machines, {mapped} movement-mapped, {withimg} with photo.")
        return
    if mode == "montage":
        montage(doc, machines)
        return

    with Session(engine) as s:
        brand = s.exec(select(Brand).where(Brand.name == "Watson")).first()
        if not brand:
            brand = Brand(name="Watson", abbr="WA")
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

        cache: dict[int, str] = {}
        added: list[Machine] = []
        for d in machines:
            xref = d.get("xref")
            if xref and xref not in cache:
                cache[xref] = data_uri(doc, xref)
            slug = d["slug"]
            m = Machine(
                brand_id=brand.id,
                model=f"{d['name'].title()} ({d['code']})",
                machine_type=d["mech"],
                exercise_id=slug_to_id.get(slug) if slug else None,
                muscle_label=MUSCLE.get(slug) if slug else None,
                image_url=cache.get(xref) if xref else None,
                source=SOURCE,
            )
            s.add(m); added.append(m)
        s.commit()
        for m in added:
            s.refresh(m)

        gym = Gym(name=GYM_NAME, area="heavy duty · proudly made in great britain · demo")
        s.add(gym); s.commit(); s.refresh(gym)
        for m in added:
            s.add(GymMachine(gym_id=gym.id, machine_id=m.id, added_by="catalog"))
        s.commit()

        mapped = sum(1 for d in machines if d["slug"])
        withimg = sum(1 for d in machines if d.get("xref"))
        kb = sum(len(v) for v in cache.values()) * 3 // 4 // 1024
        print(f"Watson: {len(added)} machines added ({mapped} movement-mapped, "
              f"{withimg} with photo), {len(cache)} renders (~{kb}KB), gym '{GYM_NAME}' id={gym.id}.")


if __name__ == "__main__":
    mode = "dry" if "--dry" in sys.argv else "montage" if "--montage" in sys.argv else ""
    run(mode)
