"""Fold the Booty Builder range into the catalog.

    python catalog/booty_to_catalog.py --write
    python catalog/build_taxonomy.py --from-resolved

Booty Builder is a glute-training specialist. Its 2025 commercial catalog
(docs/Booty-Builder-2025-Commercial-Catalog-.pdf) is a marketing brochure —
product names are prose headings with no model codes — so the range is
transcribed here directly (the same curated approach as Prime), then appended
to the hand-curated machines_resolved.json. Idempotent on (brand, model).

Two products ship in both a plate-loaded and a selectorized version (Standing
Abductor, Standing Hip Thrust); those get the implement in the model name so the
(brand, model) key stays unique and a user can tell them apart.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RESOLVED = ROOT / "catalog" / "machines_resolved.json"
BRAND = "Booty Builder"

# name -> (mechanism, region, muscle, movement, secondary)
TAX: dict[str, tuple] = {
    "Platinum V4":          ("Hip Thrust", "glutes", "glutes", "hip thrust", ["hamstrings"]),
    "Dual Hip Thrust":      ("Hip Thrust", "glutes", "glutes", "hip thrust", ["hamstrings"]),
    "Standing Hip Thrust":  ("Hip Thrust", "glutes", "glutes", "hip thrust", []),
    "V8.0":                 ("Hip Thrust", "glutes", "glutes", "hip thrust", ["hamstrings"]),
    "Belt Squat":           ("Belt Squat", "legs", "quads", "belt squat", ["glutes"]),
    "V-Squat":              ("Hack/V-Squat", "legs", "quads", "hack / v-squat", ["glutes"]),
    "Pendulum Squat":       ("Hack/V-Squat", "legs", "quads", "hack / v-squat", ["glutes"]),
    "Reverse Lunge Machine":("Lunge", "legs", "quads", "lunge", ["glutes"]),
    "Step-Up":              ("Lunge", "legs", "quads", "lunge", ["glutes"]),
    "Standing Abductor":    ("Hip Abduction", "legs", "abductors", "hip abduction", ["glutes"]),
    "3D Multi-Abductor":    ("Hip Abduction", "legs", "abductors", "hip abduction", ["glutes"]),
    "Standing Adductor":    ("Hip Adduction", "legs", "adductors", "hip adduction", []),
    "Kick Back":            ("Glute Kickback", "glutes", "glutes", "glute (kickback/bridge)", ["hamstrings"]),
    "Deadlift":             ("Deadlift/Squat machine", "legs", "hamstrings", "deadlift / squat", ["glutes", "lower back"]),
    "Deadlift/Split Squat": ("Deadlift/Squat machine", "legs", "quads", "deadlift / squat", ["glutes", "hamstrings"]),
    "Back Extension":       ("Back Extension", "back", "lower back", "back extension", ["glutes", "hamstrings"]),
}

# (name, implement); order = catalog order (plate-loaded section, then selectorized)
PLATE_LOADED = ["Platinum V4", "Dual Hip Thrust", "Belt Squat", "Reverse Lunge Machine",
                "Standing Abductor", "Standing Hip Thrust", "V-Squat"]
SELECTORIZED = ["3D Multi-Abductor", "Deadlift/Split Squat", "Step-Up", "Pendulum Squat",
                "Deadlift", "Standing Adductor", "Standing Abductor", "Kick Back",
                "Standing Hip Thrust", "V8.0", "Back Extension"]

# names that appear in both sections -> disambiguate by implement in the model
DUAL = {n for n in PLATE_LOADED if n in SELECTORIZED}


def rows() -> list[dict]:
    out = []
    for names, implement, impl_label in (
        (PLATE_LOADED, "plate-loaded", "Plate-Loaded"),
        (SELECTORIZED, "selectorized", "Selectorized"),
    ):
        for name in names:
            mech, region, muscle, movement, secondary = TAX[name]
            model = f"{BRAND} {name}"
            if name in DUAL:
                model = f"{model} ({impl_label})"
            out.append({
                "mechanism": mech, "model": model, "brand": BRAND,
                "region": region, "muscle": muscle, "movement": movement,
                "secondary": list(secondary), "facets": {"implement": implement},
            })
    return out


def main() -> None:
    data = rows()
    if "--write" not in sys.argv:
        for r in data:
            print(f"  {r['model']:44s} | {r['facets']['implement']:12s} | {r['movement']}")
        print(f"\n{len(data)} Booty Builder rows (dry run — pass --write to merge)")
        return
    resolved = json.loads(RESOLVED.read_text(encoding="utf-8"))
    have = {(m["brand"], m["model"]) for m in resolved}
    added = [r for r in data if (r["brand"], r["model"]) not in have]
    resolved.extend(added)
    RESOLVED.write_text(json.dumps(resolved, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8")
    print(f"added {len(added)} Booty Builder machines")
    print(f"machines_resolved.json now {len(resolved)} rows")
    if not added:
        print("  (nothing new — already merged)")


if __name__ == "__main__":
    main()
