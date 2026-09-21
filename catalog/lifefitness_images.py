"""Attach Life Fitness + Hammer Strength product photos from the 2025 catalog.

    python catalog/lifefitness_images.py            # dry run: pairing + matches
    python catalog/lifefitness_images.py --write    # extract, attach, inline into DB

Source: docs/life-fitness-hammer-strength-2025-catalog.pdf. Its product pages put a
"NAME / CODE" label directly under each studio photo (the same layout Precor uses),
so every photo is found by locating the product CODE on the page and taking the
photo whose bottom edge sits just above that label line. A few labels are printed
on top of a hero photo or beside it; those are pinned by hand in OVERRIDES.

Our Life Fitness / Hammer Strength rows are marketplace listings with seller
spellings ("ISO Lateral DY (Dorian Yates) Row", "Select Bicep & Tricep"), so the
join is by normalised name within a product FAMILY, and only current lines that
are in the catalog get a photo:

  Insignia (SS-)  Axiom (OP-)  Signature plate-loaded (SPL*)  Cable Motion
  Hammer plate-loaded (IL-/PL-)  Ground Base (GB-)  Hammer Select (HS-)  MTS

Older generations that merely share a name (Signature/Pro selectorized, Optima,
first-gen "OG" Hammer pieces, PL-LP seated leg press) are deliberately left on
their marketplace photo — a successor's photo is the wrong machine.

Writes tools/cap/www/img/lifefitness/<code>.jpg, sets `image` on the matched rows
in catalog/machines_resolved.json, and (with --write) inlines the photo into
api/rackd.db for the same rows, replacing the marketplace URL.
"""
from __future__ import annotations

import base64
import io
import json
import re
import sqlite3
import sys
from collections import Counter
from pathlib import Path

import pymupdf
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
PDF = ROOT / "docs" / "life-fitness-hammer-strength-2025-catalog.pdf"
RESOLVED = ROOT / "catalog" / "machines_resolved.json"
DB = ROOT / "api" / "rackd.db"
OUT = ROOT / "tools" / "cap" / "www" / "img" / "lifefitness"
BRANDS = ("Life Fitness", "Hammer Strength")

MAX_PX, JPEG_Q = 512, 82          # same inlining budget as api/load_resolved.py
CLIP_DPI = 200

# product pages of the catalog (1-based) and the codes printed on them
PAGES = [33, 34, 36, 37, 46, 68, 69, 70, 72, 74, 75, 77]
CODES = """
SS-ADC SS-SP SS-RW SS-CP SS-TP SS-LR SS-TE SS-BCD SS-CPX SS-BC SS-PD SS-PDX SS-FLY
SS-LE SS-LC SS-SLC SS-CE SS-SLP SS-GL SS-GLB SS-AB SS-TR SS-BE SS-ABD SS-SHB SS-HAD SS-HAA
OP-CP OP-LP OP-RW OP-SP OP-PD OP-BC OP-TE OP-LE OP-LC OP-AB OP-MP OP-LR OP-FLY OP-BT
OP-HAA OP-LCE OP-SLCE OP-ABBA OP-SM OP-DAP
SPLLLP SPLPD SPLROW SPLKLC SPLBC SPLHR SPLDIP SPLLE SPLDCP SPLIP SPLSP SPLCALF SSM
CMDAP LCM-CC
IL-BP PL-FLY IL-CB IL-DRW IL-DCP IL-LR IL-ROW IL-SP IL-FMP PL-TBR PL-PO IL-WPD PL-LR IL-PD
IL-HR IL-IP IL-WC IL-HBP
PL-DIP PL-BI PL-SH PL-AB PL-4W PL-GRIP
PL-BSQ PL-HSQ PL-ANH PL-GHRH HSLLP IL-LC IL-KLC PL-VSQ PL-CALF HSSM-V PL-TIB HSSM PL-GLD IL-LE PL-XSQ
GB-MSQ GB-CT GB-J GB-SHP
HS-CP HS-FPD HS-ADC HS-BC HS-RW HS-SP HS-TE HS-PD HS-LR HS-PEC HS-FLY HS-BE HS-HAB HS-HAD
HS-LE HS-SLP HS-SLC HS-SC HS-ABC HS-HG HS-HC HS-LC
MTSAB MTSDP MTSLE MTSHR MTSBC MTSSP MTSKC MTSIP MTSCP MTSTE MTSFP MTSRW
""".split()

