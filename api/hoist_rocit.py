"""Add HOIST's ROC-IT Plate Loaded (RPL) line to the catalog, with the official
brochure renders inlined as base64.

The existing Hoist rows are a mix of selectorized + secondhand listings; this adds
the full, current ROC-IT plate-loaded line as clean recognisable models. A showcase
gym "Hoist ROC-IT Studio" is (re)built so they're pickable in the app immediately.

Idempotent: re-running wipes the source-tagged rows + the showcase gym and rebuilds.

    python hoist_rocit.py
"""
from __future__ import annotations

import base64
from pathlib import Path

import fitz
from sqlmodel import Session, delete, select

from database import engine
from models import Brand, Exercise, Gym, GymMachine, Machine

PDF = Path(__file__).resolve().parent.parent / "tools" / "hoist_rocit" / "brochure.pdf"
SOURCE = "hoist-rocit-brochure"
GYM_NAME = "Hoist ROC-IT Studio"

# (model code, display name, exercise slug | None, muscle label, hero image xref)
MACHINES: list[tuple[str, str, str | None, str, int]] = [
    ("RPL-5101", "Seated Dip", "triceps-dip", "triceps", 10),
    ("RPL-5102", "Biceps Curl", "biceps-curl", "biceps", 15),
    ("RPL-5201", "Lat Pulldown", "lat-pulldown", "lats · biceps", 20),
    ("RPL-5203", "Seated Mid Row", "seated-row", "back · biceps", 25),
    ("RPL-5301", "Chest Press", "chest-press", "chest · triceps", 30),
    ("RPL-5303", "Incline Chest Press", "incline-chest-press", "upper chest", 33),
    ("RPL-5305", "Decline Chest Press", "chest-press", "lower chest", 38),
    ("RPL-5356", "Hack Squat / Dead Lift / Shrug", "hack-squat", "legs · back", 42),
    ("RPL-5363", "Seated Calf Raise", "calf-raise", "calves", 49),
    ("RPL-5403", "Dual Action Leg Press", "leg-press", "quads · glutes", 53),
    ("RPL-5405", "Standing Calf Raise", "calf-raise", "calves", 60),
    ("RPL-5501", "Shoulder Press", "shoulder-press", "delts · triceps", 65),
    ("RPL-5601", "Abdominals", "ab-crunch", "abs", 73),
]


def data_uri(doc: fitz.Document, xref: int) -> str:
    pix = fitz.Pixmap(doc, xref)
    if pix.colorspace and pix.colorspace.n == 4:        # CMYK -> RGB
        pix = fitz.Pixmap(fitz.csRGB, pix)
    if pix.width > 320:                                  # downscale to a tile-sized render
        pix.shrink(1)
    if pix.alpha:
        pix = fitz.Pixmap(pix, 0)
    jpg = pix.tobytes("jpg", jpg_quality=82)
    return "data:image/jpeg;base64," + base64.b64encode(jpg).decode("ascii")


def run() -> None:
    doc = fitz.open(PDF)

    with Session(engine) as s:
        brand = s.exec(select(Brand).where(Brand.name == "Hoist")).first()
        if not brand:
            brand = Brand(name="Hoist", abbr="HO")
            s.add(brand)
            s.commit()
            s.refresh(brand)

        slug_to_id = {e.slug: e.id for e in s.exec(select(Exercise)).all()}

        # idempotent reset
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

        added: list[Machine] = []
        for code, name, slug, muscle, xref in MACHINES:
            m = Machine(
                brand_id=brand.id,
                model=f"ROC-IT {name} ({code})",
                machine_type="plate-loaded",
                exercise_id=slug_to_id.get(slug) if slug else None,
                muscle_label=muscle,
                image_url=data_uri(doc, xref),
                source=SOURCE,
            )
            s.add(m)
            added.append(m)
        s.commit()
        for m in added:
            s.refresh(m)

        gym = Gym(name=GYM_NAME, area="ride oriented · demo")
        s.add(gym)
        s.commit()
        s.refresh(gym)
        for m in added:
            s.add(GymMachine(gym_id=gym.id, machine_id=m.id, added_by="catalog"))
        s.commit()

        print(f"Hoist ROC-IT: {len(added)} plate-loaded machines added, "
              f"gym '{GYM_NAME}' id={gym.id}.")


if __name__ == "__main__":
    run()
