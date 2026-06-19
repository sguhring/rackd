"""Load the open exercise dataset (free-exercise-db / ExerciseDB) into the DB.

These are generic, brand-agnostic movements (barbell bench press, pull-up, …) — the
"reuse, don't rebuild" movement layer from docs/DATA_SOURCES.md. They become the
DEFAULT exercise options in the custom-workout builder, alongside the branded machines.

    python load_library.py     # wipes the library table and reloads from the dataset

Source: https://github.com/yuhonas/free-exercise-db (public domain).
"""
from __future__ import annotations

import json
import urllib.request

from sqlmodel import Session, delete

from database import engine, init_db
from models import LibraryExercise

SRC = "https://raw.githubusercontent.com/yuhonas/free-exercise-db/main/dist/exercises.json"
IMG = "https://raw.githubusercontent.com/yuhonas/free-exercise-db/main/exercises/"

# keep gym-relevant categories (skip stretching / plyometrics noise)
KEEP_CATEGORIES = {"strength", "strongman", "powerlifting", "olympic weightlifting"}

# primary muscle -> the builder's segment
GROUP_BY_MUSCLE = {
    "chest": "push", "shoulders": "push", "triceps": "push",
    "lats": "pull", "middle back": "pull", "lower back": "pull", "traps": "pull",
    "biceps": "pull", "forearms": "pull", "neck": "pull",
    "quadriceps": "legs", "hamstrings": "legs", "glutes": "legs", "calves": "legs",
    "abductors": "legs", "adductors": "legs",
    "abdominals": "core",
}


def _group(primary: list[str]) -> str:
    return GROUP_BY_MUSCLE.get((primary or [""])[0], "core")


def run() -> None:
    init_db()
    with urllib.request.urlopen(SRC, timeout=60) as r:   # noqa: S310 (trusted public dataset)
        data = json.loads(r.read().decode("utf-8"))

    with Session(engine) as s:
        s.exec(delete(LibraryExercise))
        s.commit()

        added = 0
        for e in data:
            if (e.get("category") or "").lower() not in KEEP_CATEGORIES:
                continue
            primary = e.get("primaryMuscles") or []
            equip = (e.get("equipment") or "").lower().replace("body only", "bodyweight")
            images = e.get("images") or []
            s.add(LibraryExercise(
                name=e["name"],
                equipment=equip or None,
                muscle_group=_group(primary),
                muscle_label=" · ".join(primary) if primary else None,
                category=(e.get("category") or None),
                image_url=(IMG + images[0]) if images else None,
            ))
            added += 1
        s.commit()
        print(f"Loaded {added} library exercises.")


if __name__ == "__main__":
    run()
