"""Add the official gym80 ("King of Machines", Gelsenkirchen) catalog from their
Gesamtbroschuere (full brochure, May 2025) to the DB, with each model's own
white-background product render inlined as a base64 data URI.

gym80 builds heavy German weight-stack + plate-loaded strength machines. This
imports the recognisable product lines a user actually stands in front of and
picks:

    SYGNUM (weight stack) · SYGNUM DUAL · CABLE ART · STATIONS · COMBO
    PURE KRAFT / PURE KRAFT STRONG (plate loaded)
    80ATHLETICS (functional / racks) · IRON QUBES · MOBILITY
    BENCHES · BASICS

Each catalogue grid page lays the models out in a 2-column grid of large
white-background renders, with the model's code caption ("LEG EXTENSION 3001
BEINSTRECKER 1570 x 1100 x 1040 mm 340 kg ...") sitting just below its render.
We bin renders -> machines geometrically (find the code caption directly under
each render), so we never rely on global text reading order.

A showcase gym "gym80 Showroom" is (re)built to hold the whole catalogue so it's
pickable in the app immediately.

Idempotent: re-running wipes the source-tagged rows + the showcase gym and rebuilds.

    python gym80_catalog.py            # build
    python gym80_catalog.py --dry      # extract + print, no DB writes
"""
from __future__ import annotations

import base64
import re
import sys
from pathlib import Path

import fitz
from sqlmodel import Session, delete, select

from database import engine
from models import Brand, Exercise, Gym, GymMachine, Machine

PDF = Path(__file__).resolve().parent.parent / "docs" / "gym80-Gesamtbroschuere.pdf"
SOURCE = "gym80-brochure"
GYM_NAME = "gym80 Showroom"

# page (0-based) where each product line starts -> (line label, mechanism).
# Carried forward until the next entry. Pages before the first are skipped.
# Sections we don't treat as loggable machines (pure storage, customisation,
# 80athletics small add-ons) are marked with mechanism None and skipped.
LINE_STARTS: list[tuple[int, str, str | None]] = [
    (10, "SYGNUM", "selectorized"),
    (26, "SYGNUM DUAL", "selectorized"),
    (32, "SYGNUM CABLE ART", "cable"),
    (37, "SYGNUM STATIONS", "multi-station"),
    (44, "SYGNUM COMBO", "selectorized"),
    (50, "PURE KRAFT", "plate-loaded"),
    (69, "PURE KRAFT STRONG", "plate-loaded"),
    (76, "80ATHLETICS", "performance"),
    (86, "80ATHLETICS", None),            # p86-94: pins / anchors / shelves -> skip
    (95, "IRON QUBES", "multi-station"),
    (99, "MOBILITY", "mobility"),
    (104, "BENCHES", "bench"),
    (111, "BASICS", "rack"),
    (119, "STORAGE", None),               # pure storage racks -> skip
    (126, "CUSTOM", None),                # upholstery / frame customisation -> skip
]

# english-name keyword -> exercise slug. First match wins (order matters:
# more specific phrases first).
SLUG_RULES: list[tuple[str, str]] = [
    ("leg extension", "leg-extension"),
    ("leg curl", "leg-curl"),
    ("lying abdominal", "ab-crunch"),
    ("abdominal", "ab-crunch"),
    ("ab swing", "ab-crunch"),
    ("crunch", "ab-crunch"),
    ("rotation", "torso-rotation"),
    ("twister", "torso-rotation"),
    ("lower back", "back-extension"),
    ("back extension", "back-extension"),
    ("back-extension", "back-extension"),
    ("hyper extension", "back-extension"),
    ("roman chair", "back-extension"),
    ("glute ham", "back-extension"),
    ("incline chest", "incline-chest-press"),
    ("incline bench", "incline-chest-press"),
    ("incline press", "incline-chest-press"),
    ("inner chest", "pec-fly"),
    ("chest cross", "pec-fly"),
    ("butterfly reverse", "rear-delt"),
    ("butterfly", "pec-fly"),
    ("pec", "pec-fly"),
    ("chest press", "chest-press"),
    ("seated chest", "chest-press"),
    ("bench press", "chest-press"),
    ("press bench", "chest-press"),
    ("decline chest", "chest-press"),
    ("decline bench", "chest-press"),
    ("decline press", "chest-press"),
    ("viking press", "shoulder-press"),
    ("neck press", "shoulder-press"),
    ("shoulder press", "shoulder-press"),
    ("multipress", "shoulder-press"),
    ("multi press", "shoulder-press"),
    ("multidr", "shoulder-press"),
    ("lateral raise", "lateral-raise"),
    ("seithebe", "lateral-raise"),
    ("lat pull", "lat-pulldown"),
    ("pulldown", "lat-pulldown"),
    ("pull down", "lat-pulldown"),
    ("iso lat", "lat-pulldown"),
    ("pull over", "pullover"),
    ("pullover", "pullover"),
    ("high row", "seated-row"),
    ("low row", "seated-row"),
    ("power row", "seated-row"),
    ("t-bar row", "seated-row"),
    ("bent over row", "seated-row"),
    ("seated row", "seated-row"),
    ("rowing", "seated-row"),
    ("row", "seated-row"),
    ("biceps", "biceps-curl"),
    ("bizeps", "biceps-curl"),
    ("scott curl", "biceps-curl"),
    ("curl", "biceps-curl"),
    ("triceps dip", "triceps-dip"),
    ("trizeps dip", "triceps-dip"),
    ("triceps", "triceps-extension"),
    ("trizeps", "triceps-extension"),
    ("dip", "triceps-dip"),
    ("forearm", "biceps-curl"),
    ("seated leg press", "leg-press"),
    ("lying leg press", "leg-press"),
    ("vertical leg press", "leg-press"),
    ("leg press", "leg-press"),
    ("hack squat", "hack-squat"),
    ("hackenschmidt", "hack-squat"),
    ("pendulum squat", "hack-squat"),
    ("belt squat", "hack-squat"),
    ("sissy squat", "hack-squat"),
    ("calf", "calf-raise"),
    ("wade", "calf-raise"),
    ("abduction", "hip-abduction"),
    ("abduktion", "hip-abduction"),
    ("adduction", "hip-adduction"),
    ("adduktion", "hip-adduction"),
    ("glute", "glute"),
    ("gluteus", "glute"),
    ("booty", "glute"),
    ("kick", "glute"),
    ("deadlift", "hip-thrust"),
    ("hip", "multi-hip"),
    ("multi-joint", "leg-press"),
    ("multi extension", "leg-press"),
    ("chin", "chin-up"),
    ("pull-up", "chin-up"),
    ("pull up", "chin-up"),
    ("leg raise", "leg-raise"),
    ("beinhebe", "leg-raise"),
    ("jammer", "jammer-press"),
    ("shrug", "shrug"),
]

