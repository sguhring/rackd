"""Fold the gym80 (German heavy-duty manufacturer) range into the catalog.

    python catalog/gym80_to_catalog.py            # dry run
    python catalog/gym80_to_catalog.py --write
    python catalog/build_taxonomy.py --from-resolved

gym80's Gesamtbroschuere is a bilingual product catalog with a very regular
block per machine:

    ENGLISH NAME
    <code>            e.g. 3036, 4401, 4338N
    GERMAN NAME
    <W x L x H mm>
    <machine weight kg>
    <weight stack kg>

We anchor on the numeric code, take the line above as the English name (used
with pdf_map_en.classify_en) and the line below as the German name (fallback via
hbp_map.classify — it catches German-only spellings like RÜCKENSTRECKER or
BIZEPSMASCHINE that the English rules miss). Appended to machines_resolved.json,
idempotent on (brand, model).
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
import hbp_map  # noqa: E402

PDF = ROOT / "docs" / "gym80-Gesamtbroschuere.pdf"
RESOLVED = ROOT / "catalog" / "machines_resolved.json"
BRAND = "gym80"

CODE = re.compile(r"^\d{3,4}[A-Z]?$")
SECTION = {"sygnum", "pure kraft", "medical", "gym80", "4sports", "cardio",
           "weight stack", "content", "inhalt"}
DIM = re.compile(r"\d\s*x\s*\d|mm$|^\d+\s*kg|kg$|optional", re.I)


def is_heading(s: str) -> bool:
    s = s.strip()
    if len(s) < 3:
        return False
    letters = [c for c in s if c.isalpha()]
    if len(letters) < 3 or sum(c.isupper() for c in letters) / len(letters) < 0.75:
        return False
    if DIM.search(s):
        return False
    return norm(s) not in SECTION


def extract() -> list[tuple[str, str, str]]:
    """(english_name, code, german_name)."""
    doc = fitz.open(PDF)
    out: list[tuple[str, str, str]] = []
    seen: set[str] = set()
    for page in doc:
        lines = [ln.strip() for ln in page.get_text().splitlines() if ln.strip()]
        for i, ln in enumerate(lines):
            if not CODE.match(ln) or ln in seen:
                continue
            # english name: nearest heading line above the code
            english = ""
            for j in range(i - 1, max(-1, i - 5), -1):
                if is_heading(lines[j]):
                    english = lines[j]
                    break
            if not english:
                continue
            german = lines[i + 1] if i + 1 < len(lines) and is_heading(lines[i + 1]) else ""
            if is_accessory(english):
                continue
            seen.add(ln)
            out.append((re.sub(r"\s+", " ", english), ln, re.sub(r"\s+", " ", german)))
    return out


def implement_for(region: str, name: str) -> str:
    n = norm(name)
    if region == "functional-other":
        if "smith" in n or "multipress" in n or "multidruck" in n or "multidr" in n:
            return "smith"
        if "pulley" in n or "seilzug" in n or "cable" in n or "crossover" in n or "kabel" in n:
            return "cable"
        return "machine"
    if "pure kraft" in n or "ftm" in n or "free weight" in n or "plate" in n or "freie" in n:
        return "plate-loaded"
    return "selectorized"


def title(name: str) -> str:
    return " ".join(w.capitalize() for w in name.split())


def rows() -> list[dict]:
    out = []
    for english, code, german in extract():
        c = classify_en(english)
        if c["movement"] is None and german:
            g = hbp_map.classify(german)
            if g["movement"] is not None or g["mechanism"] is not None:
                c = {"mechanism": g["mechanism"], "region": g["region"],
                     "muscle": g["muscle"], "movement": g["movement"],
                     "secondary": g["secondary"]}
        facets = {"implement": implement_for(c["region"], f"{english} {german}")}
        if "iso" in norm(english):
            facets["laterality"] = "iso-lateral"
        out.append({
            "mechanism": c["mechanism"],
            "model": f"gym80 {title(english)} {code}",
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
            print(f"  {r['model']:52s} | {r['region']:16s} | {r['movement']}")
        print(f"\n{len(data)} gym80 rows parsed (dry run — pass --write to merge)")
        return
    resolved = json.loads(RESOLVED.read_text(encoding="utf-8"))
    have = {(m["brand"], m["model"]) for m in resolved}
    added = [r for r in data if (r["brand"], r["model"]) not in have]
    resolved.extend(added)
    RESOLVED.write_text(json.dumps(resolved, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8")
    print(f"added {len(added)} gym80 machines")
    print(f"machines_resolved.json now {len(resolved)} rows")
    if not added:
        print("  (nothing new — already merged)")


if __name__ == "__main__":
    main()
