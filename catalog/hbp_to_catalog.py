"""Fold the recovered HBP range into the catalog.

    python catalog/hbp_to_catalog.py
    python catalog/build_taxonomy.py --from-resolved     # rebuild the tree + counts

Reads catalog/hbp_from_wayback.json, maps it through hbp_map.py and appends the
rows to machines_resolved.json — the same append-only path Prime and Strive use,
since machines_resolved.json is hand-curated beyond the scrape. Idempotent on
(brand, model). Copies the 38 surviving photos into the curator's image dir.
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
from hbp_map import classify, norm  # noqa: E402

SRC = ROOT / "catalog" / "hbp_from_wayback.json"
RESOLVED = ROOT / "catalog" / "machines_resolved.json"
IMG_SRC = ROOT / "catalog" / "hbp_images"
IMG_DST = ROOT / "tools" / "cap" / "www" / "img" / "hbp"
BRAND = "HBP"

# ActiveLine is explicitly hydraulic; everything else with a weight stack is
# selectorized. "hydraulic" is a new implement value — the facet vocab in
# taxonomy.json is built from the data, so it flows through without a schema change.
HYDRAULIC_LINES = {"ActiveLine"}


def facets(rec: dict) -> dict[str, str]:
    n = norm(rec["name"])
    f: dict[str, str] = {}
    if rec["line"] in HYDRAULIC_LINES:
        f["implement"] = "hydraulic"
    elif rec.get("stack_kg"):
        f["implement"] = "selectorized"
    else:
        f["implement"] = "machine"
    if "schrag" in n:
        f["angle"] = "incline"
    elif "negativ" in n:
        f["angle"] = "decline"
    for kw, val in (("sitzend", "seated"), ("liegend", "lying"), ("stehend", "standing")):
        if kw in n:
            f["position"] = val
            break
    return f


def main() -> None:
    recs = json.loads(SRC.read_text(encoding="utf-8"))
    resolved = json.loads(RESOLVED.read_text(encoding="utf-8"))
    have = {(m["brand"], m["model"]) for m in resolved}

    IMG_DST.mkdir(parents=True, exist_ok=True)
    added, copied = [], 0
    for rec in recs:
        c = classify(rec["name"])
        art = (rec.get("article") or "").strip()
        model = " ".join(x for x in (rec["line"], rec["name"], art) if x)
        if (BRAND, model) in have:
            continue
        row: dict = {
            "mechanism": c["mechanism"],
            "model": model,
            "brand": BRAND,
            "region": c["region"],
            "muscle": c["muscle"],
            "movement": c["movement"],
            "secondary": c["secondary"],
            "facets": facets(rec),
        }
        img = rec.get("image")
        if img and (IMG_SRC / img).exists():
            shutil.copy2(IMG_SRC / img, IMG_DST / img)
            row["image"] = f"img/hbp/{img}"
            copied += 1
        added.append(row)

    resolved.extend(added)
    RESOLVED.write_text(json.dumps(resolved, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8")
    print(f"added {len(added)} HBP machines ({copied} with a photo)")
    print(f"machines_resolved.json now {len(resolved)} rows")
    if not added:
        print("  (nothing new — already merged)")


if __name__ == "__main__":
    main()
