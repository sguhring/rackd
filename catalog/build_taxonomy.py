"""Build the machine taxonomy: body part -> muscle -> movement, plus facets.

Layer 1 (region) and layer 2 (muscle) come from muscle_label; layer 3 (movement)
comes from the `exercise` field, canonicalised so angle/implement/position
variants collapse onto ONE implement-agnostic movement node (chest-press and
incline-chest-press both -> "chest press"). The variation that was collapsed is
re-exposed as FACETS (angle / position / implement / laterality) parsed from the
model name + machine_type — orthogonal tags you filter by, not tree depth.
Secondary muscles come from the 2nd+ tokens of muscle_label (many-to-many).

Writes:
  catalog/taxonomy.json          the region->muscle->movement tree (+ facet vocab)
  catalog/machines_resolved.json  per-machine {region,muscle,movement,secondary,facets}

    python catalog/build_taxonomy.py
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CATALOG = ROOT / "catalog" / "scraped_machines.json"
OUT_TAX = ROOT / "catalog" / "taxonomy.json"
OUT_RES = ROOT / "catalog" / "machines_resolved.json"

# ---- layer 1 -> layer 2 : body part -> specific muscles (display order)
REGIONS: dict[str, list[str]] = {
    "chest":     ["upper chest", "mid chest", "lower chest"],
    "back":      ["lats", "upper-back", "mid-back", "lower back", "traps"],
    "shoulders": ["front delts", "side delts", "rear delts", "delts"],
    "arms":      ["biceps", "triceps", "forearms"],
    "legs":      ["quads", "hamstrings", "calves", "adductors", "abductors", "hip flexors", "shins"],
    "glutes":    ["glutes"],
    "abs":       ["abs", "obliques", "core"],
    "neck":      ["neck"],
}

# raw muscle_label token -> specific muscle
ALIAS: dict[str, str] = {
    "chest": "mid chest", "upper chest": "upper chest", "lower chest": "lower chest",
    "front delts": "front delts", "front delt": "front delts",
    "side delts": "side delts", "side delt": "side delts",
    "rear delts": "rear delts", "rear delt": "rear delts",
    "delts": "delts", "shoulders": "delts",
    "lats": "lats", "mid-back": "mid-back",
    "upper-back": "upper-back", "upper back": "upper-back",
    "lower back": "lower back", "traps": "traps",
    "biceps": "biceps", "triceps": "triceps", "forearms": "forearms", "forearm": "forearms",
    "quads": "quads", "hamstrings": "hamstrings", "calves": "calves",
    "adductors": "adductors", "abductors": "abductors", "hip flexors": "hip flexors",
    "shins": "shins", "tibialis": "shins",
    "glutes": "glutes",
    "abs": "abs", "obliques": "obliques", "core": "core",
    "neck": "neck",
}

# exercise value -> canonical, implement-agnostic movement node.
# angle/position/laterality are NOT encoded here — they fall out as facets.
MOVEMENT: dict[str, str] = {
    "chest-press": "chest press", "incline-chest-press": "chest press",
    "chest-press laying": "chest press", "chest press standing": "chest press",
    "pec-fly": "chest fly",
    "shoulder-press": "shoulder press", "shoulder press standing": "shoulder press",
    "lateral-raise": "lateral raise", "rear-delt": "rear-delt fly",
    "lat-pulldown": "pulldown",
    "seated-row": "row", "mid row": "row", "low row": "row", "high row": "row", "overhead row": "row",
    "upright row": "upright row",
    "chin-up": "pull-up / chin", "pullover": "pullover",
    "biceps-curl": "biceps curl", "triceps-extension": "triceps extension", "triceps-dip": "dip",
    "leg-extension": "leg extension",
    "leg-curl": "leg curl", "Leg curl kneeling": "leg curl",
    "leg-press": "leg press", "hack-squat": "hack / v-squat",
    "calf-raise": "calf raise", "calf rais": "calf raise",
    "tibia flexion": "tibialis raise",
    "glute": "glute (kickback/bridge)", "hip-thrust": "hip thrust",
    "hip-abduction": "hip abduction", "hip-adduction": "hip adduction", "multi-hip": "multi-hip",
    "back-extension": "back extension",
    "ab-crunch": "ab crunch", "Ab Crunch": "ab crunch",
    "leg-raise": "leg raise", "Leg raises": "leg raise",
    "torso-rotation": "torso rotation", "shrug": "shrug", "jammer-press": "jammer / push press",
}

MUSCLE_REGION = {m: r for r, ms in REGIONS.items() for m in ms}


def tokens(label: str) -> list[str]:
    return [t.strip().lower() for t in (label or "").replace("/", "·").split("·") if t.strip()]


def slug(s: str) -> str:
    return s.replace(" ", "-").replace("/", "-").replace("(", "").replace(")", "")


def canon_movement(ex: str | None) -> str | None:
    if not ex:
        return None
    e = ex.strip()
    return MOVEMENT.get(e) or MOVEMENT.get(e.lower()) or e.lower()


def facets(model: str, mtype: str) -> dict[str, str]:
    m = (model or "").lower()
    f: dict[str, str] = {}
    f["implement"] = {
        "plate-loaded": "plate-loaded", "selectorized": "selectorized",
        "cable": "cable", "smith/rack": "smith", "machine": "machine",
    }.get(mtype, "machine")
    if "incline" in m:
        f["angle"] = "incline"
    elif "decline" in m:
        f["angle"] = "decline"
    for kw, val in (("seated", "seated"), ("standing", "standing"),
                    ("prone", "lying"), ("lying", "lying"), ("kneeling", "kneeling")):
        if kw in m:
            f["position"] = val
            break
    if any(k in m for k in ("iso lateral", "iso-lateral", "unilateral")):
        f["laterality"] = "iso-lateral"
    elif "converging" in m:
        f["laterality"] = "converging"
    return f


def main() -> None:
    rows = json.loads(CATALOG.read_text(encoding="utf-8"))

    resolved = []
    mv_count: dict[tuple, Counter] = defaultdict(Counter)         # (region,muscle) -> movement counts
    mv_facets: dict[tuple, dict] = defaultdict(lambda: defaultdict(Counter))  # (r,m,mv) -> axis -> vals
    muscle_count: Counter = Counter()
    unassigned = 0

    for i, r in enumerate(rows):
        toks = [ALIAS[t] for t in tokens(r.get("muscle_label", "")) if t in ALIAS]
        primary = toks[0] if toks else None
        secondary = list(dict.fromkeys(toks[1:]))            # dedupe, keep order
        mv = canon_movement(r.get("exercise"))
        fc = facets(r.get("model", ""), r.get("machine_type", ""))
        resolved.append({
            "model": r.get("model"), "brand": r.get("brand"),
            "region": MUSCLE_REGION.get(primary, "functional-other") if primary else "functional-other",
            "muscle": primary, "movement": mv, "secondary": secondary, "facets": fc,
        })
        if primary:
            muscle_count[primary] += 1
            region = MUSCLE_REGION[primary]
            if mv:
                mv_count[(region, primary)][mv] += 1
                for ax, val in fc.items():
                    mv_facets[(region, primary, mv)][ax][val] += 1
        else:
            unassigned += 1

    # ---- assemble tree ----
    tree = []
    for region, muscles in REGIONS.items():
        rnode = {"slug": region, "label": region, "machines": 0, "muscles": []}
        for m in muscles:
            moves = mv_count.get((region, m), Counter())
            mnode = {
                "slug": slug(m), "label": m, "machines": muscle_count.get(m, 0),
                "movements": [
                    {
                        "slug": slug(mv), "label": mv, "machines": n,
                        "facets": {ax: dict(c) for ax, c in mv_facets[(region, m, mv)].items()},
                    }
                    for mv, n in moves.most_common()
                ],
            }
            rnode["muscles"].append(mnode)
        rnode["machines"] = sum(mm["machines"] for mm in rnode["muscles"])
        tree.append(rnode)
    tree.append({"slug": "functional-other", "label": "functional / other",
                 "machines": unassigned, "muscles": [],
                 "note": "no single target muscle; ~60 are unlabeled and will move into the tree later"})

    OUT_TAX.write_text(json.dumps({"version": 2, "regions": tree}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    OUT_RES.write_text(json.dumps(resolved, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    # ---- report ----
    print(f"wrote {OUT_TAX.name} + {OUT_RES.name}\n")
    movements = {mv for c in mv_count.values() for mv in c}
    print(f"regions {len(REGIONS)+1} · muscles attached {sum(1 for m in muscle_count if muscle_count[m])}"
          f" · distinct movements {len(movements)} · unassigned {unassigned}\n")
    for region in ("chest", "legs"):
        rnode = next(r for r in tree if r["slug"] == region)
        print(f"=== {region} ({rnode['machines']}) ===")
        for m in rnode["muscles"]:
            if not m["machines"]:
                continue
            print(f"  {m['label']} ({m['machines']})")
            for mv in m["movements"]:
                fac = " · ".join(f"{ax}:{'/'.join(v)}" for ax, v in mv["facets"].items() if ax != "implement")
                print(f"     {mv['label']:<22} {mv['machines']:>3}   {fac}")
        print()


if __name__ == "__main__":
    main()
