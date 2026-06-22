"""Add the Panatta (Panatta Sport, Apiro, Italy) strength catalog from their
general brochure to the DB, with each model's own white-background product
render inlined as a base64 data URI.

Panatta builds Italian selectorized + plate-loaded strength lines. This imports
the recognisable strength lines a user picks from:

    XPLUX · FIT EVO · SEC (selectorized weight-stack)
    FREEWEIGHT HP (plate loaded) · OASIS · MULTIMEDIA (AMD/AMT, selectorized)

Brochure layout (validated against the renders): each strength spread lays
models out in a grid of large white-background renders. Per cell the model NAME
and a body-part category sit ABOVE the render, and the model CODE sits at the
render's lower edge. So we:
  - bind each render to its code geometrically (nearest code at the render's
    bottom edge, same column), and
  - read the name/category as the nearest text segment ABOVE the render in its
    column (categories are a fixed vocabulary; everything else is the name).

A showcase gym "Panatta Showroom" is (re)built to hold the whole catalogue.

Idempotent: re-running wipes the source-tagged rows + the showcase gym and rebuilds.

    python panatta_catalog.py            # build
    python panatta_catalog.py --dry      # extract + print, no DB writes
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

PDF = Path(__file__).resolve().parent.parent / "docs" / "panatta_general.pdf"
SOURCE = "panatta-brochure"
GYM_NAME = "Panatta Showroom"

# line label -> (grid pages [0-based], mechanism). Intro/blank pages excluded.
LINES: dict[str, tuple[list[int], str]] = {
    "XPLUX": ([18, 19, 20, 21], "selectorized"),
    "FIT EVO": ([24, 25, 26, 27, 28, 29, 30], "selectorized"),
    "SEC": ([33, 34, 35, 37], "selectorized"),
    "FREEWEIGHT HP": ([42, 43, 44, 45, 46, 47], "plate-loaded"),
    "OASIS": ([60, 61], "selectorized"),
    "MULTIMEDIA": ([65, 66], "selectorized"),
}

CODE = re.compile(r"^1[A-Za-z]{1,3}\d{2,4}[A-Za-z]?$")

# exact body-part / group tags Panatta prints above each render (lowercased,
# letters only). A segment that matches one of these is a category, not a name.
CAT_FULL = {
    "upperbody", "lowerbody", "core", "shoulders", "shoulder", "thighs", "thigh",
    "calves", "calf", "arms", "arm", "back", "dorsals", "pectorals", "abdomen",
    "multifunctional", "benches", "legs", "glutes", "biceps", "triceps",
}

# header / sub-label / spec noise that is never a machine name.
NOISE = re.compile(
    r"(designed|made in italy|strength|cardio|^services|special lines|\blines\b|"
    r"net tutor|ground pow|self pow|easy |optional|dimension|width|height|lenght|"
    r"weight|^load|standard|digit|\btech\b|n°|panatta|your logo|interactive|"
    r"guide|wall|^it$|^en$|^ar$)",
    re.I,
)

# name keyword -> exercise slug (first match wins; specific phrases first).
SLUG_RULES: list[tuple[str, str]] = [
    ("inclined chest", "incline-chest-press"),
    ("inclined bench", "incline-chest-press"),
    ("incline", "incline-chest-press"),
    ("vertical chest", "chest-press"),
    ("chest press", "chest-press"),
    ("pectoral", "pec-fly"),
    ("dips press", "triceps-dip"),
    ("peck back", "rear-delt"),
    ("back deltoid", "rear-delt"),
    ("lateral deltoid", "lateral-raise"),
    ("deltoid press", "shoulder-press"),
    ("deltoid", "shoulder-press"),
    ("shoulder bench", "shoulder-press"),
    ("shoulder", "shoulder-press"),
    ("lat machine", "lat-pulldown"),
    ("lat pull", "lat-pulldown"),
    ("pulldown", "lat-pulldown"),
    ("pullover", "pullover"),
    ("high row", "seated-row"),
    ("low row", "seated-row"),
    ("super rowing", "seated-row"),
    ("rowing", "seated-row"),
    ("row", "seated-row"),
    ("lower back", "back-extension"),
    ("iperextension", "back-extension"),
    ("hyperextension", "back-extension"),
    ("back extension", "back-extension"),
    ("upper abdominal", "ab-crunch"),
    ("abdominal", "ab-crunch"),
    ("crunch", "ab-crunch"),
    ("torsion", "torso-rotation"),
    ("twister", "torso-rotation"),
    ("twist", "torso-rotation"),
    ("leg extension", "leg-extension"),
    ("leg curling", "leg-curl"),
    ("leg curl", "leg-curl"),
    ("multi hip", "multi-hip"),
    ("abductor", "hip-abduction"),
    ("adductor", "hip-adduction"),
    ("gluteus", "glute"),
    ("glute", "glute"),
    ("calf", "calf-raise"),
    ("calves", "calf-raise"),
    ("leg press", "leg-press"),
    ("sissy squat", "hack-squat"),
    ("pendulum", "hack-squat"),
    ("hack", "hack-squat"),
    ("curling machine", "biceps-curl"),
    ("arm curl", "biceps-curl"),
    ("scott", "biceps-curl"),
    ("biceps", "biceps-curl"),
    ("curl", "biceps-curl"),
    ("arm extension", "triceps-extension"),
    ("triceps", "triceps-extension"),
    ("dip", "triceps-dip"),
    ("chin", "chin-up"),
    ("jammer", "jammer-press"),
]

MUSCLE: dict[str, str] = {
    "leg-extension": "quads", "leg-curl": "hamstrings", "leg-press": "quads · glutes",
    "hack-squat": "quads · glutes", "calf-raise": "calves", "hip-abduction": "outer thigh",
    "hip-adduction": "inner thigh", "multi-hip": "abductors · adductors", "glute": "glutes",
    "chest-press": "chest · triceps", "incline-chest-press": "upper chest", "pec-fly": "chest",
    "rear-delt": "rear delts", "shoulder-press": "delts · triceps", "lateral-raise": "delts",
    "lat-pulldown": "lats · biceps", "seated-row": "back · biceps", "pullover": "lats",
    "biceps-curl": "biceps", "triceps-extension": "triceps", "triceps-dip": "triceps · chest",
    "chin-up": "back · biceps", "ab-crunch": "abs", "torso-rotation": "obliques",
    "back-extension": "lower back", "jammer-press": "chest · shoulders",
}

# fallback muscle label from the body-part category when no slug matched.
CAT_MUSCLE = {
    "upperbody": "upper body", "lowerbody": "lower body", "core": "core",
    "shoulders": "delts", "thighs": "thighs", "calves": "calves", "arms": "arms",
    "back": "back", "dorsals": "back", "pectorals": "chest", "abdomen": "abs",
}


def is_render(im: dict) -> bool:
    b = im["bbox"]
    return (b[2] - b[0]) > 120 and (b[3] - b[1]) > 120 and im["width"] > 150


def catonly(txt: str) -> bool:
    return re.sub(r"[^a-z]", "", txt.lower()) in CAT_FULL


def segments(page) -> tuple[list, list]:
    """(name segments, category segments) as (cx, y, text), from text laid out
    into lines then split on horizontal gaps (so multi-column rows separate)."""
    ws = [w for w in page.get_text("words") if w[4].strip() and ord(w[4][0]) < 0x400]
    ws.sort(key=lambda w: (round(w[1] / 4), w[0]))
    lines: list[list] = []
    cy = None
    for w in ws:
        if cy is not None and abs(w[1] - cy) <= 4:
            lines[-1].append(w)
        else:
            lines.append([w])
        cy = w[1]
    names, cats = [], []
    for ln in lines:
        ln.sort(key=lambda w: w[0])
        part: list = []
        parts: list[list] = []
        for w in ln:
            if part and w[0] - part[-1][2] > 16:
                parts.append(part)
                part = []
            part.append(w)
        if part:
            parts.append(part)
        for p in parts:
            txt = " ".join(w[4] for w in p)
            if any(c.isdigit() for c in txt) or CODE.match(p[0][4]):
                continue
            cx = (p[0][0] + p[-1][2]) / 2
            if catonly(txt):
                cats.append((cx, p[0][1], txt))
                continue
            if NOISE.search(txt) or len(re.sub(r"[^A-Za-z]", "", txt)) < 3:
                continue
            names.append((cx, p[0][1], txt))
    return names, cats


def nearest_above(segs, cx, y0):
    cand = [s for s in segs if s[1] < y0 - 2 and abs(s[0] - cx) < 90]
    return max(cand, key=lambda s: s[1]) if cand else None


def code_under(page, bbox):
    x0, _, x1, y1 = bbox
    best, bd = None, 1e9
    for w in page.get_text("words"):
        if CODE.match(w[4]) and x0 - 10 <= w[0] <= x1 + 12 and -16 <= w[1] - y1 <= 46:
            d = abs(w[1] - y1)
            if d < bd:
                bd, best = d, w[4]
    return best


def slug_for(name: str):
    low = name.lower()
    for kw, slug in SLUG_RULES:
        if re.search(r"\b" + re.escape(kw), low):
            return slug
    return None


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


def extract(doc: fitz.Document) -> list[dict]:
    out: list[dict] = []
    seen: set[str] = set()
    for label, (pages, mech) in LINES.items():
        for pno in pages:
            page = doc.load_page(pno)
            renders = [im for im in page.get_image_info(xrefs=True) if is_render(im)]
            if len(renders) < 2:
                continue
            names, cats = segments(page)
            for im in renders:
                b = im["bbox"]
                cx = (b[0] + b[2]) / 2
                code = code_under(page, b)
                if not code or code in seen:
                    continue
                nm = nearest_above(names, cx, b[1])
                ct = nearest_above(cats, cx, b[1])
                if not nm:
                    continue                       # no readable name -> skip
                seen.add(code)
                out.append({
                    "line": label, "code": code, "name": nm[2].strip(),
                    "cat": (ct[2].strip() if ct else ""), "mech": mech,
                    "xref": im["xref"], "page": pno,
                })
    return out


def run(dry: bool = False) -> None:
    doc = fitz.open(PDF)
    machines = extract(doc)
    machines.sort(key=lambda m: (m["page"], m["code"]))
    for m in machines:
        m["slug"] = slug_for(m["name"])

    if dry:
        by_line: dict[str, int] = {}
        for m in machines:
            by_line[m["line"]] = by_line.get(m["line"], 0) + 1
            print(f"p{m['page']:>2} {m['code']:9s} {m['line']:14s} "
                  f"{m['name'][:34]:34s} [{m['cat']:14s}] -> {m['slug']}")
        print("\n--- per line ---")
        for k, v in by_line.items():
            print(f"  {k:<16} {v}")
        mapped = sum(1 for m in machines if m["slug"])
        print(f"\nTOTAL {len(machines)} machines, {mapped} movement-mapped.")
        return

    with Session(engine) as s:
        brand = s.exec(select(Brand).where(Brand.name == "Panatta")).first()
        if not brand:
            brand = Brand(name="Panatta", abbr="PA")
            s.add(brand)
            s.commit()
            s.refresh(brand)

        slug_to_id = {e.slug: e.id for e in s.exec(select(Exercise)).all()}

        old_gym = s.exec(select(Gym).where(Gym.name == GYM_NAME)).first()
        old_ids = [m.id for m in s.exec(
            select(Machine).where(Machine.source == SOURCE)).all()]
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
            if d["xref"] not in cache:
                cache[d["xref"]] = data_uri(doc, d["xref"])
            slug = d["slug"]
            muscle = MUSCLE.get(slug) if slug else None
            if not muscle:
                muscle = CAT_MUSCLE.get(re.sub(r"[^a-z]", "", d["cat"].lower()))
            m = Machine(
                brand_id=brand.id,
                model=f"{d['line']} {d['name'].title()} ({d['code']})",
                machine_type=d["mech"],
                exercise_id=slug_to_id.get(slug) if slug else None,
                muscle_label=muscle,
                image_url=cache[d["xref"]],
                source=SOURCE,
            )
            s.add(m)
            added.append(m)
        s.commit()
        for m in added:
            s.refresh(m)

        gym = Gym(name=GYM_NAME, area="made in Italy · demo")
        s.add(gym)
        s.commit()
        s.refresh(gym)
        for m in added:
            s.add(GymMachine(gym_id=gym.id, machine_id=m.id, added_by="catalog"))
        s.commit()

        mapped = sum(1 for d in machines if d["slug"])
        kb = sum(len(v) for v in cache.values()) * 3 // 4 // 1024
        print(f"Panatta: {len(added)} machines added ({mapped} movement-mapped), "
              f"{len(cache)} unique renders (~{kb}KB), gym '{GYM_NAME}' id={gym.id}.")


if __name__ == "__main__":
    run(dry="--dry" in sys.argv)
