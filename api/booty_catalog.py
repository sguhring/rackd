"""Add the Booty Builder (glute-training brand) 2025 commercial catalog to the DB,
with each model's white-background render inlined as a base64 data URI.

Two machine lines (accessories/zone pages skipped):
    Plate Loaded  ·  Selectorized

Layout: each spread is a 2-3 column grid; the model NAME is an ALL-CAPS header line
directly above its render. So we anchor on the caps header (exact line match against
the known model set) and bind the render just below it in the same column.

Idempotent: re-running wipes the source-tagged rows + the showcase gym and rebuilds.

    python booty_catalog.py            # build
    python booty_catalog.py --dry      # extract + print, no DB writes
"""
from __future__ import annotations

import base64
import sys
from pathlib import Path

import fitz
from sqlmodel import Session, delete, select

from database import engine
from models import Brand, Exercise, Gym, GymMachine, Machine

PDF = Path(__file__).resolve().parent.parent / "docs" / "Booty-Builder-2025-Commercial-Catalog-.pdf (1).pdf"
SOURCE = "booty-brochure"
GYM_NAME = "Booty Builder Showroom"

# page groups (0-based) -> mechanism. Marketing / accessories / zone pages excluded.
PAGES: dict[str, tuple[list[int], str]] = {
    "plate-loaded": [3, 4, 5],
    "selectorized": [7, 8, 9, 10],
}

# ALL-CAPS header (as printed) -> (clean model name, exercise slug or None, muscle_label)
MODELS: dict[str, tuple[str, str | None, str]] = {
    "PLATINUM V4":          ("Platinum V4", "hip-thrust", "glutes"),
    "DUAL HIP THRUST":      ("Dual Hip Thrust", "hip-thrust", "glutes"),
    "BELT SQUAT":           ("Belt Squat", "hack-squat", "quads · glutes"),
    "REVERSE LUNGE MACHINE":("Reverse Lunge Machine", "lunge", "quads · glutes"),
    "STANDING ABDUCTOR":    ("Standing Abductor", "hip-abduction", "glutes · abductors"),
    "STANDING HIP THRUST":  ("Standing Hip Thrust", "hip-thrust", "glutes"),
    "V-SQUAT":              ("V-Squat", "hack-squat", "quads · glutes"),
    "3D MULTI-ABDUCTOR":    ("3D Multi-Abductor", "multi-hip", "glutes · abductors"),
    "DEADLIFT/SPLIT SQUAT": ("Deadlift / Split Squat", "deadlift", "glutes · hamstrings"),
    "STEP-UP":             ("Step-Up", "step-up", "quads · glutes"),
    "PENDULUM SQUAT":       ("Pendulum Squat", "hack-squat", "quads · glutes"),
    "DEADLIFT":            ("Deadlift", "deadlift", "glutes · hamstrings · back"),
    "STANDING ADDUCTOR":    ("Standing Adductor", "hip-adduction", "adductors"),
    "KICK BACK":           ("Kick Back", "glute", "glutes"),
    "V8.0":                ("V8.0", "hip-thrust", "glutes"),
    "BACK EXTENSION":       ("Back Extension", "back-extension", "lower back · glutes"),
}
# exercises that may not exist yet in the library (slug -> (name, muscle_group))
NEW_EXERCISES = {"lunge": ("Lunge", "legs"), "deadlift": ("Deadlift", "legs"),
                 "step-up": ("Step-Up", "legs")}


def is_render(im: dict) -> bool:
    b = im["bbox"]
    return (b[2] - b[0]) > 120 and (b[3] - b[1]) > 120 and im["width"] > 150


def caps_headers(page) -> list[tuple[str, float, float, float]]:
    """(text, cx, top, bottom) for each ALL-CAPS header line that names a model."""
    ws = [w for w in page.get_text("words") if w[4].strip()]
    ws.sort(key=lambda w: (round(w[1] / 3), w[0]))
    out, cur, cy = [], [], None
    for w in ws:
        if cy is None or abs(w[1] - cy) <= 4:
            cur.append(w)
        else:
            out.append(cur); cur = [w]
        cy = w[1]
    if cur:
        out.append(cur)
    res = []
    for ln in out:
        ln.sort(key=lambda w: w[0])
        # split a row into its column segments on large horizontal gaps
        segs, seg = [], []
        for w in ln:
            if seg and w[0] - seg[-1][2] > 45:
                segs.append(seg); seg = []
            seg.append(w)
        if seg:
            segs.append(seg)
        for p in segs:
            txt = " ".join(w[4] for w in p).strip()
            if txt in MODELS:
                cx = (p[0][0] + p[-1][2]) / 2
                res.append((txt, cx, p[0][1], p[-1][3]))
    return res


