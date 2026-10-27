"""Write the machine taxonomy (region -> muscle -> movement + facets) onto every DB machine.

    python api/load_taxonomy.py            # dry run — coverage report
    python api/load_taxonomy.py --write    # add/fill the columns, rewrite catalog/taxonomy.json

Until now the taxonomy lived only in catalog/machines_resolved.json (2340 hand-curated
rows), while the DB the app serves has grown past it — Brightway, DAVID, the renamed
GervaSport rows and others were added straight into rackd.db and never got a region.
So per DB machine:

  * curated row matches (same brand + product code / normalised name as load_resolved)
    and places it in a real region -> take its region / muscle / movement / secondary /
    facets as-is
  * otherwise -> derive them from the DB's own muscle_label + exercise + machine_type
      with the same alias/movement/facet rules build_taxonomy.py uses

catalog/taxonomy.json is then rebuilt from the DB rows, so the tree and the API agree.
"""
from __future__ import annotations

import json
import shutil
import sqlite3
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "catalog"))
from build_taxonomy import (
    ALIAS,
    MUSCLE_REGION,
    OUT_RES,
    OUT_TAX,
    build_tree,
    canon_movement,
    facets,
    tokens,
)
from load_resolved import codes, name_keys, nb

DB = HERE / "rackd.db"
COLUMNS = {"region": "VARCHAR", "muscle": "VARCHAR", "movement": "VARCHAR",
           "secondary": "VARCHAR", "facets": "VARCHAR"}


def from_rules(muscle_label: str | None, exercise: str | None, model: str, mtype: str | None) -> dict:
    toks = [ALIAS[t] for t in tokens(muscle_label or "") if t in ALIAS]
    primary = toks[0] if toks else None
    return {
        "region": MUSCLE_REGION.get(primary, "functional-other") if primary else "functional-other",
        "muscle": primary,
        "movement": canon_movement(exercise),
        "secondary": list(dict.fromkeys(t for t in toks[1:] if t != primary)),
        "facets": facets(model, mtype or ""),
    }


def resolve(rows: list[tuple], curated: list[dict]) -> tuple[dict[int, dict], Counter]:
    by_name: dict[tuple[str, str], dict] = {}
    by_code: dict[tuple[str, str], dict] = {}
    for r in curated:
        key = nb(r["brand"])
        for k in name_keys(r["brand"], r["model"]):
            by_name.setdefault((key, k), r)
        for c in codes(r["model"]):
            by_code.setdefault((key, c), r)

    out: dict[int, dict] = {}
    stat: Counter = Counter()
    for mid, brand, model, mtype, label, exercise in rows:
        key = nb(brand)
        hit = next((by_name[(key, k)] for k in name_keys(brand, model) if (key, k) in by_name), None)
        if hit is None:
            hit = next((by_code[(key, c)] for c in codes(model) if (key, c) in by_code), None)
        # a curated "functional-other" is only a non-answer (227 Panatta rows are bare
        # codes there) — when the DB's own label places the machine, that wins
        ruled = from_rules(label, exercise, model, mtype)
        if hit is not None and hit.get("region") not in (None, "functional-other"):
            t = {f: hit.get(f) for f in ("region", "muscle", "movement")}
            t["secondary"] = list(hit.get("secondary") or [])
            # curated muscles are sometimes compound ("chest · triceps"): first token is
            # the primary, the rest join secondary; the region follows the primary
            toks = [ALIAS.get(x, x) for x in tokens(t["muscle"] or "")]
            if toks:
                t["muscle"] = toks[0]
                t["region"] = MUSCLE_REGION.get(toks[0], t["region"])
                t["secondary"] = list(dict.fromkeys(x for x in toks[1:] + t["secondary"]
                                                    if x != toks[0]))
            t["facets"] = dict(hit.get("facets") or {}) or facets(model, mtype or "")
            # a curated row without a movement can still borrow the DB's exercise link
            t["movement"] = t["movement"] or canon_movement(exercise)
            stat["curated"] += 1
        else:
            t = ruled
            stat["rules"] += 1
        out[mid] = {"brand": brand, "model": model, **t}
    return out, stat


def main() -> None:
    write = "--write" in sys.argv
    curated = json.loads(OUT_RES.read_text(encoding="utf-8"))
    con = sqlite3.connect(DB)
    rows = con.execute(
        "select m.id, b.name, m.model, m.machine_type, m.muscle_label, e.slug "
        "from machine m join brand b on b.id = m.brand_id "
        "left join exercise e on e.id = m.exercise_id").fetchall()

    resolved, stat = resolve(rows, curated)
    regions = Counter(t["region"] for t in resolved.values())
    print(f"db machines {len(rows)} · from curated {stat['curated']} · from rules {stat['rules']}")
    print("regions:", dict(regions.most_common()))
    no_mv = sum(1 for t in resolved.values() if not t["movement"])
    print(f"without movement {no_mv} · functional/other {regions['functional-other']}")
    other = Counter(t["brand"] for t in resolved.values() if t["region"] == "functional-other")
    print("functional/other by brand:", dict(other.most_common(10)))
    if not write:
        print("\ndry run — pass --write to apply")
        return

    bak = DB.with_suffix(".db.pre-taxonomy.bak")
    if not bak.exists():
        con.close()
        shutil.copy2(DB, bak)
        con = sqlite3.connect(DB)
    have = {r[1] for r in con.execute("pragma table_info(machine)")}
    for col, typ in COLUMNS.items():
        if col not in have:
            con.execute(f"alter table machine add column {col} {typ}")
    con.executemany(
        "update machine set region=?, muscle=?, movement=?, secondary=?, facets=? where id=?",
        [(t["region"], t["muscle"], t["movement"], " · ".join(t["secondary"]) or None,
          json.dumps(t["facets"], ensure_ascii=False) if t["facets"] else None, mid)
         for mid, t in resolved.items()])
    con.commit()
    con.close()

    tree = build_tree(list(resolved.values()))
    OUT_TAX.write_text(json.dumps({"version": 3, "regions": tree}, ensure_ascii=False, indent=2) + "\n",
                       encoding="utf-8")
    print(f"\nwrote taxonomy onto {len(resolved)} machines (backup {bak.name}) and rebuilt {OUT_TAX.name}")


if __name__ == "__main__":
    main()
