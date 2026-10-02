"""GervaSport: give the 85 catalog rows real machine names instead of bare codes.

    python api/gervasport_names.py            # dry run: print old -> new
    python api/gervasport_names.py --write    # rename in machines_resolved.json + rackd.db

Source: the manufacturer's own 2018 catalog pages, via the Wayback Machine
(gervasport.com now hosts an unrelated blog). Each line has one page per muscle
group listing "<CODE> - <SPANISH NAME>":
  web.archive.org/web/2018*/gervasport.com/maquina_de_piernas.html   Classic legs
  ..._1.html = Exclusive line (codes printed as "SO11"), ..._2.html = Fitness line,
  convergentes_gervasport.html (CE lever line), maquina_isolaterales.html,
  bancos_gervasport.html, carga_de_discos_gervasport.html (plate-loaded Fitness)
Names below are those translated to English; the code stays at the end so the
row still matches the plate on the machine ("Classic Leg Extension C012").

Where the site contradicts the brochure photo we already ship, the photo wins:
  C022    site prints it as a second "C021A - MAQUINA DE ADDUCTORES"
  C082ISO site lists it under biceps with the C080 copy; the photo is a
          converging shoulder press (C082 is the non-iso version)
  C052A   site's "abdominales y fondos de rodilla" heading, but the text and photo
          are the kneeling assisted chin/dip

Renaming changes the brand+model identity the app keys sets on. The one
GervaSport machine with logged sets (Classic C080) is carried over by the app's
migrateLegacyMachines3 in tools/cap/www/index.html -- keep the two in sync.
"""
from __future__ import annotations

import json
import shutil
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "api" / "rackd.db"
RESOLVED = ROOT / "catalog" / "machines_resolved.json"
BRAND = "GervaSport"

