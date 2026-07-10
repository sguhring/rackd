"""Add the Megamass Europe gym-machine range to the DB, with each model's product
photo inlined as a base64 data URI.

Source is a print-to-PDF of the megamasseurope.com shop grid. Unlike the manufacturer
brochures, this PDF has NO TEXT LAYER — every caption is pixels — so we cannot anchor
a model name to its render by reading the page. What the layout does give us is a
rigid 4-column card grid, and the shop lists products alphabetically. So MODELS below
is ordered to match reading order (left->right, top->bottom, page 0->2) and binds
positionally.

megamass2.pdf is the COMPLETE capture (19 machines); the earlier MEGAMASS.pdf was
truncated at 16 and missed the page-2 additions (X-Shoulder Press, Xpload Linear
Press, Xpload Linear Row).

That makes the mapping fragile by construction: a product added to the shop, or a
reordering, silently shifts every later name onto the wrong photo. Two guards:
  * we assert the PDF yields exactly len(MODELS) product renders and refuse to build
    otherwise, rather than binding a truncated zip();
  * `--montage` writes a contact sheet pairing each photo with the name it received,
    so the binding can be eyeballed after any change to the source PDF.

The range is plate-loaded leverage/linear iron, plus one Smith tower.

Idempotent: re-running wipes the source-tagged rows + the showcase gym and rebuilds.

    python megamass_catalog.py            # build
    python megamass_catalog.py --dry      # extract + print, no DB writes
    python megamass_catalog.py --montage  # render the binding validation sheet
"""
from __future__ import annotations

import base64
import sys
from pathlib import Path

import fitz
from sqlmodel import Session, delete, select

from database import engine
from models import Brand, Exercise, Gym, GymMachine, Machine

PDF = Path(__file__).resolve().parent.parent / "docs" / "megamass2.pdf"
SOURCE = "megamass-shop"
GYM_NAME = "Megamass Showroom"

# IN READING ORDER — index i binds to the i-th product render. See module docstring.
# (model name, mechanism, exercise slug or None, muscle_label)
MODELS: list[tuple[str, str, str | None, str]] = [
    # page 0
    ("45 Degree Iso Linear Row Pro", "plate-loaded", "seated-row", "lats · mid-back"),
    ("45 Degree Linear Row", "plate-loaded", "seated-row", "lats · mid-back"),
    ("Chain Drive Lateral Raise", "plate-loaded", "lateral-raise", "side delts"),
    ("Classic T Bar Row", "plate-loaded", "seated-row", "lats · mid-back"),
    # page 1, row 1
    ("Leverage Chest", "plate-loaded", "chest-press", "chest · triceps"),
    ("Leverage Chest Pro", "plate-loaded", "chest-press", "chest · triceps"),
    ("Leverage Incline", "plate-loaded", "incline-chest-press", "upper chest"),
    ("Leverage Incline Pro", "plate-loaded", "incline-chest-press", "upper chest"),
    # page 1, row 2
    ("Leverage Pulldown", "plate-loaded", "lat-pulldown", "lats · biceps"),
    ("Leverage Row", "plate-loaded", "seated-row", "lats · mid-back"),
    ("Leverage Shoulder", "plate-loaded", "shoulder-press", "delts · triceps"),
    ("Shrug Row / RDLs Combo", "plate-loaded", "shrug", "traps · hamstrings"),
    # page 2, row 1
    ("Swing Squat Pro", "plate-loaded", "hack-squat", "quads · glutes"),
    ("T Bar Linear Row", "plate-loaded", "seated-row", "lats · mid-back"),
    ("Tower Smith", "rack", None, "full body"),
    ("V Type Linear Row", "plate-loaded", "seated-row", "lats · mid-back"),
    # page 2, row 2  (only in the complete megamass2.pdf capture)
    ("X-Shoulder Press", "plate-loaded", "shoulder-press", "delts · triceps"),
    ("Xpload Linear Press", "plate-loaded", "chest-press", "chest · triceps"),
    ("Xpload Linear Row", "plate-loaded", "seated-row", "lats · mid-back"),
]

# slug -> (name, muscle_group), created only if the exercise library lacks it
EXERCISE_FALLBACK = {
    "seated-row": ("Seated Row", "pull"), "lat-pulldown": ("Lat Pulldown", "pull"),
    "shrug": ("Shrug", "pull"), "chest-press": ("Chest Press", "push"),
    "incline-chest-press": ("Incline Chest Press", "push"),
    "shoulder-press": ("Shoulder Press", "push"), "lateral-raise": ("Lateral Raise", "push"),
    "hack-squat": ("Hack Squat", "legs"),
}


