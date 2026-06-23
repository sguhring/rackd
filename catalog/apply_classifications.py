"""Merge a classify.html export back into catalog/scraped_machines.json.

Takes the classifications.json produced by the classifier page and applies it to
the source catalog: deletes the machines you removed, and writes your edited
function / type / muscle / brand / model values onto the matching rows. Rows you
didn't touch are left byte-for-byte unchanged.

    python catalog/apply_classifications.py path/to/classifications.json

Matches by the same djb2 image hash the classifier uses, so it lines up with the
exported ids. The original file is tracked in git — that's your undo.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CATALOG = ROOT / "catalog" / "scraped_machines.json"
FIELDS = ("brand", "model", "machine_type", "muscle_label", "exercise")


def img_hash(s: str) -> str:
    h = 5381
    for ch in s:
        h = (((h * 33) & 0xFFFFFFFF) ^ ord(ch)) & 0xFFFFFFFF
    return format(h, "x")


def row_id(row: dict, i: int) -> str:
    url = row.get("image_url") or ""
    return img_hash(url) if url else f"row{i}"


def main(export_path: str) -> None:
    rows = json.loads(CATALOG.read_text(encoding="utf-8"))
    export = json.loads(Path(export_path).read_text(encoding="utf-8"))

    deleted = set(export.get("deleted", []))
    edits = {m["id"]: m for m in export.get("machines", []) if m.get("edited")}

    kept, dropped, updated = [], 0, 0
    for i, row in enumerate(rows):
        rid = row_id(row, i)
        if rid in deleted:
            dropped += 1
            continue
        e = edits.get(rid)
        if e:
            changed = False
            for f in FIELDS:
                if f in e and (e[f] or "") != (row.get(f) or ""):
                    row[f] = e[f]
                    changed = True
            updated += changed
        kept.append(row)

    CATALOG.write_text(
        json.dumps(kept, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"applied {export_path}")
    print(f"  {len(rows)} -> {len(kept)} machines · deleted {dropped} · edited {updated}")
    missing = deleted - {row_id(r, i) for i, r in enumerate(rows)}
    if missing:
        print(f"  note: {len(missing)} deleted ids weren't found (already gone)")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("usage: python catalog/apply_classifications.py <classifications.json>")
    main(sys.argv[1])
