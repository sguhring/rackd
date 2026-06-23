"""Build a local, offline machine-classification / editing page.

Reads catalog/scraped_machines.json, pairs each machine with its local cutout
photo (web img/<hash>.png — same djb2 hash the PWA uses), and emits a single
self-contained HTML editor: a wall of large photos where you can set each
machine's function, type and muscles (pick an existing value or type a new
one), delete machines, and add new ones. Everything persists in the browser
and exports to a JSON that merges back into the catalog.

    python catalog/build_classifier.py
    # then double-click tools/cap/www/classify.html

The page lives in www/ so the relative img/<hash>.png paths resolve when opened
straight from disk (file://) — no server needed.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CATALOG = ROOT / "catalog" / "scraped_machines.json"
IMG_DIR = ROOT / "tools" / "cap" / "www" / "img"
OUT = ROOT / "tools" / "cap" / "www" / "classify.html"
TEMPLATE = Path(__file__).resolve().parent / "classify_template.html"


def img_hash(s: str) -> str:
    """Must match imgHash() in the PWA: djb2-xor over char codes, 32-bit."""
    h = 5381
    for ch in s:
        h = (((h * 33) & 0xFFFFFFFF) ^ ord(ch)) & 0xFFFFFFFF
    return format(h, "x")


def build() -> None:
    rows = json.loads(CATALOG.read_text(encoding="utf-8"))
    have = {p.name for p in IMG_DIR.iterdir()} if IMG_DIR.is_dir() else set()

    machines = []
    for i, r in enumerate(rows):
        url = r.get("image_url") or ""
        fname = f"{img_hash(url)}.png" if url else ""
        machines.append({
            "id": fname[:-4] if fname else f"row{i}",
            "brand": r.get("brand") or "",
            "model": r.get("model") or "",
            "type": r.get("machine_type") or "",
            "muscle": r.get("muscle_label") or "",
            "fn": r.get("exercise") or "",          # scraped guess ('' = unclassified)
            "img": f"img/{fname}" if fname in have else "",   # local cutout (offline)
            "imgurl": url,                           # original photo (needs internet)
        })

    # suggestion lists for the editable fields (existing values; user may add new).
    functions = sorted({m["fn"] for m in machines if m["fn"]})
    types = sorted({m["type"] for m in machines if m["type"]})
    # muscles: offer individual tokens (labels are like "delts · triceps").
    muscles = sorted({
        tok.strip()
        for m in machines if m["muscle"]
        for tok in m["muscle"].replace("/", "·").split("·") if tok.strip()
    })

    total = len(machines)
    unclassified = sum(1 for m in machines if not m["fn"])
    withphoto = sum(1 for m in machines if m["img"])

    html = (TEMPLATE.read_text(encoding="utf-8")
            .replace("/*__DATA__*/null", json.dumps(machines, ensure_ascii=False, separators=(",", ":")))
            .replace("/*__FUNCTIONS__*/null", json.dumps(functions, ensure_ascii=False))
            .replace("/*__TYPES__*/null", json.dumps(types, ensure_ascii=False))
            .replace("/*__MUSCLES__*/null", json.dumps(muscles, ensure_ascii=False)))
    OUT.write_text(html, encoding="utf-8")
    print(f"wrote {OUT}")
    print(f"  {total} machines · {withphoto} with photo · {unclassified} unclassified")
    print(f"  suggestions: {len(functions)} functions · {len(types)} types · {len(muscles)} muscles")


if __name__ == "__main__":
    build()
