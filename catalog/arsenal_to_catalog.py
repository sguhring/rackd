"""Fold the Arsenal Strength plate-loaded / pin-select range into the catalog.

    python catalog/arsenal_to_catalog.py            # dry run — print what it would add
    python catalog/arsenal_to_catalog.py --write    # append to machines_resolved.json
    python catalog/build_taxonomy.py --from-resolved # rebuild the tree + counts

Arsenal has no structured web feed (marketing-catalog site), so — like Prime,
Strive and HBP — its range is recovered from the source PDF and appended to the
hand-curated machines_resolved.json. Idempotent on (brand, model).

Layout: the catalog prints each product as "NAME  CODE" on one line (or the code
on the line just below the name). Codes carry the mechanism: AR- = Reloaded
plate-loaded, M1- = selectorized pin-select, ALPHA/BRAVO = racks/benches/smith.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import fitz  # PyMuPDF

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
from pdf_map_en import classify_en, is_accessory, norm  # noqa: E402

PDF = ROOT / "docs" / "Arsenal Strength Catalog 6.2-1.pdf"
RESOLVED = ROOT / "catalog" / "machines_resolved.json"
BRAND = "Arsenal Strength"

CODE = re.compile(r"((?:AR|M1|BRAVO)-[A-Z0-9-]+|ALPHA\s*\d*-\s*[A-Z0-9-]+)")
# lines that are never a product heading
STOP = ("special features", "dimensions are", "product featured", "contents",
        "choose your accessories", "powerslide series", "series racks",
        "alpha series", "olympic benches", "utility benches", "storage racks")


def looks_like_heading(s: str) -> bool:
    s = s.strip()
    if not s or len(s) < 3:
        return False
    letters = [c for c in s if c.isalpha()]
    if len(letters) < 2:
        return False
    # headings are set in all-caps; skip sentence-case marketing/spec lines
    if sum(c.isupper() for c in letters) / len(letters) < 0.8:
        return False
    low = s.lower()
    return not any(w in low for w in STOP)


def extract() -> list[tuple[str, str]]:
    doc = fitz.open(PDF)
    pairs: list[tuple[str, str]] = []
    seen: set[str] = set()
    for page in doc:
        lines = [ln.rstrip() for ln in page.get_text().splitlines()]
        for i, ln in enumerate(lines):
            m = CODE.search(ln)
            if not m:
                continue
            code = re.sub(r"\s+", "", m.group(1))
            before = ln[: m.start()].strip(" -–—")
            name = before
            if not looks_like_heading(name):
                # code sits on its own line; the name is the line above
                prev = lines[i - 1].strip() if i > 0 else ""
                name = prev if looks_like_heading(prev) else before
            name = re.sub(r"\s+", " ", name).strip(" -–—/")
            if not name or not looks_like_heading(name) or is_accessory(name):
                continue
            if code in seen:
                continue
            seen.add(code)
            pairs.append((name, code))
    return pairs


def implement_for(name: str, code: str, mechanism: str | None) -> str:
    n = norm(name)
    if mechanism == "Smith Machine":
        return "smith"
    if "basic trainer" in n or "cable" in n:
        return "cable"
    if code.startswith("AR-"):
        return "plate-loaded"
    if code.startswith("M1"):
        return "selectorized"
    return "machine"  # racks, benches, GHD, sissy squat, ...


def title(name: str) -> str:
    return " ".join(w.capitalize() for w in name.split())


def build_rows() -> list[dict]:
    rows = []
    for name, code in extract():
        c = classify_en(name)
        facets = {"implement": implement_for(name, code, c["mechanism"])}
        if "iso" in norm(name):
            facets["laterality"] = "iso-lateral"
        rows.append({
            "mechanism": c["mechanism"],
            "model": f"Arsenal {title(name)} {code}",
            "brand": BRAND,
            "region": c["region"],
            "muscle": c["muscle"],
            "movement": c["movement"],
            "secondary": c["secondary"],
            "facets": facets,
        })
    return rows


def main() -> None:
    rows = build_rows()
    write = "--write" in sys.argv
    if not write:
        for r in rows:
            print(f"  {r['model']:52s} | {r['region']:16s} | {r['movement']}")
        print(f"\n{len(rows)} Arsenal rows parsed (dry run — pass --write to merge)")
        return
    resolved = json.loads(RESOLVED.read_text(encoding="utf-8"))
    have = {(m["brand"], m["model"]) for m in resolved}
    added = [r for r in rows if (r["brand"], r["model"]) not in have]
    resolved.extend(added)
    RESOLVED.write_text(json.dumps(resolved, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8")
    print(f"added {len(added)} Arsenal machines")
    print(f"machines_resolved.json now {len(resolved)} rows")
    if not added:
        print("  (nothing new — already merged)")


if __name__ == "__main__":
    main()
