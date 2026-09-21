# Data sources

Where gym machine **model** data actually lives, ranked for building the catalog. No single
source has every model; the catalog is assembled from these and grown by users.

## Tier 1 — model-level, cross-brand (best for the catalog)

**Used / remanufactured equipment marketplaces.** Richest source: ~30 brands each, with a
per-model page (photo, name, specs) in a consistent structure. Ideal to scrape into
`brand / model / category / image`. Examples to evaluate: Fitness Superstore, Pro Gym Supply,
Fitness Equipment Empire, Primo Fitness. ⚠️ Check each site's robots.txt / ToS before scraping;
prefer official feeds where offered.

**Manufacturer catalogs.** Authoritative per brand.
- Life Fitness publishes a full PDF catalog covering Life Fitness + Hammer Strength + Cybex +
  ParaBody + SCIFIT (one company, post-consolidation). Shop is organized into model lines
  (Axiom, Insignia, Hammer Strength Select, MTS).
- Technogym product pages embed structured JSON in the HTML (`item_id`, `item_name`,
  `item_brand`, `item_category`) — scraper-friendly.
- Matrix, Precor, Hoist, etc. publish their own catalogs / spec sheets.

⚠️ Not every brand has one. Discontinued lines can have **no** digital record at all — see
`STAIRMASTER_ARCUATE.md` for a worked example and the fallback method (per-model listing scraping).

## Tier 2 — movement/exercise base layer (category-level, reuse don't rebuild)

- **ExerciseDB API** — open-source, 5,000–11,000+ exercises, self-hostable (Vercel/Supabase),
  `equipments` field, images/GIFs/instructions.
- **yuhonas/free-exercise-db** — 800+ public-domain exercises, clean JSON, `equipment` field.
  **Implemented**: `api/load_library.py` loads it into the `LibraryExercise` table (675 gym-
  relevant movements, grouped push/pull/legs/core, with images); served at `GET /library` and
  used as the default exercise options + search in the custom-workout builder.
- **wger** — open-source tracker (AGPL) with a REST API and equipment-tagged exercise wiki; good
  architectural precedent. Equipment is generic categories, not models.

## Tier 3 — niche / not useful for the catalog

- **Manufacturer APIs.** Life Fitness LFopen exposes workout/console telemetry, **not** a model
  catalog — doesn't solve "pick the machine in my gym".
- **Image-recognition datasets** (Kaggle, Roboflow, GitHub CNNs) — classify ~20–25 generic
  equipment *types*, not models. Possible future "point camera to identify machine" feature only.

## Chosen method (implemented) — Shopify `/products.json`

The commercial-equipment shops (`shop.lifefitness.com`, Fitness Superstore, Gym Pros, …) run on
**Shopify**, which exposes an official, structured product feed — no HTML scraping required:

```
https://<store>/products.json?limit=250&page=N           # whole store
https://<store>/collections/<handle>/products.json        # one collection
```

Each product gives `vendor` (brand), `title` (brand + model), `product_type` + `tags`
(mechanism + body region), and image URLs. `shop.lifefitness.com`'s robots.txt disallows
`/cart`, `/checkout` and sorted/filtered collection URLs but **not** `/collections/` or `*.json`.

## Chosen method (implemented) — WooCommerce Store API

The used/remanufactured marketplaces — the richest source (~30 brands each) — run on
**WooCommerce**, which exposes a public Store API:

```
https://<store>/wp-json/wc/store/v1/products?per_page=100&page=N
https://<store>/wp-json/wc/store/v1/products/categories
```

Each product gives `name` (brand + model), `categories` and `images`. There's no clean vendor
field, so the brand is recovered by `brands.extract_brand()` (a known-brand alias map; rows with
no known brand are skipped rather than mislabelled), and `brands.clean_model()` strips the heavy
marketing/condition noise. Implemented in `catalog/scrapers/woocommerce.py`. Note: some sites
(`progymsupply.com`) sit behind Cloudflare and return 403.

## Combined result (implemented)

