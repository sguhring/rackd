"""Map RawMachine records from scrapers into the DB schema.

Responsibilities:
  - canonicalise brand names (e.g. 'hammer strength' -> 'Hammer Strength')
  - dedupe (brand, model) against what's already in the catalog
  - best-effort map each machine to an exercise slug by keyword
  - upsert Brand + Machine rows

This is intentionally small; the hard part is the scrapers, not the mapping.
"""
from __future__ import annotations

from sqlmodel import Session, select

from scrapers.base import RawMachine  # noqa: E402

# keyword -> exercise slug (extend as the catalog grows)
EXERCISE_KEYWORDS = {
    "chest press": "chest-press",
    "shoulder press": "shoulder-press",
    "lat pulldown": "lat-pulldown",
    "row": "seated-row",
    "leg press": "leg-press",
    "leg extension": "leg-extension",
    "leg curl": "leg-curl",
}

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


def guess_exercise_slug(model: str) -> str | None:
    m = model.lower()
    for kw, slug in EXERCISE_KEYWORDS.items():
        if kw in m:
            return slug
    return None


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

        slug = guess_exercise_slug(r.model)
        ex = session.exec(select(Exercise).where(Exercise.slug == slug)).first() if slug else None
        session.add(Machine(
            brand_id=brand.id, model=r.model,
            exercise_id=ex.id if ex else None,
            image_url=r.image_url, source=r.source,
        ))
        added += 1
    session.commit()
    return added