# muscle label by slug (gainzy-style lowercase, mirrors the other catalogs).
MUSCLE: dict[str, str] = {
    "leg-extension": "quads",
    "leg-curl": "hamstrings",
    "leg-press": "quads · glutes",
    "hack-squat": "quads · glutes",
    "calf-raise": "calves",
    "hip-abduction": "outer thigh",
    "hip-adduction": "inner thigh",
    "multi-hip": "abductors · adductors",
    "glute": "glutes",
    "hip-thrust": "glutes",
    "chest-press": "chest · triceps",
    "incline-chest-press": "upper chest",
    "pec-fly": "chest",
    "rear-delt": "rear delts",
    "shoulder-press": "delts · triceps",
    "lateral-raise": "delts",
    "lat-pulldown": "lats · biceps",
    "seated-row": "back · biceps",
    "pullover": "lats",
    "biceps-curl": "biceps",
    "triceps-extension": "triceps",
    "triceps-dip": "triceps · chest",
    "chin-up": "back · biceps",
    "ab-crunch": "abs",
    "torso-rotation": "obliques",
    "back-extension": "lower back",
    "leg-raise": "abs",
    "jammer-press": "chest · shoulders",
    "shrug": "traps",
}

CODE_RE = re.compile(r"^(?:\d{3,4}[A-Z]?|80A\d{5}|\d{4})$")


def line_for_page(page: int) -> tuple[str, str | None]:
    line, mech = "", None
    for start, lbl, m in LINE_STARTS:
        if page >= start:
            line, mech = lbl, m
        else:
            break
    return line, mech


def slug_for(name: str) -> str | None:
    low = name.lower()
    for kw, slug in SLUG_RULES:
        # word-start match: blocks "chin" inside "ma-chin-e" and "pec" inside
        # "s-pec-ial", but still catches plurals/compounds (glutes, crossover)
        if re.search(r"\b" + re.escape(kw), low):
            return slug
    return None


def is_render(info: dict) -> bool:
    """A large white-background product render (not a muscle/feature icon)."""
    b = info["bbox"]
    return (b[2] - b[0]) > 150 and info["width"] > 600


def caption_under(words, bbox) -> list:
    """Words in the caption band just below a render's bbox, tight to the
    render's own column (so the neighbouring column doesn't bleed in)."""
    x0, _, x1, y1 = bbox
    return [
        w for w in words
        if y1 - 8 <= w[1] <= y1 + 140 and x0 - 6 <= w[0] <= x1 + 6
    ]


def _lines(band) -> list[list]:
    """Cluster caption words into visual lines (by y), each sorted left->right."""
    out: list[list] = []
    for w in sorted(band, key=lambda w: (w[1], w[0])):
        if out and abs(w[1] - out[-1][0][1]) <= 6:
            out[-1].append(w)
        else:
            out.append([w])
    for ln in out:
        ln.sort(key=lambda w: w[0])
    return out


