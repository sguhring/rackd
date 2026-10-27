"""English machine names -> rackd taxonomy (region/muscle/movement/mechanism).

The English counterpart to hbp_map.py (which handles German). Used by the
per-brand PDF folders (Arsenal, Booty Builder, Watson, ...) whose catalogs are
in English. Rules are keyword-based, ordered MOST SPECIFIC FIRST — the same
shape as categorize.py and hbp_map.py.

Every value emitted here is checked against what machines_resolved.json already
uses; no new mechanism/region/muscle/movement strings are invented, so the
faceted taxonomy rebuilds cleanly. Pieces that aren't a single trainable
movement (racks, benches, smith, storage) resolve to region "functional-other"
with movement/muscle None, exactly like the existing functional-other rows.

Each rule: (keywords_all_match, mechanism, region, muscle, movement, secondary)
"""
from __future__ import annotations

import re


def norm(s: str) -> str:
    s = s.lower().replace("-", " ").replace("/", " ")
    return " ".join(re.sub(r"[^a-z0-9 ]", " ", s).split())


# fmt: off
RULES: list[tuple[tuple[str, ...], str | None, str, str | None, str | None, list[str]]] = [
    # --- chest -------------------------------------------------------------
    (("incline", "shoulder"),   "Shoulder Press", "shoulders", "delts", "shoulder press", ["triceps"]),
    (("incline", "fly"),        "Incline Chest Fly", "chest", "upper chest", "chest fly", ["front delts"]),
    (("incline", "chest press"),"Incline Chest Press", "chest", "upper chest", "chest press", ["front delts"]),
    (("incline", "press"),      "Incline Chest Press", "chest", "upper chest", "chest press", ["front delts"]),
    (("decline", "press"),      "Decline Chest Press", "chest", "lower chest", "chest press", ["triceps"]),
    (("chest press",),          "Chest Press", "chest", "mid chest", "chest press", ["front delts", "triceps"]),
    (("bench press",),          "Chest Press", "chest", "mid chest", "chest press", ["front delts", "triceps"]),
    (("pec", "rear delt"),      "Chest Fly", "chest", "mid chest", "chest fly", ["rear delts"]),
    (("pec deck",),             "Chest Fly", "chest", "mid chest", "chest fly", []),
    (("pec fly",),              "Chest Fly", "chest", "mid chest", "chest fly", []),
    (("chest fly",),            "Chest Fly", "chest", "mid chest", "chest fly", []),
    (("fly",),                  "Chest Fly", "chest", "mid chest", "chest fly", []),
    # --- shoulders ---------------------------------------------------------
    (("shoulder press",),       "Shoulder Press", "shoulders", "delts", "shoulder press", ["triceps"]),
    (("overhead press",),       "Shoulder Press", "shoulders", "delts", "shoulder press", ["triceps"]),
    (("military press",),       "Shoulder Press", "shoulders", "delts", "shoulder press", ["triceps"]),
    (("viking press",),         "Shoulder Press", "shoulders", "delts", "shoulder press", ["triceps"]),
    (("multi press",),          "Shoulder Press", "shoulders", "delts", "shoulder press", ["triceps"]),
    (("jammer",),               "Jammer Press", "chest", "mid chest", "jammer / push press", ["delts", "triceps"]),
    (("push press",),           "Jammer Press", "chest", "mid chest", "jammer / push press", ["delts", "triceps"]),
    (("lateral raise",),        "Lateral Raise", "shoulders", "side delts", "lateral raise", []),
    (("side lateral",),         "Lateral Raise", "shoulders", "side delts", "lateral raise", []),
    (("rear delt",),            "Rear-Delt Fly", "shoulders", "rear delts", "rear-delt fly", []),
    (("reverse fly",),          "Rear-Delt Fly", "shoulders", "rear delts", "rear-delt fly", []),
    (("upright row",),          "Upright Row", "shoulders", "delts", "upright row", ["traps"]),
    # --- back --------------------------------------------------------------
    (("lat pulldown",),         "Lat Pulldown", "back", "lats", "pulldown", ["biceps"]),
    (("lat pull",),             "Lat Pulldown", "back", "lats", "pulldown", ["biceps"]),
    (("pulldown",),             "Lat Pulldown", "back", "lats", "pulldown", ["biceps"]),
    (("iso lat",),              "Lat Pulldown", "back", "lats", "pulldown", ["biceps"]),
    (("pullover",),             "Pullover", "back", "lats", "pullover", []),
    (("t bar row",),            "T-Bar Row", "back", "mid-back", "row", ["lats"]),
    (("high row",),             "High Row", "back", "upper-back", "row", ["lats"]),
    (("low row",),              "Low Row", "back", "mid-back", "row", ["lats"]),
    (("seated row",),           "Seated Row", "back", "mid-back", "row", ["lats"]),
    (("lever row",),            "Row", "back", "mid-back", "row", ["lats"]),
    (("vertical row",),         "Row", "back", "mid-back", "row", ["lats"]),
    (("multi row",),            "Row", "back", "mid-back", "row", ["lats"]),
    (("iso row",),              "Row", "back", "mid-back", "row", ["lats"]),
    (("row",),                  "Row", "back", "mid-back", "row", ["lats"]),
    (("hyperextension",),       "Back Extension", "back", "lower back", "back extension", ["glutes"]),
    (("hyper", "extension"),    "Back Extension", "back", "lower back", "back extension", ["glutes"]),
    (("back extension",),       "Back Extension", "back", "lower back", "back extension", ["glutes"]),
    (("roman chair",),          "Back Extension", "back", "lower back", "back extension", ["glutes"]),
    (("glute ham",),            "Back Extension", "back", "lower back", "back extension", ["hamstrings", "glutes"]),
    (("glute hamstring",),      "Back Extension", "back", "lower back", "back extension", ["hamstrings", "glutes"]),
    (("ghd",),                  "Back Extension", "back", "lower back", "back extension", ["hamstrings", "glutes"]),
    (("reverse hyper",),        "Reverse Hyper", "back", "lower back", "back extension", ["glutes"]),
    (("assisted pull",),        "Assisted Pull-up", "back", "lats", "pull-up / chin", ["biceps"]),
    (("chin",),                 "Assisted Pull-up", "back", "lats", "pull-up / chin", ["biceps"]),
    (("shrug",),                "Shrug", "back", "traps", "shrug", []),
    # --- arms --------------------------------------------------------------
    (("overhead tricep",),      "Triceps Extension", "arms", "triceps", "triceps extension", []),
    (("tricep", "dip"),         "Dip", "arms", "triceps", "dip", ["mid chest"]),
    (("triceps",),              "Triceps Extension", "arms", "triceps", "triceps extension", []),
    (("tricep",),               "Triceps Extension", "arms", "triceps", "triceps extension", []),
    (("pushdown",),             "Triceps Pushdown", "arms", "triceps", "triceps extension", []),
    (("preacher",),             "Biceps Curl", "arms", "biceps", "biceps curl", []),
    (("scott",),                "Biceps Curl", "arms", "biceps", "biceps curl", []),
    (("biceps",),               "Biceps Curl", "arms", "biceps", "biceps curl", []),
    (("bicep",),                "Biceps Curl", "arms", "biceps", "biceps curl", []),
    (("arm curl",),             "Biceps Curl", "arms", "biceps", "biceps curl", []),
    (("dip",),                  "Dip", "arms", "triceps", "dip", ["mid chest"]),
    # --- legs --------------------------------------------------------------
    (("leg press",),            "Leg Press", "legs", "quads", "leg press", ["glutes"]),
    (("hack squat",),           "Hack/V-Squat", "legs", "quads", "hack / v-squat", ["glutes"]),
    (("v squat",),              "Hack/V-Squat", "legs", "quads", "hack / v-squat", ["glutes"]),
    (("pendulum squat",),       "Hack/V-Squat", "legs", "quads", "hack / v-squat", ["glutes"]),
    (("power squat",),          "Hack/V-Squat", "legs", "quads", "hack / v-squat", ["glutes"]),
    (("sissy squat",),          "Hack/V-Squat", "legs", "quads", "hack / v-squat", []),
    (("belt squat",),           "Belt Squat", "legs", "quads", "belt squat", ["glutes"]),
    (("leg extension",),        "Leg Extension", "legs", "quads", "leg extension", []),
    (("seated leg curl",),      "Seated Leg Curl", "legs", "hamstrings", "leg curl", []),
    (("lying leg curl",),       "Lying Leg Curl", "legs", "hamstrings", "leg curl", []),
    (("standing leg curl",),    "Standing Leg Curl", "legs", "hamstrings", "leg curl", []),
    (("kneeling leg curl",),    "Kneeling Leg Curl", "legs", "hamstrings", "leg curl", []),
    (("leg curl",),             "Leg Curl", "legs", "hamstrings", "leg curl", []),
    (("seated calf",),          "Seated Calf Raise", "legs", "calves", "calf raise", []),
    (("standing calf",),        "Standing Calf Raise", "legs", "calves", "calf raise", []),
    (("donkey calf",),          "Calf Raise", "legs", "calves", "calf raise", []),
    (("calf",),                 "Calf Raise", "legs", "calves", "calf raise", []),
    (("tibialis",),             "Tibialis Raise", "legs", "shins", "tibialis raise", []),
    (("lunge",),                "Lunge", "legs", "quads", "lunge", ["glutes"]),
    (("deadlift",),             "Deadlift/Squat machine", "legs", "hamstrings", "deadlift / squat", ["glutes"]),
    (("squat",),                "Hack/V-Squat", "legs", "quads", "hack / v-squat", ["glutes"]),
    # --- glutes / hips -----------------------------------------------------
    (("hip thrust",),           "Hip Thrust", "glutes", "glutes", "hip thrust", ["hamstrings"]),
    (("glute bridge",),         "Hip Thrust", "glutes", "glutes", "hip thrust", ["hamstrings"]),
    (("glute drive",),          "Hip Thrust", "glutes", "glutes", "hip thrust", ["hamstrings"]),
    (("inner outer",),          "Hip Abduction/Adduction", "legs", "adductors", "hip adduction", ["abductors"]),
    (("abductor", "adductor"),  "Hip Abduction/Adduction", "legs", "adductors", "hip adduction", ["abductors"]),
    (("abduction", "adduction"),"Hip Abduction/Adduction", "legs", "adductors", "hip adduction", ["abductors"]),
    (("abduction",),            "Hip Abduction", "legs", "abductors", "hip abduction", []),
    (("abductor",),             "Hip Abduction", "legs", "abductors", "hip abduction", []),
    (("adduction",),            "Hip Adduction", "legs", "adductors", "hip adduction", []),
    (("adductor",),             "Hip Adduction", "legs", "adductors", "hip adduction", []),
    (("multi hip",),            "Multi-Hip", "glutes", "glutes", "multi-hip", ["hamstrings"]),
    (("glute isolator",),       "Glute Kickback", "glutes", "glutes", "glute (kickback/bridge)", ["hamstrings"]),
    (("glute kickback",),       "Glute Kickback", "glutes", "glutes", "glute (kickback/bridge)", ["hamstrings"]),
    (("kickback",),             "Glute Kickback", "glutes", "glutes", "glute (kickback/bridge)", ["hamstrings"]),
    (("glute",),                "Glute Kickback", "glutes", "glutes", "glute (kickback/bridge)", ["hamstrings"]),
    # --- core --------------------------------------------------------------
    (("torso rotation",),       "Torso Rotation", "abs", "obliques", "torso rotation", []),
    (("rotary torso",),         "Torso Rotation", "abs", "obliques", "torso rotation", []),
    (("ab crunch",),            "Ab Crunch", "abs", "abs", "ab crunch", []),
    (("abdominal",),            "Ab Crunch", "abs", "abs", "ab crunch", []),
    (("crunch",),               "Ab Crunch", "abs", "abs", "ab crunch", []),
    (("knee raise",),           "Leg Raise", "abs", "abs", "leg raise", ["hip flexors"]),
    (("leg raise",),            "Leg Raise", "abs", "abs", "leg raise", ["hip flexors"]),
    # --- functional / other (no single movement) ---------------------------
    (("smith",),                "Smith Machine", "functional-other", None, None, []),
    (("half rack",),            None, "functional-other", None, None, []),
    (("power rack",),           None, "functional-other", None, None, []),
    (("monolift",),             None, "functional-other", None, None, []),
    (("rack",),                 None, "functional-other", None, None, []),
    (("cable",),                None, "functional-other", None, None, []),
    (("crossover",),            None, "functional-other", None, None, []),
    (("functional trainer",),   None, "functional-other", None, None, []),
    (("basic trainer",),        None, "functional-other", None, None, []),
    (("bench",),                None, "functional-other", None, None, []),
]
# fmt: on

