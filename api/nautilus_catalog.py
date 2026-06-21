"""Add the official Nautilus Strength catalog (from the product brochure) to the
DB, with the brochure's own product renders inlined as base64.

The 93 pre-existing Nautilus rows are random secondhand listings; this adds the
*current* product lines (One, Inspiration, Impact, Instinct, HumanSport, Leverage,
Multi-Stations, Benches & Racks) as clean, recognisable models — the kind a user
actually stands in front of and picks. Each gets the brochure's white-background
render (document-global image xref -> downscaled JPEG data URI).

A showcase gym "Nautilus Strength Center" (the brochure's own facility name) is
(re)built to hold the whole catalog, so it's pickable in the app immediately.

Idempotent: re-running wipes the source-tagged rows + the showcase gym and rebuilds.

    python nautilus_catalog.py
"""
from __future__ import annotations

import base64
from pathlib import Path

import fitz
from sqlmodel import Session, delete, select

from database import engine
from models import Brand, Exercise, Gym, GymMachine, Machine

PDF = Path(__file__).resolve().parent.parent / "tools" / "nautilus" / "brochure.pdf"
SOURCE = "nautilus-brochure"
GYM_NAME = "Nautilus Strength Center"

# (line, model code, display name, mechanism, exercise slug | None, muscle label, image xref)
# xrefs were resolved from the brochure by side+row grid-binning, then verified.
MACHINES: list[tuple[str, str, str, str, str | None, str, int]] = [
    # --- Nautilus One (selectorized, side-stacked towers) ---
    ("One", "S6LP", "Leg Press", "selectorized", "leg-press", "quads · glutes", 38),
    ("One", "S6LE", "Leg Extension", "selectorized", "leg-extension", "quads", 42),
    ("One", "S6LC", "Seated Leg Curl", "selectorized", "leg-curl", "hamstrings", 46),
    ("One", "S6AA", "Hip Abduction / Adduction", "selectorized", "multi-hip", "abductors · adductors", 50),
    ("One", "S6CP", "Chest Press", "selectorized", "chest-press", "chest · triceps", 54),
    ("One", "S6LATP", "Lat Pulldown", "selectorized", "lat-pulldown", "lats · biceps", 58),
    ("One", "S6MR", "Row", "selectorized", "seated-row", "back · biceps", 62),
    ("One", "S6SP", "Shoulder Press", "selectorized", "shoulder-press", "delts · triceps", 66),
    ("One", "S6BC", "Biceps Curl", "selectorized", "biceps-curl", "biceps", 70),
    ("One", "S6TP", "Triceps Press", "selectorized", "triceps-extension", "triceps", 74),
    ("One", "S6AB", "Abdominal Crunch", "selectorized", "ab-crunch", "abs", 81),
    ("One", "S6RT", "Rotary Torso", "selectorized", "torso-rotation", "obliques", 85),
    ("One", "S6LB", "Low Back", "selectorized", "back-extension", "lower back", 89),
    ("One", "S6FWN", "Four-Way Neck", "selectorized", None, "neck", 93),
    # --- Inspiration (selectorized, Lock N Load) ---
    ("Inspiration", "IPLP3", "Leg Press", "selectorized", "leg-press", "quads · glutes", 111),
    ("Inspiration", "IPLE3", "Leg Extension", "selectorized", "leg-extension", "quads", 115),
    ("Inspiration", "IPLC3", "Leg Curl", "selectorized", "leg-curl", "hamstrings", 119),
    ("Inspiration", "IPAA3", "Abduction / Adduction", "selectorized", "multi-hip", "abductors · adductors", 123),
    ("Inspiration", "IPGM3", "Glute Press", "selectorized", "glute", "glutes", 127),
    ("Inspiration", "IPVP3", "Chest Press", "selectorized", "chest-press", "chest · triceps", 131),
    ("Inspiration", "IPPD3", "Lat Pull Down", "selectorized", "lat-pulldown", "lats · biceps", 135),
    ("Inspiration", "IPVR3", "Vertical Row", "selectorized", "seated-row", "back · biceps", 139),
    ("Inspiration", "IPPO3", "Pull Over", "selectorized", "pullover", "lats", 143),
    ("Inspiration", "IPPF3", "Pec Fly / Rear Deltoid", "selectorized", "pec-fly", "chest · rear delts", 150),
    ("Inspiration", "IPSP3", "Shoulder Press", "selectorized", "shoulder-press", "delts · triceps", 154),
    ("Inspiration", "IPDR3", "Deltoid Raise", "selectorized", "lateral-raise", "delts", 158),
    ("Inspiration", "IPBC3", "Biceps Curl", "selectorized", "biceps-curl", "biceps", 162),
    ("Inspiration", "IPBA3", "Bilateral Arm Curl", "selectorized", "biceps-curl", "biceps", 166),
    ("Inspiration", "IPTD4", "Tricep Dip", "selectorized", "triceps-dip", "triceps", 168),
    ("Inspiration", "IPTE3", "Tricep Extension", "selectorized", "triceps-extension", "triceps", 172),
    ("Inspiration", "IPAC3", "Abdominal Crunch", "selectorized", "ab-crunch", "abs", 176),
    ("Inspiration", "IPBE3", "Back Extension", "selectorized", "back-extension", "lower back", 180),
    ("Inspiration", "9NP-D9302", "Dual Adjustable Pulley", "functional", None, "full body", 182),
    # --- Impact (selectorized) ---
    ("Impact", "9NA-S1305", "Seated Leg Press", "selectorized", "leg-press", "quads · glutes", 200),
    ("Impact", "9NA-S1312", "Leg Extension", "selectorized", "leg-extension", "quads", 204),
    ("Impact", "9NA-S1313", "Seated Leg Curl", "selectorized", "leg-curl", "hamstrings", 208),
    ("Impact", "9NA-S1301", "Leg Curl", "selectorized", "leg-curl", "hamstrings", 212),
    ("Impact", "9NA-S1311", "Kneeling Leg Curl", "selectorized", "leg-curl", "hamstrings", 216),
    ("Impact", "9NA-S1308", "Adductor", "selectorized", "hip-adduction", "inner thigh", 220),
    ("Impact", "9NA-S1307", "Abductor", "selectorized", "hip-abduction", "outer thigh", 224),
    ("Impact", "9NA-S1309", "Standing Calf", "selectorized", "calf-raise", "calves", 228),
    ("Impact", "9NA-S4301", "Chest Press", "selectorized", "chest-press", "chest · triceps", 232),
    ("Impact", "9NA-S2301", "Incline Press", "selectorized", "incline-chest-press", "upper chest", 236),
    ("Impact", "9NA-S4304", "Deltoid Fly", "selectorized", "pec-fly", "chest · rear delts", 243),
    ("Impact", "9NA-S3303", "Fixed Lat Pull Down", "selectorized", "lat-pulldown", "lats · biceps", 247),
    ("Impact", "9NA-S3305", "Lat Pull Down", "selectorized", "lat-pulldown", "lats · biceps", 251),
    ("Impact", "9NA-S3301", "Vertical Row", "selectorized", "seated-row", "back · biceps", 255),
    ("Impact", "9NA-S3306", "Low Row", "selectorized", "seated-row", "back · biceps", 259),
    ("Impact", "9NA-S4307", "Shoulder Press", "selectorized", "shoulder-press", "delts · triceps", 263),
    ("Impact", "9NA-S4302", "Deltoid Raise", "selectorized", "lateral-raise", "delts", 267),
    ("Impact", "9NA-S5301", "Biceps Curl", "selectorized", "biceps-curl", "biceps", 271),
    ("Impact", "9NA-S5302", "Tricep Extension", "selectorized", "triceps-extension", "triceps", 275),
    ("Impact", "9NA-S5303", "Dip Machine", "selectorized", "triceps-dip", "triceps · chest", 279),
    ("Impact", "9NA-S6334", "Chin Dip Assist", "selectorized", "chin-up", "back · triceps", 286),
    ("Impact", "9NA-S3302", "Low Back", "selectorized", "back-extension", "lower back", 290),
    ("Impact", "9NA-S6301", "Abdominal", "selectorized", "ab-crunch", "abs", 294),
    # --- Instinct (selectorized, compact + dual-function) ---
    ("Instinct", "9NL-S1010", "Leg Extension", "selectorized", "leg-extension", "quads", 314),
    ("Instinct", "9NL-S1011", "Leg Curl", "selectorized", "leg-curl", "hamstrings", 318),
    ("Instinct", "9NL-D1014", "Dual Leg Extension / Leg Curl", "selectorized", "leg-extension", "quads · hamstrings", 322),
    ("Instinct", "9NL-D1013", "Dual Leg Press / Calf Raise", "selectorized", "leg-press", "quads · calves", 326),
    ("Instinct", "9NL-D1015", "Dual Inner / Outer Thigh", "selectorized", "multi-hip", "inner · outer thigh", 330),
    ("Instinct", "9NL-S1012", "Glute Press", "selectorized", "glute", "glutes", 334),
    ("Instinct", "9NL-S2100", "Chest Press", "selectorized", "chest-press", "chest · triceps", 338),
    ("Instinct", "9NL-D2120", "Dual Multi-Press", "selectorized", "chest-press", "chest · shoulders", 342),
    ("Instinct", "9NL-D3340", "Dual Lat Pull Down / Vertical Row", "selectorized", "lat-pulldown", "lats · back", 346),
    ("Instinct", "9NL-S3310", "Lat Pull Down", "selectorized", "lat-pulldown", "lats · biceps", 353),
    ("Instinct", "9NL-S3320", "Vertical Row", "selectorized", "seated-row", "back · biceps", 357),
    ("Instinct", "9NL-S4100", "Shoulder Press", "selectorized", "shoulder-press", "delts · triceps", 361),
    ("Instinct", "9NL-D2110", "Dual Pectoral Fly / Rear Deltoid", "selectorized", "pec-fly", "chest · rear delts", 365),
    ("Instinct", "9NL-S5100", "Biceps Curl", "selectorized", "biceps-curl", "biceps", 369),
    ("Instinct", "9NL-S5110", "Triceps Extension", "selectorized", "triceps-extension", "triceps", 373),
    ("Instinct", "9NL-D5120", "Dual Biceps Curl / Triceps Extension", "selectorized", "biceps-curl", "biceps · triceps", 377),
    ("Instinct", "9NL-S6300", "Rotary Torso", "selectorized", "torso-rotation", "obliques", 381),
    ("Instinct", "9NL-D6330", "Dual Abdominal / Lower Back", "selectorized", "ab-crunch", "abs · lower back", 385),
    ("Instinct", "9NL-D2002", "Dual Adjustable Pulley", "functional", None, "full body", 389),
    # --- HumanSport (dual-stack functional cable) ---
    ("HumanSport", "HSSC3", "Shoulder Chest", "functional", "chest-press", "chest · shoulders", 410),
    ("HumanSport", "HSLP3", "Lat Pulley", "functional", "lat-pulldown", "lats", 414),
    ("HumanSport", "HSAC3", "Arm Crunch", "functional", "ab-crunch", "abs", 418),
    ("HumanSport", "HSPL3", "Pull Lift", "functional", "seated-row", "full body pull", 422),
    ("HumanSport", "HSTD3", "Total Delts", "functional", "lateral-raise", "delts", 426),
    ("HumanSport", "HSTL3", "Total Legs", "functional", "leg-press", "legs", 430),
    ("HumanSport", "HSFT3", "Freedom Trainer Dual Stack", "functional", None, "full body", 434),
    # --- Leverage (plate-loaded) + featured plate-loaded ---
    ("Leverage", "9NP-L2002", "Chest Press", "plate-loaded", "chest-press", "chest · triceps", 454),
    ("Leverage", "9NP-L2003", "Incline Press", "plate-loaded", "incline-chest-press", "upper chest", 458),
    ("Leverage", "9NP-L2004", "Decline Press", "plate-loaded", "chest-press", "lower chest", 462),
    ("Leverage", "9NP-L3003", "Lat Pull Down", "plate-loaded", "lat-pulldown", "lats · biceps", 466),
    ("Leverage", "9NP-L3005", "High Row", "plate-loaded", "seated-row", "upper back", 470),
    ("Leverage", "9NP-L3004", "Low Row", "plate-loaded", "seated-row", "back", 474),
    ("Leverage", "9NP-L4002", "Shoulder Press", "plate-loaded", "shoulder-press", "delts · triceps", 478),
    ("Leverage", "9NP-L5002", "Biceps Curl", "plate-loaded", "biceps-curl", "biceps", 482),
    ("Leverage", "9NP-L5003", "Abdominal Crunch", "plate-loaded", "ab-crunch", "abs", 484),
    ("Leverage", "NP-L1131", "Glute Drive", "plate-loaded", "hip-thrust", "glutes", 489),
    ("Leverage", "NP-L8507", "Freedom Rack", "rack", None, "full body", 493),
    ("Leverage", "NP-L8500", "Smith Machine", "rack", None, "full body", 497),
    ("Leverage", "NP-L1141", "Angled Leg Press", "plate-loaded", "leg-press", "quads · glutes", 501),
    ("Leverage", "NP-L1130", "Hack Squat", "plate-loaded", "hack-squat", "quads · glutes", 505),
    ("Leverage", "NP-L1110", "Tilt Seat Calf", "plate-loaded", "calf-raise", "calves", 509),
    ("Leverage", "NP-L3140", "Incline Lever Row", "plate-loaded", "seated-row", "back", 513),
    # --- Multi-Stations ---
    ("Multi-Station", "9NP-M9201", "Multi-Station", "multi-station", None, "full body", 534),
    ("Multi-Station", "9NP-M9605", "Cable Crossover", "multi-station", None, "full body", 536),
    ("Multi-Station", "9NP-M9601", "5 Station", "multi-station", None, "full body", 526),
    ("Multi-Station", "9NP-M9620", "4 Station", "multi-station", None, "full body", 530),
    ("Multi-Station", "9NP-M9619", "9 Station", "multi-station", None, "full body", 522),
    # --- Benches & Racks ---
    ("Benches & Racks", "9-HDHR2", "Half Rack", "rack", None, "full body", 597),
    ("Benches & Racks", "9-HDHR2-SVA", "Half Rack w/ SVA Platform", "rack", None, "full body", 599),
    ("Benches & Racks", "9-HDP6D-SA", "Stand Alone SVA Platform", "accessory", None, "platform", 601),
    ("Benches & Racks", "9NP-B7506", "Multi-Adjustable Bench", "bench", None, "bench", 603),
    ("Benches & Racks", "9NP-B7507", "Flat Bench", "bench", None, "bench", 605),
    ("Benches & Racks", "9NP-B7523", "Adjustable Incline Bench", "bench", None, "bench", 609),
    ("Benches & Racks", "9NP-B7508", "Adjustable Decline Bench", "bench", None, "bench", 613),
    ("Benches & Racks", "9NP-B7516", "Utility Bench", "bench", None, "bench", 617),
    ("Benches & Racks", "9NP-B7521", "Stool", "accessory", None, "accessory", 619),
    ("Benches & Racks", "9NP-B7514", "Adjustable Back Extension", "bench", "back-extension", "lower back", 623),
    ("Benches & Racks", "9NP-B7522", "Glute Ham", "bench", "back-extension", "glutes · hamstrings", 628),
    ("Benches & Racks", "9NP-B7510", "Adjustable Abdominal Bench", "bench", "ab-crunch", "abs", 632),
    ("Benches & Racks", "9NP-B7509", "Seated Preacher Curl", "bench", "biceps-curl", "biceps", 636),
    ("Benches & Racks", "9NP-B7515", "Standing Preacher Curl", "bench", "biceps-curl", "biceps", 640),
    ("Benches & Racks", "9NP-B7518", "Dip Station", "rack", "triceps-dip", "triceps", 644),
    ("Benches & Racks", "9NP-B7511", "Pull-Up / Dip / Leg Raise", "rack", "chin-up", "full body", 648),
    ("Benches & Racks", "9NP-B7517", "Leg Raise / Dip", "rack", "leg-raise", "abs", 652),
    ("Benches & Racks", "9NP-B7202", "Olympic Bench Press", "bench", "chest-press", "chest", 656),
    ("Benches & Racks", "9NP-B7203", "Incline Bench Press", "bench", "incline-chest-press", "upper chest", 660),
    ("Benches & Racks", "9NP-B7204", "Decline Bench Press", "bench", "chest-press", "lower chest", 664),
    ("Benches & Racks", "9NP-B7205", "Military Press", "bench", "shoulder-press", "delts", 671),
    ("Benches & Racks", "9NP-R8008", "Squat Rack", "rack", None, "full body", 675),
    ("Benches & Racks", "9NP-R8005", "Power Cage", "rack", None, "full body", 679),
    ("Benches & Racks", "9NP-R8009", "Single Dumbbell Rack", "accessory", None, "storage", 683),
    ("Benches & Racks", "9NP-R8010", "Double Dumbbell Rack", "accessory", None, "storage", 687),
    ("Benches & Racks", "9NP-R8011", "Triple Dumbbell Rack", "accessory", None, "storage", 691),
    ("Benches & Racks", "9NP-R8014", "Beauty Bell Rack", "accessory", None, "storage", 695),
    ("Benches & Racks", "9NP-R8012", "Barbell Rack", "accessory", None, "storage", 699),
    ("Benches & Racks", "9NP-R8013", "Accessory Rack", "accessory", None, "storage", 703),
    ("Benches & Racks", "9NP-R7512", "2-Sided Olympic Weight Tree", "accessory", None, "storage", 710),
    ("Benches & Racks", "9NP-R7513", "4-Sided Olympic Weight Tree", "accessory", None, "storage", 714),
    ("Benches & Racks", "9NN-B7501", "Multi-Adjustable Bench", "bench", None, "bench", 718),
    ("Benches & Racks", "9NN-B7200", "Adjustable Abdominal Decline Bench", "bench", "ab-crunch", "abs", 722),
    ("Benches & Racks", "9NN-B7505", "Ab Bench", "bench", "ab-crunch", "abs", 726),
    ("Benches & Racks", "9NN-B7502", "45-Degree Back Extension", "bench", "back-extension", "lower back", 730),
    ("Benches & Racks", "9NN-R8001", "Dumbbell Rack 10-Pair / 2-Tier", "accessory", None, "storage", 734),
    ("Benches & Racks", "9NN-R8002", "Dumbbell Rack 10-Pair / 3-Tier", "accessory", None, "storage", 738),
    ("Benches & Racks", "9NN-B7503", "Olympic Flat Bench", "bench", "chest-press", "chest", 742),
    ("Benches & Racks", "9NN-B7201", "Olympic Incline Bench", "bench", "incline-chest-press", "upper chest", 746),
]


