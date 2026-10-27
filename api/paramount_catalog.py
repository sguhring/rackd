"""Add Paramount's SP Circuit selectorized line to the catalog, with the official
brochure renders inlined as base64.

Source: the Paramount "SP Circuit — Style & Performance" brochure saved to
docs/catalog_sp.pdf. The existing Paramount rows are secondhand marketplace listings
(source=empire); this adds the full 17-piece SP line as clean, recognisable models
under its own source tag. Photos are the hero render of each machine, pulled straight
from the PDF by image xref (mapped by hand against the page layout).

Idempotent: re-running wipes this source's rows first and rebuilds them.

    python paramount_catalog.py            # build
    python paramount_catalog.py --dry      # print, no DB writes
"""
from __future__ import annotations

import base64
import sys
from pathlib import Path

import pymupdf
from sqlmodel import Session, delete, select

from database import engine
from models import Brand, Exercise, GymMachine, Machine

PDF = Path(__file__).resolve().parent.parent / "docs" / "catalog_sp.pdf"
SOURCE = "paramount-sp-brochure"
BRAND = "Paramount"
LINE = "SP"

# (model code, display name, exercise slug, muscle label, hero image xref in the PDF)
MACHINES: list[tuple[str, str, str, str, int]] = [
    ("SP-5000", "Leg Extension",       "leg-extension",     "quads",               123),
    ("SP-5100", "Seated Leg Curl",     "leg-curl",          "hamstrings",          119),
    ("SP-5200", "Leg Press",           "leg-press",         "quads · glutes",      109),
    ("SP-5300", "Inner Thigh",         "hip-adduction",     "adductors",           138),
    ("SP-5400", "Outer Thigh",         "hip-abduction",     "abductors",           142),
    ("SP-5500", "Biceps Curl",         "biceps-curl",       "biceps",              276),
    ("SP-5600", "Triceps Extension",   "triceps-extension", "triceps",             278),
    ("SP-5700", "Pec Fly / Rear Delt", "pec-fly",           "chest · rear delts",  249),
    ("SP-5800", "Rotary Chest",        "chest-press",       "chest · front delts", 237),
    ("SP-5900", "Seated Row",          "seated-row",        "mid-back · lats",     263),
    ("SP-6000", "Low Back Extension",  "back-extension",    "lower back",          298),
    ("SP-6100", "Lat Pulldown",        "lat-pulldown",      "lats · biceps",       251),
    ("SP-6200", "Rotary Shoulder",     "shoulder-press",    "delts · triceps",     239),
    ("SP-6300", "Abdominal",           "ab-crunch",         "abs",                 296),
    ("SP-6400", "Rotary Torso",        "torso-rotation",    "obliques",            294),
    ("SP-6500", "Calf Raise",          "calf-raise",        "calves",              152),
    ("SP-6600", "Glute Press",         "glute",             "glutes",              150),
]


def _model_name(name: str, code: str) -> str:
    return f"{LINE} {name} ({code})"


def _data_uri(doc: pymupdf.Document, xref: int) -> str:
    pix = pymupdf.Pixmap(doc, xref)
    if pix.colorspace and pix.colorspace.n == 4:        # CMYK -> RGB
        pix = pymupdf.Pixmap(pymupdf.csRGB, pix)
    while pix.width > 1200:                              # keep near-native res
        pix.shrink(1)
    if pix.alpha:
        pix = pymupdf.Pixmap(pix, 0)
    jpg = pix.tobytes("jpg", jpg_quality=88)
    return "data:image/jpeg;base64," + base64.b64encode(jpg).decode("ascii")


def run(dry: bool = False) -> None:
    doc = pymupdf.open(PDF)

    if dry:
        for code, name, slug, muscle, xref in MACHINES:
            pix = pymupdf.Pixmap(doc, xref)
            print(f"  {_model_name(name, code):36} -> {slug:18} [{muscle}]  "
                  f"img {pix.width}x{pix.height}")
        print(f"\n{len(MACHINES)} machines.")
        return

    with Session(engine) as s:
        brand = s.exec(select(Brand).where(Brand.name == BRAND)).first()
        if not brand:
            brand = Brand(name=BRAND, abbr="PA")
            s.add(brand)
            s.commit()
            s.refresh(brand)

        slug_to_id = {e.slug: e.id for e in s.exec(select(Exercise)).all()}
        missing = sorted({slug for _, _, slug, _, _ in MACHINES} - slug_to_id.keys())
        if missing:
            raise SystemExit(f"exercise slugs not in DB: {missing}")

        # idempotent reset of this source's rows
        old_ids = [m.id for m in s.exec(select(Machine).where(Machine.source == SOURCE)).all()]
        if old_ids:
            s.exec(delete(GymMachine).where(GymMachine.machine_id.in_(old_ids)))
            s.exec(delete(Machine).where(Machine.source == SOURCE))
            s.commit()

        for code, name, slug, muscle, xref in MACHINES:
            s.add(Machine(
                brand_id=brand.id,
                model=_model_name(name, code),
                machine_type="selectorized",
                exercise_id=slug_to_id[slug],
                muscle_label=muscle,
                image_url=_data_uri(doc, xref),
                source=SOURCE,
            ))
        s.commit()

        print(f"Paramount SP Circuit: {len(MACHINES)} selectorized machines added "
              f"(replaced {len(old_ids)} previous rows).")


if __name__ == "__main__":
    run(dry="--dry" in sys.argv)
