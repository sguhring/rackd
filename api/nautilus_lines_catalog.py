"""Add the Nautilus lines from the "Nautilus Strength Catalog" (docs/) that the DB
does not carry yet — NOVA, EVO, XPLoad, the two ONE pieces missing from the earlier
import, and the Freedom Trainers — with the catalog's own renders inlined as base64.

Source: docs/Nautilus Strength Catalog.pdf (user-supplied, 54 pages). Every product
page prints "Name  CODE" at 11pt beside its photo; the (page, xref) pairs below were
pinned by hand against the page dumps and checked on a contact sheet.

Like api/nautilus_catalog.py (ONE / Inspiration / Impact / Instinct / Leverage) these
are the official lines a user actually stands in front of; the secondhand XPLoad and
EVO listings stay as they are. Idempotent: re-running wipes this source's rows first.

    python nautilus_lines_catalog.py            # build
    python nautilus_lines_catalog.py --dry      # print, no DB writes
"""
from __future__ import annotations

import base64
import io
import sys
from pathlib import Path

import pymupdf
from PIL import Image
from sqlmodel import Session, delete, select

from database import engine
from models import Brand, Exercise, GymMachine, Machine

PDF = Path(__file__).resolve().parent.parent / "docs" / "Nautilus Strength Catalog.pdf"
SOURCE = "nautilus-strength-catalog"
BRAND = "Nautilus"
MAX_PX, JPEG_Q = 900, 86

# (line, code, display name, machine_type, exercise slug | None, muscle label, page, xref)
MACHINES: list[tuple[str, str, str, str, str | None, str, int, int]] = [
    # --- ONE: the two pieces the earlier import did not have ---
    ("One", "S6PF", "Pec Fly", "selectorized", "pec-fly", "chest", 5, 127),
    ("One", "S6LR", "Lateral Raise", "selectorized", "lateral-raise", "side delts", 7, 177),
    # --- NOVA (selectorized) ---
    ("Nova", "S8OP", "Overhead Press", "selectorized", "shoulder-press", "delts · triceps", 19, 461),
    ("Nova", "S8CR", "Compound Row", "selectorized", "seated-row", "back · biceps", 20, 484),
    ("Nova", "S8PF", "Pec Fly", "selectorized", "pec-fly", "chest", 20, 480),
    ("Nova", "S8LR", "Lateral Raise", "selectorized", "lateral-raise", "side delts", 20, 492),
    ("Nova", "S8AB", "Abdominal", "selectorized", "ab-crunch", "abs", 21, 507),
    ("Nova", "S8LE", "Leg Extension", "selectorized", "leg-extension", "quads", 21, 515),
    ("Nova", "S8LC", "Seated Leg Curl", "selectorized", "leg-curl", "hamstrings", 21, 519),
    ("Nova", "S8MCH", "Multi-Chest", "selectorized", "chest-press", "chest · front delts", 22, 538),
    ("Nova", "S8AB-LB", "Abdominal / Low Back", "selectorized", "ab-crunch", "abs · lower back", 22, 530),
    ("Nova", "S8LPCF", "Leg Press / Calf Flex", "selectorized", "leg-press", "quads · calves", 24, 570),
    # --- EVO (selectorized) ---
    ("EVO", "S9VC", "Vertical Chest", "selectorized", "chest-press", "chest · triceps", 11, 263),
    ("EVO", "S9IP", "Incline Press", "selectorized", "incline-chest-press", "upper chest", 11, 267),
    ("EVO", "S9PF", "Pec Fly", "selectorized", "pec-fly", "chest", 11, 271),
    ("EVO", "S9RDPF", "Rear Delt / Pec Fly", "selectorized", "pec-fly", "chest · rear delts", 11, 259),
    ("EVO", "S9MR", "Mid Row", "selectorized", "seated-row", "mid-back · lats", 12, 285),
    ("EVO", "S9PO", "Pullover", "selectorized", "pullover", "lats", 12, 289),
    ("EVO", "S9CR", "Compound Row", "selectorized", "seated-row", "back · biceps", 12, 293),
    ("EVO", "S9BC", "Biceps Curl", "selectorized", "biceps-curl", "biceps", 13, 308),
    ("EVO", "S9PC", "Preacher Curl", "selectorized", "biceps-curl", "biceps", 13, 312),
    ("EVO", "S9TE", "Triceps Extension", "selectorized", "triceps-extension", "triceps", 13, 316),
    ("EVO", "S9VTE", "V-Triceps Extension", "selectorized", "triceps-extension", "triceps", 13, 320),
    ("EVO", "S9OP", "Overhead Press", "selectorized", "shoulder-press", "delts · triceps", 14, 347),
    ("EVO", "S9LR", "Lateral Raise", "selectorized", "lateral-raise", "side delts", 14, 339),
    ("EVO", "S9SD", "Seated Dip", "selectorized", "triceps-dip", "triceps · chest", 14, 343),
    ("EVO", "S9LATP", "Lat Pulldown", "selectorized", "lat-pulldown", "lats · biceps", 14, 335),
    ("EVO", "S9LB", "Lower Back", "selectorized", "back-extension", "lower back", 15, 374),
    ("EVO", "S9RT", "Rotary Torso", "selectorized", "torso-rotation", "obliques", 15, 370),
    ("EVO", "S9AB", "Abdominal", "selectorized", "ab-crunch", "abs", 15, 366),
    ("EVO", "S9GRV", "Gravitron", "selectorized", "chin-up", "back · triceps", 15, 362),
    ("EVO", "S9LP", "Leg Press", "selectorized", "leg-press", "quads · glutes", 16, 409),
    ("EVO", "S9LE", "Leg Extension", "selectorized", "leg-extension", "quads", 16, 413),
    ("EVO", "S9LCP", "Prone Leg Curl", "selectorized", "leg-curl", "hamstrings", 16, 393),
    ("EVO", "S9SC", "Seated Calf", "selectorized", "calf-raise", "calves", 16, 401),
    ("EVO", "S9LC", "Seated Leg Curl", "selectorized", "leg-curl", "hamstrings", 16, 397),
    ("EVO", "S9AA", "Hip Abduction / Adduction", "selectorized", "multi-hip", "abductors · adductors", 16, 405),
    # --- XPLoad (plate-loaded) ---
    ("XPLoad", "P3VC", "Vertical Chest", "plate-loaded", "chest-press", "chest · triceps", 27, 615),
    ("XPLoad", "P3IP", "Incline Press", "plate-loaded", "incline-chest-press", "upper chest", 27, 619),
    ("XPLoad", "P3OP", "Overhead Press", "plate-loaded", "shoulder-press", "delts · triceps", 27, 623),
    ("XPLoad", "P3CR", "Compound Row", "plate-loaded", "seated-row", "back · biceps", 27, 627),
    ("XPLoad", "P3TE", "Triceps Extension", "plate-loaded", "triceps-extension", "triceps", 28, 650),
    ("XPLoad", "P3SD", "Seated Dip", "plate-loaded", "triceps-dip", "triceps · chest", 28, 654),
    ("XPLoad", "P3LATP", "Lat Pulldown", "plate-loaded", "lat-pulldown", "lats · biceps", 28, 642),
    ("XPLoad", "P3BC", "Biceps Curl", "plate-loaded", "biceps-curl", "biceps", 28, 646),
    ("XPLoad", "P3TBR", "T-Bar Row", "plate-loaded", "seated-row", "mid-back · lats", 29, 681),
    ("XPLoad", "P3FWN", "Four-Way Neck", "plate-loaded", None, "neck", 29, 689),
    ("XPLoad", "P3LCP", "Prone Leg Curl", "plate-loaded", "leg-curl", "hamstrings", 29, 677),
    ("XPLoad", "P3SC", "Seated Calf", "plate-loaded", "calf-raise", "calves", 29, 685),
    ("XPLoad", "P3LE", "Leg Extension", "plate-loaded", "leg-extension", "quads", 30, 713),
    ("XPLoad", "P3GH", "Glute-Ham", "plate-loaded", "back-extension", "hamstrings · glutes", 30, 725),
    ("XPLoad", "P3LP", "Leg Press", "plate-loaded", "leg-press", "quads · glutes", 30, 717),
    ("XPLoad", "P3DLS", "Deadlift / Shrug", "plate-loaded", "shrug", "traps · back", 30, 709),
    # --- Freedom Trainer (cable) ---
    ("Freedom Trainer", "F3FT", "Single Stack", "cable", None, "full body", 44, 966),
    ("Freedom Trainer", "F3FTD", "Dual Stack", "cable", None, "full body", 44, 970),
]


