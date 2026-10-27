"""Build the offline taxonomy-curation page.

Pairs each resolved machine (catalog/machines_resolved.json) with its local
cutout photo and the dependent body-part -> muscle -> movement dropdowns from
catalog/taxonomy.json, then emits one self-contained HTML editor: a wall of
large photos where you set each machine's region / muscle / movement / facets
(pick an existing value or add a new one), edit secondary muscles, delete
machines, and add new ones. Everything persists in the browser and exports a
machines_resolved.json that drops straight back into the catalog.

    python catalog/build_curator.py
    # then double-click tools/cap/www/curate.html
    # ...curate, click "export", replace catalog/machines_resolved.json
    # python catalog/build_taxonomy.py --from-resolved   # rebuild the tree + counts

machines_resolved.json is index-aligned with scraped_machines.json (both come
from the same scrape, in order), so photos are recovered by pairing on index.
The page lives in www/ so the relative img/<hash>.png paths resolve from disk.
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRAPED = ROOT / "catalog" / "scraped_machines.json"
RESOLVED = ROOT / "catalog" / "machines_resolved.json"
TAXONOMY = ROOT / "catalog" / "taxonomy.json"
IMG_DIR = ROOT / "tools" / "cap" / "www" / "img"
OUT = ROOT / "tools" / "cap" / "www" / "curate.html"
TEMPLATE = Path(__file__).resolve().parent / "curate_template.html"

FACET_AXES = ("implement", "angle", "position", "laterality")


def img_hash(s: str) -> str:
    """Must match imgHash() in the PWA: djb2-xor over char codes, 32-bit."""
    h = 5381
    for ch in s:
        h = (((h * 33) & 0xFFFFFFFF) ^ ord(ch)) & 0xFFFFFFFF
    return format(h, "x")


def build() -> None:
    scraped = json.loads(SCRAPED.read_text(encoding="utf-8"))
    resolved = json.loads(RESOLVED.read_text(encoding="utf-8"))
    tax = json.loads(TAXONOMY.read_text(encoding="utf-8"))
    have = {p.name for p in IMG_DIR.iterdir()} if IMG_DIR.is_dir() else set()

    if len(scraped) != len(resolved):
        print(f"  warning: scraped ({len(scraped)}) and resolved ({len(resolved)}) "
              f"lengths differ — pairing by index up to the shorter one")
    mismatch = sum(1 for i, r in enumerate(resolved)
                   if i < len(scraped) and (r.get("model") or "") != (scraped[i].get("model") or ""))
    if mismatch:
        print(f"  warning: {mismatch} index-paired rows have mismatched models — "
              f"photos for those may be wrong")

    machines = []
    for i, res in enumerate(resolved):
        sc = scraped[i] if i < len(scraped) else {}
        url = sc.get("image_url") or ""
        fname = f"{img_hash(url)}.png" if url else ""
        machines.append({
            "id": fname[:-4] if fname else f"row{i}",
            "mechanism": res.get("mechanism") or "",
            "brand": res.get("brand") or "",
            "model": res.get("model") or "",
            "region": res.get("region") or "",
            "muscle": res.get("muscle") or "",
            "movement": res.get("movement") or "",
            "secondary": res.get("secondary") or [],
            "facets": res.get("facets") or {},
            "img": res.get("image") or (f"img/{fname}" if fname in have else ""),  # local cutout (offline)
            "imgurl": url,                                     # original photo (needs internet)
        })

    # slim taxonomy: only what the dependent dropdowns need.
    tax_slim = [
        {
            "slug": r["slug"], "label": r["label"],
            "muscles": [
                {"label": mu["label"],
                 "movements": [{"label": mv["label"]} for mv in mu.get("movements", [])]}
                for mu in r.get("muscles", [])
            ],
        }
        for r in tax["regions"]
    ]

    # facet value vocab + muscle list (for secondary datalist), gathered from the tree.
    facets: dict[str, set] = defaultdict(set)
    muscles: set = set()
    for r in tax["regions"]:
        for mu in r.get("muscles", []):
            muscles.add(mu["label"])
            for mv in mu.get("movements", []):
                for ax, vals in mv.get("facets", {}).items():
                    facets[ax].update(vals)
    facets_out = {ax: sorted(facets.get(ax, ())) for ax in FACET_AXES}
    muscles_out = sorted(muscles)

    total = len(machines)
    withphoto = sum(1 for m in machines if m["img"])
    categorised = sum(1 for m in machines
                      if m["region"] and m["region"] != "functional-other"
                      and m["muscle"] and m["movement"])

    html = (TEMPLATE.read_text(encoding="utf-8")
            .replace("/*__DATA__*/null", json.dumps(machines, ensure_ascii=False, separators=(",", ":")))
            .replace("/*__TAX__*/null", json.dumps(tax_slim, ensure_ascii=False, separators=(",", ":")))
            .replace("/*__FACETS__*/null", json.dumps(facets_out, ensure_ascii=False))
            .replace("/*__MUSCLES__*/null", json.dumps(muscles_out, ensure_ascii=False)))
    OUT.write_text(html, encoding="utf-8")
    print(f"wrote {OUT}")
    print(f"  {total} machines · {withphoto} with photo · {categorised} categorised")
    print(f"  taxonomy: {len(tax_slim)} regions · {len(muscles_out)} muscles · "
          f"facet axes {', '.join(f'{ax}({len(facets_out[ax])})' for ax in FACET_AXES)}")


if __name__ == "__main__":
    build()
