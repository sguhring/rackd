"""Categorize a machine model on two independent axes.

A machine in front of you is two things at once:

  1. a MECHANISM — how resistance is applied (plate-loaded, selectorized stack,
     cable/functional, smith/rack). Derived from Shopify product_type + tags.
  2. a MOVEMENT — what exercise it trains (chest press, row, leg press, …), which
     in turn carries the MUSCLES worked. Derived by keyword-matching the model name
     against a movement table seeded from the open free-exercise-db taxonomy.

Keeping these separate matters: the same movement (e.g. "row") exists as a
plate-loaded Hammer Strength and a selectorized Technogym, and rackd tracks
progression per machine because the load is not comparable across mechanisms.

This module is pure (no IO) so it is trivially testable.
"""
from __future__ import annotations

from dataclasses import dataclass

# --- mechanism axis -------------------------------------------------------
# Ordered: first matching rule wins. Keys are matched against product_type and tags.
MECHANISM_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("plate-loaded", ("plate-loaded", "plate loaded", "iso-lateral")),
    ("selectorized", ("selectorized", "select", "mts", "pin-loaded", "pin loaded")),
    ("cable",        ("cable", "functional trainer", "dual adjustable", "fts")),
    ("smith/rack",   ("smith", "rack", "half rack", "power rack")),
    ("cardio",       ("treadmill", "bike", "elliptical", "rower", "stair", "cardio")),
]
MECHANISM_DEFAULT = "machine"

# --- movement axis --------------------------------------------------------
# keyword (matched in the model name, longest first) -> (exercise slug, muscles)
# Muscle groups follow free-exercise-db's primaryMuscles vocabulary, condensed.
MOVEMENTS: list[tuple[str, str, str]] = [
    ("incline chest press", "incline-chest-press", "chest · front delts"),
    ("chest press",         "chest-press",         "chest · front delts"),
    ("shoulder press",      "shoulder-press",      "delts · triceps"),
    ("overhead press",      "shoulder-press",      "delts · triceps"),
    ("multi-press",         "shoulder-press",      "delts · triceps"),
    ("lat pulldown",        "lat-pulldown",        "lats · biceps"),
    ("pulldown",            "lat-pulldown",        "lats · biceps"),
    ("pullover",            "pullover",            "lats"),
    ("iso-lateral row",     "seated-row",          "lats · mid-back"),
    ("seated row",          "seated-row",          "mid-back · lats"),
    ("low row",             "seated-row",          "mid-back · lats"),
    ("high row",            "seated-row",          "upper-back · lats"),
    ("row",                 "seated-row",          "mid-back · lats"),
    ("rear delt",           "rear-delt",           "rear delts"),
    ("lateral raise",       "lateral-raise",       "side delts"),
    ("biceps curl",         "biceps-curl",         "biceps"),
    ("arm curl",            "biceps-curl",         "biceps"),
    ("triceps",             "triceps-extension",   "triceps"),
    ("pec",                 "pec-fly",             "chest"),
    ("fly",                 "pec-fly",             "chest"),
    ("leg press",           "leg-press",           "quads · glutes"),
    ("hack squat",          "hack-squat",          "quads · glutes"),
    ("leg extension",       "leg-extension",       "quads"),
    ("leg curl",            "leg-curl",            "hamstrings"),
    ("hamstring",           "leg-curl",            "hamstrings"),
    ("calf",                "calf-raise",          "calves"),
    ("hip thrust",          "hip-thrust",          "glutes"),
    ("glute",               "glute",               "glutes"),
    ("abductor / adductor", "hip-abduction",       "abductors · adductors"),
    ("hip abduction",       "hip-abduction",       "glutes · abductors"),
    ("abduction",           "hip-abduction",       "abductors"),
    ("abductor",            "hip-abduction",       "abductors"),
    ("adduction",           "hip-adduction",       "adductors"),
    ("adductor",            "hip-adduction",       "adductors"),
    ("abdominal",           "ab-crunch",           "abs"),
    ("ab crunch",           "ab-crunch",           "abs"),
    ("back extension",      "back-extension",      "lower back"),
    ("nordic ham",          "leg-curl",            "hamstrings"),
    ("dip",                 "triceps-dip",         "triceps · chest"),
    ("chin",                "chin-up",             "lats · biceps"),
    ("shrug",               "shrug",               "traps"),
    ("squat",               "hack-squat",          "quads · glutes"),
    ("jammer",              "jammer-press",        "chest · shoulders"),
    ("lat",                 "lat-pulldown",        "lats · biceps"),
]


@dataclass
class Category:
    mechanism: str            # how resistance is applied
    exercise_slug: str | None  # canonical movement, or None if unmatched
    muscle_label: str | None   # human muscle string for the UI

    @property
    def matched(self) -> bool:
        return self.exercise_slug is not None


def mechanism_for(product_type: str | None, tags: list[str] | None) -> str:
    hay = " ".join(filter(None, [(product_type or "").lower(), *(tags or [])]))
    for name, needles in MECHANISM_RULES:
        if any(n in hay for n in needles):
            return name
    return MECHANISM_DEFAULT


def movement_for(model: str) -> tuple[str | None, str | None]:
    m = model.lower()
    for needle, slug, muscles in MOVEMENTS:  # longest/most-specific listed first
        if needle in m:
            return slug, muscles
    return None, None


def categorize(model: str, product_type: str | None = None,
               tags: list[str] | None = None) -> Category:
    slug, muscles = movement_for(model)
    return Category(
        mechanism=mechanism_for(product_type, tags),
        exercise_slug=slug,
        muscle_label=muscles,
    )
