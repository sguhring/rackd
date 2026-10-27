"""Add the Newtech Strength Equipment "Torture" range to the DB, with each model's
product photo inlined as a base64 data URI.

Source is five print-to-PDF captures of the megamasseurope-style Shopify collection
pages (Chest / Back / Legs / Arms / Shoulders) under docs/. They are hostile input:

  * NO TEXT LAYER — every caption is a glyph image, so a name cannot be located or
    read programmatically. The MODELS lists below were transcribed by eye.
  * Embedding is inconsistent. newtech.pdf draws two overlapping images per cell in
    its second row (one xref reused across three cells); newtech2.pdf page 0 has no
    per-product images at all — the whole page is three full-width raster strips.
    So we do NOT extract embedded images. We render the page and CROP each photo,
    which is uniform across all five files.
  * Card columns vary per row (4-across, 3-across for the Legs tail, 2-across for
    Arms/Shoulders), so columns are DETECTED per row by finding the white gutters
    between photos rather than hardcoded.

Binding is positional: within a row, the i-th detected photo takes the i-th name.
Guarded two ways — each row asserts detected-count == len(names) and refuses to
build otherwise, and `--montage` renders a contact sheet to eyeball the pairing.

KNOWN GAP: the Back collection advertises 10 products but only 8 are recoverable.
The last two cards were captured mid-fade-in; their photos AND captions are baked
into the PDF as near-white pixels (max channel value 255, 5 distinct values), so
there is nothing to extract. Re-capture docs/newtech2.pdf with the page fully
loaded to pick them up, then append them to the BACK list below.

    python newtech_catalog.py            # build
    python newtech_catalog.py --dry      # detect + print, no DB writes
    python newtech_catalog.py --montage  # render the binding validation sheet
"""
from __future__ import annotations

import base64
import sys
from pathlib import Path

import fitz
from sqlmodel import Session, delete, select

from database import engine
from models import Brand, Exercise, Gym, GymMachine, Machine

DOCS = Path(__file__).resolve().parent.parent / "docs"
SOURCE = "newtech-shop"
GYM_NAME = "Newtech Showroom"
BRAND = "Newtech"

DETECT_DPI = 100      # cheap pass to locate photos
CROP_DPI = 200        # quality pass to cut them out
DARK = 120            # a pixel this dark is machine, not background
GUTTER = 25           # detect-px of whitespace that separates two cards
PAD = 10              # pt of breathing room around a cropped photo

# (model name, exercise slug or None, muscle_label) — IN READING ORDER within each row.
CHEST = [
    [("Torture Wide Chest Press 2 (NEW)", "chest-press", "chest · triceps"),
     ("Torture Chest & Decline Combo 2 (NEW)", "chest-press", "chest · triceps"),
     ("Torture Incline Chest Press 2 (NEW)", "incline-chest-press", "upper chest"),
     ("Torture Seated Chest Press (Rotary)", "chest-press", "chest · triceps")],
    [("Torture Wide Chest Press", "chest-press", "chest · triceps"),
     ("Torture Incline Chest Press", "incline-chest-press", "upper chest"),
     ("Torture Pec Dec Fly", "pec-fly", "chest"),
     ("Torture Chest & Decline Combo", "chest-press", "chest · triceps")],
]
BACK = [
    [("Torture Standing & Seated Row Combo (New)", "seated-row", "lats · mid-back"),
     ("Torture Vertical Pull Down", "lat-pulldown", "lats · biceps"),
     ("Torture High Row", "seated-row", "upper back"),
     ("Torture 2 Way Row", "seated-row", "lats · mid-back")],
    [("Torture Low Row (Rotary) (New)", "seated-row", "lats · mid-back"),
     ("Torture Wide Pulldown Rear 2", "lat-pulldown", "lats · biceps"),
     ("Torture Front Row", "seated-row", "lats · mid-back"),
     ("Torture Wide Pulldown Front", "lat-pulldown", "lats · biceps")],
]
LEGS = [
    [("Torture Hack Squat Premium (Thomson) (New)", "hack-squat", "quads · glutes"),
     ("Torture Power Leg Press Premium (Thomson) (New)", "leg-press", "quads · glutes"),
     ("Torture Hack Squat (Thomson)", "hack-squat", "quads · glutes"),
     ("Torture Hip Thrust (Rotary) (New)", "hip-thrust", "glutes")],
    [("Torture Power Leg Press (Thomson)", "leg-press", "quads · glutes"),
     ("Torture Hack Press (Thomson)", "hack-squat", "quads · glutes"),
     ("Torture Belt Squat (New)", "hack-squat", "quads · glutes"),
     ("Torture Drop Squat", "hack-squat", "quads · glutes")],
    [("Torture Squat & Calf Raise", "hack-squat", "quads · calves"),
     ("Torture Leg Extension", "leg-extension", "quads"),
     ("Torture Leg Curl", "leg-curl", "hamstrings"),
     ("Torture Seated Calf Raise (NEW)", "calf-raise", "calves")],
    [("Torture Hip Thrust", "hip-thrust", "glutes"),
     ("Torture Kneeling Leg Curl", "leg-curl", "hamstrings"),
     ("Torture Glute Kick-Back", "glute", "glutes")],
]
ARMS = [
    [("Torture Overhead Extension", "triceps-extension", "triceps"),
     ("Torture Arm Curl", "biceps-curl", "biceps")],
]
SHOULDERS = [
    [("Torture Shoulder Press", "shoulder-press", "delts · triceps"),
     ("Torture Lateral Raise", "lateral-raise", "side delts")],
]