def parse_caption(band) -> tuple[str, str, str] | None:
    """(english name, code, german name) from a caption band.

    Layout per cell, top to bottom:  GERMAN NAME / ENGLISH NAME + CODE / dims.
    The code is right-aligned on the english-name line; the german name is the
    line directly above it.
    """
    lines = _lines(band)
    code_li = code = None
    for i, ln in enumerate(lines):
        for w in ln:
            if CODE_RE.match(w[4]):
                code_li, code = i, w
                break
        if code:
            break
    if code is None:
        return None
    eng_line = lines[code_li]
    english = " ".join(w[4] for w in eng_line if w[0] < code[0] - 2).strip()
    german = ""
    if code_li > 0:
        german = " ".join(w[4] for w in lines[code_li - 1]).strip()
    if len(english) < 2:                      # title may sit on the line above
        if code_li > 0:
            english = " ".join(w[4] for w in lines[code_li - 1]).strip()
            german = ""
    if len(english) < 2:
        return None
    return english, code[4], german


def data_uri(doc: fitz.Document, xref: int) -> str:
    pix = fitz.Pixmap(doc, xref)
    if pix.colorspace and pix.colorspace.n == 4:        # CMYK -> RGB
        pix = fitz.Pixmap(fitz.csRGB, pix)
    while pix.width > 1200:                              # keep near-native res (~1200px)
        pix.shrink(1)
    if pix.alpha:
        pix = fitz.Pixmap(pix, 0)
    jpg = pix.tobytes("jpg", jpg_quality=88)
    return "data:image/jpeg;base64," + base64.b64encode(jpg).decode("ascii")


def extract(doc: fitz.Document):
    """-> list of dicts: line, code, name, german, mech, slug, xref, page."""
    seen: dict[str, dict] = {}
    for pno in range(doc.page_count):
        line, mech = line_for_page(pno)
        if mech is None:
            continue
        page = doc.load_page(pno)
        renders = [i for i in page.get_image_info(xrefs=True) if is_render(i)]
        if len(renders) < 2:           # skip single-image feature/section pages
            continue
        words = page.get_text("words")
        for info in renders:
            parsed = parse_caption(parse := caption_under(words, info["bbox"]))
            if not parsed:
                continue
            english, code, german = parsed
            if code in seen:           # keep first (largest series) occurrence
                continue
            slug = slug_for(english)
            seen[code] = {
                "line": line, "code": code, "name": english.title(),
                "german": german.title(), "mech": mech, "slug": slug,
                "xref": info["xref"], "page": pno,
            }
    return list(seen.values())


def run(dry: bool = False) -> None:
    doc = fitz.open(PDF)
    machines = extract(doc)
    machines.sort(key=lambda m: (m["page"], m["code"]))

    if dry:
        by_line: dict[str, int] = {}
        for m in machines:
            by_line[m["line"]] = by_line.get(m["line"], 0) + 1
            print(f"p{m['page']:>3} {m['code']:>9}  {m['line']:<18} "
                  f"{m['name']:<42} -> {m['slug']}")
        print("\n--- per line ---")
        for k, v in by_line.items():
            print(f"  {k:<20} {v}")
        mapped = sum(1 for m in machines if m["slug"])
        print(f"\nTOTAL {len(machines)} machines, {mapped} movement-mapped.")
        return

    with Session(engine) as s:
        brand = s.exec(select(Brand).where(Brand.name == "gym80")).first()
        if not brand:
            brand = Brand(name="gym80", abbr="G80")
            s.add(brand)
            s.commit()
            s.refresh(brand)

        slug_to_id = {e.slug: e.id for e in s.exec(select(Exercise)).all()}

        # --- idempotent reset ---
        old_gym = s.exec(select(Gym).where(Gym.name == GYM_NAME)).first()
        old_ids = [m.id for m in s.exec(
            select(Machine).where(Machine.source == SOURCE)).all()]
        if old_ids:
            s.exec(delete(GymMachine).where(GymMachine.machine_id.in_(old_ids)))
        if old_gym:
            s.exec(delete(GymMachine).where(GymMachine.gym_id == old_gym.id))
        s.exec(delete(Machine).where(Machine.source == SOURCE))
        if old_gym:
            s.exec(delete(Gym).where(Gym.id == old_gym.id))
        s.commit()

        cache: dict[int, str] = {}
        added: list[Machine] = []
        for d in machines:
            xref = d["xref"]
            if xref not in cache:
                cache[xref] = data_uri(doc, xref)
            slug = d["slug"]
            m = Machine(
                brand_id=brand.id,
                model=f"{d['line']} {d['name']} ({d['code']})",
                machine_type=d["mech"],
                exercise_id=slug_to_id.get(slug) if slug else None,
                muscle_label=MUSCLE.get(slug) if slug else None,
                image_url=cache[xref],
                source=SOURCE,
            )
            s.add(m)
            added.append(m)
        s.commit()
        for m in added:
            s.refresh(m)

        gym = Gym(name=GYM_NAME, area="King of Machines · demo")
        s.add(gym)
        s.commit()
        s.refresh(gym)
        for m in added:
            s.add(GymMachine(gym_id=gym.id, machine_id=m.id, added_by="catalog"))
        s.commit()

        mapped = sum(1 for d in machines if d["slug"])
        kb = sum(len(v) for v in cache.values()) * 3 // 4 // 1024
        print(f"gym80: {len(added)} machines added ({mapped} movement-mapped), "
              f"{len(cache)} unique renders (~{kb}KB), gym '{GYM_NAME}' id={gym.id}.")


if __name__ == "__main__":
    run(dry="--dry" in sys.argv)