def data_uri(doc: pymupdf.Document, xref: int) -> str:
    pix = pymupdf.Pixmap(doc, xref)
    if pix.colorspace and pix.colorspace.n > 3:
        pix = pymupdf.Pixmap(pymupdf.csRGB, pix)
    smask = doc.extract_image(xref).get("smask")
    if smask:
        pix = pymupdf.Pixmap(pix, pymupdf.Pixmap(doc, smask))
    im = Image.open(io.BytesIO(pix.tobytes("png")))
    if im.mode == "RGBA":
        bg = Image.new("RGB", im.size, (255, 255, 255))
        bg.paste(im, mask=im.split()[-1])
        im = bg
    im = im.convert("RGB")
    im.thumbnail((MAX_PX, MAX_PX))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=JPEG_Q, optimize=True)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


def run(dry: bool = False) -> None:
    doc = pymupdf.open(PDF)
    if dry:
        for line, code, name, mtype, slug, muscle, pno, xref in MACHINES:
            info = doc.extract_image(xref)
            print(f"  {line + ' ' + name + ' (' + code + ')':44} {mtype:13} -> {slug or '(none)':20} "
                  f"[{muscle}]  p{pno} {info['width']}x{info['height']}")
        print(f"\n{len(MACHINES)} machines.")
        return

    with Session(engine) as s:
        brand = s.exec(select(Brand).where(Brand.name == BRAND)).first()
        if not brand:
            brand = Brand(name=BRAND, abbr="NA")
            s.add(brand)
            s.commit()
            s.refresh(brand)
        slug_to_id = {e.slug: e.id for e in s.exec(select(Exercise)).all()}
        missing = sorted({m[4] for m in MACHINES if m[4]} - slug_to_id.keys())
        if missing:
            raise SystemExit(f"exercise slugs not in DB: {missing}")

        old_ids = [m.id for m in s.exec(select(Machine).where(Machine.source == SOURCE)).all()]
        if old_ids:
            s.exec(delete(GymMachine).where(GymMachine.machine_id.in_(old_ids)))
            s.exec(delete(Machine).where(Machine.source == SOURCE))
            s.commit()

        for line, code, name, mtype, slug, muscle, pno, xref in MACHINES:
            s.add(Machine(
                brand_id=brand.id,
                model=f"{line} {name} ({code})",
                machine_type=mtype,
                exercise_id=slug_to_id[slug] if slug else None,
                muscle_label=muscle,
                image_url=data_uri(doc, xref),
                source=SOURCE,
            ))
        s.commit()
        print(f"Nautilus strength catalog: {len(MACHINES)} machines added (replaced {len(old_ids)} previous rows).")


if __name__ == "__main__":
    run(dry="--dry" in sys.argv)