def data_uri(doc: fitz.Document, xref: int) -> str:
    """Document-global image xref -> downscaled white-background JPEG data URI."""
    pix = fitz.Pixmap(doc, xref)
    if pix.colorspace and pix.colorspace.n == 4:        # CMYK -> RGB
        pix = fitz.Pixmap(fitz.csRGB, pix)
    if pix.width > 300:                                  # ~500px renders -> ~250px tiles
        pix.shrink(1)
    if pix.alpha:                                        # flatten any alpha (jpg has none)
        pix = fitz.Pixmap(pix, 0)
    jpg = pix.tobytes("jpg", jpg_quality=80)
    return "data:image/jpeg;base64," + base64.b64encode(jpg).decode("ascii")


def run() -> None:
    doc = fitz.open(PDF)

    with Session(engine) as s:
        brand = s.exec(select(Brand).where(Brand.name == "Nautilus")).first()
        if not brand:
            brand = Brand(name="Nautilus", abbr="NA")
            s.add(brand)
            s.commit()
            s.refresh(brand)

        slug_to_id = {e.slug: e.id for e in s.exec(select(Exercise)).all()}

        # --- idempotent reset: drop the showcase gym + previously added rows ---
        old_gym = s.exec(select(Gym).where(Gym.name == GYM_NAME)).first()
        old_machine_ids = [
            m.id for m in s.exec(select(Machine).where(Machine.source == SOURCE)).all()
        ]
        if old_machine_ids:
            s.exec(delete(GymMachine).where(GymMachine.machine_id.in_(old_machine_ids)))
        if old_gym:
            s.exec(delete(GymMachine).where(GymMachine.gym_id == old_gym.id))
        s.exec(delete(Machine).where(Machine.source == SOURCE))
        if old_gym:
            s.exec(delete(Gym).where(Gym.id == old_gym.id))
        s.commit()

        # --- insert machines ---
        cache: dict[int, str] = {}
        added: list[Machine] = []
        for line, code, name, mtype, slug, muscle, xref in MACHINES:
            if xref not in cache:
                cache[xref] = data_uri(doc, xref)
            m = Machine(
                brand_id=brand.id,
                model=f"{line} {name} ({code})",
                machine_type=mtype,
                exercise_id=slug_to_id.get(slug) if slug else None,
                muscle_label=muscle,
                image_url=cache[xref],
                source=SOURCE,
            )
            s.add(m)
            added.append(m)
        s.commit()
        for m in added:
            s.refresh(m)

        # --- showcase gym holding the whole catalog ---
        gym = Gym(name=GYM_NAME, area="trusted strength · demo")
        s.add(gym)
        s.commit()
        s.refresh(gym)
        for m in added:
            s.add(GymMachine(gym_id=gym.id, machine_id=m.id, added_by="catalog"))
        s.commit()

        mapped = sum(1 for *_, slug, _, _ in MACHINES if slug)
        kb = sum(len(v) for v in cache.values()) * 3 // 4 // 1024
        print(f"Nautilus: {len(added)} machines added ({mapped} movement-mapped), "
              f"{len(cache)} unique renders (~{kb}KB), gym '{GYM_NAME}' id={gym.id}.")


if __name__ == "__main__":
    run()
