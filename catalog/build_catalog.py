"""Build the machine catalog from live sources and categorize it.

Standalone (no DB needed): runs the configured scrapers, categorizes every model
on both axes (mechanism + movement/muscles), writes the result to
`scraped_machines.json`, and prints a breakdown so you can eyeball coverage.

    python build_catalog.py            # pull + categorize + write JSON + summary
    python build_catalog.py --dry      # same, but don't write the file

To load into the DB instead, pipe RawMachine records through normalize.upsert()
(see normalize.py) with the API's models on sys.path.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from categorize import categorize
from scrapers.shopify import ShopifyScraper

OUT = Path(__file__).resolve().parent / "scraped_machines.json"

# Each store is one Shopify storefront. shop.lifefitness.com carries Life Fitness,
# Hammer Strength and Cybex (one company) — a large share of real gym floors.
SOURCES = [
    ShopifyScraper("shop-lifefitness", "https://shop.lifefitness.com"),
]


def build(write: bool = True) -> list[dict]:
    rows: list[dict] = []
    for scraper in SOURCES:
        for r in scraper.fetch():
            cat = categorize(r.model, r.category, r.extra.get("tags"))
            rows.append({
                "brand": r.brand,
                "model": r.model,
                "machine_type": cat.mechanism,
                "exercise": cat.exercise_slug,
                "muscle_label": cat.muscle_label,
                "product_type": r.category,
                "image_url": r.image_url,
                "source": r.source,
            })
    rows.sort(key=lambda x: (x["brand"], x["model"]))
    if write:
        OUT.write_text(json.dumps(rows, indent=2, ensure_ascii=False))
    _summarize(rows)
    return rows


def _summarize(rows: list[dict]) -> None:
    by_brand = Counter(r["brand"] for r in rows)
    by_mech = Counter(r["machine_type"] for r in rows)
    matched = sum(1 for r in rows if r["exercise"])
    print(f"\n{len(rows)} machines  ·  {matched} mapped to a movement "
          f"({matched * 100 // max(len(rows), 1)}%)\n")
    print("by brand:")
    for b, n in by_brand.most_common():
        print(f"  {n:4}  {b}")
    print("\nby mechanism:")
    for m, n in by_mech.most_common():
        print(f"  {n:4}  {m}")
    unmapped = [r for r in rows if not r["exercise"]]
    if unmapped:
        print(f"\n{len(unmapped)} unmapped (need a movement keyword), e.g.:")
        for r in unmapped[:12]:
            print(f"  - {r['brand']} {r['model']}  [{r['product_type']}]")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true", help="don't write the JSON file")
    args = ap.parse_args()
    build(write=not args.dry)
