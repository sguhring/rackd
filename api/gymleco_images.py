"""Point every Gymleco machine at its official product image from gymleco.com.

Gymleco runs on Shopify, so /collections/all/products.json gives clean titles
(prefixed with the model code, e.g. "010 Seated Row") + image URLs. We match our
catalog machines to products by that leading code and store the website image URL.

Usage:  python gymleco_images.py
"""
from __future__ import annotations

import json
import re
import urllib.request

from sqlmodel import Session, select

from database import engine
from models import Brand, Machine

BASE = "https://gymleco.com/collections/all/products.json"
CODE = re.compile(r"^\s*(\d{2,4})")  # leading model code, e.g. 010 / 243


def fetch_products() -> list[dict]:
    out: list[dict] = []
    for page in range(1, 10):
        req = urllib.request.Request(
            f"{BASE}?limit=250&page={page}",
            headers={"User-Agent": "Mozilla/5.0"},
        )
        batch = json.load(urllib.request.urlopen(req, timeout=30))["products"]
        if not batch:
            break
        out.extend(batch)
    return out


def by_code(products: list[dict]) -> dict[str, str]:
    """code -> first image src (skip products with no code or no image)."""
    table: dict[str, str] = {}
    for p in products:
        m = CODE.match(p.get("title", ""))
        imgs = p.get("images") or []
        if not m or not imgs:
            continue
        table.setdefault(m.group(1), imgs[0]["src"])
    return table


def run() -> None:
    table = by_code(fetch_products())
    print(f"fetched {len(table)} Gymleco products with images")

    with Session(engine) as s:
        brand = s.exec(select(Brand).where(Brand.name == "Gymleco")).first()
        if not brand:
            print("[skip] no Gymleco brand in DB")
            return
        machines = s.exec(select(Machine).where(Machine.brand_id == brand.id)).all()

        hit = miss = 0
        for m in machines:
            code_m = CODE.match(m.model or "")
            src = table.get(code_m.group(1)) if code_m else None
            if not src:
                miss += 1
                print(f"  [miss] {m.model!r} (id={m.id})")
                continue
            m.image_url = src
            s.add(m)
            hit += 1
            print(f"  [ok]   {m.model!r} -> {src.rsplit('/', 1)[-1]}")
        s.commit()
        print(f"done. {hit} updated, {miss} unmatched of {len(machines)} Gymleco machines.")


if __name__ == "__main__":
    run()
