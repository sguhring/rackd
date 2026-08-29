"""Fold the Watson Gym Equipment range into the catalog.

    python catalog/watson_to_catalog.py            # dry run
    python catalog/watson_to_catalog.py --write
    python catalog/build_taxonomy.py --from-resolved

Watson (British, heavy-duty) has no structured web feed, so — like Prime, Strive,
HBP and Arsenal — the range is recovered from the source PDF brochure and
appended to machines_resolved.json. Idempotent on (brand, model).

Layout: each product is a block of ALL-CAPS name lines (sometimes two) followed
by a zero-padded 3-4 digit product code line, then DIMENSIONS / WEIGHT spec
blocks. The section (and thus the implement) is fixed by page range, taken from
the brochure's own contents page.
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

PDF = ROOT / "docs" / "Watson-Gym-Equipment-2026.pdf"
RESOLVED = ROOT / "catalog" / "machines_resolved.json"
BRAND = "Watson"

CODE = re.compile(r"^\d{3,4}$")
# section implement by 1-based page number (from the brochure contents page).
# Plate Loaded 14-26; Single/Dual Stack 27-43; Multi-Gyms 44-48; Stations 53-60;
# Racks/Benches 61-77; Functional Rigs 88-96. Pages 49-52 (attachments) and
# 78-87 / 97+ (furniture, storage, dumbbells, plates) are not standalone machines.
def implement_for_page(p: int) -> str | None:
    if 14 <= p <= 26:
        return "plate-loaded"
    if 27 <= p <= 48:
        return "selectorized"
    if 53 <= p <= 77 or 88 <= p <= 96:
        return "machine"
    return None  # skip


SPEC = ("dimension", "weight", "unloaded", "proudly made", "great britain",
        "degree", "per arm", "per carriage", "per pod", "diameter", "adjustable pin")
DIM = re.compile(r"^[whl]\s|mm$|^\d+\s*kg|kg\s*\(|\(bar\)|^\d+(\.\d+)?\s*kg", re.I)


def is_heading(s: str) -> bool:
    s = s.strip()
    if len(s) < 3:
        return False
    letters = [c for c in s if c.isalpha()]
    if len(letters) < 3 or sum(c.isupper() for c in letters) / len(letters) < 0.8:
        return False
    low = s.lower()
    if any(w in low for w in SPEC) or DIM.search(s):
        return False
    return True


def extract() -> list[tuple[str, str, str]]:
    """(name, code, implement) tuples."""
    doc = fitz.open(PDF)
    out: list[tuple[str, str, str]] = []
    seen: set[str] = set()
    for pno, page in enumerate(doc, start=1):
        implement = implement_for_page(pno)
        if implement is None:
            continue
        lines = [ln.strip() for ln in page.get_text().splitlines()]
        for i, ln in enumerate(lines):
            if not CODE.match(ln) or ln in seen:
                continue
            # walk backwards collecting the ALL-CAPS name lines above the code
            name_parts: list[str] = []
            j = i - 1
            while j >= 0 and len(name_parts) < 3:
                cand = lines[j].strip()
                if not cand:
                    j -= 1
                    if name_parts:
                        break
                    continue
                if is_heading(cand):
                    name_parts.insert(0, cand)
                    j -= 1
                else:
                    break
            if not name_parts:
                continue
            name = re.sub(r"\s+", " ", " ".join(name_parts)).strip()
            if is_accessory(name) or len(name) < 4:
                continue
            seen.add(ln)
            out.append((name, ln, implement))
    return out


def title(name: str) -> str:
    return " ".join(w.capitalize() for w in name.split())


def rows() -> list[dict]:
    out = []
    for name, code, implement in extract():
        c = classify_en(name)
        facets = {"implement": implement}
        if "converging" in norm(name) or "iso" in norm(name):
            facets["laterality"] = "iso-lateral"
        out.append({
            "mechanism": c["mechanism"],
            "model": f"Watson {title(name)} {code}",
            "brand": BRAND,
            "region": c["region"],
            "muscle": c["muscle"],
            "movement": c["movement"],
            "secondary": c["secondary"],
            "facets": facets,
        })
    return out


def main() -> None:
    data = rows()
    if "--write" not in sys.argv:
        for r in data:
            print(f"  {r['model']:56s} | {r['region']:16s} | {r['movement']}")
        print(f"\n{len(data)} Watson rows parsed (dry run — pass --write to merge)")
        return
    resolved = json.loads(RESOLVED.read_text(encoding="utf-8"))
    have = {(m["brand"], m["model"]) for m in resolved}
    added = [r for r in data if (r["brand"], r["model"]) not in have]
    resolved.extend(added)
    RESOLVED.write_text(json.dumps(resolved, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8")
    print(f"added {len(added)} Watson machines")
    print(f"machines_resolved.json now {len(resolved)} rows")
    if not added:
        print("  (nothing new — already merged)")


if __name__ == "__main__":
    main()