def render_below(renders, cx, ybot):
    cand = [im for im in renders
            if im["bbox"][3] > ybot - 4 and im["bbox"][0] - 45 <= cx <= im["bbox"][2] + 45]
    return min(cand, key=lambda im: abs(im["bbox"][1] - ybot)) if cand else None


def data_uri(doc, xref) -> str:
    pix = fitz.Pixmap(doc, xref)
    if pix.colorspace and pix.colorspace.n == 4:
        pix = fitz.Pixmap(fitz.csRGB, pix)
    while pix.width > 1200:
        pix.shrink(1)
    if pix.alpha:
        pix = fitz.Pixmap(pix, 0)
    return "data:image/jpeg;base64," + base64.b64encode(pix.tobytes("jpg", jpg_quality=88)).decode("ascii")


def extract(doc):
    out, seen = [], set()
    for mech, pages in PAGES.items():
        for pno in pages:
            page = doc.load_page(pno)
            renders = [im for im in page.get_image_info(xrefs=True) if is_render(im)]
            entries, used = [], set()
            for txt, cx, top, bot in caps_headers(page):
                name, slug, muscle = MODELS[txt]
                if (mech, name) in seen:
                    continue
                seen.add((mech, name))
                im = render_below(renders, cx, bot)
                if im:
                    used.add(im["xref"])
                entries.append({"mech": mech, "name": name, "slug": slug, "muscle": muscle,
                                "xref": (im["xref"] if im else None), "page": pno, "_b": bot})
            # leftover: bind headers without a render to the nearest unused render on the page
            free = [im for im in renders if im["xref"] not in used]
            for e in (x for x in entries if x["xref"] is None):
                if not free:
                    break
                im = min(free, key=lambda im: abs(im["bbox"][1] - e["_b"]))
                e["xref"] = im["xref"]; free.remove(im); used.add(im["xref"])
            for e in entries:
                e.pop("_b", None); out.append(e)
    return out


def run(dry=False):
    doc = fitz.open(PDF)
    machines = extract(doc)
    if dry:
        for m in machines:
            print(f"p{m['page']:>2} {m['mech']:12} {m['name'][:26]:26} -> {m['slug']}  [{m['muscle']}]"
                  f"  {'img' if m['xref'] else 'NO-IMG'}")
        print(f"\nTOTAL {len(machines)} machines, {sum(1 for m in machines if m['xref'])} with image, "
              f"{sum(1 for m in machines if m['slug'])} movement-mapped.")
        return

    with Session(engine) as s:
        brand = s.exec(select(Brand).where(Brand.name == "Booty Builder")).first()
        if not brand:
            brand = Brand(name="Booty Builder", abbr="BB"); s.add(brand); s.commit(); s.refresh(brand)
        for slug, (nm, mg) in NEW_EXERCISES.items():
            if not s.exec(select(Exercise).where(Exercise.slug == slug)).first():
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

        cache, added = {}, []
        for d in machines:
            if d["xref"] and d["xref"] not in cache:
                cache[d["xref"]] = data_uri(doc, d["xref"])
            m = Machine(brand_id=brand.id, model=f"{d['name']} ({'PL' if d['mech']=='plate-loaded' else 'Sel'})",
                        machine_type=d["mech"], exercise_id=slug_to_id.get(d["slug"]) if d["slug"] else None,
                        muscle_label=d["muscle"], image_url=cache.get(d["xref"]) if d["xref"] else None, source=SOURCE)
            s.add(m); added.append(m)
        s.commit()
        for m in added:
            s.refresh(m)
        gym = Gym(name=GYM_NAME, area="glute training · demo"); s.add(gym); s.commit(); s.refresh(gym)
        for m in added:
            s.add(GymMachine(gym_id=gym.id, machine_id=m.id, added_by="catalog"))
        s.commit()
        print(f"Booty Builder: {len(added)} machines added "
              f"({sum(1 for m in added if m.image_url)} with image), gym '{GYM_NAME}' id={gym.id}.")


if __name__ == "__main__":
    run(dry="--dry" in sys.argv)