# code -> (name, exercise slug or None, region, muscle label or None)
NAMES: dict[str, tuple[str, str | None, str, str | None]] = {
    # ---- Classic: legs
    "C001": ("45-Degree Leg Press", "leg-press", "legs", "quads · glutes"),
    "C005": ("Horizontal Leg Press", "leg-press", "legs", "quads · glutes"),
    "C007": ("Hack Squat", "hack-squat", "legs", "quads · glutes"),
    "C008": ("Squat Stand", None, "legs", "quads · glutes"),
    "C011": ("Lying Leg Curl", "leg-curl", "legs", "hamstrings"),
    "C012": ("Leg Extension", "leg-extension", "legs", "quads"),
    "C015": ("Squat Cage", None, "legs", "quads · glutes"),
    "C016": ("Standing Calf & Squat", "calf-raise", "legs", "calves"),
    "C018": ("Seated Calf Raise (Plate-Loaded)", "calf-raise", "legs", "calves"),
    "C019": ("Standing Glute", "glute", "glutes", "glutes"),
    "C021": ("Glute Machine", "glute", "glutes", "glutes"),
    "C021A": ("Kneeling Glute Kickback", "glute", "glutes", "glutes"),
    "C022": ("Adductor", "hip-adduction", "legs", "adductors"),
    "C023": ("Abductor", "hip-abduction", "glutes", "abductors"),
    "C058": ("45-Degree Calf Raise", "calf-raise", "legs", "calves"),
    "C059": ("Seated Calf Raise", "calf-raise", "legs", "calves"),
    # ---- Classic: upper body
    "C032": ("Chest-Supported T-Bar Row", "seated-row", "back", "mid-back · lats"),
    "C035": ("Chest-Supported Seated Row", "seated-row", "back", "mid-back · lats"),
    "C052A": ("Kneeling Assisted Chin & Dip", "chin-up", "back", "lats · triceps"),
    "C040": ("Lateral Raise", "lateral-raise", "shoulders", "side delts"),
    "C082": ("Shoulder Press", "shoulder-press", "shoulders", "delts · triceps"),
    "C082ISO": ("Iso-Lateral Shoulder Press", "shoulder-press", "shoulders", "delts · triceps"),
    "C044": ("Pec Fly", "pec-fly", "chest", "chest"),
    "C045": ("Pec Fly / Rear Delt", "rear-delt", "shoulders", "rear delts · chest"),
    "C046": ("Vertical Chest Press", "chest-press", "chest", "chest · triceps"),
    "C078": ("Seated Chest & Triceps Dip", "triceps-dip", "arms", "triceps · chest"),
    "CG085": ("Plate-Loaded Smith Machine", None, "functional-other", None),
    "C080": ("Biceps Curl", "biceps-curl", "arms", "biceps"),
    "C057": ("Total Abdominal Crunch", "ab-crunch", "abs", "abs"),
    "C060": ("Lower Back Extension", "back-extension", "back", "lower back"),
    # ---- Classic: iso-lateral + CE lever (plate-loaded converging) line
    "C043": ("Iso-Lateral Lat Pulldown", "lat-pulldown", "back", "lats · biceps"),
    "C048": ("Iso-Lateral Incline Press", "incline-chest-press", "chest", "upper chest"),
    "CE001": ("Lever Incline Press", "incline-chest-press", "chest", "upper chest"),
    "CE002": ("Lever Bench Press", "chest-press", "chest", "chest · triceps"),
    "CE004": ("Lever Shoulder Press", "shoulder-press", "shoulders", "delts · triceps"),
    "CE005": ("Lever T-Bar Row", "seated-row", "back", "mid-back · lats"),
    "CE006": ("Lever Lat Pulldown", "lat-pulldown", "back", "lats · biceps"),
    "CE008": ("Lever Leg Press", "leg-press", "legs", "quads · glutes"),
    # ---- Classic: benches and stations
    "C050": ("Decline Press Bench", None, "functional-other", None),
    "C053": ("Olympic Bench Press", None, "functional-other", None),
    "C056": ("Incline Press Bench", None, "functional-other", None),
    "C069": ("Crunch Bench", None, "abs", "abs"),
    "C071": ("Adjustable Ab Bench", None, "abs", "abs"),
    "C073": ("Ab Crunch Bench", None, "abs", "abs"),
    "C079": ("Preacher Curl Bench", None, "arms", "biceps"),
    "C083": ("Shoulder Press Bench", None, "functional-other", None),
    "C090": ("Multi-Station Cable Crossover", None, "functional-other", None),
    "C094": ("Flat Bench", None, "functional-other", None),
    "C109": ("Plate Tree", None, "functional-other", None),
    "C164A": ("Barbell Rack", None, "functional-other", None),
    "C168": ("Sit-Up Bench", None, "abs", "abs"),
    "CG061": ("Hyperextension", "back-extension", "back", "lower back"),
    # ---- Exclusive
    "S011": ("Lying Leg Curl", "leg-curl", "legs", "hamstrings"),
    "S012": ("Leg Extension", "leg-extension", "legs", "quads"),
    "S019": ("Standing Glute", "glute", "glutes", "glutes"),
    "S021": ("Kneeling Glute Kickback", "glute", "glutes", "glutes"),
    "S023": ("Abductor", "hip-abduction", "glutes", "abductors"),
    "S046": ("Vertical Chest Press", "chest-press", "chest", "chest · triceps"),
    "S052": ("Assisted Chin & Dip", "chin-up", "back", "lats · triceps"),
    "S052A": ("Standing Assisted Chin & Dip", "chin-up", "back", "lats · triceps"),
    "S057": ("Total Abdominal Crunch", "ab-crunch", "abs", "abs"),
    "S060": ("Lower Back Extension", "back-extension", "back", "lower back"),
    "S080": ("Biceps Curl", "biceps-curl", "arms", "biceps"),
    # ---- Fitness
    "F005": ("Horizontal Leg Press", "leg-press", "legs", "quads · glutes"),
    "F010": ("45-Degree Calf Raise", "calf-raise", "legs", "calves"),
    "F011": ("Lying Leg Curl", "leg-curl", "legs", "hamstrings"),
    "F011D": ("Lying Leg Curl (Plate-Loaded)", "leg-curl", "legs", "hamstrings"),
    "F012": ("Leg Extension", "leg-extension", "legs", "quads"),
    "F014": ("Seated Leg Curl", "leg-curl", "legs", "hamstrings"),
    "F016": ("Standing Calf & Squat", "calf-raise", "legs", "calves"),
    "F035": ("Chest-Supported Seated Row", "seated-row", "back", "mid-back · lats"),
    "F036": ("Pullover", "pullover", "back", "lats"),
    "F040": ("Lateral Raise", "lateral-raise", "shoulders", "side delts"),
    "F082": ("Shoulder Press", "shoulder-press", "shoulders", "delts · triceps"),
    "F044": ("Pec Fly", "pec-fly", "chest", "chest"),
    "F045": ("Pec Fly / Rear Delt", "rear-delt", "shoulders", "rear delts · chest"),
    "F046": ("Vertical Chest Press", "chest-press", "chest", "chest · triceps"),
    "F076D": ("Vertical Chest Press (Plate-Loaded)", "chest-press", "chest", "chest · triceps"),
    "F078": ("Seated Chest & Triceps Dip", "triceps-dip", "arms", "triceps · chest"),
    "F078D": ("Seated Dip (Plate-Loaded)", "triceps-dip", "arms", "triceps · chest"),
    "F057": ("Total Abdominal Crunch", "ab-crunch", "abs", "abs"),
    "F060": ("Lower Back Extension", "back-extension", "back", "lower back"),
    "F061": ("Upper Ab Crunch", "ab-crunch", "abs", "abs"),
    "F080": ("Biceps Curl", "biceps-curl", "arms", "biceps"),
    "F081": ("Triceps Extension", "triceps-extension", "arms", "triceps"),
}


