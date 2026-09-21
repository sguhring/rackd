"""Link machines that have no exercise (movement) to one, so the app's
movement -> brand -> model browse actually lists them.

    python api/link_exercises.py            # dry run: counts + every rule-based pick
    python api/link_exercises.py --write

Three sources, most trustworthy first:
  1. the curated mechanism in catalog/machines_resolved.json ("Incline Chest Press")
  2. the curated movement there ("chest press", the taxonomy's canonical vocabulary)
  3. keyword rules over model name + muscle label, for rows outside the curated list

Multi-stations, cable crossovers, functional trainers, smith machines, racks and
the like are left unlinked on purpose: they are not one movement. Rows that
already have an exercise are never touched.
"""
from __future__ import annotations

import json
import re
import sqlite3
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "api" / "rackd.db"
RESOLVED = ROOT / "catalog" / "machines_resolved.json"

# curated mechanism -> exercise slug (None = deliberately not a single movement)
MECHANISM: dict[str, str | None] = {
    "Chest Press": "chest-press", "Incline Chest Press": "incline-chest-press", "Decline Chest Press": "chest-press",
    "Chest Fly": "pec-fly", "Pec Fly": "pec-fly", "Rear-Delt Fly": "rear-delt", "Rear Delt": "rear-delt",
    "Shoulder Press": "shoulder-press", "Lateral Raise": "lateral-raise",
    "Lat Pulldown": "lat-pulldown", "Pulldown": "lat-pulldown", "Row": "seated-row", "Seated Row": "seated-row",
    "Low Row": "seated-row", "High Row": "seated-row", "Pullover": "pullover",
    "Assisted Pull-up": "chin-up", "Chin Up": "chin-up", "Chin/Dip": "chin-up",
    "Biceps Curl": "biceps-curl", "Triceps Extension": "triceps-extension", "Dip": "triceps-dip",
    "Leg Press": "leg-press", "Hack/V-Squat": "hack-squat", "Hack Squat": "hack-squat", "Squat": "hack-squat",
    "Leg Extension": "leg-extension", "Leg Curl": "leg-curl",
    "Calf Raise": "calf-raise", "Seated Calf Raise": "calf-raise", "Standing Calf Raise": "calf-raise",
    "Glute Kickback": "glute", "Glute": "glute", "Hip Thrust": "hip-thrust",
    "Hip Abduction": "hip-abduction", "Hip Adduction": "hip-adduction", "Multi Hip": "multi-hip",
    "Back Extension": "back-extension", "Ab Crunch": "ab-crunch", "Leg Raise": "leg-raise",
    "Torso Rotation": "torso-rotation", "Shrug": "shrug", "Jammer Press": "jammer-press",
    "Deadlift": "deadlift", "Lunge": "lunge", "Step-Up": "step-up",
    "Smith Machine": None, "Neck": None, "Grip": None, "Cable Station": None, "Multi-Station": None,
}

# curated movement (taxonomy vocabulary) -> slug
MOVEMENT: dict[str, str | None] = {
    "chest press": "chest-press", "chest fly": "pec-fly", "shoulder press": "shoulder-press",
    "lateral raise": "lateral-raise", "rear-delt fly": "rear-delt", "pulldown": "lat-pulldown",
    "row": "seated-row", "upright row": "shrug", "pull-up / chin": "chin-up", "pullover": "pullover",
    "biceps curl": "biceps-curl", "triceps extension": "triceps-extension", "dip": "triceps-dip",
    "leg extension": "leg-extension", "leg curl": "leg-curl", "leg press": "leg-press",
    "hack / v-squat": "hack-squat", "calf raise": "calf-raise", "glute (kickback/bridge)": "glute",
    "hip thrust": "hip-thrust", "hip abduction": "hip-abduction", "hip adduction": "hip-adduction",
    "multi-hip": "multi-hip", "back extension": "back-extension", "ab crunch": "ab-crunch",
    "leg raise": "leg-raise", "torso rotation": "torso-rotation", "shrug": "shrug",
    "jammer / push press": "jammer-press", "lunge": "lunge", "deadlift": "deadlift",
    "neck": None, "tibialis raise": None, "grip": None, "shoulder rotation": None,
}

# rows whose name says they are not one movement -> never linked by rules
NOT_ONE_MOVEMENT = re.compile(
    r"multi[- ]?station|jungle|crossover|cross over|functional trainer|dual adjustable|cable (column|tower|station|motion)|"
    r"smith|power rack|half rack|squat rack|rack\b|bench\b(?!.*press)|storage|platform|multi[- ]?press|multi[- ]?gym|"
    r"\bft\b|4[- ]?stack|8[- ]?stack|circuit|kinesis|synrgy|hoist mi\d|home gym|total gym|combo\b.*/|"
    r"ablage|\bstands?$|jack\b|bravo|platinum|triple press|multifunctional|dual system|monolith|push and pull|"
    r"tibia|sissy", re.I)