# code -> (page, image xref): labels the geometric rule can't place (printed
# beside the photo, or the code broken over two lines like "HS-" / "ADC").
OVERRIDES: dict[str, tuple[int, int]] = {
    "HS-ADC": (74, 1894), "HS-SLC": (75, 1943), "HS-HC": (75, 1953),
    "LCM-CC": (46, 1102), "CMDAP": (46, 1110), "OP-DAP": (46, 1106),
}

# ── name matching ─────────────────────────────────────────────────────────────
# seller noise stripped before matching
NOISE = re.compile(
    r"(\s*[-–]\s*(rare|clean|model|style|newest style|newest series|current ?&?|condition|mint|"
    r"stunning|phenomenal|immaculate|extremely rare|latest ?&?|true linear version|"
    r"one left|2019 model|best version|top load model.*)\s*$)|"
    r"(\s*\(\s*rare\s*\))|(\s*w\s*/\s*\d+\s*lb\.?\s*stacks?)|(\s*\d+\s*lb\.?\s*stacks?)|"
    r"(\s*w\s*/\s*rom)|(\s*\(4\)\s*loading horns)|(\s*4 loading horns)",
    re.I,
)


def norm(s: str) -> str:
    s = s.lower()
    s = NOISE.sub("", s)
    s = s.replace("&", " and ").replace("/", " ").replace("-", " ").replace(".", "")
    s = re.sub(r"\b(iso lateral|iso lat|isolateral)\b", "iso", s)
    s = re.sub(r"\b(plate loaded|plateloaded|platinum|series|machine|combo|hammer strength|"
               r"selectorized|w|the|dual \(4\))\b", " ", s)
    s = re.sub(r"\b(bicep|biceps)\b", "biceps", s)
    s = re.sub(r"\b(tricep|triceps)\b", "triceps", s)
    s = re.sub(r"\bpec fly\b", "pectoral fly", s)
    s = re.sub(r"\brear delt\b", "rear deltoid", s)
    s = re.sub(r"\babdominal crunch\b|\bab crunch\b", "abdominal crunch", s)
    return " ".join(s.split())