Run via `catalog/build_catalog.py` across four stores — Shopify (`shop.lifefitness.com`,
`fitnesssuperstore.com`) + WooCommerce (`fitnessequipmentempire.com`, `primofitnessusa.com`) —
yielding **~1,100 machines across ~33 brands** (Cybex, Life Fitness, Hammer Strength, Precor,
Nautilus, Technogym, Hoist, Matrix, Star Trac, Muscle D, Atlantis, FreeMotion, Keiser, MedX, …),
89% auto-categorized. Add a source by appending one `ShopifyScraper(...)` / `WooCommerceScraper(...)`
line to `SOURCES`.

## Practical first step (done)

Pick **one** source, confirm its ToS allows it, pull the dominant brands, normalize to the
`machines` schema. That covers the vast majority of machines a user will stand in front of.
Everything else is crowdsourced per gym.

## Exercise illustrations (the library layer)

**Everkinetic** line-art exercise drawings, via
[chaosbastler/opentraining-exercises](https://github.com/chaosbastler/opentraining-exercises)
— **CC BY-SA 3.0**, credit "Everkinetic". ~170 movements (start/end poses, svg + png).
`api/everkinetic_images.py` token-matches these onto the free-exercise-db library exercises
(~97 matched); unmatched exercises keep their free-exercise-db photo. Attribution must be
shown in-app wherever these illustrations appear (BY-SA also makes derivatives share-alike).

## Manufacturer brochures recovered from the web (Sept 2026)

Marketplace listings (Fitness Equipment Empire, Primo, Fitness Superstore) ship ghosted
warehouse photos. Wherever an official brochure exists for the *same generation* we swap in
the manufacturer render. The generation rule is strict — a successor line's photo is the wrong
machine (Cybex Eagle ≠ Eagle NX, Precor Discovery ≠ Resolute, Muscle D Power Leverage ≠ V2).

| brand / line | file in `docs/` | origin | script |
|---|---|---|---|
| Cybex Eagle (11xxx) | `cybex-eagle-brochure.pdf` | kb.cybexintl.com/Product_Info/Eagle_Line.pdf (live) | `catalog/cybex_lines_images.py` |
| Cybex VR3 (12xxx), 23 pieces | `cybex-vr3-brochure-2007.pdf` | Wayback: cybexintl.com/Products/Data/Brochures/VR3_Brochure.pdf (2007-08) — page scan, photos cut out by column density | same |
| Cybex VR3 2006 (13 pieces, vector) | `cybex-vr3-brochure-2006.pdf` | Wayback, same path (2006-10) — kept as reference | — |
| Cybex VR2 / VR / Plate Loaded / FT 360 | `CYBEX Strength.pdf` | user-supplied | `catalog/cybex_strength_images.py` |
| Cybex VR1 (2013 scan) | `Cybey_V1.pdf` | user-supplied | `catalog/cybex_vr1_images.py` |
| Cybex Eagle NX 2014 | `cybex-eagle-nx-brochure-2014.pdf` | user-supplied | `catalog/cybex_nx_images.py` |
| Cybex Prestige VRS / Total Access / Bravo (2022 catalog) | `Cybex-Brochure_1649337819.pdf` | user-supplied | `catalog/brand_brochure_photos.py` |
| Technogym Selection / Element+ / Pure Strength | `technogym-strength-collection-2010.pdf` | Wayback: technogym.com/media/Files/0122_StrengthCollection_UK.pdf (2010-02) | `catalog/brand_brochure_photos.py` |
| Matrix Ultra / Versa / Aura | `matrix-strength-brochure-2021.pdf` | matrixmembers.nl (dealer mirror of the official 2021 brochure) | same |
| Precor Discovery Plate Loaded / Vitality | `precor-2020-catalog.pdf` | static.precor.com/catalog/Precor-2020-Catalog-ENG.pdf (live) | same |
| Precor Discovery Selectorized (DSL) | `Precor-2019-Catalog-ENG.pdf` | user-supplied; last catalog before Resolute replaced DSL | same |
| Precor Icarian (601, 320, 624, 603, 616, 550, 311, 202, 702, 802, 304, selectorized bicep/tricep/leg-ext/back-ext, 407B) | — (downloaded at run time) | Wayback: precor.com Magento image cache, July 2011 — Icarian never had an archived site of its own; most renders are 165 px | `catalog/precor_icarian_images.py` |
| Nautilus Nitro Plus (S5) | `nautilus-nitro-plus-brochure.pdf` | abirsport.co.il dealer mirror; identical copy on Wayback nautiluscommercial.com (2010) | same |
| Nautilus XPLoad (P3) | `nautilus-xpload-brochure.pdf` | Wayback: nautiluscommercial.com/xploadhome_htm_files/XPLOAD.pdf (2010-12) | same |
| Nautilus EVO (S9) | `nautilus-evo-brochure.pdf` | medicalfitsolutions.com dealer mirror | same |
| Nautilus ONE / NOVA / EVO / XPLoad / Freedom Trainer (55 new rows) | `Nautilus Strength Catalog.pdf` | user-supplied | `api/nautilus_lines_catalog.py` |
| Nautilus Nitro (S3, 25 pieces) | `nautilus-nitro-galerie.html` | user-built gallery of Wayback links to nautilus.com's own product renders (2007–08); the product pages were never archived, the images were | `catalog/nautilus_nitro_images.py` |
| Keiser Air 250 / 300 / Infinity | `keiser-catalog-2007.pdf` | Wayback: keiser.com/media/catalog_web.pdf (2007-02) | same |
| Life Fitness / Hammer Strength 2025 | `life-fitness-hammer-strength-2025-catalog.pdf` | user-supplied | `catalog/lifefitness_images.py` |
| Life Fitness Optima (OS*) + Signature Cable Motion / Multi-Jungle | `lifefitness_produktkatalog_2020.pdf` | user-supplied | `catalog/brand_brochure_photos.py` |
| Life Fitness Signature Series single stations (FZ*) + Pro2 (PS*SE) | `lifefitness-catalog-2015.pdf` | Wayback: lifefitness.com/static-assets/document/LF_product_catalogs/LF_DIGITAL_Spreads.pdf (2015-02) | same |
| Muscle D Power Leverage (MDP) + Classic MDC-1011A / Dual Function MDD-1008 / Free Weight MD-LPM, Smith | `muscledfitness.com_.pdf` | user-supplied print of the original muscledfitness.com Strength Equipment Catalog (page images only, no text layer — photos are hand-pinned crop rectangles) | `catalog/muscled_images.py` |
| StairMaster Arcuate / Linear (Pacific Fitness design; 11 renders + 4 new Linear rows) | — (downloaded at run time) | Wayback: stairmaster.com/commercial/products/strength/ (2001–02), /Images/Product/arcuate*.jpg, linearline*.jpg — the Seated Row image was never captured | `catalog/stairmaster_wayback_images.py` |
| Brightway Power Series (BF/BH/HS/TY pin-loaded, BL/PL/PS/TM/TN/TB plate-loaded; 263 machines) | — (fetched at run time) | www.brtwfitness.com — the page's own AJAX product feed (POST /ajax/products, category 60) with 1000 px renders; benches, racks, jungles skipped | `api/brightway_catalog.py` |
| Paramount SP Circuit | `catalog_sp.pdf` | user-supplied | `api/paramount_catalog.py` |

Still open (no same-generation source found yet): Precor Discovery *Selectorized* (DSL, needs the
2014–2018 Precor catalog), Life Fitness Signature selectorized / Pro 2 / Optima, Nautilus Nitro
(pre-Plus) and the vintage 2ST / Gen-1 pieces, Cybex Prestige / Classic / Galileo / Bravo,
Muscle D Elite Leverage (L*** plate-loaded line; the catalog's "Elite Line" is the unrelated selectorized MDE range), Flex Fitness, Body Masters.
Wayback tip: `web.archive.org/cdx/search/cdx?url=<domain>*&filter=mimetype:application/pdf` lists
every archived PDF; fetch with `web.archive.org/web/<timestamp>id_/<url>` to get the raw file.