# Pieces that are pure accessories / storage / consumables — never machines.
SKIP = (
    "resistance band", "db rack", "dumbbell rack", "weight tree", "barbell rack",
    "bar jack", "tier", "add on", "flooring", "storage rack", "battle rope",
    "landmine attachment", "band peg", "olympic weight tree", "attachment",
    "bumper", "plyo box", "barbell", "kettlebell",
    # storage / holders / stands — not trainable equipment
    "disc stand", "dumbell rack", "disc rack", "mat storage", "ball stand",
    "handle box", "handle stand", "hanger", "pump set", "langhantel",
    "training bars", "dumbbell spotter", "disc holder", "weight stand",
)


def _exact_skip(name: str) -> bool:
    # standalone furniture/storage headings that carry no movement
    return norm(name) in {"storage", "furniture", "locker", "lockers"}


def is_accessory(name: str) -> bool:
    n = norm(name)
    return _exact_skip(name) or any(k in n for k in SKIP)


def _has(n: str, kw: str) -> bool:
    # whole-word / whole-phrase match, so "chin" does not fire inside "machine"
    return f" {kw} " in f" {n} "


def classify_en(name: str) -> dict:
    """Return {mechanism, region, muscle, movement, secondary} for an English name."""
    n = norm(name)
    for keys, mech, region, muscle, movement, secondary in RULES:
        if all(_has(n, k) for k in keys):
            return {"mechanism": mech, "region": region, "muscle": muscle,
                    "movement": movement, "secondary": list(secondary)}
    return {"mechanism": None, "region": "functional-other", "muscle": None,
            "movement": None, "secondary": []}