def new_model(old: str) -> str | None:
    """'Classic C012' -> 'Classic Leg Extension C012'. None if already renamed/unknown."""
    parts = old.split()
    if len(parts) != 2 or parts[1] not in NAMES:
        return None
    return f"{parts[0]} {NAMES[parts[1]][0]} {parts[1]}"


def main() -> None:
    write = "--write" in sys.argv
    rows = json.loads(RESOLVED.read_text(encoding="utf-8"))
    plan: dict[str, str] = {}
    for r in rows:
        if r["brand"] != BRAND:
            continue
        nm = new_model(r["model"])
        if nm is None:
            continue
        code = r["model"].split()[1]
        _, _, region, muscle = NAMES[code]
        plan[r["model"]] = nm
        print(f"{r['model']:<18} -> {nm}")
        r["model"], r["region"], r["muscle"] = nm, region, muscle
    print(f"\n{len(plan)} catalog rows to rename")

    con = sqlite3.connect(DB)
    slugs = dict(con.execute("select slug, id from exercise").fetchall())
    db_rows = con.execute("select m.id, m.model from machine m join brand b on b.id=m.brand_id "
                          "where b.name=?", (BRAND,)).fetchall()
    updates = []
    for mid, model in db_rows:
        nm = new_model(model)
        if nm is None:
            continue
        _, slug, _, muscle = NAMES[model.split()[1]]
        updates.append((nm, slugs.get(slug) if slug else None, muscle, mid))
    print(f"{len(updates)} DB rows to rename, {sum(1 for u in updates if u[1])} linked to a movement")

    if not write:
        print("dry run -- pass --write to apply")
        return
    shutil.copy2(DB, DB.with_name("rackd.db.pre-gerva-names.bak"))
    con.executemany("update machine set model=?, exercise_id=?, muscle_label=? where id=?", updates)
    con.commit()
    RESOLVED.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("written")


if __name__ == "__main__":
    main()
