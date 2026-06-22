"""Add the PRIME Fitness (Specialty Fitness Systems, USA) strength catalog from
their product brochure to the DB, with each model's own white-background product
render inlined as a base64 data URI.

PRIME builds US selectorized + plate-loaded machines (known for the SmartStrength
cam). This imports the three core strength lines a user picks from:

    Evolution (selectorized) · Hybrid (selectorized) · Plate Loaded

Brochure layout: each line page is a 2-column grid of square product thumbnails
with the model NAME in caps directly to the RIGHT of each thumbnail, dimensions
below it. So we bind each thumbnail to the caps name at its top-right.

A showcase gym "PRIME Fitness Showroom" is (re)built to hold the catalogue.

Idempotent: re-running wipes the source-tagged rows + the showcase gym and rebuilds.

    python prime_catalog.py            # build
    python prime_catalog.py --dry      # extract + print, no DB writes
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

PDF = Path(__file__).resolve().parent.parent / "docs" / "prime.pdf"
SOURCE = "prime-brochure"
GYM_NAME = "PRIME Fitness Showroom"

# line label -> (grid pages [0-based], mechanism).
LINES: dict[str, tuple[list[int], str]] = {
    "Evolution": ([8, 9], "selectorized"),
    "Hybrid": ([11, 12, 13], "selectorized"),
    "Plate Loaded": ([15, 16], "plate-loaded"),
}

# caps tokens that are feature callouts / boilerplate, never a machine name.
NOISE = {"UPGRADE", "FEATURES", "NEW", "OPTIONS", "ACCESSORIES", "PRIME", "USA",
         "COM", "LLC", "THE", "AND", "FOR", "ROT8", "REVOLUTION", "JOIN"}

SLUG_RULES: list[tuple[str, str]] = [
    ("incline press", "incline-chest-press"),
    ("chest press", "chest-press"),
    ("pec fly", "pec-fly"),
    ("pec", "pec-fly"),
    ("shoulder press", "shoulder-press"),
    ("lateral raise", "lateral-raise"),
    ("lat pulldown", "lat-pulldown"),
    ("pulldown", "lat-pulldown"),
    ("pullover", "pullover"),
    ("seated row", "seated-row"),
    ("extreme row", "seated-row"),
    ("row", "seated-row"),
    ("back extension", "back-extension"),
    ("abdominal", "ab-crunch"),
    ("crunch", "ab-crunch"),
    ("rotary torso", "torso-rotation"),
    ("leg extension", "leg-extension"),
    ("prone leg curl", "leg-curl"),
    ("seated leg curl", "leg-curl"),
    ("leg curl", "leg-curl"),
    ("leg press", "leg-press"),
    ("seated calf", "calf-raise"),
    ("calf", "calf-raise"),
    ("multi-hip", "multi-hip"),
    ("arm curl", "biceps-curl"),
    ("curl", "biceps-curl"),
    ("pushdown", "triceps-extension"),
    ("tricep", "triceps-extension"),
]

MUSCLE: dict[str, str] = {
    "leg-extension": "quads", "leg-curl": "hamstrings", "leg-press": "quads · glutes",
    "calf-raise": "calves", "multi-hip": "abductors · adductors",
    "chest-press": "chest · triceps", "incline-chest-press": "upper chest", "pec-fly": "chest",
    "shoulder-press": "delts · triceps", "lateral-raise": "delts",
    "lat-pulldown": "lats · biceps", "seated-row": "back · biceps", "pullover": "lats",
    "biceps-curl": "biceps", "triceps-extension": "triceps", "ab-crunch": "abs",
    "torso-rotation": "obliques", "back-extension": "lower back",
}


def is_thumb(im: dict) -> bool:
    b = im["bbox"]
    w, h = b[2] - b[0], b[3] - b[1]
    return 80 < w < 160 and 80 < h < 170 and im["width"] > 120


def name_right(page, bbox) -> str:
    x0, y0, x1, y1 = bbox
    band = [
        w for w in page.get_text("words")
        if y0 - 12 <= w[1] <= y0 + 30 and x1 - 6 <= w[0] <= x1 + 175
        and w[4].isupper() and len(re.sub(r"[^A-Z]", "", w[4])) >= 2
        and not re.match(r"\d", w[4])
    ]
    band.sort(key=lambda w: w[0])
    words = [w[4] for w in band if w[4] not in ("L", "W", "H", "IN", "CM")]
    if not words or words[0] in NOISE:
        return ""
    return " ".join(words).strip()


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
    for label, (pages, mech) in LINES.items():
        for pno in pages:
            page = doc.load_page(pno)
            thumbs = [im for im in page.get_image_info(xrefs=True) if is_thumb(im)]
            for im in sorted(thumbs, key=lambda i: (round(i["bbox"][1] / 20), i["bbox"][0])):
                nm = name_right(page, im["bbox"])
                if not nm:
                    continue
                out.append({
                    "line": label, "name": nm.title(), "mech": mech,
                    "xref": im["xref"], "page": pno,
                })
    return out


def run(dry: bool = False) -> None:
    doc = fitz.open(PDF)
    machines = extract(doc)
    for m in machines:
        m["slug"] = slug_for(m["name"])

    if dry:
        for m in machines:
            print(f"p{m['page']:>2} {m['line']:13s} {m['name']:26s} -> {m['slug']}")
        mapped = sum(1 for m in machines if m["slug"])
        print(f"\nTOTAL {len(machines)} machines, {mapped} movement-mapped.")
        return

    with Session(engine) as s:
        brand = s.exec(select(Brand).where(Brand.name == "PRIME Fitness")).first()
        if not brand:
            brand = Brand(name="PRIME Fitness", abbr="PR")
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
            m = Machine(
                brand_id=brand.id,
                model=f"{d['line']} {d['name']}",
                machine_type=d["mech"],
                exercise_id=slug_to_id.get(slug) if slug else None,
                muscle_label=MUSCLE.get(slug) if slug else None,
                image_url=cache[d["xref"]],
                source=SOURCE,
            )
            s.add(m)
            added.append(m)
        s.commit()
        for m in added:
            s.refresh(m)

        gym = Gym(name=GYM_NAME, area="made in the USA · demo")
        s.add(gym)
        s.commit()
        s.refresh(gym)
        for m in added:
            s.add(GymMachine(gym_id=gym.id, machine_id=m.id, added_by="catalog"))
        s.commit()

        mapped = sum(1 for d in machines if d["slug"])
        kb = sum(len(v) for v in cache.values()) * 3 // 4 // 1024
        print(f"PRIME: {len(added)} machines added ({mapped} movement-mapped), "
              f"{len(cache)} unique renders (~{kb}KB), gym '{GYM_NAME}' id={gym.id}.")


if __name__ == "__main__":
    run(dry="--dry" in sys.argv)