# family -> (prefix regex on the ORIGINAL model, [(regex on normalised remainder, code)])
# first matching rule wins, so specific patterns come before general ones.
FAMILIES: list[tuple[str, re.Pattern[str], list[tuple[str, str]]]] = [
    ("insignia", re.compile(r"^insignia\b", re.I), [
        (r"assist(ed)?.*dip", "SS-ADC"),
        (r"dual axis chest press", "SS-CPX"), (r"uni lateral chest press", ""),
        (r"chest press", "SS-CP"),
        (r"pulldown.*dual", "SS-PDX"), (r"lat pulldown|pulldown", "SS-PD"),
        (r"overhead press|shoulder press", "SS-SP"),
        (r"\brow\b", "SS-RW"), (r"lateral raise", "SS-LR"),
        (r"triceps press|seated dip", "SS-TP"), (r"triceps extension", "SS-TE"),
        (r"biceps curl dependent|curl.*dependent", "SS-BCD"),
        (r"biceps curl|bilateral biceps", "SS-BC"),
        (r"pectoral fly", "SS-FLY"),
        (r"leg extension and leg curl|leg extension.*curl", ""),
        (r"leg extension", "SS-LE"), (r"seated leg curl", "SS-SLC"),
        (r"prone lying leg curl|leg curl", "SS-LC"), (r"calf", "SS-CE"),
        (r"arc leg press|seated leg press", "SS-SLP"),
        (r"glute bridge", "SS-GLB"), (r"\bglute\b", "SS-GL"),
        (r"hip abduction adduction|abduction.*adduction", "SS-HAA"),
        (r"sit stand hip abduct|abductor", "SS-SHB"), (r"hip adduction", "SS-HAD"),
        (r"abdominal advanced", "SS-ABD"), (r"abdominal", "SS-AB"),
        (r"back extension", "SS-BE"), (r"torso rotation", "SS-TR"),
    ]),
    ("axiom", re.compile(r"^axiom\b", re.I), [
        (r"abdominal.*back extension", "OP-ABBA"), (r"biceps curl.*triceps", "OP-BT"),
        (r"seated leg curl.*extension", "OP-SLCE"),
        (r"leg (curl|extension).*(curl|extension)|leg extension.*prone", "OP-LCE"),
        (r"pulldown.*row", "OP-LR"), (r"pectoral fly", "OP-FLY"),
        (r"hip abduct", "OP-HAA"), (r"multi press", "OP-MP"),
        (r"dual adjustable pulley", "OP-DAP"), (r"smith", "OP-SM"),
        (r"chest press", "OP-CP"), (r"leg press", "OP-LP"), (r"row", "OP-RW"),
        (r"shoulder press", "OP-SP"), (r"lat pulldown", "OP-PD"), (r"biceps curl", "OP-BC"),
        (r"triceps extension", "OP-TE"), (r"leg extension", "OP-LE"),
        (r"leg curl", "OP-LC"), (r"abdominal", "OP-AB"),
    ]),
    ("signature-pl", re.compile(r"^signature( series)?( iso lateral)? plate loaded\b", re.I), [
        (r"linear leg press", "SPLLLP"), (r"high row", "SPLHR"), (r"\brow\b", "SPLROW"),
        (r"kneeling leg curl", "SPLKLC"), (r"biceps curl", "SPLBC"), (r"seated dip", "SPLDIP"),
        (r"leg extension", "SPLLE"), (r"decline", "SPLDCP"), (r"incline", "SPLIP"),
        (r"shoulder press", "SPLSP"), (r"calf", "SPLCALF"), (r"pulldown", "SPLPD"),
    ]),
    ("hammer-mts", re.compile(r"^(hammer strength )?mts\b", re.I), [
        (r"abdominal", "MTSAB"), (r"decline", "MTSDP"), (r"leg extension", "MTSLE"),
        (r"high row", "MTSHR"), (r"biceps", "MTSBC"), (r"shoulder press", "MTSSP"),
        (r"kneeling leg curl", "MTSKC"), (r"incline", "MTSIP"),
        (r"chest press|chest bench press", "MTSCP"), (r"triceps", "MTSTE"),
        (r"front pulldown", "MTSFP"), (r"\brow\b", "MTSRW"),
    ]),
    ("hammer-select", re.compile(r"^(hammer strength )?select\b", re.I), [
        (r"biceps and triceps|bicep.*tricep", ""),
        (r"assist(ed)?.*dip", "HS-ADC"), (r"chest press", "HS-CP"), (r"fixed pulldown", "HS-FPD"),
        (r"biceps", "HS-BC"), (r"\brow\b", "HS-RW"), (r"shoulder press", "HS-SP"),
        (r"triceps", "HS-TE"), (r"lat pulldown", "HS-PD"), (r"lateral raise", "HS-LR"),
        (r"pectoral fly.*rear deltoid", "HS-FLY"), (r"pectoral fly", "HS-PEC"),
        (r"back extension", "HS-BE"), (r"hip abduction", "HS-HAB"), (r"hip adduction", "HS-HAD"),
        (r"leg extension", "HS-LE"), (r"seated leg press", "HS-SLP"), (r"seated leg curl", "HS-SLC"),
        (r"standing calf", "HS-SC"), (r"horizontal calf", "HS-HC"), (r"abdominal", "HS-ABC"),
        (r"hip and glute|hip.*glute", "HS-HG"), (r"prone lying leg curl|leg curl", "HS-LC"),
    ]),
    ("signature-cable", re.compile(r"^(signature( series)?( platinum)?\s*)?", re.I), [
        (r"^pro\b|^optima|jungle|mj\d|station|universal|pulldown|row", ""),
        (r"dual adjustable pulley|cmdap", "CMDAP"), (r"adjustable cable crossover", "LCM-CC"),
        (r"smith", "SSM"),
    ]),
    ("ground-base", re.compile(r"^(plate loaded |plate-loaded )?ground base", re.I), [
        (r"jammer", "GB-J"), (r"multi squat|deadlift", "GB-MSQ"), (r"twist", "GB-CT"),
        (r"squat.*high pull", "GB-SHP"),
    ]),
    ("hammer-pl", re.compile(r"^", re.I), [          # everything else under Hammer Strength
        (r"^og\b|first gen", ""), (r"^pl lp\b|seated leg press|iso seated leg press|^leg press$", ""),
        (r"behind.*neck", ""), (r"super squat|hack super squat", ""),
        (r"cable|dual pulldown|hd elite|jammer|core station|standing calf|vkr|chin|2 in 1|fixed pad", ""),
        (r"combo twist|twist", "GB-CT"), (r"squat high pull", "GB-SHP"),
        (r"seated dip", "PL-DIP"),
        (r"horizontal bench press", "IL-HBP"), (r"bench press", "IL-BP"),
        (r"super fly|superfly|10 degree fly", "PL-FLY"),
        (r"chest.*back", "IL-CB"), (r"d ?y|dorian", "IL-DRW"),
        (r"decline", "IL-DCP"), (r"low row", "IL-LR"), (r"high row", "IL-HR"),
        (r"t bar row", "PL-TBR"), (r"standing row", ""), (r"\brow\b", "IL-ROW"),
        (r"super incline|front military", "IL-FMP"), (r"incline", "IL-IP"),
        (r"shoulder press", "IL-SP"), (r"wide chest", "IL-WC"),
        (r"pullover", "PL-PO"), (r"wide pulldown", "IL-WPD"),
        (r"front (lat )?pulldown", "IL-PD"), (r"lateral raise|iso raise", "PL-LR"),
        (r"seated dip|dip", "PL-DIP"), (r"seated biceps|biceps curl", "PL-BI"),
        (r"shrug", "PL-SH"), (r"abdominal oblique|oblique", "PL-AB"),
        (r"4 way neck|neck", "PL-4W"), (r"gripper", "PL-GRIP"),
        (r"belt squat", "PL-BSQ"), (r"hack squat", "PL-HSQ"), (r"nordic", "PL-ANH"),
        (r"glute ham|reverse hyper", "PL-GHRH"), (r"linear leg press|45 degree.*leg press", "HSLLP"),
        (r"kneeling leg curl", "IL-KLC"), (r"leg curl", "IL-LC"), (r"leg extension", "IL-LE"),
        (r"v squat", "PL-VSQ"), (r"pendulum", "PL-XSQ"),
        (r"seated calf|calf", "PL-CALF"), (r"tibia", "PL-TIB"), (r"glute drive", "PL-GLD"),
        (r"vertical smith", "HSSM-V"), (r"smith", "HSSM"),
        (r"triceps extension|triceps", ""), (r"jammer", ""),
    ]),
]


