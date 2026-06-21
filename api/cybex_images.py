"""Inline official Cybex renders from the product-catalog PDF into our machines.

Each strength page of the brochure is a labelled grid of movements; we bin the
embedded cutouts to their grid cell (the reliable mapping — see notes) and pull
one clean render per movement. Stored as base64 (the PDF has no image URLs).

Usage:  python cybex_images.py
"""
from __future__ import annotations

import base64
from pathlib import Path

import fitz
from sqlmodel import Session

from database import engine
from models import Machine

PDF = Path(__file__).resolve().parent.parent / "tools" / "cybex" / "brochure.pdf"

# movement -> PDF image xref (Eagle NX black line from p21/p22; Prestige VRS for
# fly & lateral raise, which the Eagle NX line doesn't include)
MOVEMENT_XREF = {
    "chest-press": 171, "pulldown": 180, "arm-curl": 186, "leg-press": 189,
    "overhead-press": 174, "row": 177, "arm-extension": 183, "hip": 192,
    "leg-extension": 204, "calf": 207, "abdominal": 213, "torso-rotation": 210,
    "seated-leg-curl": 198, "glute": 201, "back-extension": 216,
    "fly-rear-delt": 249, "lateral-raise": 243,
}

# in-gym Cybex machine.id -> movement (48 keeps its real photo; 57 Bravo
# functional trainer has no matching movement render, left as-is)
MACHINE_MOVEMENT = {
    47: "leg-press",        # 45 Degree Linear Hack Squat
    49: "calf",             # 45 Degree Plate Loaded Donkey Calf
    54: "hip",              # Abductor & Adductor
    55: "chest-press",      # Incline ISO Lateral Converging Chest Press
    56: "fly-rear-delt",    # Incline Press & Fly Machine
    63: "seated-leg-curl",  # Class Seated Leg Curl
    65: "abdominal",        # Classic Abdominal Machine
    66: "back-extension",   # Classic Back Extension
    67: "arm-curl",         # Classic Bicep Curl
    70: "fly-rear-delt",    # Classic Fly Press
    72: "hip",              # Classic Hip Adduction / Inner Thigh
    73: "pulldown",         # Classic Lat Pulldown
    75: "lateral-raise",    # Classic Lateral Raise
    76: "leg-extension",    # Classic Leg Extension
    78: "overhead-press",   # Classic Multi Grip Overhead Shoulder Press
    79: "glute",            # Classic Multi Hip
    81: "torso-rotation",   # Classic Rotary Torso
    82: "arm-extension",    # Classic Seated Dip
}


def data_uri(doc: fitz.Document, xref: int) -> str:
    pix = fitz.Pixmap(doc, xref)
    if pix.colorspace and pix.colorspace.n == 4:   # CMYK -> RGB
        pix = fitz.Pixmap(fitz.csRGB, pix)
    if pix.alpha:
        pix = fitz.Pixmap(pix, 0)
    jpg = pix.tobytes("jpg", jpg_quality=85)
    return "data:image/jpeg;base64," + base64.b64encode(jpg).decode("ascii")


def run() -> None:
    doc = fitz.open(PDF)
    uris = {mv: data_uri(doc, xref) for mv, xref in MOVEMENT_XREF.items()}

    with Session(engine) as s:
        hit = 0
        for mid, mv in MACHINE_MOVEMENT.items():
            machine = s.get(Machine, mid)
            if not machine:
                print(f"  [skip] no machine id={mid}")
                continue
            machine.image_url = uris[mv]
            s.add(machine)
            hit += 1
            kb = len(uris[mv]) * 3 // 4 // 1024
            print(f"  [ok] {mid} {machine.model[:38]:40} <- {mv} (~{kb}KB)")
        s.commit()
    print(f"done. {hit}/{len(MACHINE_MOVEMENT)} Cybex machines updated.")


if __name__ == "__main__":
    run()