# ordered keyword rules over "model · muscle_label" (lowercased); first hit wins
RULES: list[tuple[str, str]] = [
    (r"rear[- ]?delt|reverse fly|rear fly|delts? machine", "rear-delt"),
    (r"pec ?deck|pec ?fly|chest fly|butterfly|\bfly\b|flye|flight", "pec-fly"),
    (r"total chest|incline decline|flat.*incline|incline.*flat", "chest-press"),
    (r"incline.*(press|chest)|(press|chest).*incline", "incline-chest-press"),
    (r"chest press|bench press|decline press|vertical press|seated press|converging.*press|press.*chest|brust", "chest-press"),
    (r"shoulder press|overhead press|military press|delt press|press.*shoulder", "shoulder-press"),
    (r"lateral raise|lat raise|side raise|deltoid raise|seithebe", "lateral-raise"),
    (r"lat ?pull|pull ?down|pull-?down|front pull|latzug|back-pulling", "lat-pulldown"),
    (r"pull[- ]?up|\bchin\b|chin/|/chin|gravitron|assisted dip|dip.*assist|assist.*dip|klimmzug", "chin-up"),
    (r"pullover|pull over", "pullover"),
    (r"\brow\b|rowing|rower|rudern|ruder", "seated-row"),
    (r"shrug", "shrug"),
    (r"jammer|push press|ground base", "jammer-press"),
    (r"tricep|triceps|pushdown|arm extension|trizeps", "triceps-extension"),
    (r"\bdip\b|dips\b", "triceps-dip"),
    (r"bicep|biceps|preacher|arm curl|curl.*(arm|bicep)|bizeps|scott", "biceps-curl"),
    (r"hip thrust|glute bridge|glute drive", "hip-thrust"),
    (r"glute|kickback|kick back|rear kick|booty|butt blaster|hip extension", "glute"),
    (r"multi[- ]?hip|4[- ]way hip|total hip", "multi-hip"),
    (r"abduct|outer thigh", "hip-abduction"),
    (r"adduct|inner thigh", "hip-adduction"),
    (r"leg press|beinpresse|legpress|linear press", "leg-press"),
    (r"hack|v[- ]?squat|squat|pendulum|belt squat|kniebeuge", "hack-squat"),
    (r"leg ext|leg-ext|knee ext|beinstreck", "leg-extension"),
    (r"leg curl|leg-curl|hamstring|beinbeug|kneeling curl|prone curl|seated curl", "leg-curl"),
    (r"calf|wade", "calf-raise"),
    (r"lunge|ausfall", "lunge"),
    (r"step[- ]?up", "step-up"),
    (r"deadlift|kreuzheben|trap bar", "deadlift"),
    (r"back ext|back raise|hyper|lower back|lumbar|rückenstreck|45 degree back|roman chair|glute ham|ghd", "back-extension"),
    (r"leg raise|knee raise|vkr|captain|hanging", "leg-raise"),
    (r"rotary torso|torso rot|torso|rotation|twist|oblique", "torso-rotation"),
    (r"\bab\b|abdominal|crunch|bauch|core\b", "ab-crunch"),
]


def by_rules(model: str, muscle: str | None) -> str | None:
    hay = f"{model} · {muscle or ''}".lower()
    if NOT_ONE_MOVEMENT.search(model):
        return None
    for pat, slug in RULES:
        if re.search(pat, hay):
            return slug
    return None


def main() -> None:
    write = "--write" in sys.argv
    con = sqlite3.connect(DB)
    slugs = dict(con.execute("select slug, id from exercise").fetchall())
    curated = {(r["brand"].lower(), r["model"].lower()): r
               for r in json.loads(RESOLVED.read_text(encoding="utf-8"))}
    rows = con.execute(
        "select m.id, b.name, m.model, m.muscle_label from machine m join brand b on b.id=m.brand_id "
        "where m.exercise_id is null order by b.name, m.model").fetchall()
    picks: list[tuple[int, str, str, str, str]] = []   # id, brand, model, slug, how
    left: list[tuple[str, str, str]] = []
    for mid, brand, model, muscle in rows:
        cur = curated.get((brand.lower(), model.lower()))
        slug = None
        how = ""
        if cur:
            mech = cur.get("mechanism")
            if mech in MECHANISM:
                slug, how = MECHANISM[mech], "mechanism"
            if slug is None and cur.get("movement") in MOVEMENT:
                slug, how = MOVEMENT[cur["movement"]], "movement"
            if slug is None and (mech not in MECHANISM or MECHANISM.get(mech) is None) and not cur.get("movement"):
                slug, how = by_rules(model, muscle), "rules"
        else:
            slug, how = by_rules(model, muscle), "rules"
        if slug:
            picks.append((mid, brand, model, slug, how))
        else:
            left.append((brand, model, (cur or {}).get("mechanism") or (cur or {}).get("movement") or ""))

    print(f"unlinked: {len(rows)}  ->  link {len(picks)}  leave {len(left)}")
    print("by source:", Counter(h for *_, h in picks))
    print("by exercise:", Counter(s for *_, s, _ in picks).most_common())
    print("\n-- rule-based picks (review) --")
    for mid, brand, model, slug, how in picks:
        if how == "rules":
            print(f"   {slug:<20} {brand[:14]:<14} {model[:70]}")
    print("\n-- left unlinked --")
    for brand, model, why in left:
        print(f"   {brand[:14]:<14} {model[:60]:<60} {why}")
    if not write:
        return
    n = 0
    for mid, _, _, slug, _ in picks:
        n += con.execute("update machine set exercise_id=? where id=? and exercise_id is null", (slugs[slug], mid)).rowcount
    con.commit()
    print(f"\nlinked {n} machines")


if __name__ == "__main__":
    main()