def is_render(im: dict) -> bool:
    """Product photos only. The logo strip, hero banner and cart dot are excluded by
    the size floor plus an aspect cap (those are all wide-and-short, or tiny)."""
    b = im["bbox"]
    w, h = b[2] - b[0], b[3] - b[1]
    return w > 100 and h > 100 and im["width"] > 150 and w / h < 3.0


def product_renders(doc) -> list[dict]:
    """Every product photo, in reading order: page, then row, then column."""
    out = []
    for pno in range(doc.page_count):
        ims = [im for im in doc.load_page(pno).get_image_info(xrefs=True) if is_render(im)]
        # bucket y to a 20pt row band so a slightly taller photo doesn't jump rows
        ims.sort(key=lambda im: (round(im["bbox"][1] / 20), im["bbox"][0]))
        out += [{"xref": im["xref"], "page": pno} for im in ims]
    return out


def data_uri(doc, xref: int) -> str:
    pix = fitz.Pixmap(doc, xref)
    if pix.colorspace and pix.colorspace.n == 4:
        pix = fitz.Pixmap(fitz.csRGB, pix)
    while pix.width > 1200:
        pix.shrink(1)
    if pix.alpha:
        pix = fitz.Pixmap(pix, 0)
    return "data:image/jpeg;base64," + base64.b64encode(pix.tobytes("jpg", jpg_quality=88)).decode("ascii")


def extract(doc) -> list[dict]:
    renders = product_renders(doc)
    if len(renders) != len(MODELS):
        raise SystemExit(
            f"ABORT: {PDF.name} yielded {len(renders)} product renders but MODELS has "
            f"{len(MODELS)}. The shop grid changed — re-read the PDF, fix MODELS to "
            f"match reading order, and verify with --montage before building."
        )
    return [{"name": n, "mech": m, "slug": s, "muscle": mu, **r}
            for (n, m, s, mu), r in zip(MODELS, renders)]


def montage(doc, machines: list[dict]) -> None:
    cols, cw, ch = 4, 260, 250
    rows = (len(machines) + cols - 1) // cols
    out = fitz.open()
    pg = out.new_page(width=cols * cw, height=rows * ch)
    for i, m in enumerate(machines):
        r, c = divmod(i, cols)
        x, y = c * cw, r * ch
        raw = base64.b64decode(data_uri(doc, m["xref"]).partition(",")[2])
        pg.insert_image(fitz.Rect(x + 5, y + 5, x + cw - 5, y + ch - 34),
                        pixmap=fitz.Pixmap(raw), keep_proportion=True)
        pg.insert_textbox(fitz.Rect(x + 4, y + ch - 32, x + cw - 4, y + ch),
                          f"{i + 1}. {m['name']}\n-> {m['slug'] or '(no movement)'}",
                          fontsize=9, align=1)
    path = Path(__file__).resolve().parent / "_megamass_montage.png"
    pg.get_pixmap(dpi=120).save(path)
    print("montage ->", path)


def run(mode: str = "") -> None:
    doc = fitz.open(PDF)
    machines = extract(doc)

    if mode in ("dry", "montage"):
        for i, m in enumerate(machines, 1):
            print(f"{i:2d}. p{m['page']} xref={m['xref']:3d} {m['mech']:12} "
                  f"{m['name'][:28]:28} -> {m['slug'] or '-':20} [{m['muscle']}]")
        print(f"\nTOTAL {len(machines)} machines, "
              f"{sum(1 for m in machines if m['slug'])} movement-mapped.")
        if mode == "montage":
            montage(doc, machines)
        return

    with Session(engine) as s:
        brand = s.exec(select(Brand).where(Brand.name == "Megamass")).first()
        if not brand:
            brand = Brand(name="Megamass", abbr="MM")
            s.add(brand)
            s.commit()
            s.refresh(brand)

        have = {e.slug for e in s.exec(select(Exercise)).all()}
        for slug in {m["slug"] for m in machines if m["slug"]} - have:
            nm, mg = EXERCISE_FALLBACK[slug]
            s.add(Exercise(slug=slug, name=nm, muscle_group=mg))
        s.commit()
        slug_to_id = {e.slug: e.id for e in s.exec(select(Exercise)).all()}

        # clean slate for this source
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
            if d["xref"] not in cache:
                cache[d["xref"]] = data_uri(doc, d["xref"])
            m = Machine(brand_id=brand.id, model=d["name"], machine_type=d["mech"],
                        exercise_id=slug_to_id.get(d["slug"]) if d["slug"] else None,
                        muscle_label=d["muscle"], image_url=cache[d["xref"]], source=SOURCE)
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
        print(f"Megamass: {len(added)} machines added "
              f"({sum(1 for m in added if m.image_url)} with image), gym '{GYM_NAME}' id={gym.id}.")


if __name__ == "__main__":
    run(mode="dry" if "--dry" in sys.argv else "montage" if "--montage" in sys.argv else "")