# file -> (collection, [(page, (y_top, y_bottom)) per photo row], rows of names)
COLLECTIONS = [
    ("newtech.pdf",  "Chest",     [(0, (347.8, 473.8)), (0, (616.3, 777.6))], CHEST),
    ("newtech2.pdf", "Back",      [(0, (338.4, 491.8)), (0, (642.2, 787.0))], BACK),
    ("newtech3.pdf", "Legs",      [(0, (347.8, 469.4)), (0, (639.4, 780.5)),
                                   (1, (137.5, 294.5)), (1, (445.0, 653.8))], LEGS),
    ("newtech4.pdf", "Arms",      [(1, (88.6, 421.2))], ARMS),
    ("newtch5.pdf",  "Shoulders", [(1, (119.5, 452.2))], SHOULDERS),
]

EXERCISE_FALLBACK = {
    "chest-press": ("Chest Press", "push"), "incline-chest-press": ("Incline Chest Press", "push"),
    "pec-fly": ("Pec Fly", "push"), "shoulder-press": ("Shoulder Press", "push"),
    "lateral-raise": ("Lateral Raise", "push"), "triceps-extension": ("Triceps Extension", "push"),
    "seated-row": ("Seated Row", "pull"), "lat-pulldown": ("Lat Pulldown", "pull"),
    "biceps-curl": ("Biceps Curl", "pull"), "hack-squat": ("Hack Squat", "legs"),
    "leg-press": ("Leg Press", "legs"), "leg-extension": ("Leg Extension", "legs"),
    "leg-curl": ("Leg Curl", "legs"), "calf-raise": ("Calf Raise", "legs"),
    "hip-thrust": ("Hip Thrust", "legs"), "glute": ("Glute", "legs"),
}


def photo_columns(page, y0: float, y1: float) -> list[tuple[float, float]]:
    """x-spans of each product photo in a row, found via the white gutters between."""
    pm = page.get_pixmap(dpi=DETECT_DPI)
    sc = 72.0 / DETECT_DPI
    ya, yb = int(y0 / sc), int(y1 / sc)
    s, n, st = pm.samples, pm.n, pm.stride
    runs: list[list[int]] = []
    for x in range(pm.width):
        if not any(s[y * st + x * n] < DARK for y in range(ya, min(yb, pm.height), 2)):
            continue
        if runs and x - runs[-1][1] <= GUTTER:
            runs[-1][1] = x
        else:
            runs.append([x, x])
    return [(a * sc, b * sc) for a, b in runs if (b - a) * sc > 40]


def crop_uri(page, rect: fitz.Rect) -> str:
    pm = page.get_pixmap(clip=rect, dpi=CROP_DPI)
    return "data:image/jpeg;base64," + base64.b64encode(
        pm.tobytes("jpg", jpg_quality=88)).decode("ascii")


def extract() -> list[dict]:
    out: list[dict] = []
    for fname, collection, bands, name_rows in COLLECTIONS:
        doc = fitz.open(DOCS / fname)
        if len(bands) != len(name_rows):
            raise SystemExit(f"ABORT {fname}: {len(bands)} photo rows vs {len(name_rows)} name rows.")
        for (pno, (y0, y1)), names in zip(bands, name_rows):
            page = doc.load_page(pno)
            cols = photo_columns(page, y0, y1)
            if len(cols) != len(names):
                raise SystemExit(
                    f"ABORT {fname} p{pno} row y{y0:.0f}-{y1:.0f}: detected {len(cols)} photos "
                    f"but have {len(names)} names. The capture changed — re-read the PDF, fix the "
                    f"row bands / names, and verify with --montage."
                )
            for (x0, x1), (name, slug, muscle) in zip(cols, names):
                out.append({
                    "file": fname, "collection": collection, "name": name,
                    "slug": slug, "muscle": muscle,
                    "rect": fitz.Rect(x0 - PAD, y0 - PAD, x1 + PAD, y1 + PAD),
                    "page": pno, "doc": doc,
                })
    return out


