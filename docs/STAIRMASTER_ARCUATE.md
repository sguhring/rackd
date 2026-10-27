# StairMaster Arcuate — source research

Research note on the **StairMaster Arcuate** strength line (late 1990s, discontinued). Written up
because it is the first brand we've hit with a **zero digital footprint** — no catalog, no manual,
no spec sheet anywhere online. It's the clearest case yet for why the catalog has to be assembled
and crowdsourced rather than fetched (see `DATA_SOURCES.md`, and the moat argument in `CLAUDE.md`).

Every other brand in `docs/` arrived as a single PDF (Panatta, Prime, Watson, gym80, Arsenal,
Booty Builder, Megamass, Newtech, Strive). Arcuate has no such PDF. This documents what was
searched, what actually exists, and how to build the entries anyway.

## The dead end (searched Aug 2026 — do not repeat)

No Arcuate catalog, brochure, owner's manual, spec sheet, or parts diagram exists online.
Checked and came up empty:

| Source | Result |
|---|---|
| Sportsmith (`sportsmith.net/images/product_support/stairmaster/`) | cardio manuals only |
| ManualsLib, device.report, manualzz, manualsbase | cardio only |
| Fitness Superstore manual download center (112 docs) | cardio only |
| Internet Archive — full StairMaster holdings | cardio only, no catalog/brochure |
| Core Health & Fitness current catalog | modern cardio/HIIT lineup, no legacy strength |
| `fitnessrepairparts.com` model pages | parts lists, **no** diagrams or PDFs |

Everything StairMaster that has been digitised is cardio: 4000/4200/4400/4600 PT, FreeClimber,
StepMill 5 / 7000, Gauntlet, HIIT bike. The strength lines were never scanned by anyone.

**Update Sept 2026 — the Wayback lead paid off.** `stairmaster.com` (2001–02) has a product page per
machine under `commercial/products/strength/arcuate/` and `/linear/`, with the official render in
`/Images/Product/`. 11 of 12 survive (300 px, or the 200 px `_sm` thumbnail); the **Arcuate Seated Row**
page is archived but its image was never captured. Recovered by `catalog/stairmaster_wayback_images.py`,
which also adds the four Linear machines the model list below lacked (Lower Back, Outer Thigh, Seated
Leg Curl, Total Glute). The line was designed with Pacific Fitness (StairMaster partnered with them for
strength in 1996; Precor bought Pacific Fitness in 1998, whose site then only carried home gyms).

## What does exist — the model list

Recovered from [fitnessrepairparts.com](https://www.fitnessrepairparts.com/m/brand/View/8/StairMaster),
which still stocks replacement parts per machine. Because each has a live parts page, the factory
model codes are **confirmed**, not inferred.

### Arcuate line — plate-stack, curved motion path

| Code | Model |
|---|---|
| ABC | Arcuate Bicep Curl |
| ACP | Arcuate Chest Press |
| AIP | Arcuate Incline Press |
| ALT | Arcuate Lat Pull |
| ALP | Arcuate Leg Press |
| ASR | Arcuate Seated Row |
| ASP | Arcuate Shoulder Press |
| ATP | Arcuate Tricep Press |

### Linear line — the sibling range

| Code | Model |
|---|---|
| NAB | Linear Ab Torso |
| NFD | Linear Fly / Deltoid |
| NIT | Linear Inner Thigh |
| NLE | Linear Leg Extension |

Both are listed by the parts supplier under category **Strength — Multi Station**.

### Confidence notes

- **Model codes + names** — high confidence, sourced from live parts inventory.
- **12 models** is a floor, not a ceiling. Period trade press describes StairMaster strength as
  "the Gravitron 2000 AT and the new Arcuate and Linear lines" totalling **17 products**, so
  roughly 4–5 models are still unaccounted for — most likely more Linear entries.
- **Manufacture** — Tri-Tech, Inc. of Tulsa, Oklahoma. Line promoted ~1997–1999, catalog then
  offered only as a physical mailer via a 1-800 number, which is almost certainly why nothing
  was ever digitised.
- The `ACP` parts page is titled "Arcuate **Chess** Press" — a supplier typo for Chest Press.
  Normalize on ingest.

## Verified specimen — Arcuate Bicep Curl (ABC)

The one machine with a full, photographed listing:
[recycledgoods.com](https://www.recycledgoods.com/stairmaster-arcuate-bicep-curl-arcuate-bicep-curl-station/)

| Field | Value |
|---|---|
| Resistance | plate stack, 5–150 lb |
| Dimensions | 58"L × 40"W × 58"H |
| Weight | 600 lb |
| Frame | white |
| Upholstery | black pads |
| Photos | 4 × 1280px, clean, multiple angles |

Useful as the reference for the line's visual identity: **white frame, black pads** — which is
how a user will recognise these on a gym floor, and matches the machine that started this
(an ASR seated row, German-labelled "ARCUATE RUDERMASCHINE", so the line was sold in Europe too).

The 5–150 lb stack is worth noting for the per-machine progression model: a light top end by
modern standards, so users on these will cap out sooner than on a current machine. Another
argument for never comparing loads across models (`CLAUDE.md`, point 3).

## How to build the entries

The Strive workflow — **PDF → `catalog/strive_images/` → `machines_resolved.json`** — does not
apply here. There is no source PDF. The Arcuate equivalent is per-model listing scraping:

1. Seed the 12 known models into `machines_resolved.json` with brand `StairMaster`, using the
   codes above. Photos are the only missing field.
2. Pull photos per model from resale listings. Ranked by promise:
   - [recycledgoods.com](https://www.recycledgoods.com) — BigCommerce, 1280px images, real specs.
     Confirmed to carry Arcuate. Best target.
   - [preownedgym.com](https://preownedgym.com/brands/stairmaster/) — keeps a photo archive of
     equipment it has sold, including discontinued lines.
   - [fitnessmarkt.com](https://www.fitnessmarkt.com/article?brand=stairmaster) — European
     listings; Arcuate units keep surfacing on German classifieds specifically.
3. ⚠️ `hydrafitnessexchange.com` and `sportsmith.com` both return **403** to automated fetches
   (Cloudflare) — same failure mode as `progymsupply.com` noted in `DATA_SOURCES.md`.
4. Check each site's robots.txt / ToS first. Neither BigCommerce nor these listing sites expose
   the clean Shopify `/products.json` or WooCommerce Store API feeds we rely on elsewhere, so
   this is genuine HTML scraping — the exception, not the pattern.

## Open leads

- **Wayback Machine** — `stairmaster.com` 1998–2002. Untested from here; needs a client that can
  reach `web.archive.org`. Highest-value remaining lead by far, since a period product page would
  give both the missing models and official photography.
- **Core Health & Fitness** — current owner of the StairMaster brand. A direct request for legacy
  strength documentation is cheap and might surface an internal scan.
- **Vintage equipment collectors / dealers** — the physical brochures exist in the world; nobody
  has scanned one.

## Why this note exists

This is the shape of the problem the app is betting on. A machine that is physically present in
a gym today, that a user wants to log sets against, and that the internet has **no record of**.
No amount of scraping fixes that — only a user standing in front of it, adding it. Arcuate is the
worked example to point at when explaining the crowdsourcing layer.