def code_for(brand: str, model: str) -> str | None:
    """Catalog code for a DB/catalog model, or None when it is not a current
    catalogued piece (older generation, combo, rack, etc.)."""
    m = model.strip()
    if brand == "Life Fitness":
        fam_names = ("insignia", "axiom", "signature-pl", "hammer-mts", "hammer-select", "signature-cable")
        if re.match(r"^hammer strength (linear )?counter ?balanced .*smith", m, re.I):
            return "HSSM"
    else:
        fam_names = ("hammer-mts", "hammer-select", "ground-base", "hammer-pl")
    for fam, prefix, rules in FAMILIES:
        if fam not in fam_names or not prefix.search(m):
            continue
        rest = norm(prefix.sub("", m, count=1))
        for pat, code in rules:
            if re.search(pat, rest):
                return code or None
        return None
    return None


# ── photo location ────────────────────────────────────────────────────────────

def find_photos(doc: pymupdf.Document) -> dict[str, tuple[int, int, pymupdf.Rect]]:
    """code -> (page, xref, rect) using the label-under-photo layout."""
    out: dict[str, tuple[int, int, pymupdf.Rect]] = {}
    wanted = set(CODES)
    for pno in PAGES:
        page = doc[pno - 1]
        area = page.rect.width * page.rect.height
        imgs = []
        seen = set()
        for x in page.get_images(full=True):
            for r in page.get_image_rects(x[0]):
                k = (x[0], round(r.x0), round(r.y0))
                if k in seen:
                    continue
                seen.add(k)
                if r.width >= 80 and r.height >= 80 and r.width * r.height / area <= 0.45:
                    imgs.append((x[0], r))
        words = page.get_text("words")                      # x0 y0 x1 y1 text block line word
        lines: dict[tuple[int, int], list] = {}
        for w in words:
            lines.setdefault((w[5], w[6]), []).append(w)
        for w in words:
            code = w[4].strip("/*").upper()
            if code not in wanted or code in out or code in OVERRIDES:
                continue
            line = lines[(w[5], w[6])]
            lx0, ly0 = min(l[0] for l in line), min(l[1] for l in line)
            cx = lx0 + 10
            below = [(ly0 - r.y1, x, r) for x, r in imgs
                     if r.x0 - 12 <= cx <= r.x1 and -30 <= ly0 - r.y1 <= 70]
            inside = [(r.width * r.height, x, r) for x, r in imgs
                      if r.x0 <= cx <= r.x1 and r.y0 <= ly0 <= r.y1]
            pick = None
            if below:
                pick = min(below, key=lambda t: abs(t[0]))
            elif inside:
                pick = min(inside)
            if pick:
                out[code] = (pno, pick[1], pick[2])
    for code, (pno, xref) in OVERRIDES.items():
        page = doc[pno - 1]
        rects = page.get_image_rects(xref)
        if rects:
            out[code] = (pno, xref, rects[0])
    return out


