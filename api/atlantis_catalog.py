"""Add Atlantis Strength's biceps-machine line to the catalog.

Unlike the brochure-driven brand scripts, the source here was a set of product
photos the user pasted into chat (Atlantis "Biceps Machines" page), so there is no
PDF to crop and these rows go in IMAGE-LESS. Names + model codes are transcribed
from those photos; drop an Atlantis PDF in docs/ and extend this to attach renders
the same way megamass_catalog.py does.

The existing Atlantis rows come from the base scraped_machines.json load; these are
added on top under their own source tag, idempotently.

    python atlantis_catalog.py            # build
    python atlantis_catalog.py --dry      # print, no DB writes
"""
from __future__ import annotations

import sys
from pathlib import Path

from sqlmodel import Session, delete, select

from database import engine
from models import Brand, Exercise, Machine

SOURCE = "atlantis-biceps"
BRAND = "Atlantis"
SLUG = "biceps-curl"

# (product name, model code, mechanism, muscle_label) — from the pasted page photos.
# Names are kept plain (no code suffix) so machine identity stays human-readable and,
# for "Horizontal Biceps Isolator", matches the on-device history that references it.
MODELS: list[tuple[str, str, str, str]] = [
    ("Poliquin Seated Preacher Curl", "B856", "bench", "biceps"),
    ("Biceps Curl", "B157", "selectorized", "biceps"),
    ("Horizontal Curl", "B158", "selectorized", "biceps"),
    ("Biceps Isolator", "B160", "selectorized", "biceps"),
    ("Horizontal Biceps Isolator", "B260", "selectorized", "biceps"),
    ("Preacher Curl", "PW357", "plate-loaded", "biceps"),
    ("Seated Preacher Curl", "B256", "bench", "biceps"),
    ("Standing Bicep Curl", "B257", "selectorized", "biceps"),
]


def run(dry: bool = False) -> None:
    if dry:
        for name, code, mech, muscle in MODELS:
            print(f"  {name:32} [{code:6}] {mech:12} -> {SLUG} [{muscle}]  NO-IMG")
        print(f"\n{len(MODELS)} machines (all image-less).")
        return

    with Session(engine) as s:
        brand = s.exec(select(Brand).where(Brand.name == BRAND)).first()
        if not brand:
            brand = Brand(name=BRAND, abbr="AT")
            s.add(brand)
            s.commit()
            s.refresh(brand)

        ex = s.exec(select(Exercise).where(Exercise.slug == SLUG)).first()
        if not ex:
            ex = Exercise(slug=SLUG, name="Biceps Curl", muscle_group="pull")
            s.add(ex)
            s.commit()
            s.refresh(ex)

        # idempotent: clear this source's rows (source is "atlantis-biceps:<code>")
        s.exec(delete(Machine).where(Machine.source.like(f"{SOURCE}:%")))
        s.commit()

        added = 0
        for name, code, mech, muscle in MODELS:
            # our own rows were just deleted, so any remaining match is a base-load
            # row with the same name — don't duplicate it.
            dupe = s.exec(select(Machine).where(
                Machine.brand_id == brand.id, Machine.model == name)).first()
            if dupe:
                print(f"  skip (already in catalog): {name}")
                continue
            s.add(Machine(brand_id=brand.id, model=name, machine_type=mech,
                          exercise_id=ex.id, muscle_label=muscle,
                          image_url=None, source=f"{SOURCE}:{code}"))
            added += 1
        s.commit()
        print(f"Atlantis biceps: {added} machines added (image-less), brand id={brand.id}.")


if __name__ == "__main__":
    run(dry="--dry" in sys.argv)
