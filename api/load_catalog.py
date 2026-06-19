"""Load the real scraped catalog (catalog/scraped_machines.json) into the DB and
build a few realistic demo gyms out of actual machines.

This replaces the tiny hand-written seed: ~1,350 machines across ~34 brands become
the global catalog, and each demo gym is a SUBSET of it (the core rackd idea) — e.g.
a Hammer Strength + Life Fitness floor, a Technogym + Matrix studio, a Gymleco box.

    python load_catalog.py        # wipes catalog tables and reloads from JSON
"""
from __future__ import annotations

import json
from pathlib import Path

from sqlmodel import Session, delete, select

from database import engine, init_db
from models import Brand, Exercise, Gym, GymMachine, Machine, Set, Workout

CATALOG = Path(__file__).resolve().parent.parent / "catalog" / "scraped_machines.json"

# exercise slug -> the segment the PWA filters by (push / pull / legs / core)
GROUP_BY_SLUG = {
    "chest-press": "push", "incline-chest-press": "push", "shoulder-press": "push",
    "pec-fly": "push", "triceps-extension": "push", "triceps-dip": "push",
    "jammer-press": "push", "lateral-raise": "push",
    "lat-pulldown": "pull", "seated-row": "pull", "pullover": "pull",
    "rear-delt": "pull", "biceps-curl": "pull", "chin-up": "pull", "shrug": "pull",
    "back-extension": "pull",
    "leg-press": "legs", "hack-squat": "legs", "leg-extension": "legs",
    "leg-curl": "legs", "calf-raise": "legs", "hip-thrust": "legs", "glute": "legs",
    "hip-abduction": "legs", "hip-adduction": "legs", "multi-hip": "legs",
    "ab-crunch": "core", "torso-rotation": "core", "leg-raise": "core",
}

# Demo gyms: (name, area, [brands to draw from], how many machines). Each is filled
# from the real catalog, preferring machines mapped to a movement.
DEMO_GYMS = [
    ("Iron Works",      "downtown",   ["Hammer Strength", "Life Fitness"], 20),
    ("Pulse Studio",    "midtown",    ["Technogym", "Matrix"],             16),
    ("Nordic Strength", "harbour",    ["Gymleco"],                         20),
    ("Legacy Fitness",  "old town",   ["Cybex", "Nautilus", "Precor"],     20),
    ("The Vault",       "warehouse",  ["Hoist", "Muscle D", "Keiser", "FreeMotion", "MedX"], 18),
]


def _name_from_slug(slug: str) -> str:
    return slug.replace("-", " ").title()


def run() -> None:
    init_db()
    rows = json.loads(CATALOG.read_text(encoding="utf-8"))

    with Session(engine) as s:
        # clean slate for the catalog tables (dev only)
        for model in (Set, Workout, GymMachine, Machine, Exercise, Gym, Brand):
            s.exec(delete(model))
        s.commit()

        # --- brands ---
        brands: dict[str, Brand] = {}
        for r in rows:
            bn = r["brand"]
            if bn not in brands:
                brands[bn] = Brand(name=bn, abbr=_abbr(bn))
        for b in brands.values():
            s.add(b)
        s.commit()
        for b in brands.values():
            s.refresh(b)

        # --- exercises (distinct movement slugs present in the catalog) ---
        exercises: dict[str, Exercise] = {}
        for r in rows:
            slug = r.get("exercise")
            if slug and slug not in exercises:
                exercises[slug] = Exercise(
                    slug=slug, name=_name_from_slug(slug),
                    muscle_group=GROUP_BY_SLUG.get(slug, "core"),
                )
        for e in exercises.values():
            s.add(e)
        s.commit()
        for e in exercises.values():
            s.refresh(e)

        # --- machines (the global catalog) ---
        machines: list[Machine] = []
        for r in rows:
            ex = exercises.get(r.get("exercise"))
            m = Machine(
                brand_id=brands[r["brand"]].id,
                model=r["model"],
                machine_type=r.get("machine_type"),
                exercise_id=ex.id if ex else None,
                muscle_label=r.get("muscle_label"),
                image_url=r.get("image_url"),
                source=r.get("source"),
            )
            machines.append(m)
            s.add(m)
        s.commit()
        for m in machines:
            s.refresh(m)

        # --- demo gyms, each a real subset of the catalog ---
        by_brand: dict[str, list[Machine]] = {}
        for m in machines:
            by_brand.setdefault(brands_inv(brands, m.brand_id), []).append(m)

        gym_count = 0
        for name, area, brand_names, n in DEMO_GYMS:
            pool: list[Machine] = []
            for bn in brand_names:
                pool += by_brand.get(bn, [])
            picked = _spread(pool, n)
            if not picked:
                continue
            gym = Gym(name=name, area=f"{area} · demo")
            s.add(gym)
            s.commit()
            s.refresh(gym)
            for m in picked:
                s.add(GymMachine(gym_id=gym.id, machine_id=m.id, added_by="catalog"))
            s.commit()
            gym_count += 1

        print(f"Loaded {len(brands)} brands, {len(exercises)} exercises, "
              f"{len(machines)} machines, {gym_count} demo gyms.")


def _abbr(brand: str) -> str:
    parts = [p for p in brand.replace("-", " ").split() if p]
    if len(parts) >= 2:
        return (parts[0][0] + parts[1][0]).upper()
    return brand[:2].upper()


def brands_inv(brands: dict[str, Brand], brand_id: int) -> str:
    for name, b in brands.items():
        if b.id == brand_id:
            return name
    return ""


def _spread(pool: list[Machine], n: int) -> list[Machine]:
    """Pick up to n machines, preferring mapped ones and a spread of movements."""
    mapped = [m for m in pool if m.exercise_id]
    rest = [m for m in pool if not m.exercise_id]
    out: list[Machine] = []
    seen_models: set[str] = set()
    seen_ex: set[int] = set()
    # first pass: one per distinct movement (variety)
    for m in mapped:
        if m.exercise_id in seen_ex or m.model in seen_models:
            continue
        out.append(m); seen_ex.add(m.exercise_id); seen_models.add(m.model)
        if len(out) >= n:
            return out
    # fill with more mapped, then unmapped
    for m in mapped + rest:
        if m.model in seen_models:
            continue
        out.append(m); seen_models.add(m.model)
        if len(out) >= n:
            break
    return out


if __name__ == "__main__":
    run()