def montage(machines: list[dict]) -> None:
    cols, cw, ch = 5, 260, 250
    rows = (len(machines) + cols - 1) // cols
    out = fitz.open()
    pg = out.new_page(width=cols * cw, height=rows * ch)
    for i, m in enumerate(machines):
        r, c = divmod(i, cols)
        x, y = c * cw, r * ch
        raw = base64.b64decode(crop_uri(m["doc"].load_page(m["page"]), m["rect"]).partition(",")[2])
        pg.insert_image(fitz.Rect(x + 5, y + 5, x + cw - 5, y + ch - 40),
                        pixmap=fitz.Pixmap(raw), keep_proportion=True)
        pg.insert_textbox(fitz.Rect(x + 4, y + ch - 38, x + cw - 4, y + ch),
                          f"{i + 1}. {m['name']}\n-> {m['slug'] or '(none)'}", fontsize=7, align=1)
    path = Path(__file__).resolve().parent / "_newtech_montage.png"
    pg.get_pixmap(dpi=110).save(path)
    print("montage ->", path)


def run(mode: str = "") -> None:
    machines = extract()
    print("Back collection advertises 10 products; 2 are unrecoverable (blank in the "
          "capture) — see module docstring.")

    if mode in ("dry", "montage"):
        for i, m in enumerate(machines, 1):
            print(f"{i:2d}. {m['collection']:10} {m['name'][:44]:44} -> {m['slug'] or '-':20} [{m['muscle']}]")
        print(f"\nTOTAL {len(machines)} machines, {sum(1 for m in machines if m['slug'])} movement-mapped.")
        if mode == "montage":
            montage(machines)
        return

    with Session(engine) as s:
        brand = s.exec(select(Brand).where(Brand.name == BRAND)).first()
        if not brand:
            brand = Brand(name=BRAND, abbr="NT")
            s.add(brand)
            s.commit()
            s.refresh(brand)

        have = {e.slug for e in s.exec(select(Exercise)).all()}
        for slug in {m["slug"] for m in machines if m["slug"]} - have:
            nm, mg = EXERCISE_FALLBACK[slug]
            s.add(Exercise(slug=slug, name=nm, muscle_group=mg))
        s.commit()
        slug_to_id = {e.slug: e.id for e in s.exec(select(Exercise)).all()}

        old_gym = s.exec(select(Gym).where(Gym.name == GYM_NAME)).first()
        old_ids = [m.id for m in s.exec(select(Machine).where(Machine.source == SOURCE)).all()]
        if old_ids:
            s.exec(delete(GymMachine).where(GymMachine.machine_id.in_(old_ids)))
        if old_gym:
            s.exec(delete(GymMachine).where(GymMachine.gym_id == old_gym.id))
        s.exec(delete(Machine).where(Machine.source == SOURCE))
        if old_gym:
            s.exec(delete(Gym).where(Gym.id == old_gym.id))
        s.commit()

        added = []
        for d in machines:
            m = Machine(brand_id=brand.id, model=d["name"], machine_type="plate-loaded",
                        exercise_id=slug_to_id.get(d["slug"]) if d["slug"] else None,
                        muscle_label=d["muscle"],
                        image_url=crop_uri(d["doc"].load_page(d["page"]), d["rect"]),
                        source=SOURCE)
            s.add(m)
            added.append(m)
        s.commit()
        for m in added:
            s.refresh(m)

        gym = Gym(name=GYM_NAME, area="plate-loaded · demo")
        s.add(gym)
        s.commit()
        s.refresh(gym)
        for m in added:
            s.add(GymMachine(gym_id=gym.id, machine_id=m.id, added_by="catalog"))
        s.commit()
        print(f"Newtech: {len(added)} machines added "
              f"({sum(1 for m in added if m.image_url)} with image), gym '{GYM_NAME}' id={gym.id}.")


if __name__ == "__main__":
    run(mode="dry" if "--dry" in sys.argv else "montage" if "--montage" in sys.argv else "")
