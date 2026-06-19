"""Map RawMachine records from scrapers into the DB schema.

Responsibilities:
  - canonicalise brand names (e.g. 'hammer strength' -> 'Hammer Strength')
  - dedupe (brand, model) against what's already in the catalog
  - categorize each machine (mechanism + movement + muscles) via categorize.py
  - upsert Brand + Machine rows

This is intentionally small; the hard part is the scrapers, not the mapping.
"""
from __future__ import annotations

from sqlmodel import Session, select

from categorize import categorize
from scrapers.base import RawMachine  # noqa: E402

BRAND_CANON = {
    "hammer strength": "Hammer Strength",
    "life fitness": "Life Fitness",
    "technogym": "Technogym",
    "cybex": "Cybex",
    "matrix": "Matrix",
    "precor": "Precor",
}


def canon_brand(raw: str) -> str:
    return BRAND_CANON.get(raw.strip().lower(), raw.strip())


def upsert(session: Session, records: list[RawMachine]) -> int:
    """Insert new (brand, model) machines; returns count added. Stub-safe."""
    from models import Brand, Exercise, Machine  # local import; api/ on path

    added = 0
    for r in records:
        bname = canon_brand(r.brand)
        brand = session.exec(select(Brand).where(Brand.name == bname)).first()
        if not brand:
            brand = Brand(name=bname)
            session.add(brand)
            session.commit()
            session.refresh(brand)

        exists = session.exec(
            select(Machine).where(Machine.brand_id == brand.id, Machine.model == r.model)
        ).first()
        if exists:
            continue

        cat = categorize(r.model, r.category, r.extra.get("tags"))
        ex = (session.exec(select(Exercise).where(Exercise.slug == cat.exercise_slug)).first()
              if cat.exercise_slug else None)
        session.add(Machine(
            brand_id=brand.id, model=r.model,
            machine_type=cat.mechanism,
            exercise_id=ex.id if ex else None,
            muscle_label=cat.muscle_label,
            image_url=r.image_url, source=r.source,
        ))
        added += 1
    session.commit()
    return added