def extract(doc: pymupdf.Document, pno: int, xref: int, rect: pymupdf.Rect, dest: Path,
            placements: Counter) -> None:
    if placements[xref] == 1:
        pix = pymupdf.Pixmap(doc, xref)
        if pix.colorspace and pix.colorspace.n > 3:
            pix = pymupdf.Pixmap(pymupdf.csRGB, pix)
        smask = doc.extract_image(xref).get("smask")    # cut-outs keep their alpha in a soft mask
        if smask:
            pix = pymupdf.Pixmap(pix, pymupdf.Pixmap(doc, smask))
        if pix.alpha:                                   # composite the cut-out on white
            im = Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGBA")
            bg = Image.new("RGB", im.size, (255, 255, 255))
            bg.paste(im, mask=im.split()[-1])
            bg.save(dest, "JPEG", quality=90)
        else:
            pix.save(dest, jpg_quality=90)
    else:
        doc[pno - 1].get_pixmap(clip=rect, dpi=CLIP_DPI).save(dest, jpg_quality=90)


def inline(path: Path) -> str:
    im = Image.open(path)
    if im.mode not in ("RGB", "L"):
        im = im.convert("RGB")
    im.thumbnail((MAX_PX, MAX_PX))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=JPEG_Q, optimize=True)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    write = "--write" in sys.argv
    doc = pymupdf.open(PDF)
    photos = find_photos(doc)
    missing = [c for c in CODES if c not in photos]
    print(f"catalog codes: {len(CODES)}   photos located: {len(photos)}   "
          f"unlocated: {missing}\n")

    resolved = json.loads(RESOLVED.read_text(encoding="utf-8"))
    rows = [r for r in resolved if r["brand"] in BRANDS]
    hits: list[tuple[dict, str]] = []
    skipped: list[str] = []
    for r in rows:
        code = code_for(r["brand"], r["model"])
        if code and code in photos:
            hits.append((r, code))
        else:
            skipped.append(f"{r['brand'][:4]:4} {r['model'][:60]}" + (f"  (code {code} has no photo)" if code else ""))
    print(f"{len(rows)} Life Fitness / Hammer Strength rows: {len(hits)} matched, "
          f"{len(skipped)} left on their current photo\n")
    for r, code in sorted(hits, key=lambda t: (t[1], t[0]["model"])):
        print(f"   {code:<8} <- {r['brand'][:4]:4} {r['model'][:70]}")
    print("\nleft as-is:")
    for s in skipped:
        print("   ", s)
    if not write:
        print("\ndry run — pass --write to extract and attach")
        return

    placements: Counter = Counter()
    for i in range(doc.page_count):
        for x in {x[0] for x in doc[i].get_images(full=True)}:
            placements[x] += len(doc[i].get_image_rects(x))
    OUT.mkdir(parents=True, exist_ok=True)
    for code in {c for _, c in hits}:
        pno, xref, rect = photos[code]
        extract(doc, pno, xref, rect, OUT / f"{code}.jpg", placements)
    for r, code in hits:
        r["image"] = f"img/lifefitness/{code}.jpg"
    RESOLVED.write_text(json.dumps(resolved, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    con = sqlite3.connect(DB)
    brand_ids = dict(con.execute("select name, id from brand").fetchall())
    uris = {code: inline(OUT / f"{code}.jpg") for _, code in hits}
    updated = 0
    for r, code in hits:
        cur = con.execute("update machine set image_url=? where brand_id=? and lower(trim(model))=lower(trim(?))",
                          (uris[code], brand_ids[r["brand"]], r["model"]))
        updated += cur.rowcount
    con.commit()
    print(f"\nwrote {len(uris)} photos to {OUT.relative_to(ROOT)}, attached {len(hits)} catalog rows, "
          f"updated {updated} DB rows")


if __name__ == "__main__":
    main()
