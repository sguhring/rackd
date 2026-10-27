"""Merge catalog/machines_resolved.json into the DB catalog.

    python api/load_resolved.py            # dry run — report what would change
    python api/load_resolved.py --write

machines_resolved.json is the curated catalog (2610 rows, hand-classified) and
since the PDF extraction work it carries a local `image` path for 1314 of them.
This brings that into the DB the app actually serves.

THE RULE: an existing machine keeps its brand and model string, always.

That string is the identity the app stores against every logged set, saved
session, workout preset and per-machine note — the phone has 200 sets keyed on
it. The two sources spell the same machine differently ("Watson Animal Leg Press
0041" in the catalog, "Animal Leg Press (0041)" in the DB), so rebuilding from
the catalog wholesale silently detaches that history: it drops the phone's
resolvable machines from 41/55 to 20/55. Measured, not theoretical.

So this is additive:
  * existing rows  -> keep identity, upgrade the image if the catalog has a
                      better one (a PDF-extracted studio photo beats a scraped
                      marketplace URL)
  * catalog rows with no DB counterpart -> added as new machines
  * DB-only brands (Newtech, Megamass) -> untouched, they have logged sets

Matching between the two is by (brand, product code) with a normalised-name
fallback. Local images are downscaled to MAX_PX before inlining, which keeps the
1314 new photos at 22 MB instead of 61.
"""
from __future__ import annotations

import base64
import io
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

from PIL import Image
from sqlmodel import Session, select

sys.path.insert(0, str(Path(__file__).resolve().parent))
from database import engine, init_db  # noqa: E402
from models import Brand, Machine  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
RESOLVED = ROOT / "catalog" / "machines_resolved.json"
WWW = ROOT / "tools" / "cap" / "www"

MAX_PX = 512
JPEG_Q = 82
BRAND_ALIAS = {"primefitness": "prime"}          # same brand, two spellings
# Product codes appear in several shapes across the two sources: "1FE056",
# "AR-VLP", bare "0041", "(3002)". One regex is fragile here -- an alternation
# that allows a separator swallows the preceding word, so the catalog's
# "Curl 3002" normalised to "curl3002" while the DB's "Curl (3002)" gave
# "3002", and the duplicate slipped through as a new machine. Pull the
# alphanumeric tokens and the bare digit runs separately, then union them.
ALNUM = re.compile(r"\b([0-9]?[A-Za-z]{1,5}-?\d{3,4}[A-Za-z]{0,2}|[A-Z]{2,6}-[A-Z0-9]{2,8})\b")
DIGITS = re.compile(r"\b(\d{3,4})\b")


def n(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(s).lower())


def name_keys(brand: str, model: str) -> set[str]:
    """Normalised model, plus the model with a leading brand token stripped:
    the catalog says "PRIME Evolution Arm Curl" where the DB says
    "Evolution Arm Curl"."""
    variants = {model}
    # the DB tags a line onto the end -- "Platinum V4 (PL)", "Back Extension
    # (SEL)" -- where the catalog puts it nowhere. Without this the whole of
    # Booty Builder duplicates.
    stripped = re.sub(r"\s*\((?:pl|sel|plate loaded|selectorized)\)\s*$", "", model, flags=re.I)
    variants.add(stripped)
    out = set()
    for v in variants:
        out.add(n(v))
        for pre in (brand, brand.replace(" ", ""), brand.split()[0] if brand.split() else brand):
            if pre and v.lower().startswith(pre.lower()):
                out.add(n(v[len(pre):]))
    return {k for k in out if k}


def nb(brand: str) -> str:
    k = n(brand)
    return BRAND_ALIAS.get(k, k)


def codes(s: str) -> set[str]:
    t = str(s)
    return ({n(m.group(1)) for m in ALNUM.finditer(t)} |
            {m.group(1) for m in DIGITS.finditer(t)})


def inline(path: Path) -> str | None:
    try:
        im = Image.open(path)
        im.load()
    except Exception:
        return None
    if im.mode not in ("RGB", "L"):
        im = im.convert("RGB")
    im.thumbnail((MAX_PX, MAX_PX))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=JPEG_Q, optimize=True)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def main() -> None:
    write = "--write" in sys.argv
    rows = json.loads(RESOLVED.read_text(encoding="utf-8"))
    init_db()

    with Session(engine) as s:
        pairs = s.exec(select(Machine, Brand).join(Brand, Brand.id == Machine.brand_id)).all()
        existing = [(m, b.name) for m, b in pairs]

    # index existing machines so a catalog row can find its DB counterpart
    by_name: dict[tuple[str, str], Machine] = {}
    by_code: dict[tuple[str, str], Machine] = {}
    for m, bname in existing:
        for k in name_keys(bname, m.model):
            by_name.setdefault((nb(bname), k), m)
        for c in codes(m.model):
            by_code.setdefault((nb(bname), c), m)

    upgrades: list[tuple[Machine, str]] = []
    additions: list[dict] = []
    stat = Counter()
    for r in rows:
        key = nb(r["brand"])
        hit = None
        for k in name_keys(r["brand"], r["model"]):
            hit = by_name.get((key, k))
            if hit:
                break
        if hit is None:
            for c in codes(r["model"]):
                hit = by_code.get((key, c))
                if hit:
                    break
        if hit is None:
            additions.append(r)
            stat["new machine"] += 1
            continue
        # existing machine: only consider replacing its image
        if r.get("image"):
            p = WWW / r["image"]
            if p.exists():
                if not hit.image_url or hit.image_url.startswith("http"):
                    upgrades.append((hit, str(p)))
                    stat["image upgraded"] += 1
                else:
                    stat["kept existing data-uri"] += 1
            else:
                stat["catalog image file missing"] += 1
        else:
            stat["no catalog image"] += 1

    print(f"catalog rows      : {len(rows)}")
    print(f"existing machines : {len(existing)}")
    print(f"  matched         : {len(rows) - len(additions)}")
    print(f"  new to add      : {len(additions)}")
    print(f"  image upgrades  : {len(upgrades)}")
    print("detail:", dict(stat))
    per = Counter(r["brand"] for r in additions)
    print("additions by brand:")
    for b, k in per.most_common():
        sample = next(r["model"] for r in additions if r["brand"] == b)
        print(f'   {b:20} +{k:4}   e.g. {sample[:44]}')
    if not write:
        print("\ndry run — pass --write to apply")
        return

    with Session(engine) as s:
        brands = {nb(b.name): b for b in s.exec(select(Brand)).all()}
        done = 0
        for m, path in upgrades:
            uri = inline(Path(path))
            if uri:
                row = s.get(Machine, m.id)
                row.image_url = uri
                s.add(row)
                done += 1
        s.commit()

        added = 0
        for r in additions:
            key = nb(r["brand"])
            b = brands.get(key)
            if b is None:
                b = Brand(name=r["brand"])
                s.add(b)
                s.commit()
                s.refresh(b)
                brands[key] = b
            uri = None
            if r.get("image"):
                p = WWW / r["image"]
                if p.exists():
                    uri = inline(p)
            s.add(Machine(brand_id=b.id, model=r["model"], machine_type=r.get("mechanism"),
                          muscle_label=r.get("muscle"), image_url=uri, source="machines_resolved"))
            added += 1
        s.commit()
        total = len(s.exec(select(Machine)).all())
    print(f"\nupgraded {done} images, added {added} machines -> {total} total")


if __name__ == "__main__":
    main()
