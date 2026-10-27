"""German HBP machine names -> English gloss + rackd taxonomy.

The archived HBP catalog is entirely in German ("Bankdrückmaschine, liegend"),
so nothing matches the catalog's vocabulary by string comparison. Rules are
keyword-based and ordered MOST SPECIFIC FIRST, the same shape as categorize.py:
"Beinbeuge Maschine, sitzend" must hit the seated rule before the generic one.

Values are checked against what machines_resolved.json already uses — no new
mechanism/region/muscle/movement strings are invented here.

Each rule: (keywords, english, mechanism, region, muscle, movement, secondary)
`keywords` all-must-match, lowercased, umlauts folded.
"""
from __future__ import annotations

FOLD = str.maketrans({"ü": "u", "ö": "o", "ä": "a", "ß": "s", "º": "", "°": ""})


def norm(s: str) -> str:
    return " ".join(s.lower().translate(FOLD).replace("-", " ").replace("/", " ").split())


# fmt: off
RULES: list[tuple[tuple[str, ...], str, str | None, str, str | None, str | None, list[str]]] = [
    # --- chest -------------------------------------------------------------
    (("schragbank",),      "Incline Press Machine",   "Incline Chest Press", "chest", "upper chest", "chest press", ["front delts"]),
    (("bankdruck", "liegend"), "Lying Chest Press",   "Chest Press", "chest", "mid chest", "chest press", ["front delts"]),
    (("bankdruck", "horizontal"), "Horizontal Chest Press", "Chest Press", "chest", "mid chest", "chest press", ["front delts"]),
    (("bankdruck", "ruder"), "Chest Press / Row Combo", "Chest Press", "chest", "mid chest", "chest press", ["mid-back"]),
    (("bankdruck",),       "Chest Press Machine",     "Chest Press", "chest", "mid chest", "chest press", ["front delts"]),
    (("butterfly", "invers"), "Pec Fly / Rear Delt",  "Rear-Delt Fly", "shoulders", "rear delts", "rear-delt fly", ["mid chest"]),
    (("butterfly",),       "Pec Deck",                "Chest Fly", "chest", "mid chest", "chest fly", []),
    (("brust", "maschine"), "Chest Machine",          "Chest Press", "chest", "mid chest", "chest press", ["front delts"]),
    (("druckbank",),       "Wide Press Bench",        "Chest Press", "chest", "mid chest", "chest press", ["triceps"]),
    # --- shoulders ---------------------------------------------------------
    (("nackendruckbank",), "Behind-Neck Press Bench", "Shoulder Press", "shoulders", "delts", "shoulder press", ["triceps"]),
    (("nackendruck",),     "Behind-Neck Press",       "Shoulder Press", "shoulders", "delts", "shoulder press", ["triceps"]),
    (("deltoid",),         "Deltoid Machine",         "Shoulder Press", "shoulders", "delts", "shoulder press", ["triceps"]),
    (("schulterwippe",),   "Shoulder Press Lever",    "Shoulder Press", "shoulders", "delts", "shoulder press", ["triceps"]),
    (("seithebe",),        "Lateral Raise Machine",   "Lateral Raise", "shoulders", "side delts", "lateral raise", []),
    (("rucken", "schulter"), "Lat Pulldown / Shoulder Press", "Lat Pulldown", "back", "lats", "pulldown", ["delts"]),
    # --- back --------------------------------------------------------------
    (("latzug",),          "Lat Pulldown Station",    "Lat Pulldown", "back", "lats", "pulldown", ["biceps"]),
    (("dorsal",),          "Dorsal Machine",          "Lat Pulldown", "back", "lats", "pulldown", ["biceps"]),
    (("pull", "over"),     "Pullover Machine",        "Pullover", "back", "lats", "pullover", []),
    (("ruderbodenhantel",), "T-Bar Row",              "T-Bar Row", "back", "mid-back", "row", ["lats"]),
    (("ruderhantel",),     "Chest-Supported Row",     "Row", "back", "mid-back", "row", ["lats"]),
    (("ruderstation",),    "Row Station",             "Seated Row", "back", "mid-back", "row", ["lats"]),
    (("rudern",),          "Row Machine",             "Row", "back", "mid-back", "row", ["lats"]),
    (("ruckenisolator",),  "Back Isolator",           "Back Extension", "back", "lower back", "back extension", []),
    (("ruckenstreck",),    "Back Extension Machine",  "Back Extension", "back", "lower back", "back extension", []),
    (("ruckenwippe",),     "Back Extension Lever",    "Back Extension", "back", "lower back", "back extension", []),
    (("hyperextension",),  "Hyperextension",          "Back Extension", "back", "lower back", "back extension", ["glutes"]),
    (("rucken", "maschine"), "Back Machine",          "Back Extension", "back", "lower back", "back extension", []),
    (("klimmzug", "dipp"), "Pull-up / Dip Machine",   "Assisted Pull-up", "back", "lats", "pull-up / chin", ["biceps"]),
    (("klimmzug",),        "Pull-up Frame",           "Assisted Pull-up", "back", "lats", "pull-up / chin", ["biceps"]),
    # --- arms --------------------------------------------------------------
    (("scottcurler",),     "Preacher Curl Bench",     "Biceps Curl", "arms", "biceps", "biceps curl", []),
    (("bizeps", "trizeps"), "Biceps / Triceps Combo", "Biceps Curl", "arms", "biceps", "biceps curl", ["triceps"]),
    (("bizeps",),          "Biceps Machine",          "Biceps Curl", "arms", "biceps", "biceps curl", []),
    (("armdruck",),        "Arm Press Machine",       "Triceps Extension", "arms", "triceps", "triceps extension", []),
    (("trizepsstation",),  "Triceps Station",         "Triceps Extension", "arms", "triceps", "triceps extension", []),
    (("trizeps",),         "Triceps Machine",         "Triceps Extension", "arms", "triceps", "triceps extension", []),
    (("dipp", "barren"),   "Dip Bars",                "Dip", "arms", "triceps", "dip", ["mid chest"]),
    (("dipp",),            "Dip Machine",             "Dip", "arms", "triceps", "dip", ["mid chest"]),
    # --- legs --------------------------------------------------------------
    (("beinbeuge", "sitzend"), "Seated Leg Curl",     "Seated Leg Curl", "legs", "hamstrings", "leg curl", []),
    (("beinbeuge", "liegend"), "Lying Leg Curl",      "Lying Leg Curl", "legs", "hamstrings", "leg curl", []),
    (("beinbeuge", "stehend"), "Standing Leg Curl",   "Standing Leg Curl", "legs", "hamstrings", "leg curl", []),
    (("beinbeuge",),       "Leg Curl Machine",        "Leg Curl", "legs", "hamstrings", "leg curl", []),
    (("beinstreck", "beinbeuge"), "Leg Extension / Curl Combo", "Leg Extension", "legs", "quads", "leg extension", ["hamstrings"]),
    (("beinstreck",),      "Leg Extension Machine",   "Leg Extension", "legs", "quads", "leg extension", []),
    (("beinpresse",),      "Leg Press",               "Leg Press", "legs", "quads", "leg press", ["glutes"]),
    (("hackenmitt",),      "Hack Squat",              "Hack/V-Squat", "legs", "quads", "hack / v-squat", ["glutes"]),
    (("kniebeuge", "huftstrecken"), "Squat / Hip Thrust", "Leg Press", "legs", "quads", "leg press", ["glutes"]),
    (("kniebeugenhilfe",), "Squat Assist",            "Hack/V-Squat", "legs", "quads", "hack / v-squat", ["glutes"]),
    (("kniebeugenablage",), "Squat Rack",             None, "functional-other", None, None, []),
    (("waden", "donkey"),  "Donkey Calf Raise",       "Calf Raise", "legs", "calves", "calf raise", []),
    (("waden", "sitzend"), "Seated Calf Raise",       "Seated Calf Raise", "legs", "calves", "calf raise", []),
    (("wadengerat", "sitzend"), "Seated Calf Raise",  "Seated Calf Raise", "legs", "calves", "calf raise", []),
    (("waden", "stehend"), "Standing Calf Raise",     "Standing Calf Raise", "legs", "calves", "calf raise", []),
    (("waden",),           "Calf Machine",            "Calf Raise", "legs", "calves", "calf raise", []),
    (("adduktion", "abduktion"), "Adductor / Abductor Combo", "Hip Abduction/Adduction", "legs", "adductors", "hip adduction", ["abductors"]),
    (("adduktions", "abduktions"), "Adductor / Abductor Combo", "Hip Abduction/Adduction", "legs", "adductors", "hip adduction", ["abductors"]),
    (("adduktions",),      "Adductor Machine",        "Hip Adduction", "legs", "adductors", "hip adduction", []),
    (("abduktions",),      "Abductor Machine",        "Hip Abduction", "legs", "abductors", "hip abduction", []),
    (("gluteus",),         "Glute Machine",           "Glute Kickback", "glutes", "glutes", "glute (kickback/bridge)", ["hamstrings"]),
    (("gluetus",),         "Glute Machine",           "Glute Kickback", "glutes", "glutes", "glute (kickback/bridge)", ["hamstrings"]),
    (("multi", "kick"),    "Multi-Hip Machine",       "Multi-Hip", "glutes", "glutes", "multi-hip", ["hamstrings"]),
    (("beinhebegestell",), "Leg Raise Frame",         "Leg Raise", "abs", "abs", "leg raise", ["hip flexors"]),
    # --- core --------------------------------------------------------------
    (("rumpf", "rotation"), "Torso Rotation",         "Torso Rotation", "abs", "obliques", "torso rotation", []),
    (("twister",),         "Torso Rotation",          "Torso Rotation", "abs", "obliques", "torso rotation", []),
    (("rumpfbeugen",),     "Abdominal / Back Combo",  "Ab Crunch", "abs", "abs", "ab crunch", ["lower back"]),
    (("bauchfixator",),    "Abdominal Fixator",       "Ab Crunch", "abs", "abs", "ab crunch", []),
    (("bauchmuskelbank",), "Abdominal Bench",         "Ab Crunch", "abs", "abs", "ab crunch", []),
    (("bauchmuskelsitz",), "Abdominal Seat",          "Ab Crunch", "abs", "abs", "ab crunch", []),
    (("bauchbeugemaschine",), "Abdominal Crunch",     "Ab Crunch", "abs", "abs", "ab crunch", []),
    (("bauchgeuge",),      "Abdominal Crunch",        "Ab Crunch", "abs", "abs", "ab crunch", []),
    (("bauch",),           "Abdominal Machine",       "Ab Crunch", "abs", "abs", "ab crunch", []),
    # --- neck / misc -------------------------------------------------------
    (("hals", "nacken"),   "Neck Machine",            "Neck", "neck", "neck", "neck", []),
    (("multipresse",),     "Smith Machine",           "Smith Machine", "functional-other", None, None, []),
    (("kreuzzugstation",), "Cable Crossover",         None, "functional-other", None, None, []),
    (("doppelstation",),   "Dual Cable Station",      None, "functional-other", None, None, []),
    (("stationen", "turm"), "Multi-Station Tower",    None, "functional-other", None, None, []),
    (("powerrack",),       "Power Rack",              None, "functional-other", None, None, []),
    (("kurzhantelstander",), "Dumbbell Rack",         None, "functional-other", None, None, []),
    (("negativbank",),     "Decline Bench",           None, "functional-other", None, None, []),
    (("flachbank",),       "Flat Bench",              None, "functional-other", None, None, []),
    (("universalbank",),   "Utility Bench",           None, "functional-other", None, None, []),
]
# fmt: on


def classify(name: str) -> dict:
    """Return the gloss + taxonomy for a German HBP machine name."""
    n = norm(name)
    for keys, english, mech, region, muscle, movement, secondary in RULES:
        if all(k in n for k in keys):
            return {
                "english": english, "mechanism": mech, "region": region,
                "muscle": muscle, "movement": movement, "secondary": list(secondary),
            }
    return {"english": None, "mechanism": None, "region": "functional-other",
            "muscle": None, "movement": None, "secondary": []}
