"""Add Strive's "Smart Strength" selectorized line to the catalog.

Source: the Full Circle Padding "Strive > Smart Strength" parts page the user saved
to catalog/strive#.pdf (a printed webpage, so image-less here — the product photos on
that page are the reseller's watermarked stock shots, not ours to ship). Names + model
codes are transcribed from the 25 product tiles on that page.

Like atlantis_catalog.py, these rows are added on top of the base catalog under their
own source tag, idempotently — re-running clears only this source's rows first.

    python strive_catalog.py            # build
    python strive_catalog.py --dry      # print, no DB writes
"""
from __future__ import annotations

import sys

from sqlmodel import Session, delete, select

from database import engine
from models import Brand, Exercise, Machine

SOURCE = "strive-smart-strength"
BRAND = "Strive"
LINE = "Smart Strength"

# slug -> (display name, muscle_group) so we can create any exercise the base load
# happened not to include. Every slug below already exists in the shipped DB, but this
# keeps the script self-sufficient.
EX_META = {
    "ab-crunch": ("Ab Crunch", "core"),
    "biceps-curl": ("Biceps Curl", "pull"),
    "triceps-extension": ("Triceps Extension", "push"),
    "chest-press": ("Chest Press", "push"),
    "chin-up": ("Chin Up", "pull"),
    "lat-pulldown": ("Lat Pulldown", "pull"),
    "seated-row": ("Seated Row", "pull"),
    "incline-chest-press": ("Incline Chest Press", "push"),
    "hip-abduction": ("Hip Abduction", "legs"),
    "lateral-raise": ("Lateral Raise", "push"),
    "leg-extension": ("Leg Extension", "legs"),
    "leg-press": ("Leg Press", "legs"),
    "back-extension": ("Back Extension", "pull"),
    "multi-hip": ("Multi Hip", "legs"),
    "pec-fly": ("Pec Fly", "push"),
    "leg-curl": ("Leg Curl", "legs"),
    "pullover": ("Pullover", "pull"),
    "torso-rotation": ("Torso Rotation", "core"),
    "shoulder-press": ("Shoulder Press", "push"),
}

# (name, model code, machine_type, exercise slug | None, muscle_label | None)
MODELS: list[tuple[str, str, str, str | None, str | None]] = [
    ("Abdominal Crunch", "S-109", "selectorized", "ab-crunch", "abs"),
    ("Arm Curl", "S-101", "selectorized", "biceps-curl", "biceps"),
    ("Arm Extension", "S-117", "selectorized", "triceps-extension", "triceps"),
    ("Chest Press", "S-102", "selectorized", "chest-press", "chest"),
    ("Chin Up Dip Assist", "", "selectorized", "chin-up", "lats"),
    ("Diverging Lat Pull", "S-127", "selectorized", "lat-pulldown", "lats"),
    ("Diverging Seated Row", "S-128", "selectorized", "seated-row", "back"),
    ("Functional Trainer", "NS-123", "cable", None, None),
    ("Incline Press", "S-120", "selectorized", "incline-chest-press", "upper chest"),
    ("Inner Outer Thigh", "S-126", "selectorized", "hip-abduction", "inner · outer thigh"),
    ("Lat Pulldown", "S-104", "selectorized", "lat-pulldown", "lats"),
    ("Lat Raise", "S-119", "selectorized", "lateral-raise", "side delts"),
    ("Leg Extension", "S-105", "selectorized", "leg-extension", "quads"),
    ("Leg Press", "S-108", "selectorized", "leg-press", "quads"),
    ("Low Back", "S-110", "selectorized", "back-extension", "lower back"),
    ("Multi Hip", "S-114", "selectorized", "multi-hip", "glutes"),
    ("Pec Fly", "S-118", "selectorized", "pec-fly", "chest"),
    ("Pec Fly/Rear Delt", "S-129", "selectorized", "pec-fly", "chest · rear delts"),
    ("Prone Leg Curl", "S-106", "selectorized", "leg-curl", "hamstrings"),
    ("Pullover", "S-136", "selectorized", "pullover", "lats"),
    ("Rotary Torso", "S-111", "selectorized", "torso-rotation", "obliques"),
    ("Seated Leg Curl", "S-124", "selectorized", "leg-curl", "hamstrings"),
    ("Seated Push Down", "S-125", "selectorized", "triceps-extension", "triceps"),
    ("Seated Row", "S-121", "selectorized", "seated-row", "back"),
    ("Shoulder Press", "S-103", "selectorized", "shoulder-press", "delts"),
]


def _model_name(name: str, code: str) -> str:
    return f"{LINE} {name} {code}".strip() if code else f"{LINE} {name}"


def run(dry: bool = False) -> None:
    if dry:
        for name, code, mech, slug, muscle in MODELS:
            print(f"  {_model_name(name, code):42} {mech:12} -> {slug or '(none)':20} [{muscle or '-'}]")
        print(f"\n{len(MODELS)} machines (all image-less).")
        return

    with Session(engine) as s:
        brand = s.exec(select(Brand).where(Brand.name == BRAND)).first()
        if not brand:
            brand = Brand(name=BRAND, abbr="ST")
            s.add(brand)
            s.commit()
            s.refresh(brand)

        # get-or-create every exercise this line needs, keyed by slug
        ex_by_slug: dict[str, Exercise] = {}
        for slug in {m[3] for m in MODELS if m[3]}:
            ex = s.exec(select(Exercise).where(Exercise.slug == slug)).first()
            if not ex:
                nm, grp = EX_META[slug]
                ex = Exercise(slug=slug, name=nm, muscle_group=grp)
                s.add(ex)
                s.commit()
                s.refresh(ex)
            ex_by_slug[slug] = ex

        # idempotent: clear this source's prior rows
        s.exec(delete(Machine).where(Machine.source.like(f"{SOURCE}:%")))
        s.commit()

        added = 0
        for name, code, mech, slug, muscle in MODELS:
            model = _model_name(name, code)
            dupe = s.exec(select(Machine).where(
                Machine.brand_id == brand.id, Machine.model == model)).first()
            if dupe:
                print(f"  skip (already in catalog): {model}")
                continue
            ex = ex_by_slug.get(slug) if slug else None
            s.add(Machine(brand_id=brand.id, model=model, machine_type=mech,
                          exercise_id=ex.id if ex else None, muscle_label=muscle,
                          image_url=None, source=f"{SOURCE}:{code or name}"))
            added += 1
        s.commit()
        print(f"Strive Smart Strength: {added} machines added (image-less), brand id={brand.id}.")


if __name__ == "__main__":
    run(dry="--dry" in sys.argv)
